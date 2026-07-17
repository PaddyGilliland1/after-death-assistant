"""Knowledge ingestion pipeline: fetch -> extract -> chunk -> embed -> store.

Hash-diff behaviour (PROCESSES.md section 4):
- unchanged content: no new version; the skip is logged and reported;
- changed content: version + 1, chunks replaced, "changed" flagged in the
  report so tax constants and process steps get reviewed.

Every stored document records its licence (Open Government Licence
attribution) and provenance: source URL, fetch date, sha256 content hash
and the object-storage key of the raw fetched file. Every write emits an
estate-scoped audit event.

Tests never fetch the network: they pass a fake `fetcher` coroutine (see
app/ingest/fetcher.build_fetch_result).
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.chunker import chunk_text
from app.ingest.embedder import EmbeddingProvider, get_embedding_provider
from app.ingest.extractor import extract_text
from app.ingest.fetcher import FetchResult, fetch_url
from app.ingest.registry import RegistrySource
from app.models import KnowledgeChunk, KnowledgeDoc
from app.models.base import utcnow
from app.schemas.knowledge import IngestReport
from app.schemas.registers import snapshot
from app.services.seeding import record_audit
from app.services.storage import StorageBackend, get_storage

logger = logging.getLogger(__name__)

FetchFn = Callable[[str], Awaitable[FetchResult]]


GUIDE_PART_LIMIT = 20


def _guide_part_urls(url: str, content: bytes, content_type: str) -> list[str]:
    """Same-guide sub-page URLs from a gov.uk multi-page guide landing page.

    gov.uk splits guides like /paying-inheritance-tax across part pages
    (/paying-inheritance-tax/yearly-instalments and so on). Ingesting only
    the landing page silently loses most of the guidance, so links whose
    path sits directly under the source path are treated as parts of the
    same document. Non-gov.uk sources and non-HTML content return nothing.
    """
    normalised = (content_type or "").split(";")[0].strip().lower()
    if "gov.uk" not in url or "html" not in normalised:
        return []
    from urllib.parse import urljoin, urlparse

    from bs4 import BeautifulSoup

    base_path = urlparse(url).path.rstrip("/")
    if not base_path:
        return []
    soup = BeautifulSoup(content, "html.parser")
    parts: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(url, anchor["href"].split("#")[0])
        parsed = urlparse(href)
        if parsed.netloc and "gov.uk" not in parsed.netloc:
            continue
        path = parsed.path.rstrip("/")
        if not path.startswith(base_path + "/"):
            continue
        remainder = path[len(base_path) + 1 :]
        if not remainder or "/" in remainder:
            continue
        if href not in parts:
            parts.append(href)
    return parts[:GUIDE_PART_LIMIT]


async def _guide_text(
    url: str, result: FetchResult, fetcher: FetchFn
) -> str:
    """Extracted text of the landing page plus any guide part pages.

    Part fetch failures are logged and skipped; the landing page alone is
    never lost. Versioning note: the stored content_hash is the landing
    page's, so a change to a part page alone does not trigger a new
    version until the landing page changes or a forced re-ingest runs.
    """
    text = extract_text(result.content, result.content_type)
    for part_url in _guide_part_urls(url, result.content, result.content_type):
        try:
            part = await fetcher(part_url)
            part_text = extract_text(part.content, part.content_type)
        except Exception as exc:  # noqa: BLE001 - a bad part must not kill the doc
            logger.warning("Guide part fetch failed for %s: %s", part_url, exc)
            continue
        text = f"{text}\n\n{part_text}"
    return text


def _storage_suffix(content_type: str) -> str:
    normalised = (content_type or "").split(";")[0].strip().lower()
    if "pdf" in normalised:
        return ".pdf"
    if "html" in normalised:
        return ".html"
    return ".txt"


def _chunk_db_text(heading: str | None, text: str) -> str:
    """Store the heading context inline so full-text search can use it."""
    return f"{heading}\n{text}" if heading else text


async def _existing_doc(
    session: AsyncSession, estate_id: uuid.UUID, source_url: str
) -> KnowledgeDoc | None:
    result = await session.execute(
        select(KnowledgeDoc)
        .where(KnowledgeDoc.estate_id == estate_id)
        .where(KnowledgeDoc.source_url == source_url)
        .where(KnowledgeDoc.archived_at.is_(None))
        .order_by(KnowledgeDoc.created_at)
        .limit(1)
    )
    return result.scalars().first()


async def ingest(
    session: AsyncSession,
    source: RegistrySource,
    *,
    estate_id: uuid.UUID,
    actor: str = "system",
    fetcher: FetchFn | None = None,
    provider: EmbeddingProvider | None = None,
    storage: StorageBackend | None = None,
    force: bool = False,
) -> IngestReport:
    """Ingest one registry source into knowledge_doc + knowledge_chunk.

    Commits on success so a long run keeps its progress per source.
    Fetch or processing failures are reported, never raised.
    """
    fetcher = fetcher or fetch_url
    if provider is None:
        from app.services.app_settings import embeddings_enabled

        if await embeddings_enabled(session):
            provider = get_embedding_provider()
        else:
            from app.ingest.embedder import NoneProvider

            provider = NoneProvider()
    storage = storage or get_storage()

    try:
        result = await fetcher(source.url)
    except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
        logger.warning("Fetch failed for %s (%s): %s", source.key, source.url, exc)
        return IngestReport(
            source_key=source.key, url=source.url, status="error", detail=str(exc)
        )

    existing = await _existing_doc(session, estate_id, source.url)
    if not force and existing is not None and existing.content_hash == result.content_hash:
        logger.info(
            "Skipping %s: content unchanged (hash %s, version %s)",
            source.key,
            result.content_hash[:12],
            existing.version,
        )
        return IngestReport(
            source_key=source.key,
            url=source.url,
            status="unchanged",
            doc_id=existing.id,
            version=existing.version,
            detail="Content hash unchanged; no new version stored.",
        )

    try:
        text = await _guide_text(source.url, result, fetcher)
        chunks = chunk_text(text)
        vectors = provider.embed_texts([chunk.text for chunk in chunks]) if chunks else None
        if vectors is not None and len(vectors) != len(chunks):
            raise ValueError(
                f"Embedding provider returned {len(vectors)} vectors for {len(chunks)} chunks"
            )
        raw_file_key = storage.save(result.content, suffix=_storage_suffix(result.content_type))
    except NotImplementedError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Processing failed for %s (%s): %s", source.key, source.url, exc)
        return IngestReport(
            source_key=source.key, url=source.url, status="error", detail=str(exc)
        )

    if existing is None:
        doc = KnowledgeDoc(
            estate_id=estate_id,
            source_url=source.url,
            title=source.title,
            form_code=source.form_code,
            topic=source.topic,
            jurisdiction=source.jurisdiction,
            fetch_date=result.fetched_at.date(),
            content_hash=result.content_hash,
            version=1,
            licence=source.licence,
            raw_file_key=raw_file_key,
            extracted_text=text,
            created_by=actor,
        )
        session.add(doc)
        await session.flush()
        action, status, changed = "create", "ingested", False
        before = None
    else:
        doc = existing
        before = snapshot(doc)
        doc.title = source.title
        doc.form_code = source.form_code
        doc.topic = source.topic
        doc.jurisdiction = source.jurisdiction
        doc.fetch_date = result.fetched_at.date()
        doc.content_hash = result.content_hash
        doc.version = doc.version + 1
        doc.licence = source.licence
        doc.raw_file_key = raw_file_key
        doc.extracted_text = text
        doc.updated_at = utcnow()
        # Replace the retrieval chunks: they are derived data, rebuilt from
        # the stored document on every version (contract section 10).
        await session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.knowledge_doc_id == doc.id)
        )
        action, status, changed = "update", "changed", True
        logger.info(
            "Source changed: %s now version %s (hash %s)",
            source.key,
            doc.version,
            result.content_hash[:12],
        )

    for position, chunk in enumerate(chunks):
        session.add(
            KnowledgeChunk(
                estate_id=estate_id,
                knowledge_doc_id=doc.id,
                chunk_index=chunk.index,
                text=_chunk_db_text(chunk.heading, chunk.text),
                embedding=vectors[position] if vectors is not None else None,
                created_by=actor,
            )
        )

    await record_audit(
        session,
        estate_id,
        actor,
        action,
        f"knowledge_doc:{doc.id}",
        before=before,
        after=snapshot(doc),
    )
    await session.commit()

    return IngestReport(
        source_key=source.key,
        url=source.url,
        status=status,
        changed=changed,
        doc_id=doc.id,
        version=doc.version,
        chunk_count=len(chunks),
    )


async def ingest_sources(
    session: AsyncSession,
    sources: list[RegistrySource],
    *,
    estate_id: uuid.UUID,
    actor: str = "system",
    fetcher: FetchFn | None = None,
    provider: EmbeddingProvider | None = None,
    storage: StorageBackend | None = None,
    force: bool = False,
) -> list[IngestReport]:
    """Run the pipeline over a list of sources, one report per source."""
    reports: list[IngestReport] = []
    for source in sources:
        reports.append(
            await ingest(
                session,
                source,
                force=force,
                estate_id=estate_id,
                actor=actor,
                fetcher=fetcher,
                provider=provider,
                storage=storage,
            )
        )
    return reports

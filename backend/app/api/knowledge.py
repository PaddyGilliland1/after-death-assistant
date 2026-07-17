"""Knowledge library router (Module 10, contract sections 8 and 10).

- GET  /knowledge/search    hybrid retrieval: Postgres full text (always)
                            plus pgvector cosine when embeddings exist,
                            merged with reciprocal rank fusion. Read role.
- GET  /knowledge/docs      document metadata; /docs/{id} adds the text.
- POST /knowledge/ingest    admin only: FETCHES THE INTERNET, runs the
                            pipeline over the registry (or a named
                            subset) and is audited.
- POST /knowledge/qa        read role: cited Q&A over the cached corpus
                            only. Refuses beyond the sources, never
                            computes figures, guidance not advice.

Every hit and QA source returns its licence and source URL so Open
Government Licence attribution travels with every answer.
"""

import logging
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AdminUser, ReadUser
from app.core.config import Settings, get_settings
from app.db import get_session
from app.ingest import fetcher as fetcher_module
from app.ingest.embedder import get_embedding_provider
from app.ingest.pipeline import ingest_sources
from app.ingest.registry import load_registry
from app.models import KnowledgeChunk, KnowledgeDoc
from app.schemas.knowledge import (
    IngestReport,
    IngestRequest,
    KnowledgeDocDetail,
    KnowledgeDocRead,
    QARequest,
    QAResponse,
    QASource,
    SearchHit,
)
from app.services.seeding import get_active_estate, record_audit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

RRF_K = 60
QA_TOP_CHUNKS = 8
QA_MODEL = "claude-sonnet-5"

REFUSAL_TEXT = (
    "I am sorry, but the guidance held in the knowledge library does not "
    "cover that question. Please check the source documents on gov.uk or "
    "speak to a qualified professional."
)

GUIDANCE_NOTE = "This is guidance drawn from the cited sources, not legal or tax advice."

_QA_SYSTEM_PROMPT = f"""You are the knowledge assistant of an estate administration tool \
for England and Wales. You answer questions using ONLY the numbered extracts supplied \
in the user message. Follow these rules exactly:
1. Use only the supplied extracts. Never use outside knowledge.
2. Cite every claim with the number of the extract that supports it, in square \
brackets, for example [1] or [2][3]. Every citation number must exist in the extracts.
3. If no part of the question is covered by the extracts, reply with exactly this \
sentence and nothing else: "{REFUSAL_TEXT}"
3a. If the extracts cover only part of the question, answer the covered part with \
citations, then ALWAYS close with a clearly separated section headed exactly \
"What the library does not cover:" listing plainly, in one short paragraph or \
bullet list, each part of the question the extracts do not answer. This section \
is mandatory whenever coverage is partial and comes just before the final \
guidance note.
4. Never calculate, estimate or derive a figure. You may only repeat a figure that \
appears verbatim in an extract, with its citation.
5. End every answer (except a refusal) with exactly: "{GUIDANCE_NOTE}"
6. When an extract uses its own internal numbering or labels (for example \
"Step 6" of a wider guide, or a numbered form box), attribute the label to the \
CITED document by its extract title, for example: the "Applying for probate" \
page, which is Step 6 of gov.uk's wider what-to-do process [3]. Never leave a \
bare label like (Step 6), and never present a document name as a source unless \
it is one of the numbered extracts; a parent guide mentioned inside an extract \
must be clearly anchored to the numbered extract that mentions it.
7. Write in UK English. Do not use em dashes."""


# ---------------------------------------------------------------------------
# Seams for tests: the query embedder and the LLM call are module-level so
# they can be monkeypatched; _fetch is the single place the internet is
# reached from this router (admin-gated ingest only).
# ---------------------------------------------------------------------------

_fetch = fetcher_module.fetch_url


def _embed_query(question: str) -> list[float] | None:
    """Embed the query, or None when embeddings are switched off."""
    vectors = get_embedding_provider().embed_texts([question])
    return vectors[0] if vectors else None


def _call_llm(system_prompt: str, user_prompt: str, settings: Settings) -> str:
    """Single seam for the Claude call (monkeypatched in tests)."""
    from langchain_anthropic import ChatAnthropic

    model = ChatAnthropic(
        model=QA_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=2048,
        timeout=60,
    )
    response = model.invoke([("system", system_prompt), ("human", user_prompt)])
    content = response.content
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)


# ---------------------------------------------------------------------------
# Hybrid retrieval
# ---------------------------------------------------------------------------


async def _fts_rows(
    session: AsyncSession, estate_id: uuid.UUID, q: str, limit: int
) -> list[tuple[KnowledgeChunk, KnowledgeDoc]]:
    """Full-text rows for the query.

    websearch_to_tsquery ANDs every term, which is right for keyword
    searches but returns nothing for conversational questions ("when does
    inheritance tax have to be paid...?"). When the strict query finds
    nothing, fall back to reciprocal rank fusion over per-term lists: a
    chunk matching a rare term (top of that term's list) outranks one
    that merely repeats common terms, which plain ts_rank over one ORed
    query does not achieve.
    """
    strict = func.websearch_to_tsquery("english", q)
    rows = await _fts_rows_for_tsquery(session, estate_id, strict, limit)
    if rows:
        return rows
    words = list(
        dict.fromkeys(
            w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9-]+", q) if len(w) > 2
        )
    )[:8]
    if not words:
        return []
    scores: dict[uuid.UUID, float] = {}
    found: dict[uuid.UUID, tuple[KnowledgeChunk, KnowledgeDoc]] = {}
    for word in words:
        term_rows = await _fts_rows_for_tsquery(
            session, estate_id, func.to_tsquery("english", word), limit
        )
        for position, (chunk, doc) in enumerate(term_rows):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (RRF_K + position + 1)
            found.setdefault(chunk.id, (chunk, doc))
    ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:limit]
    return [found[cid] for cid in ordered]


async def _fts_rows_for_tsquery(
    session: AsyncSession, estate_id: uuid.UUID, tsquery, limit: int
) -> list[tuple[KnowledgeChunk, KnowledgeDoc]]:
    tsvector = func.to_tsvector("english", KnowledgeChunk.text)
    stmt = (
        select(KnowledgeChunk, KnowledgeDoc)
        .join(KnowledgeDoc, KnowledgeChunk.knowledge_doc_id == KnowledgeDoc.id)
        .where(KnowledgeChunk.estate_id == estate_id)
        .where(KnowledgeChunk.archived_at.is_(None))
        .where(KnowledgeDoc.archived_at.is_(None))
        .where(tsvector.op("@@")(tsquery))
        .order_by(func.ts_rank(tsvector, tsquery).desc(), KnowledgeChunk.id)
        .limit(limit)
    )
    return [(row[0], row[1]) for row in (await session.execute(stmt)).all()]


async def _vector_rows(
    session: AsyncSession, estate_id: uuid.UUID, query_vector: list[float], limit: int
) -> list[tuple[KnowledgeChunk, KnowledgeDoc]]:
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(KnowledgeChunk, KnowledgeDoc)
        .join(KnowledgeDoc, KnowledgeChunk.knowledge_doc_id == KnowledgeDoc.id)
        .where(KnowledgeChunk.estate_id == estate_id)
        .where(KnowledgeChunk.archived_at.is_(None))
        .where(KnowledgeDoc.archived_at.is_(None))
        .where(KnowledgeChunk.embedding.is_not(None))
        .order_by(distance, KnowledgeChunk.id)
        .limit(limit)
    )
    return [(row[0], row[1]) for row in (await session.execute(stmt)).all()]


def _to_hit(chunk: KnowledgeChunk, doc: KnowledgeDoc, score: float) -> SearchHit:
    return SearchHit(
        doc_id=doc.id,
        doc_title=doc.title,
        form_code=doc.form_code,
        source_url=doc.source_url,
        licence=doc.licence,
        fetch_date=doc.fetch_date,
        chunk_text=chunk.text,
        chunk_index=chunk.chunk_index,
        score=score,
    )


async def hybrid_search(
    session: AsyncSession, estate_id: uuid.UUID, q: str, limit: int
) -> list[SearchHit]:
    """Full-text always; cosine when a query embedding exists; RRF merge."""
    pool = max(limit * 2, limit)
    ranked_lists = [await _fts_rows(session, estate_id, q, pool)]

    query_vector = _embed_query(q)
    if query_vector is not None:
        ranked_lists.append(await _vector_rows(session, estate_id, query_vector, pool))

    scores: dict[uuid.UUID, float] = {}
    rows: dict[uuid.UUID, tuple[KnowledgeChunk, KnowledgeDoc]] = {}
    for ranked in ranked_lists:
        for position, (chunk, doc) in enumerate(ranked):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (RRF_K + position + 1)
            rows.setdefault(chunk.id, (chunk, doc))

    best = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [_to_hit(*rows[chunk_id], score=round(score, 6)) for chunk_id, score in best]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/search", response_model=list[SearchHit])
async def search_knowledge(
    session: SessionDep,
    user: ReadUser,
    q: Annotated[str, Query(min_length=2, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[SearchHit]:
    estate = await get_active_estate(session)
    if estate is None:
        return []
    return await hybrid_search(session, estate.id, q, limit)


@router.get("/docs", response_model=list[KnowledgeDocRead])
async def list_docs(session: SessionDep, user: ReadUser) -> list[KnowledgeDoc]:
    estate = await get_active_estate(session)
    if estate is None:
        return []
    stmt = (
        select(KnowledgeDoc)
        .where(KnowledgeDoc.estate_id == estate.id)
        .where(KnowledgeDoc.archived_at.is_(None))
        .order_by(KnowledgeDoc.title, KnowledgeDoc.id)
    )
    return list((await session.execute(stmt)).scalars().all())


@router.get("/docs/{doc_id}", response_model=KnowledgeDocDetail)
async def get_doc(doc_id: uuid.UUID, session: SessionDep, user: ReadUser) -> KnowledgeDoc:
    doc = await session.get(KnowledgeDoc, doc_id)
    if doc is None or doc.archived_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge document not found.")
    return doc


@router.post("/ingest", response_model=list[IngestReport])
async def run_ingest(
    payload: IngestRequest, session: SessionDep, user: AdminUser
) -> list[IngestReport]:
    """Fetch and ingest the registry sources. Admin only: this endpoint
    reaches the internet. The run and every document write are audited."""
    estate = await get_active_estate(session)
    if estate is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No active estate; seed the estate first."
        )

    registry = load_registry()
    not_found: list[IngestReport] = []
    if payload.source_keys:
        by_key = {source.key: source for source in registry}
        selected = []
        for key in payload.source_keys:
            source = by_key.get(key)
            if source is None:
                not_found.append(
                    IngestReport(
                        source_key=key,
                        url="",
                        status="not_found",
                        detail="Not in the source registry (or its URL is unresolved).",
                    )
                )
            else:
                selected.append(source)
    else:
        selected = registry

    reports = await ingest_sources(
        session,
        selected,
        estate_id=estate.id,
        actor=user.email,
        fetcher=_fetch,
        force=payload.force,
    )
    reports.extend(not_found)

    await record_audit(
        session,
        estate.id,
        user.email,
        "ingest_run",
        "knowledge_registry",
        after={"reports": [report.model_dump(mode="json") for report in reports]},
    )
    await session.commit()
    return reports


@router.post("/qa", response_model=QAResponse)
async def knowledge_qa(payload: QARequest, session: SessionDep, user: ReadUser) -> QAResponse:
    """Cited Q&A over the cached corpus only (read role)."""
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY.strip():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Knowledge Q&A is unavailable: ANTHROPIC_API_KEY is not configured. "
            "Search and the document viewer remain available.",
        )

    estate = await get_active_estate(session)
    hits = (
        await hybrid_search(session, estate.id, payload.question, QA_TOP_CHUNKS)
        if estate is not None
        else []
    )
    if not hits:
        return QAResponse(answer=REFUSAL_TEXT, sources=[], refused=True)

    # One numbered source per DOCUMENT, not per chunk: several chunks of
    # the same page share a number, so the reader never sees the same
    # title listed four times with different numbers.
    doc_numbers: dict[uuid.UUID, int] = {}
    sources = []
    for hit in hits:
        if hit.doc_id not in doc_numbers:
            doc_numbers[hit.doc_id] = len(doc_numbers) + 1
            sources.append(
                QASource(
                    n=doc_numbers[hit.doc_id],
                    doc_title=hit.doc_title,
                    source_url=hit.source_url,
                    form_code=hit.form_code,
                )
            )
    extracts = "\n\n".join(
        f"[{doc_numbers[hit.doc_id]}] From \"{hit.doc_title}\" "
        f"({hit.source_url}):\n{hit.chunk_text}"
        for hit in hits
    )
    user_prompt = f"Extracts:\n\n{extracts}\n\nQuestion: {payload.question}"

    answer = _call_llm(_QA_SYSTEM_PROMPT, user_prompt, settings)
    refused = REFUSAL_TEXT in answer
    return QAResponse(answer=answer, sources=[] if refused else sources, refused=refused)

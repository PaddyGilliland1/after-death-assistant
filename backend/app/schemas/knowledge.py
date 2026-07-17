"""Pydantic schemas for the knowledge library API (Module 10).

Every search hit and QA source carries provenance (source URL, licence,
fetch date) so Open Government Licence attribution is returned with every
answer (build contract guardrail 3).
"""

import datetime as dt
import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocRead(BaseModel):
    """Document metadata (no extracted text)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    estate_id: uuid.UUID
    source_url: str
    title: str
    form_code: str | None
    topic: str | None
    jurisdiction: str | None
    fetch_date: dt.date | None
    content_hash: str | None
    version: int
    licence: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class KnowledgeDocDetail(KnowledgeDocRead):
    """Document metadata plus the full extracted text for the viewer."""

    extracted_text: str | None


class SearchHit(BaseModel):
    """One hybrid-retrieval hit, always attributed to its source."""

    doc_id: uuid.UUID
    doc_title: str
    form_code: str | None
    source_url: str
    licence: str | None
    fetch_date: dt.date | None
    chunk_text: str
    chunk_index: int
    score: float


class IngestRequest(BaseModel):
    """Body for POST /knowledge/ingest: all sources, or a named subset."""

    force: bool = Field(
        default=False,
        description="Re-ingest even when the landing page hash is unchanged "
        "(guide part pages are not covered by the hash).",
    )

    source_keys: list[str] | None = None


IngestStatus = Literal["ingested", "unchanged", "changed", "error", "not_found"]


class IngestReport(BaseModel):
    """Per-source outcome of an ingestion run."""

    source_key: str
    url: str
    status: IngestStatus
    changed: bool = False
    doc_id: uuid.UUID | None = None
    version: int | None = None
    chunk_count: int = 0
    detail: str | None = None


class QARequest(BaseModel):
    """Body for POST /knowledge/qa."""

    question: str = Field(min_length=3, max_length=2000)


class QASource(BaseModel):
    """A numbered source backing a citation [n] in the answer."""

    n: int
    doc_title: str
    source_url: str
    form_code: str | None
    licence: str | None = None
    fetch_date: date | None = None
    relation: Literal["direct", "referenced"] = "direct"


class QAResponse(BaseModel):
    """Cited, guidance-only answer over the cached corpus."""

    answer: str
    sources: list[QASource]
    refused: bool

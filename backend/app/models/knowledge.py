"""Knowledge library: cached guidance documents and their embedded chunks.

Sources are public gov.uk pages and published PDFs cached with provenance
(source URL, fetch date, content hash). Chunks carry pgvector embeddings
(dimension 1024) for cosine retrieval alongside Postgres full-text search.
"""

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Text
from sqlmodel import Field

from .base import EstateScopedBase


class KnowledgeDoc(EstateScopedBase, table=True):
    """A cached guidance document with provenance (contract section 6)."""

    __tablename__ = "knowledge_doc"

    source_url: str = Field(default="", index=True)
    title: str = Field(default="", index=True)
    form_code: str | None = Field(
        default=None, index=True, description="e.g. IHT400, IHT435"
    )
    topic: str | None = Field(default=None)
    jurisdiction: str | None = Field(default=None)
    fetch_date: dt.date | None = Field(default=None)
    content_hash: str | None = Field(
        default=None, description="Hash of the fetched content for change detection"
    )
    version: int = Field(default=1)
    licence: str | None = Field(
        default=None, description="e.g. Open Government Licence v3.0"
    )
    raw_file_key: str | None = Field(
        default=None, description="Object storage key for the raw fetched file"
    )
    extracted_text: str | None = Field(default=None, sa_type=Text)


class KnowledgeChunk(EstateScopedBase, table=True):
    """A retrievable chunk of a knowledge document with its embedding."""

    __tablename__ = "knowledge_chunk"

    knowledge_doc_id: uuid.UUID = Field(
        foreign_key="knowledge_doc.id", index=True, nullable=False
    )
    chunk_index: int = Field(
        default=0, description="Position of the chunk within the document"
    )
    text: str = Field(default="", sa_type=Text)
    embedding: Any | None = Field(
        default=None,
        sa_column=Column(Vector(1024), nullable=True),
        description="pgvector embedding, dimension 1024",
    )

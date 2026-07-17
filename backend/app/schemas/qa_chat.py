"""Schemas for the knowledge chat (conversational, cited Q&A)."""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    question: str = Field(min_length=3, max_length=2000)


class ChatSource(BaseModel):
    """A source shown with an answer.

    Sources cited in the body carry their number and the exact passages
    the API attributed to them; sources retrieved but not cited have no
    number and are listed separately as related sources.
    """

    n: int | None = None
    doc_title: str
    source_url: str
    licence: str | None = None
    fetch_date: dt.date | None = None
    quotes: list[str] = Field(default_factory=list)
    relation: Literal["retrieved", "pinned"] = "retrieved"


class ChatMessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    sources_cited: list[ChatSource] = Field(default_factory=list)
    related_sources: list[ChatSource] = Field(default_factory=list)
    created_at: dt.datetime


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message: ChatMessageOut


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: dt.datetime
    updated_at: dt.datetime

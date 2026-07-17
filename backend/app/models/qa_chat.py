"""Knowledge chat: conversations, messages and the pinned-context register.

The chat replaces the one-shot Q&A. Three tables:

- qa_conversation: one thread per topic of questions, per estate.
- qa_message: every turn (user question or assistant answer). Assistant
  rows carry the structured citation data returned by the model API so
  the sources can be re-rendered faithfully at any time.
- qa_pinned_snippet: the context harness. Whenever the assistant cites a
  passage, that passage is pinned to the conversation and re-supplied to
  the model on every later turn, so topics already discussed stay
  answerable and citable even after older messages fall out of the
  replayed history.
"""

import uuid

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field

from app.models.base import EstateScopedBase


class QaConversation(EstateScopedBase, table=True):
    __tablename__ = "qa_conversation"

    title: str = Field(description="Short title, taken from the first question")
    summary: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Rolling summary of turns no longer replayed in full",
    )


class QaMessage(EstateScopedBase, table=True):
    __tablename__ = "qa_message"

    conversation_id: uuid.UUID = Field(foreign_key="qa_conversation.id", index=True)
    role: str = Field(description="user or assistant")
    content: str = Field(
        sa_column=Column(Text),
        description="The message text; assistant text includes [n] markers",
    )
    sources_cited: list | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Numbered sources cited in the body, with their quotes",
    )
    related_sources: list | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Sources retrieved for the turn but not cited in the body",
    )


class QaPinnedSnippet(EstateScopedBase, table=True):
    __tablename__ = "qa_pinned_snippet"

    conversation_id: uuid.UUID = Field(foreign_key="qa_conversation.id", index=True)
    knowledge_doc_id: uuid.UUID | None = Field(
        default=None, foreign_key="knowledge_doc.id"
    )
    doc_title: str
    source_url: str
    snippet: str = Field(
        sa_column=Column(Text),
        description="The cited passage, re-supplied to the model every turn",
    )

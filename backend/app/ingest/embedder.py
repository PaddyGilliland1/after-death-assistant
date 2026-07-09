"""Embedding provider abstraction (dimension 1024, pgvector).

When settings.EMBEDDING_MODEL is empty the NoneProvider is selected: it
returns None, the pipeline stores NULL embeddings, and retrieval falls
back to Postgres full-text search only. VoyageProvider is a stub until an
embedding key and model are wired in.
"""

from typing import Protocol

from app.core.config import Settings, get_settings

EMBEDDING_DIMENSION = 1024


class EmbeddingProvider(Protocol):
    """Embeds a batch of texts, or returns None when embedding is off."""

    def embed_texts(self, texts: list[str]) -> list[list[float]] | None:
        """Return one 1024-dimension vector per text, or None."""
        ...


class NoneProvider:
    """No embeddings: the pipeline stores NULL and retrieval is FTS-only."""

    def embed_texts(self, texts: list[str]) -> list[list[float]] | None:
        return None


class VoyageProvider:
    """Voyage AI embeddings stub. Not implemented yet (no key handling)."""

    def __init__(self, model: str) -> None:
        self.model = model

    def embed_texts(self, texts: list[str]) -> list[list[float]] | None:
        raise NotImplementedError(
            f"The Voyage embedding provider (EMBEDDING_MODEL={self.model!r}) is "
            "not implemented yet. Set EMBEDDING_MODEL to empty to run with "
            "full-text search only, or implement VoyageProvider in "
            "app/ingest/embedder.py with key handling before enabling it."
        )


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Choose the provider from settings.EMBEDDING_MODEL."""
    settings = settings or get_settings()
    model = (settings.EMBEDDING_MODEL or "").strip()
    if not model:
        return NoneProvider()
    return VoyageProvider(model)

"""Embedding provider abstraction (dimension 1024, pgvector).

EMBEDDING_MODEL selects the provider:
- "local" (the default): a local model via fastembed
  (mixedbread-ai/mxbai-embed-large-v1, 1024 dimensions). No key, no
  cost, nothing leaves the machine; the model file (~0.6 GB) downloads
  once on first use into the fastembed cache.
- "" (empty): embeddings off; the pipeline stores NULL and retrieval
  falls back to Postgres full-text search only.
- "voyage:<model>": stub for the Voyage AI API until key handling lands.
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


LOCAL_MODEL = "mixedbread-ai/mxbai-embed-large-v1"


class LocalProvider:
    """Local embeddings via fastembed. Lazy singleton: the model loads on
    first use, not at import or provider construction."""

    _embedder = None

    def embed_texts(self, texts: list[str]) -> list[list[float]] | None:
        if LocalProvider._embedder is None:
            from fastembed import TextEmbedding

            LocalProvider._embedder = TextEmbedding(model_name=LOCAL_MODEL)
        return [vector.tolist() for vector in LocalProvider._embedder.embed(texts)]


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
    if model == "local":
        return LocalProvider()
    return VoyageProvider(model)

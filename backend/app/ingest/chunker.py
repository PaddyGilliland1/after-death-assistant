"""Heading-aware chunking for retrieval.

Extracted text arrives with markdown-style heading markers ("# Title").
The text is split into sections at headings, and each section is windowed
into chunks of roughly CHUNK_SIZE characters with CHUNK_OVERLAP overlap.
Every chunk records its sequential index and its heading context.
"""

from pydantic import BaseModel, ConfigDict

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200


class TextChunk(BaseModel):
    """One retrievable chunk with its position and heading context."""

    model_config = ConfigDict(frozen=True)

    index: int
    heading: str | None
    text: str


def _split_sections(text: str) -> list[tuple[str | None, str]]:
    """Split marked-up text into (heading, body) sections."""
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    body: list[str] = []

    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            if body:
                sections.append((heading, "\n\n".join(body)))
                body = []
            heading = block.lstrip("#").strip()
        else:
            body.append(block)
    if body:
        sections.append((heading, "\n\n".join(body)))
    return sections


def _window(section_text: str, size: int, overlap: int) -> list[str]:
    """Slide a window of `size` characters with `overlap` across the text."""
    if len(section_text) <= size:
        return [section_text]
    step = max(size - overlap, 1)
    pieces: list[str] = []
    start = 0
    while start < len(section_text):
        piece = section_text[start : start + size].strip()
        if piece:
            pieces.append(piece)
        if start + size >= len(section_text):
            break
        start += step
    return pieces


def chunk_text(
    text: str,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[TextChunk]:
    """Chunk extracted text, preserving heading context per chunk."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than the chunk size")

    chunks: list[TextChunk] = []
    index = 0
    for heading, body in _split_sections(text):
        for piece in _window(body, size, overlap):
            chunks.append(TextChunk(index=index, heading=heading, text=piece))
            index += 1
    return chunks

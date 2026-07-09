"""Content extraction: HTML, PDF and plain text to clean text.

HTML is cleaned with BeautifulSoup: navigation, scripts, styles and other
chrome are dropped; headings are kept with markdown-style structure
markers ("#", "##", ...) so the chunker can preserve heading context.
PDFs are extracted with pypdf. Anything else is treated as plain text.
"""

import io
import logging

from bs4 import BeautifulSoup
from bs4.element import Tag
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Chrome and non-content elements removed before extraction.
_DROP_TAGS = ("script", "style", "nav", "header", "footer", "aside", "noscript", "form", "svg")

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_CONTENT_TAGS = _HEADING_TAGS + ("p", "li", "blockquote", "figcaption", "caption")


def heading_marker(tag_name: str) -> str:
    """Structure marker for a heading tag: h1 -> '#', h2 -> '##', ..."""
    return "#" * int(tag_name[1])


def _is_nested_in_content(element: Tag) -> bool:
    """True when an ancestor is itself a matched content tag (avoids
    emitting a paragraph twice when it sits inside a list item)."""
    parent = element.parent
    while parent is not None and isinstance(parent, Tag):
        if parent.name in ("p", "li", "blockquote"):
            return True
        parent = parent.parent
    return False


def extract_html(content: bytes) -> str:
    """HTML to clean text with heading structure markers."""
    soup = BeautifulSoup(content, "html.parser")
    for tag_name in _DROP_TAGS:
        for element in soup.find_all(tag_name):
            element.decompose()

    lines: list[str] = []
    for element in soup.find_all(_CONTENT_TAGS):
        if _is_nested_in_content(element):
            continue
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        if element.name in _HEADING_TAGS:
            lines.append(f"{heading_marker(element.name)} {text}")
        else:
            lines.append(text)
    return "\n\n".join(lines)


def extract_pdf(content: bytes) -> str:
    """PDF to text via pypdf, page by page."""
    reader = PdfReader(io.BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        page_text = (page.extract_text() or "").strip()
        if page_text:
            pages.append(page_text)
    return "\n\n".join(pages)


def extract_text(content: bytes, content_type: str) -> str:
    """Dispatch extraction on content type (with a PDF magic-byte check)."""
    normalised = (content_type or "").split(";")[0].strip().lower()
    if normalised == "application/pdf" or content.startswith(b"%PDF"):
        return extract_pdf(content)
    if normalised in ("text/html", "application/xhtml+xml") or b"<html" in content[:2048].lower():
        return extract_html(content)
    return content.decode("utf-8", errors="replace").strip()

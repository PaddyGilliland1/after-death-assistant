"""Polite HTTP fetching for the knowledge pipeline.

Fetches carry an honest User-Agent and conservative timeouts, and every
result records the fetch timestamp and a sha256 content hash for
provenance and change detection (build contract guardrail 3).

Tests NEVER call fetch_url: they build FetchResult values directly via
build_fetch_result, so no test touches the network.
"""

import datetime as dt
import hashlib

import httpx
from pydantic import BaseModel, ConfigDict

POLITE_HEADERS = {
    "User-Agent": (
        "AD-Assistant-KnowledgeIngest/0.1 "
        "(open-source estate administration tool; caches public guidance "
        "under the Open Government Licence with attribution)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.9,*/*;q=0.5",
}

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class FetchResult(BaseModel):
    """The outcome of fetching one source URL."""

    model_config = ConfigDict(frozen=True)

    url: str
    content: bytes
    content_type: str
    fetched_at: dt.datetime
    content_hash: str


def content_sha256(content: bytes) -> str:
    """The sha256 hex digest used for hash-diff change detection."""
    return hashlib.sha256(content).hexdigest()


def build_fetch_result(
    url: str,
    content: bytes,
    content_type: str,
    fetched_at: dt.datetime | None = None,
) -> FetchResult:
    """Assemble a FetchResult (also used by tests to inject fake responses)."""
    return FetchResult(
        url=url,
        content=content,
        content_type=content_type,
        fetched_at=fetched_at or dt.datetime.now(dt.UTC),
        content_hash=content_sha256(content),
    )


async def fetch_url(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,  # noqa: ASYNC109 - httpx client timeout, not asyncio
) -> FetchResult:
    """Fetch a source URL politely and return bytes plus provenance.

    Raises httpx.HTTPError (or a subclass) on network or status failures;
    the pipeline converts that into a per-source error report.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(
        headers=POLITE_HEADERS, timeout=timeout, follow_redirects=True
    )
    try:
        response = await client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "application/octet-stream")
        return build_fetch_result(url, response.content, content_type)
    finally:
        if owns_client:
            await client.aclose()

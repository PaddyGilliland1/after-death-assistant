"""Object storage abstraction for document files.

The backend is chosen from settings.STORAGE_BACKEND:

- ``local``: files live under settings.STORAGE_LOCAL_PATH with opaque
  uuid-derived keys, so no client-supplied name ever becomes a path.
- ``r2``: Cloudflare R2, not yet implemented; every method raises
  NotImplementedError with a clear message.

Keys are generated server-side (uuid4 hex plus an optional sanitised
extension) and validated on every read, stream and delete, so path
traversal is impossible by construction and double-checked by path
resolution.
"""

import logging
import re
import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# uuid4 hex, optionally followed by one short alphanumeric extension.
_KEY_RE = re.compile(r"^[0-9a-f]{32}(\.[A-Za-z0-9]{1,12})?$")
_SUFFIX_RE = re.compile(r"^\.[A-Za-z0-9]{1,12}$")

_CHUNK_SIZE = 64 * 1024


class StorageError(Exception):
    """Raised for invalid keys or missing files."""


class StorageBackend(ABC):
    """Interface every storage backend implements."""

    @abstractmethod
    def save(self, data: bytes, *, suffix: str = "") -> str:
        """Store the bytes and return the generated file key."""

    @abstractmethod
    def read(self, file_key: str) -> bytes:
        """Return the full content for a key."""

    @abstractmethod
    def stream(self, file_key: str, chunk_size: int = _CHUNK_SIZE) -> Iterator[bytes]:
        """Yield the content for a key in chunks."""

    @abstractmethod
    def delete(self, file_key: str) -> None:
        """Remove the stored file. Missing files are ignored."""

    @abstractmethod
    def exists(self, file_key: str) -> bool:
        """Whether a file is stored under the key."""


def _clean_suffix(suffix: str) -> str:
    """Keep the extension only when it is short and purely alphanumeric."""
    suffix = suffix.strip().lower()
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    return suffix if _SUFFIX_RE.match(suffix) else ""


class LocalStorage(StorageBackend):
    """Filesystem storage under a single base directory."""

    def __init__(self, base_path: str | Path) -> None:
        self._base = Path(base_path).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    def _path(self, file_key: str) -> Path:
        if not _KEY_RE.match(file_key or ""):
            raise StorageError(f"Invalid file key: {file_key!r}")
        path = (self._base / file_key).resolve()
        # Belt and braces: the key regex already forbids separators.
        if not path.is_relative_to(self._base):
            raise StorageError(f"File key escapes the storage root: {file_key!r}")
        return path

    def save(self, data: bytes, *, suffix: str = "") -> str:
        file_key = uuid.uuid4().hex + _clean_suffix(suffix)
        path = self._path(file_key)
        path.write_bytes(data)
        logger.debug("Stored %d bytes as %s", len(data), file_key)
        return file_key

    def read(self, file_key: str) -> bytes:
        path = self._path(file_key)
        if not path.is_file():
            raise StorageError(f"File not found for key {file_key!r}")
        return path.read_bytes()

    def stream(self, file_key: str, chunk_size: int = _CHUNK_SIZE) -> Iterator[bytes]:
        path = self._path(file_key)
        if not path.is_file():
            raise StorageError(f"File not found for key {file_key!r}")
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                yield chunk

    def delete(self, file_key: str) -> None:
        path = self._path(file_key)
        path.unlink(missing_ok=True)

    def exists(self, file_key: str) -> bool:
        try:
            return self._path(file_key).is_file()
        except StorageError:
            return False


_R2_MESSAGE = (
    "The Cloudflare R2 storage backend is not implemented yet. "
    "Set STORAGE_BACKEND=local for now, or implement R2Storage in "
    "app/services/storage.py using the R2_* settings (build contract section 3)."
)


class R2Storage(StorageBackend):
    """Cloudflare R2 backend stub. Every operation raises NotImplementedError."""

    def save(self, data: bytes, *, suffix: str = "") -> str:
        raise NotImplementedError(_R2_MESSAGE)

    def read(self, file_key: str) -> bytes:
        raise NotImplementedError(_R2_MESSAGE)

    def stream(self, file_key: str, chunk_size: int = _CHUNK_SIZE) -> Iterator[bytes]:
        raise NotImplementedError(_R2_MESSAGE)

    def delete(self, file_key: str) -> None:
        raise NotImplementedError(_R2_MESSAGE)

    def exists(self, file_key: str) -> bool:
        raise NotImplementedError(_R2_MESSAGE)


def get_storage(settings: Settings | None = None) -> StorageBackend:
    """Build the storage backend selected by settings.STORAGE_BACKEND."""
    settings = settings or get_settings()
    backend = (settings.STORAGE_BACKEND or "local").strip().lower()
    if backend == "local":
        return LocalStorage(settings.STORAGE_LOCAL_PATH)
    if backend == "r2":
        return R2Storage()
    raise ValueError(
        f"Unknown STORAGE_BACKEND {settings.STORAGE_BACKEND!r}; expected 'local' or 'r2'."
    )

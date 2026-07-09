"""Database backups via pg_dump, with sha256 manifests and verification.

VALIDATION.md RQ-9: daily backups are a spec non-functional requirement and
the restore must be tested, not assumed. This module shells out to the
PostgreSQL client tools (pg_dump, pg_restore) because they are the only
supported way to take a consistent logical backup of a live database:

- create_backup()  runs pg_dump in custom format (compressed, pg_restore
  compatible) into STORAGE_LOCAL_PATH/backups, named with a UTC timestamp,
  and writes a JSON manifest alongside carrying the sha256 of the dump.
- list_backups()   lists the backups found in the backup directory.
- verify_backup()  recomputes the sha256 against the manifest and asks
  pg_restore --list to read the archive's table of contents, which fails
  on a truncated or corrupted file.

The CLI wrapper lives in app/cli_backup.py (python -m app.cli_backup).
Credentials are passed to the subprocess via PGPASSWORD in its environment,
never on the command line, and are never logged.
"""

import datetime as dt
import hashlib
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
BACKUP_PREFIX = "ad_backup_"
BACKUP_SUFFIX = ".dump"
MANIFEST_SUFFIX = ".manifest.json"

_HASH_CHUNK = 1024 * 1024
_SUBPROCESS_TIMEOUT = 600  # seconds; a small estate database dumps in seconds


class BackupError(RuntimeError):
    """Raised when a backup operation fails."""


class BackupToolMissingError(BackupError):
    """Raised when pg_dump or pg_restore is not on PATH."""


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """A backup on disk, as listed from its manifest."""

    file: Path
    manifest: Path | None
    size_bytes: int
    created_at: str | None
    sha256: str | None
    database: str | None


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Outcome of verify_backup: both checks must pass."""

    file: Path
    sha256_ok: bool
    restore_list_ok: bool
    detail: str

    @property
    def ok(self) -> bool:
        return self.sha256_ok and self.restore_list_ok


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise BackupToolMissingError(
            f"{name} is not on PATH. Install the PostgreSQL client tools "
            "(postgresql-client-16) to run backups."
        )
    return path


def _connection_parts(database_url: str) -> tuple[list[str], dict[str, str], str]:
    """Split DATABASE_URL into pg tool arguments and a PGPASSWORD env.

    The async driver suffix (+asyncpg) is irrelevant to the client tools,
    so the URL is parsed structurally rather than passed through.
    """
    url = make_url(database_url)
    if not url.get_backend_name().startswith("postgresql"):
        raise BackupError(
            f"Backups require a PostgreSQL DATABASE_URL, got {url.get_backend_name()!r}."
        )
    args: list[str] = []
    if url.host:
        args += ["--host", url.host]
    if url.port:
        args += ["--port", str(url.port)]
    if url.username:
        args += ["--username", url.username]
    env: dict[str, str] = {}
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    database = url.database or ""
    if not database:
        raise BackupError("DATABASE_URL has no database name; cannot back up.")
    return args, env, database


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def backups_dir(settings: Settings | None = None) -> Path:
    """The backup directory: STORAGE_LOCAL_PATH/backups, created on use."""
    settings = settings or get_settings()
    directory = Path(settings.STORAGE_LOCAL_PATH) / BACKUP_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def manifest_path_for(dump_path: Path) -> Path:
    """The manifest that belongs to a dump file."""
    return dump_path.with_name(dump_path.name.removesuffix(BACKUP_SUFFIX) + MANIFEST_SUFFIX)


def create_backup(settings: Settings | None = None) -> BackupInfo:
    """Run pg_dump and write the dump plus its sha256 manifest.

    Returns the BackupInfo for the new backup. Raises BackupError (with the
    pg_dump stderr) on failure; a partial dump file is removed.
    """
    settings = settings or get_settings()
    pg_dump = _require_tool("pg_dump")
    conn_args, extra_env, database = _connection_parts(settings.DATABASE_URL)

    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    dump_path = backups_dir(settings) / f"{BACKUP_PREFIX}{timestamp}{BACKUP_SUFFIX}"

    env = {**os.environ, **extra_env}
    command = [
        pg_dump,
        *conn_args,
        "--dbname",
        database,
        "--format=custom",
        "--no-password",
        "--file",
        str(dump_path),
    ]
    logger.info("Backing up database %s to %s", database, dump_path.name)
    result = subprocess.run(
        command,
        env=env,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
    )
    if result.returncode != 0:
        dump_path.unlink(missing_ok=True)
        raise BackupError(f"pg_dump failed (exit {result.returncode}): {result.stderr.strip()}")

    sha256 = _sha256_of(dump_path)
    created_at = dt.datetime.now(dt.UTC).isoformat()
    manifest = {
        "file": dump_path.name,
        "sha256": sha256,
        "size_bytes": dump_path.stat().st_size,
        "created_at": created_at,
        "database": database,
        "format": "pg_dump custom",
    }
    manifest_path = manifest_path_for(dump_path)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.info("Backup complete: %s (%d bytes)", dump_path.name, manifest["size_bytes"])

    return BackupInfo(
        file=dump_path,
        manifest=manifest_path,
        size_bytes=manifest["size_bytes"],
        created_at=created_at,
        sha256=sha256,
        database=database,
    )


def list_backups(settings: Settings | None = None) -> list[BackupInfo]:
    """Backups on disk, newest first. Dumps without a manifest still list
    (with unknown hash) so nothing on disk is invisible."""
    settings = settings or get_settings()
    backups: list[BackupInfo] = []
    for dump_path in sorted(backups_dir(settings).glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}")):
        manifest_path = manifest_path_for(dump_path)
        created_at = sha256 = database = None
        manifest: Path | None = None
        if manifest_path.is_file():
            manifest = manifest_path
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                created_at = data.get("created_at")
                sha256 = data.get("sha256")
                database = data.get("database")
            except (OSError, json.JSONDecodeError):
                logger.warning("Unreadable manifest: %s", manifest_path)
        backups.append(
            BackupInfo(
                file=dump_path,
                manifest=manifest,
                size_bytes=dump_path.stat().st_size,
                created_at=created_at,
                sha256=sha256,
                database=database,
            )
        )
    backups.reverse()
    return backups


def verify_backup(dump_file: str | Path, settings: Settings | None = None) -> VerifyResult:
    """Verify a backup: sha256 against its manifest AND pg_restore --list.

    The hash check catches silent corruption and tampering; the pg_restore
    table-of-contents read proves the archive is a structurally valid dump
    that pg_restore would accept. Both must pass.
    """
    settings = settings or get_settings()
    dump_path = Path(dump_file)
    if not dump_path.is_absolute():
        dump_path = backups_dir(settings) / dump_path
    if not dump_path.is_file():
        return VerifyResult(
            file=dump_path,
            sha256_ok=False,
            restore_list_ok=False,
            detail=f"Backup file not found: {dump_path}",
        )

    details: list[str] = []

    manifest_path = manifest_path_for(dump_path)
    sha256_ok = False
    if not manifest_path.is_file():
        details.append(f"No manifest at {manifest_path.name}; cannot check the hash.")
    else:
        try:
            expected = json.loads(manifest_path.read_text(encoding="utf-8")).get("sha256")
        except (OSError, json.JSONDecodeError) as exc:
            expected = None
            details.append(f"Manifest unreadable: {exc}.")
        if expected:
            actual = _sha256_of(dump_path)
            sha256_ok = actual == expected
            details.append(
                "sha256 matches the manifest."
                if sha256_ok
                else "sha256 MISMATCH: the file does not match its manifest."
            )
        else:
            details.append("Manifest carries no sha256.")

    pg_restore = _require_tool("pg_restore")
    result = subprocess.run(
        [pg_restore, "--list", str(dump_path)],
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
    )
    restore_list_ok = result.returncode == 0
    details.append(
        "pg_restore reads the archive contents."
        if restore_list_ok
        else f"pg_restore --list failed: {result.stderr.strip()}"
    )

    return VerifyResult(
        file=dump_path,
        sha256_ok=sha256_ok,
        restore_list_ok=restore_list_ok,
        detail=" ".join(details),
    )

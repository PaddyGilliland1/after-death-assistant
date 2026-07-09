"""Backup CLI: python -m app.cli_backup {create | list | verify <file>}.

Wraps app.services.backup. Reads DATABASE_URL and STORAGE_LOCAL_PATH from
the environment (or .env) via the normal Settings model, so it behaves the
same on a laptop, in docker-compose and inside the Railway container.

Exit codes: 0 success, 1 operation failed, 2 client tools missing.
See docs/DEPLOY.md for the backup schedule and the restore drill.
"""

import argparse
import logging
import sys

from app.services.backup import (
    BackupError,
    BackupToolMissingError,
    create_backup,
    list_backups,
    verify_backup,
)


def _cmd_create() -> int:
    info = create_backup()
    print(f"Backup written: {info.file}")
    print(f"  size:    {info.size_bytes} bytes")
    print(f"  sha256:  {info.sha256}")
    print(f"  manifest: {info.manifest}")
    return 0


def _cmd_list() -> int:
    backups = list_backups()
    if not backups:
        print("No backups found.")
        return 0
    for info in backups:
        hashed = "sha256 recorded" if info.sha256 else "NO MANIFEST"
        created = info.created_at or "unknown time"
        print(f"{info.file.name}  {info.size_bytes} bytes  {created}  [{hashed}]")
    return 0


def _cmd_verify(file: str) -> int:
    result = verify_backup(file)
    status = "OK" if result.ok else "FAILED"
    print(f"Verify {result.file.name}: {status}")
    print(f"  {result.detail}")
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        prog="python -m app.cli_backup",
        description="Database backups: pg_dump with sha256 manifests.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create", help="Run pg_dump into STORAGE_LOCAL_PATH/backups")
    sub.add_parser("list", help="List backups, newest first")
    verify_parser = sub.add_parser(
        "verify", help="Check a backup's sha256 and pg_restore readability"
    )
    verify_parser.add_argument("file", help="Backup file name or path")

    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            return _cmd_create()
        if args.command == "list":
            return _cmd_list()
        return _cmd_verify(args.file)
    except BackupToolMissingError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except BackupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

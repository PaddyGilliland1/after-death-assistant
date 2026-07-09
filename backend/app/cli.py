"""Seed CLI.

Usage:
    python -m app.cli seed --file <path> [--force-fresh]
    python -m app.cli seed-demo [--force-fresh]

``seed`` loads a seed JSON (estate, assets, beneficiary_legacies, gifts,
tasks.seed_from) idempotently; ``seed-demo`` loads the synthetic demo
estate shipped in seed_templates. ``--force-fresh`` wipes seed data first
but aborts if any table holds user-entered rows. The database is taken
from DATABASE_URL (settings).
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.db import dispose_engine, get_session_factory
from app.services.seeding import (
    DEMO_SEED_PATH,
    SeedAbortError,
    seed_from_file,
    summarise_report,
)

logger = logging.getLogger("app.cli")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed", help="Load a seed JSON file")
    seed_parser.add_argument("--file", required=True, type=Path, help="Path to the seed JSON")
    seed_parser.add_argument(
        "--force-fresh",
        action="store_true",
        help="Wipe seed rows and reseed; aborts if user-entered rows exist",
    )

    demo_parser = subparsers.add_parser(
        "seed-demo", help="Load the synthetic demo estate (safe for any environment)"
    )
    demo_parser.add_argument("--force-fresh", action="store_true")

    return parser


async def _run_seed(path: Path, force_fresh: bool) -> int:
    factory = get_session_factory()
    try:
        async with factory() as session:
            report = await seed_from_file(session, path, force_fresh=force_fresh)
            await session.commit()
    except SeedAbortError as exc:
        logger.error("%s", exc)
        return 2
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 1
    finally:
        await dispose_engine()

    logger.info("%s", summarise_report(report))
    for warning in report.warnings:
        logger.warning("%s", warning)
    if report.estate_created:
        logger.info(
            "Reminder: run POST /iht/recompute and POST /deadlines/recompute "
            "so the assessment and statutory deadlines are derived."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _build_parser().parse_args(argv)
    if args.command == "seed":
        path = args.file
    else:  # seed-demo
        path = DEMO_SEED_PATH
    return asyncio.run(_run_seed(path, args.force_fresh))


if __name__ == "__main__":
    sys.exit(main())

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

    subparsers.add_parser(
        "embed-backfill",
        help="Embed knowledge chunks that have no embedding yet (no network "
        "fetch; uses the configured EMBEDDING_MODEL provider)",
    )

    subparsers.add_parser(
        "reconcile-steps",
        help="Recompute every timeline step's status from its linked tasks "
        "(one-time repair for data written before task-step sync existed)",
    )

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
            "so the assessment and statutory deadlines are derived, and "
            "scripts/fetch-knowledge.sh to cache the guidance library. "
            "Semantic search is optional: switch it on from Admin, Parameters."
        )
    return 0


async def _run_reconcile() -> int:
    from sqlalchemy import select

    from app.models import ProcessStep
    from app.services.process_sync import sync_step_from_tasks

    factory = get_session_factory()
    changed = 0
    try:
        async with factory() as session:
            result = await session.execute(
                select(ProcessStep).where(ProcessStep.archived_at.is_(None))
            )
            for step in result.scalars().all():
                before = step.status
                synced = await sync_step_from_tasks(session, step.id, "cli-reconcile")
                if synced is not None and synced.status != before:
                    changed += 1
                    logger.info("Step %s: %s -> %s", step.name, before, synced.status)
            await session.commit()
    finally:
        await dispose_engine()
    logger.info("Reconciled: %d step(s) updated.", changed)
    return 0


async def _run_embed_backfill() -> int:
    from sqlalchemy import select

    from app.ingest.embedder import get_embedding_provider
    from app.models import KnowledgeChunk

    provider = get_embedding_provider()
    factory = get_session_factory()
    done = 0
    try:
        async with factory() as session:
            result = await session.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.embedding.is_(None))
                .where(KnowledgeChunk.archived_at.is_(None))
            )
            chunks = list(result.scalars().all())
            if not chunks:
                logger.info("Nothing to embed: every chunk already has a vector.")
                return 0
            batch = 64
            for start in range(0, len(chunks), batch):
                part = chunks[start : start + batch]
                vectors = provider.embed_texts([chunk.text for chunk in part])
                if vectors is None:
                    logger.error(
                        "Embeddings are switched off (EMBEDDING_MODEL is empty)."
                    )
                    return 1
                for chunk, vector in zip(part, vectors, strict=True):
                    chunk.embedding = vector
                    session.add(chunk)
                done += len(part)
                logger.info("Embedded %d/%d chunks", done, len(chunks))
            await session.commit()
    finally:
        await dispose_engine()
    logger.info("Backfill complete: %d chunk(s) embedded.", done)
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _build_parser().parse_args(argv)
    if args.command == "embed-backfill":
        return asyncio.run(_run_embed_backfill())
    if args.command == "reconcile-steps":
        return asyncio.run(_run_reconcile())
    if args.command == "seed":
        path = args.file
    else:  # seed-demo
        path = DEMO_SEED_PATH
    return asyncio.run(_run_seed(path, args.force_fresh))


if __name__ == "__main__":
    sys.exit(main())

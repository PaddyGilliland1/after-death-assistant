"""Command-line knowledge ingestion (real, on-demand runs).

Runs the ingestion pipeline over the seed source registry (or a named
subset) against the database configured by DATABASE_URL. This DOES fetch
the internet; it is the on-demand counterpart of the admin-only
POST /knowledge/ingest endpoint. Registered as a console entry point
later; until then run it as a module:

    uv run python -m app.cli_ingest            # all resolved sources
    uv run python -m app.cli_ingest IHT400     # a named subset
"""

import argparse
import asyncio
import logging
import sys

logger = logging.getLogger(__name__)


async def _run(source_keys: list[str], registry_path: str | None, force: bool) -> int:
    from app.db import dispose_engine, get_session_factory
    from app.ingest.pipeline import ingest_sources
    from app.ingest.registry import load_registry
    from app.services.seeding import get_active_estate

    sources = load_registry(registry_path)
    if source_keys:
        by_key = {source.key: source for source in sources}
        missing = [key for key in source_keys if key not in by_key]
        if missing:
            print(f"Unknown or unresolved source keys: {', '.join(missing)}", file=sys.stderr)
            return 2
        sources = [by_key[key] for key in source_keys]

    try:
        async with get_session_factory()() as session:
            estate = await get_active_estate(session)
            if estate is None:
                print("No active estate found; seed the estate first.", file=sys.stderr)
                return 1
            reports = await ingest_sources(
                session, sources, estate_id=estate.id, actor="cli-ingest", force=force
            )
    finally:
        await dispose_engine()

    failures = 0
    for report in reports:
        line = f"{report.source_key:32s} {report.status:10s}"
        if report.version is not None:
            line += f" v{report.version}"
        if report.chunk_count:
            line += f" ({report.chunk_count} chunks)"
        if report.detail:
            line += f" - {report.detail}"
        print(line)
        if report.status == "error":
            failures += 1
    print(f"\n{len(reports)} sources processed, {failures} errors.")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    """Entry point: ingest the registry (or a subset) for the active estate."""
    parser = argparse.ArgumentParser(
        prog="ad-ingest",
        description="Fetch and ingest the knowledge source registry (network access).",
    )
    parser.add_argument(
        "source_keys",
        nargs="*",
        help="Optional registry keys (form code or topic) to ingest; default all.",
    )
    parser.add_argument(
        "--registry",
        default=None,
        help="Path to an alternative source registry JSON file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even when a landing page hash is unchanged (guide "
        "part pages are not covered by the hash).",
    )
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    return asyncio.run(_run(args.source_keys, args.registry, args.force))


if __name__ == "__main__":
    raise SystemExit(main())

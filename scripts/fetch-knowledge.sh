#!/usr/bin/env bash
# Fetch the starter knowledge library: every source in the registry
# (backend/seed_templates/source_registry.json; 50+ entries covering the
# HMRC forms and guidance, probate, tracing services, veterans support
# and bereavement organisations), pulled directly from each official or
# support-organisation site into your own database. The registry is the
# single source of truth; this script always fetches whatever it lists.
#
# Why a script rather than shipping the content: most documents are Crown
# copyright under the Open Government Licence and each source records its
# own licence, so you fetch them from the canonical source rather than a
# redistributed copy; you always get the current versions; and the pipeline
# records provenance (source URL, fetch date, content hash) on every
# document. Multi-page gov.uk guides are followed page by page.
#
# Usage:
#   scripts/fetch-knowledge.sh                # everything in the registry
#   scripts/fetch-knowledge.sh IHT400 IHT405  # named sources only
#   scripts/fetch-knowledge.sh --force        # refresh even if unchanged
#
# Prerequisites: the database is up and an estate exists (seed one first:
# see docs/INSTALL.md). Needs internet access. Run it again any time; the
# hash-diff versioning keeps history when guidance changes.

set -euo pipefail
cd "$(dirname "$0")/.."

if docker compose ps backend 2>/dev/null | grep -q "Up"; then
  echo "== Running inside the docker compose backend"
  exec docker compose exec backend python -m app.cli_ingest "$@"
fi

if [ -d backend/.venv ]; then
  echo "== Running against DATABASE_URL=${DATABASE_URL:-<backend default>}"
  cd backend
  exec uv run python -m app.cli_ingest "$@"
fi

echo "Neither a running docker compose backend nor backend/.venv was found." >&2
echo "Start the stack (docker compose up -d) or install the backend (cd backend && uv sync)." >&2
exit 1

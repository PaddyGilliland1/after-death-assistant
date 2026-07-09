"""Seed loading, plus small shared persistence helpers for the
collaboration routers (active-estate lookup and audit recording).

Seeding is idempotent: if an estate already exists the estate section is
skipped, and the Section 25 checklist is only loaded when no process
steps exist yet. ``force_fresh`` wipes and reseeds, but ABORTS if any
table holds rows that were not written by the seeder (created_by other
than "seed"), so user-entered data can never be destroyed silently
(Cardinal Rule 2).

Known gap: the seed file may list lifetime gifts, but there is no
lifetime-gift table yet (see VALIDATION.md). Gifts are skipped with a
logged warning listing each one; they are NOT loaded as asset rows.
"""

import json
import logging
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.models import (
    Asset,
    AuditEvent,
    BeneficiaryLegacy,
    Contact,
    ContactCategory,
    Estate,
    LegacyType,
    OwnershipType,
    ProcessStep,
    Task,
    ValueBasis,
)
from app.schemas.collab import (
    Section25EntryIn,
    SeedFileIn,
    SeedReport,
)

logger = logging.getLogger(__name__)

SEED_ACTOR = "seed"

_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CHECKLIST_PATH = _BACKEND_DIR / "seed_templates" / "section25_checklist.json"
DEMO_SEED_PATH = _BACKEND_DIR / "seed_templates" / "demo_estate_seed.json"


class SeedAbortError(RuntimeError):
    """Raised when --force-fresh would destroy user-entered rows."""


# ---------------------------------------------------------------------------
# Shared helpers used by the collaboration routers
# ---------------------------------------------------------------------------


async def get_active_estate(session: AsyncSession) -> Estate | None:
    """Return the single active (non-archived) estate, oldest first."""
    result = await session.execute(
        select(Estate)
        .where(Estate.archived_at.is_(None))
        .order_by(Estate.created_at)
        .limit(1)
    )
    return result.scalars().first()


async def record_audit(
    session: AsyncSession,
    estate_id: uuid.UUID,
    actor: str,
    action: str,
    entity: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    """Persist an audit event in the caller's session (estate-scoped)."""
    event = AuditEvent(
        estate_id=estate_id,
        actor=actor,
        action=action,
        entity=entity,
        before=before,
        after=after,
        created_by=actor,
    )
    session.add(event)
    await session.flush()
    return event


# ---------------------------------------------------------------------------
# Seed loading
# ---------------------------------------------------------------------------


def _resolve_checklist_path(seed_from: str | None, seed_dir: Path) -> Path:
    """Resolve the checklist path from the seed file, falling back to the
    packaged Section 25 template."""
    if seed_from:
        candidates = [
            Path(seed_from),
            seed_dir / seed_from,
            _BACKEND_DIR / seed_from,
            _BACKEND_DIR.parent / seed_from,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        logger.warning(
            "tasks.seed_from %r not found; using the default Section 25 template",
            seed_from,
        )
    return DEFAULT_CHECKLIST_PATH


async def _count_user_rows(session: AsyncSession) -> dict[str, int]:
    """Rows per table not written by the seeder (created_by != 'seed')."""
    counts: dict[str, int] = {}
    for table in SQLModel.metadata.sorted_tables:
        if "created_by" not in table.c:
            continue
        result = await session.execute(
            select(func.count())
            .select_from(table)
            .where(table.c.created_by != SEED_ACTOR)
        )
        count = int(result.scalar_one())
        if count:
            counts[table.name] = count
    return counts


async def _wipe_all_rows(session: AsyncSession) -> None:
    """Delete every row, children before parents. Only called after the
    user-entered-rows check has passed."""
    for table in reversed(SQLModel.metadata.sorted_tables):
        await session.execute(table.delete())
    await session.flush()


async def load_section25_checklist(
    session: AsyncSession,
    estate_id: uuid.UUID,
    checklist_path: Path | None = None,
) -> tuple[int, int]:
    """Load the Section 25 checklist into process_step and task rows.

    Idempotent: does nothing when the estate already has process steps.
    Task dependencies (``depends_on`` order numbers) are mapped to task
    UUIDs in blocked_by, with the reverse edges in blocks.

    Returns (steps_created, tasks_created).
    """
    checklist_path = checklist_path or DEFAULT_CHECKLIST_PATH
    existing = await session.execute(
        select(func.count())
        .select_from(ProcessStep)
        .where(ProcessStep.estate_id == estate_id)
    )
    if int(existing.scalar_one()) > 0:
        logger.info("Process steps already exist for estate %s; checklist skipped", estate_id)
        return (0, 0)

    raw = json.loads(checklist_path.read_text(encoding="utf-8"))
    entries = sorted(
        (Section25EntryIn.model_validate(item) for item in raw),
        key=lambda entry: entry.order,
    )

    steps: dict[int, ProcessStep] = {}
    tasks: dict[int, Task] = {}
    for entry in entries:
        steps[entry.order] = ProcessStep(
            estate_id=estate_id,
            order=entry.order,
            name=entry.title,
            status="not_started",
            created_by=SEED_ACTOR,
        )
        tasks[entry.order] = Task(
            estate_id=estate_id,
            title=entry.title,
            description=entry.description,
            status="todo",
            process_step_id=steps[entry.order].id,
            source="seed",
            created_by=SEED_ACTOR,
        )

    blocks_map: dict[int, list[str]] = defaultdict(list)
    for entry in entries:
        blocked_by: list[str] = []
        for dep_order in entry.depends_on:
            dep_task = tasks.get(dep_order)
            if dep_task is None:
                logger.warning(
                    "Checklist entry %s depends on unknown order %s; dependency skipped",
                    entry.order,
                    dep_order,
                )
                continue
            blocked_by.append(str(dep_task.id))
            blocks_map[dep_order].append(str(tasks[entry.order].id))
        tasks[entry.order].blocked_by = blocked_by
    for dep_order, blocked_ids in blocks_map.items():
        tasks[dep_order].blocks = blocked_ids

    session.add_all(steps.values())
    session.add_all(tasks.values())
    await session.flush()
    return (len(steps), len(tasks))


async def seed_estate(
    session: AsyncSession,
    seed: SeedFileIn,
    *,
    seed_dir: Path | None = None,
    force_fresh: bool = False,
) -> SeedReport:
    """Load a validated seed into the database. See module docstring for
    the idempotency and force-fresh rules. The caller commits."""
    report = SeedReport()
    seed_dir = seed_dir or Path.cwd()

    if force_fresh:
        user_rows = await _count_user_rows(session)
        if user_rows:
            listing = ", ".join(f"{name}={count}" for name, count in sorted(user_rows.items()))
            raise SeedAbortError(
                "force-fresh aborted: user-entered rows exist "
                f"(created_by other than '{SEED_ACTOR}'): {listing}. "
                "Remove or migrate them explicitly before reseeding."
            )
        logger.warning("force-fresh: wiping all seed rows before reseeding")
        await _wipe_all_rows(session)

    estate = await get_active_estate(session)
    if estate is not None:
        report.skipped = True
        report.warnings.append(
            f"Estate {estate.id} already exists; estate, assets, legacies and gifts skipped."
        )
        logger.info("Seed skipped: estate already present (%s)", estate.id)
    else:
        estate = Estate(
            name=seed.estate.name,
            date_of_death=seed.estate.date_of_death,
            grant_date=seed.estate.grant_date,
            constants_version=seed.estate.constants_version,
            tnrb_pct=seed.estate.tnrb_pct,
            trnrb_pct=seed.estate.trnrb_pct,
            residence_to_descendants_value=seed.estate.residence_to_descendants_value,
            charity_share_pct=seed.estate.charity_share_pct,
            created_by=SEED_ACTOR,
        )
        session.add(estate)
        await session.flush()
        report.estate_created = True
        # Estate creation deliberately triggers nothing automatic.
        logger.info(
            "Estate %s created. Reminder: run POST /iht/recompute (and "
            "POST /deadlines/recompute) to derive the assessment and deadlines.",
            estate.id,
        )

        for seed_asset in seed.assets:
            session.add(
                Asset(
                    estate_id=estate.id,
                    category=seed_asset.category,
                    sub_type=seed_asset.sub_type,
                    description=seed_asset.description,
                    ownership=OwnershipType(seed_asset.ownership),
                    dod_value=seed_asset.dod_value,
                    value_basis=ValueBasis(seed_asset.value_basis),
                    rnrb_qualifying=seed_asset.rnrb_qualifying,
                    iht_schedule=seed_asset.iht_schedule,
                    status=seed_asset.status,
                    created_by=SEED_ACTOR,
                )
            )
            report.assets_created += 1

        for legacy in seed.beneficiary_legacies:
            contact = Contact(
                estate_id=estate.id,
                kind="person",
                category=ContactCategory.beneficiary,
                name=legacy.beneficiary_name,
                created_by=SEED_ACTOR,
            )
            session.add(contact)
            await session.flush()
            report.contacts_created += 1
            session.add(
                BeneficiaryLegacy(
                    estate_id=estate.id,
                    beneficiary_contact_id=contact.id,
                    legacy_type=LegacyType(legacy.legacy_type),
                    amount_or_share=legacy.amount_or_share,
                    exempt_or_chargeable=legacy.exempt_or_chargeable,
                    status=legacy.status,
                    created_by=SEED_ACTOR,
                )
            )
            report.legacies_created += 1

        # Known gap: no lifetime-gift table yet (VALIDATION.md). Skip, loudly.
        for gift in seed.gifts:
            label = f"{gift.description or 'gift'} (amount {gift.amount})"
            report.skipped_gifts.append(label)
        if report.skipped_gifts:
            warning = (
                "Gifts skipped, no lifetime-gift table exists yet: "
                + "; ".join(report.skipped_gifts)
            )
            report.warnings.append(warning)
            logger.warning(warning)

    # The Section 25 checklist always loads (idempotently) for the estate.
    seed_from = seed.tasks.seed_from if seed.tasks else None
    checklist_path = _resolve_checklist_path(seed_from, seed_dir)
    steps, tasks = await load_section25_checklist(session, estate.id, checklist_path)
    report.steps_created = steps
    report.tasks_created = tasks

    await session.flush()
    return report


async def seed_from_file(
    session: AsyncSession,
    path: str | Path,
    *,
    force_fresh: bool = False,
) -> SeedReport:
    """Read, validate and load a seed JSON file. The caller commits."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Seed file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    seed = SeedFileIn.model_validate(data)
    return await seed_estate(
        session, seed, seed_dir=path.resolve().parent, force_fresh=force_fresh
    )


def summarise_report(report: SeedReport) -> str:
    """One-line human summary for CLI output and logs."""
    if report.skipped:
        head = "Seed skipped (estate already present)"
    elif report.estate_created:
        head = "Estate seeded"
    else:
        head = "Seed run complete"
    return (
        f"{head}: contacts={report.contacts_created} assets={report.assets_created} "
        f"legacies={report.legacies_created} steps={report.steps_created} "
        f"tasks={report.tasks_created} gifts_skipped={len(report.skipped_gifts)}"
    )

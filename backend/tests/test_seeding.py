"""Seeding service tests against the dedicated collab test database.

Own fixtures by design (conftest stays minimal): a Postgres database
ad_test_collab on localhost:5474, tables created via SQLModel metadata,
rows wiped before each test.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5474/ad_test_collab"


async def _prepare_database() -> None:
    from sqlmodel import SQLModel

    import app.models  # noqa: F401  (registers every table on the metadata)

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)
        for table in reversed(SQLModel.metadata.sorted_tables):
            await conn.execute(table.delete())
    await engine.dispose()


@pytest.fixture()
def clean_db():
    asyncio.run(_prepare_database())


@pytest.fixture()
async def session(clean_db):
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


async def _count(session, model) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())


async def test_demo_seed_loads_clean(session):
    from app.models import Asset, BeneficiaryLegacy, Contact, Estate, ProcessStep, Task
    from app.services.seeding import DEMO_SEED_PATH, seed_from_file

    report = await seed_from_file(session, DEMO_SEED_PATH)
    await session.commit()

    assert report.estate_created is True
    assert report.skipped is False
    assert report.assets_created == 4
    assert report.contacts_created == 3
    assert report.legacies_created == 3
    assert report.steps_created == 41
    assert report.tasks_created == 41

    assert await _count(session, Estate) == 1
    assert await _count(session, Asset) == 4
    assert await _count(session, Contact) == 3
    assert await _count(session, BeneficiaryLegacy) == 3
    assert await _count(session, ProcessStep) == 41
    assert await _count(session, Task) == 41

    estate = (await session.execute(select(Estate))).scalars().one()
    assert "Example" in estate.name  # obviously synthetic
    assert estate.date_of_death is not None


async def test_gifts_are_skipped_with_warning(session):
    """No lifetime-gift table exists yet (VALIDATION.md gap): gifts must be
    skipped and listed, never silently loaded as assets."""
    from app.models import Asset
    from app.services.seeding import DEMO_SEED_PATH, seed_from_file

    report = await seed_from_file(session, DEMO_SEED_PATH)
    await session.commit()

    assert len(report.skipped_gifts) == 2
    assert any("gift" in item.lower() for item in report.skipped_gifts)
    assert any("lifetime-gift table" in warning for warning in report.warnings)
    # Gifts did not leak into the asset register.
    assert await _count(session, Asset) == 4


async def test_section25_graph_mapping(session):
    """depends_on order numbers map to blocked_by task UUIDs, with the
    reverse edges in blocks, and every task links to its process step."""
    from app.models import ProcessStep, Task
    from app.services.seeding import DEMO_SEED_PATH, seed_from_file

    await seed_from_file(session, DEMO_SEED_PATH)
    await session.commit()

    steps = (
        (await session.execute(select(ProcessStep).order_by(ProcessStep.order)))
        .scalars()
        .all()
    )
    assert [step.order for step in steps] == list(range(1, 42))

    tasks = (await session.execute(select(Task))).scalars().all()
    by_title = {task.title: task for task in tasks}
    by_id = {str(task.id): task for task in tasks}

    funeral = by_title["Arrange the funeral"]  # order 5, depends on 1 and 3
    dep_titles = {by_id[dep].title for dep in funeral.blocked_by}
    assert dep_titles == {
        "Get the death verified and the MCCD issued",
        "Find the will, codicils and funeral wishes",
    }

    verified = by_title["Get the death verified and the MCCD issued"]
    assert str(funeral.id) in verified.blocks

    step_ids = {step.id for step in steps}
    assert all(task.process_step_id in step_ids for task in tasks)
    assert all(task.source == "seed" for task in tasks)


async def test_seeding_is_idempotent(session):
    from app.models import Estate, ProcessStep, Task
    from app.services.seeding import DEMO_SEED_PATH, seed_from_file

    first = await seed_from_file(session, DEMO_SEED_PATH)
    await session.commit()
    second = await seed_from_file(session, DEMO_SEED_PATH)
    await session.commit()

    assert first.estate_created is True
    assert second.skipped is True
    assert second.estate_created is False
    assert second.steps_created == 0
    assert second.tasks_created == 0

    assert await _count(session, Estate) == 1
    assert await _count(session, ProcessStep) == 41
    assert await _count(session, Task) == 41


async def test_force_fresh_aborts_on_user_entered_rows(session):
    from app.models import Contact, ContactCategory, Estate
    from app.services.seeding import DEMO_SEED_PATH, SeedAbortError, seed_from_file

    await seed_from_file(session, DEMO_SEED_PATH)
    await session.commit()

    estate_id = (await session.execute(select(Estate.id))).scalar_one()
    session.add(
        Contact(
            estate_id=estate_id,
            name="Hand-entered demo contact",
            category=ContactCategory.other,
            created_by="executor@test.local",
        )
    )
    await session.commit()

    with pytest.raises(SeedAbortError) as excinfo:
        await seed_from_file(session, DEMO_SEED_PATH, force_fresh=True)
    assert "contact" in str(excinfo.value)

    # Nothing was destroyed.
    result = await session.execute(select(func.count()).select_from(Contact))
    assert int(result.scalar_one()) == 4  # 3 seeded beneficiaries + 1 user row


async def test_force_fresh_reseeds_when_only_seed_rows_exist(session):
    from app.models import Estate, ProcessStep
    from app.services.seeding import DEMO_SEED_PATH, seed_from_file

    await seed_from_file(session, DEMO_SEED_PATH)
    await session.commit()
    first_estate_id = (await session.execute(select(Estate.id))).scalar_one()

    report = await seed_from_file(session, DEMO_SEED_PATH, force_fresh=True)
    await session.commit()

    assert report.estate_created is True
    assert report.skipped is False
    second_estate_id = (await session.execute(select(Estate.id))).scalar_one()
    assert isinstance(second_estate_id, uuid.UUID)
    assert second_estate_id != first_estate_id
    assert await _count(session, ProcessStep) == 41

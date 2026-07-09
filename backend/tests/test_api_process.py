"""Process API tests: step ordering and status patching, timeline
derivation with deadline joins, and the statutory deadline recompute
asserted against known dates from app.domain.deadlines.

Own fixtures: Postgres ad_test_collab on localhost:5474.
"""

import asyncio
import datetime as dt
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5474/ad_test_collab"

EXECUTOR = "executor@test.local"
VIEWER = "viewer@test.local"

DOD = dt.date(2026, 1, 15)


async def _prepare_database() -> None:
    from sqlmodel import SQLModel

    import app.models  # noqa: F401

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)
        for table in reversed(SQLModel.metadata.sorted_tables):
            await conn.execute(table.delete())
    await engine.dispose()


async def _with_session(fn):
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            result = await fn(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


@pytest.fixture()
def clean_db():
    asyncio.run(_prepare_database())


@pytest.fixture()
def estate_id(clean_db) -> str:
    async def _do(session):
        from app.models import Estate

        estate = Estate(name="Demo Estate (test)", date_of_death=DOD, created_by="test")
        session.add(estate)
        await session.flush()
        return str(estate.id)

    return asyncio.run(_with_session(_do))


@pytest.fixture()
def make_client(clean_db, tmp_path):
    os.environ["STORAGE_LOCAL_PATH"] = str(tmp_path / "storage")
    from app.core.config import get_settings

    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from app.api import approvals, audit_activity, documents, notifications, process
    from app.db import get_session
    from app.main import create_app

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_session():
        async with factory() as session:
            yield session

    app = create_app()
    for module in (documents, notifications, audit_activity, process, approvals):
        app.include_router(module.router)
    app.dependency_overrides[get_session] = _override_session

    def _make(user: str | None = EXECUTOR) -> TestClient:
        client = TestClient(app)
        if user is not None:
            client.headers["X-Dev-User"] = user
        return client

    yield _make
    asyncio.run(engine.dispose())


def _create_steps(estate_id: str, statuses: list[str | None]) -> list[str]:
    """Create steps (inserted out of order on purpose) and return ids by order."""

    async def _do(session):
        import uuid

        from app.models import ProcessStep

        ids: dict[int, str] = {}
        orders = list(range(1, len(statuses) + 1))
        for order in reversed(orders):  # deliberately not insertion-ordered
            step = ProcessStep(
                estate_id=uuid.UUID(estate_id),
                order=order,
                name=f"Step {order}",
                status=statuses[order - 1],
                created_by="test",
            )
            session.add(step)
            ids[order] = str(step.id)
        return [ids[order] for order in orders]

    return asyncio.run(_with_session(_do))


def test_steps_listed_in_order_and_status_patch(estate_id, make_client):
    step_ids = _create_steps(estate_id, [None, None, None])
    client = make_client(EXECUTOR)

    listed = client.get("/process/steps").json()
    assert [step["order"] for step in listed] == [1, 2, 3]
    assert [step["id"] for step in listed] == step_ids

    response = client.patch(f"/process/steps/{step_ids[0]}", json={"status": "done"})
    assert response.status_code == 200
    assert response.json()["status"] == "done"

    # Status is the only writable field, and its vocabulary is fixed.
    assert (
        client.patch(f"/process/steps/{step_ids[0]}", json={"status": "finished"})
    ).status_code == 422

    viewer = make_client(VIEWER)
    assert (
        viewer.patch(f"/process/steps/{step_ids[1]}", json={"status": "done"})
    ).status_code == 403

    events = client.get("/audit", params={"entity": f"process_step:{step_ids[0]}"}).json()
    assert any(event["action"] == "update" for event in events)


def test_timeline_derives_done_current_upcoming_with_deadline_join(estate_id, make_client):
    step_ids = _create_steps(estate_id, ["done", None, None])

    async def _attach_deadline(session):
        import uuid

        from app.models import Deadline, ProcessStep

        deadline = Deadline(
            estate_id=uuid.UUID(estate_id),
            type="iht_payment",
            derived_date=dt.date(2026, 7, 31),
            created_by="test",
        )
        session.add(deadline)
        await session.flush()
        step = await session.get(ProcessStep, uuid.UUID(step_ids[1]))
        step.deadline_id = deadline.id
        session.add(step)

    asyncio.run(_with_session(_attach_deadline))

    client = make_client(EXECUTOR)
    timeline = client.get("/process/timeline").json()

    assert [entry["derived_status"] for entry in timeline] == ["done", "current", "upcoming"]
    assert timeline[1]["deadline_type"] == "iht_payment"
    assert timeline[1]["deadline_date"] == "2026-07-31"
    assert timeline[0]["deadline_date"] is None

    viewer = make_client(VIEWER)
    assert viewer.get("/process/timeline").status_code == 200


def _add_recompute_inputs(estate_id: str) -> None:
    """An ISA asset and a placed Section 27 notice, so those deadlines apply."""

    async def _do(session):
        import uuid

        from app.models import Asset, CreditorNotice

        session.add(
            Asset(
                estate_id=uuid.UUID(estate_id),
                category="cash_and_savings",
                sub_type="cash_and_isa",
                description="Demo ISA",
                created_by="test",
            )
        )
        session.add(
            CreditorNotice(
                estate_id=uuid.UUID(estate_id),
                gazette_ref="DEMO-1",
                gazette_date=dt.date(2026, 3, 10),
                local_paper="Demo Gazette",
                local_date=dt.date(2026, 3, 12),
                created_by="test",
            )
        )

    asyncio.run(_with_session(_do))


def test_recompute_derives_statutory_dates_from_date_of_death(estate_id, make_client):
    _add_recompute_inputs(estate_id)
    client = make_client(EXECUTOR)

    response = client.post("/deadlines/recompute")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 4
    assert body["updated"] == 0

    by_type = {item["type"]: item for item in body["deadlines"]}
    # dod 2026-01-15: end of the sixth month after the month of death.
    assert by_type["iht_payment"]["derived_date"] == "2026-07-31"
    # 12 months from the end of the month of death.
    assert by_type["iht400_filing"]["derived_date"] == "2027-01-31"
    # Later notice date 2026-03-12 plus two months and one day.
    assert by_type["s27_claim"]["derived_date"] == "2026-05-13"
    # Third anniversary of death (administration not completed).
    assert by_type["isa_exemption_end"]["derived_date"] == "2029-01-15"

    # Citations from the domain module ride along in the reminders JSON.
    assert "IHTA 1984 s.226" in by_type["iht_payment"]["reminders"][0]["basis"]
    assert "IHTA 1984 s.216" in by_type["iht400_filing"]["reminders"][0]["basis"]
    assert "Trustee Act 1925 s.27" in by_type["s27_claim"]["reminders"][0]["basis"]

    # Recompute is an upsert, not an append.
    second = client.post("/deadlines/recompute").json()
    assert second["created"] == 0
    assert second["updated"] == 4

    everything = client.get("/deadlines", params={"include_past": "true"}).json()
    assert len(everything) == 4
    dates = [item["derived_date"] for item in everything]
    assert dates == sorted(dates)


def test_deadlines_listing_hides_past_dates_by_default(estate_id, make_client):
    _add_recompute_inputs(estate_id)
    client = make_client(EXECUTOR)
    client.post("/deadlines/recompute")

    upcoming = client.get("/deadlines").json()
    everything = client.get("/deadlines", params={"include_past": "true"}).json()

    today = dt.date.today().isoformat()
    assert all(item["derived_date"] >= today for item in upcoming)
    assert len(everything) >= len(upcoming)
    upcoming_dates = [item["derived_date"] for item in upcoming]
    assert upcoming_dates == sorted(upcoming_dates)


def test_recompute_requires_write_role_and_date_of_death(clean_db, make_client):
    viewer = make_client(VIEWER)
    assert viewer.post("/deadlines/recompute").status_code == 403

    async def _estate_without_dod(session):
        from app.models import Estate

        session.add(Estate(name="No DoD Estate (test)", created_by="test"))

    asyncio.run(_with_session(_estate_without_dod))
    client = make_client(EXECUTOR)
    response = client.post("/deadlines/recompute")
    assert response.status_code == 400
    assert "date of death" in response.json()["detail"]

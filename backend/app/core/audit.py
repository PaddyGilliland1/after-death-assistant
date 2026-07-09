"""Audit trail helper.

Every write route must call emit_audit so each change is attributable
(contract section 8). The audit_event model is owned by the models package,
which may not exist yet during early scaffolding, so the import is lazy and
guarded: until the model lands, events are logged instead of persisted and
the helper reports False.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _load_audit_model() -> type | None:
    """Import the AuditEvent model lazily; return None if not available yet."""
    try:
        from app.models import AuditEvent  # type: ignore[attr-defined]

        return AuditEvent
    except Exception:  # noqa: BLE001 - models package may not exist yet
        return None


async def emit_audit(
    actor: str,
    action: str,
    entity: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    *,
    estate_id: Any = None,
    session: AsyncSession | None = None,
) -> bool:
    """Record an audit event.

    Args:
        actor: email of the user (or agent identifier) performing the action.
        action: verb, for example "create", "update", "archive", "approve".
        entity: entity reference, for example "asset:UUID".
        before: prior state snapshot, if any.
        after: new state snapshot, if any.
        estate_id: UUID of the estate the change belongs to. Required for
            persistence: audit_event rows are estate-scoped (NOT NULL), so
            without it the event is logged but not persisted.
        session: optional open AsyncSession to enlist in; when omitted a
            short-lived session is used and committed.

    Returns:
        True if a row was persisted, False if the model is not yet available
        (the event is still logged, so nothing is silently lost).
    """
    timestamp = datetime.now(UTC)
    audit_model = _load_audit_model()

    if audit_model is None or estate_id is None:
        logger.info(
            "audit (not persisted%s): actor=%s action=%s entity=%s at=%s",
            "" if audit_model is None else ", no estate_id",
            actor,
            action,
            entity,
            timestamp.isoformat(),
        )
        return False

    event = audit_model(
        estate_id=estate_id,
        actor=actor,
        action=action,
        entity=entity,
        before=before,
        after=after,
        timestamp=timestamp,
    )

    if session is not None:
        session.add(event)
        await session.flush()
        return True

    from app.db import get_session_factory

    async with get_session_factory()() as own_session:
        own_session.add(event)
        await own_session.commit()
    return True

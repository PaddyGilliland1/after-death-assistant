"""IHT assessment snapshots produced by the deterministic engine.

The engine (app/domain/iht_engine.py) computes every figure; this table only
stores immutable snapshots of its output with the constants version used.
"""

from sqlalchemy import JSON
from sqlmodel import Field

from .base import EstateScopedBase


class IhtAssessment(EstateScopedBase, table=True):
    """A point-in-time IHT assessment snapshot (build contract section 6)."""

    __tablename__ = "iht_assessment"

    snapshot: dict = Field(
        default_factory=dict,
        sa_type=JSON,
        description=(
            "Engine output: allowances, taxable, tax, route, "
            "required_schedules and the inputs used"
        ),
    )
    constants_version: str = Field(
        default="", description="Version of the tax constants the engine used"
    )

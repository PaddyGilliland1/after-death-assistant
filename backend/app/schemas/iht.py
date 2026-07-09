"""Schemas for the IHT workbench endpoints.

An assessment response is a stored engine snapshot: the inputs the engine
was given and every figure it produced. Nothing here computes; parsing a
stored decimal string back to Decimal is deserialisation, not arithmetic.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class IhtAssessmentRead(BaseModel):
    """A persisted IHT assessment snapshot (engine output plus inputs)."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    estate_id: uuid.UUID
    created_at: dt.datetime
    constants_version: str
    jurisdiction_code: str
    inputs: dict[str, Any]
    nrb: Decimal
    rnrb_max: Decimal
    rnrb: Decimal
    allowance: Decimal
    taxable: Decimal
    rate: Decimal
    tax: Decimal
    is_excepted: bool
    must_file_iht400: bool
    required_schedules: list[str]

    @classmethod
    def from_row(cls, row: Any) -> "IhtAssessmentRead":
        """Build the response from an iht_assessment row's snapshot JSON."""
        result = row.snapshot.get("result", {})
        return cls(
            id=row.id,
            estate_id=row.estate_id,
            created_at=row.created_at,
            constants_version=row.constants_version,
            jurisdiction_code=result.get("jurisdiction_code", ""),
            inputs=row.snapshot.get("inputs", {}),
            nrb=Decimal(result["nrb"]),
            rnrb_max=Decimal(result["rnrb_max"]),
            rnrb=Decimal(result["rnrb"]),
            allowance=Decimal(result["allowance"]),
            taxable=Decimal(result["taxable"]),
            rate=Decimal(result["rate"]),
            tax=Decimal(result["tax"]),
            is_excepted=result["is_excepted"],
            must_file_iht400=result["must_file_iht400"],
            required_schedules=list(result.get("required_schedules", [])),
        )


class ScheduleItem(BaseModel):
    """A required supplementary schedule with a plain-English reason."""

    code: str
    reason: str


class IhtSchedulesRead(BaseModel):
    """Required schedules derived by the engine in the latest assessment."""

    assessment_id: uuid.UUID
    assessed_at: dt.datetime
    must_file_iht400: bool
    schedules: list[ScheduleItem]

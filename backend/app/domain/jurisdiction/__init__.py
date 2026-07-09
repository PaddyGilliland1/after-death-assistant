"""Jurisdiction interface for the domain core.

Jurisdiction-specific tax constants and rules (excepted estate tests,
schedule mappings) live behind this interface so that other regimes can
be added without touching the pure engine. Every constant carries
provenance: its value, source URL and fetch date (contract guardrail 3).

Pure module: no I/O, no clock reads, no environment access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:  # avoids a runtime circular import with the engine
    from app.domain.iht_engine import Estate


class ProvenancedValue(BaseModel):
    """A tax constant with its provenance (guardrail 3)."""

    model_config = ConfigDict(frozen=True)

    value: Decimal
    source_url: str
    fetch_date: date


class Jurisdiction(ABC):
    """Interface every tax regime must implement.

    Concrete jurisdictions expose their constants as ProvenancedValue
    attributes and implement the behavioural rules the engine delegates.
    """

    code: ClassVar[str]
    name: ClassVar[str]

    # -- Constants (each a ProvenancedValue) --------------------------------
    nrb: ProvenancedValue
    rnrb: ProvenancedValue
    taper_threshold: ProvenancedValue
    charity_rate_threshold: ProvenancedValue
    standard_rate: ProvenancedValue
    reduced_rate: ProvenancedValue

    # -- Rules ---------------------------------------------------------------
    @abstractmethod
    def is_excepted(self, estate: Estate) -> bool:
        """Whether the estate qualifies as excepted (no full account needed)."""

    @abstractmethod
    def required_schedules(self, estate: Estate) -> tuple[str, ...]:
        """The supplementary schedule codes a full account would require,
        derived data-driven from asset categories and claims."""


from app.domain.jurisdiction.england_wales import (  # noqa: E402
    ENGLAND_WALES,
    EnglandWales,
)

__all__ = [
    "ENGLAND_WALES",
    "EnglandWales",
    "Jurisdiction",
    "ProvenancedValue",
]

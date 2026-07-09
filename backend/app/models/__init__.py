"""AD Assistant data model: SQLModel tables per build contract section 6.

Importing this package registers every table on SQLModel.metadata, which is
what Alembic autogenerate and create_all consume.
"""

from .admin_tax import AdminTax
from .assets import Asset, ValuationEvent
from .audit import Approval, AuditEvent
from .base import (
    EstateScopedBase,
    MoneyType,
    PctType,
    SoftDeleteMixin,
    TableBase,
    TZDateTime,
    utcnow,
)
from .beneficiaries import BeneficiaryLegacy, Distribution
from .contacts import Contact, ContactInteraction
from .costs import Cost
from .debtors_creditors import Creditor, CreditorNotice, Debtor, NoticeClaim
from .decisions import Decision
from .digital import DigitalItem
from .documents import Document
from .enums import (
    ContactCategory,
    IhtTreatment,
    LegacyType,
    OwnershipType,
    ReliefType,
    ValueBasis,
    str_enum_type,
)
from .estate import Estate
from .iht import IhtAssessment
from .knowledge import KnowledgeChunk, KnowledgeDoc
from .liabilities import Liability
from .links import Link
from .notifications import Notification
from .process import Deadline, ProcessStep
from .reliefs import Relief
from .tasks import Task, TaskComment

__all__ = [
    # Bases and helpers
    "TableBase",
    "SoftDeleteMixin",
    "EstateScopedBase",
    "TZDateTime",
    "MoneyType",
    "PctType",
    "utcnow",
    "str_enum_type",
    # Enums
    "ContactCategory",
    "OwnershipType",
    "ValueBasis",
    "IhtTreatment",
    "LegacyType",
    "ReliefType",
    # Tables
    "Estate",
    "Contact",
    "ContactInteraction",
    "Asset",
    "ValuationEvent",
    "Liability",
    "Debtor",
    "Creditor",
    "CreditorNotice",
    "NoticeClaim",
    "Cost",
    "Decision",
    "BeneficiaryLegacy",
    "Distribution",
    "Task",
    "TaskComment",
    "ProcessStep",
    "Deadline",
    "Document",
    "IhtAssessment",
    "Relief",
    "AdminTax",
    "DigitalItem",
    "KnowledgeDoc",
    "KnowledgeChunk",
    "Notification",
    "AuditEvent",
    "Approval",
    "Link",
]

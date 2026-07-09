"""Str-based enums for the AD Assistant data model.

Stored as plain strings (native_enum=False) to keep Alembic migrations
simple. Only enums named in build contract section 6 are defined here;
free-text status fields stay as strings until the contract fixes their
vocabulary.
"""

from enum import Enum, StrEnum

from sqlalchemy import Enum as SAEnum


def str_enum_type(enum_cls: type[Enum]) -> SAEnum:
    """Build a string-backed SQLAlchemy Enum type for a Python enum.

    native_enum=False stores VARCHAR with a CHECK constraint rather than a
    Postgres ENUM type, which keeps migrations trivial. values_callable
    ensures the enum values (not member names) are persisted.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        values_callable=lambda e: [member.value for member in e],
        length=64,
    )


class ContactCategory(StrEnum):
    """Contact category (build contract section 6, contact.category)."""

    bank = "bank"
    nsandi = "nsandi"
    insurer = "insurer"
    pension = "pension"
    utility = "utility"
    telecom = "telecom"
    tv_licensing = "tv_licensing"
    streaming = "streaming"
    council = "council"
    hmrc = "hmrc"
    probate_registry = "probate_registry"
    solicitor = "solicitor"
    accountant = "accountant"
    valuer = "valuer"
    registrar = "registrar"
    gp = "gp"
    dentist = "dentist"
    optician = "optician"
    employer = "employer"
    landlord = "landlord"
    care_agency = "care_agency"
    beneficiary = "beneficiary"
    gift_recipient = "gift_recipient"
    creditor = "creditor"
    debtor = "debtor"
    executor = "executor"
    membership = "membership"
    other = "other"


class OwnershipType(StrEnum):
    """How an asset was owned at the date of death."""

    sole = "sole"
    joint_tenants = "joint_tenants"
    tenants_in_common = "tenants_in_common"


class ValueBasis(StrEnum):
    """Whether a value is an estimate or confirmed by evidence."""

    estimate = "estimate"
    confirmed = "confirmed"


class IhtTreatment(StrEnum):
    """IHT treatment of a cost (funeral costs deduct; admin costs do not)."""

    funeral_deductible = "funeral_deductible"
    admin_not_deductible = "admin_not_deductible"


class LegacyType(StrEnum):
    """Type of legacy left to a beneficiary."""

    pecuniary = "pecuniary"
    specific = "specific"
    residuary = "residuary"


class ReliefType(StrEnum):
    """Post-death relief or reclaim being tracked."""

    iht35 = "iht35"
    iht38 = "iht38"
    rnrb_downsizing = "rnrb_downsizing"
    bpr_apr = "bpr_apr"

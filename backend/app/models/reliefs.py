"""Post-death reliefs and reclaims (IHT35, IHT38, RNRB downsizing, BPR/APR)."""

import datetime as dt
import uuid
from decimal import Decimal

from sqlmodel import Field

from .base import EstateScopedBase, MoneyType
from .enums import ReliefType, str_enum_type


class Relief(EstateScopedBase, table=True):
    """A relief or reclaim being tracked (build contract section 6)."""

    __tablename__ = "relief"

    relief_type: ReliefType = Field(sa_type=str_enum_type(ReliefType), index=True)
    asset_id: uuid.UUID | None = Field(
        default=None, foreign_key="asset.id", index=True
    )
    probate_value: Decimal | None = Field(default=None, sa_type=MoneyType)
    sale_value: Decimal | None = Field(default=None, sa_type=MoneyType)
    sale_date: dt.date | None = Field(default=None)
    window_deadline: dt.date | None = Field(
        default=None, description="Last date the relief can be claimed"
    )
    potential_reclaim: Decimal | None = Field(default=None, sa_type=MoneyType)
    status: str | None = Field(default=None)

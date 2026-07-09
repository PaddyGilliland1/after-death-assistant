"""England and Wales inheritance tax constants and rules.

Constants carry provenance (value, source URL, fetch date) per contract
guardrail 3. The fetch date below records when these published values
were last checked against their sources; refreshing them is an ingest
concern, never a runtime concern for this pure module.

Pure module: no I/O, no clock reads, no environment access.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar

from app.domain.jurisdiction import Jurisdiction, ProvenancedValue

if TYPE_CHECKING:  # avoids a runtime circular import with the engine
    from app.domain.iht_engine import Estate

_FETCH_DATE = date(2026, 7, 6)

_RATES_URL = (
    "https://www.gov.uk/guidance/rates-and-allowances-inheritance-tax-"
    "thresholds-and-interest-rates"
)
_RNRB_URL = "https://www.gov.uk/guidance/inheritance-tax-residence-nil-rate-band"
_CHARITY_URL = (
    "https://www.gov.uk/donating-to-charity/leaving-gifts-to-charity-in-your-will"
)
_EXCEPTED_URL = "https://www.legislation.gov.uk/uksi/2021/1167"


class EnglandWales(Jurisdiction):
    """The England and Wales regime, deaths on or after 1 January 2022."""

    code: ClassVar[str] = "england_wales"
    name: ClassVar[str] = "England and Wales"

    # -- Core constants ------------------------------------------------------
    nrb = ProvenancedValue(
        value=Decimal("325000"), source_url=_RATES_URL, fetch_date=_FETCH_DATE
    )
    rnrb = ProvenancedValue(
        value=Decimal("175000"), source_url=_RATES_URL, fetch_date=_FETCH_DATE
    )
    taper_threshold = ProvenancedValue(
        value=Decimal("2000000"), source_url=_RNRB_URL, fetch_date=_FETCH_DATE
    )
    charity_rate_threshold = ProvenancedValue(
        value=Decimal("0.10"), source_url=_CHARITY_URL, fetch_date=_FETCH_DATE
    )
    standard_rate = ProvenancedValue(
        value=Decimal("0.40"), source_url=_RATES_URL, fetch_date=_FETCH_DATE
    )
    reduced_rate = ProvenancedValue(
        value=Decimal("0.36"), source_url=_CHARITY_URL, fetch_date=_FETCH_DATE
    )

    # -- Excepted estate limits (SI 2004/2543 as amended by SI 2021/1167) ----
    excepted_exempt_estate_limit = ProvenancedValue(
        value=Decimal("3000000"), source_url=_EXCEPTED_URL, fetch_date=_FETCH_DATE
    )
    excepted_specified_transfers_limit = ProvenancedValue(
        value=Decimal("250000"), source_url=_EXCEPTED_URL, fetch_date=_FETCH_DATE
    )
    excepted_trust_property_limit = ProvenancedValue(
        value=Decimal("250000"), source_url=_EXCEPTED_URL, fetch_date=_FETCH_DATE
    )
    excepted_foreign_property_limit = ProvenancedValue(
        value=Decimal("100000"), source_url=_EXCEPTED_URL, fetch_date=_FETCH_DATE
    )

    # -- Data-driven schedule mappings ---------------------------------------
    # Asset category to supplementary schedule code. Category keys are the
    # string values of iht_engine.AssetCategory (kept as strings so this
    # table stays data, not code).
    CATEGORY_SCHEDULE_MAP: ClassVar[Mapping[str, str]] = {
        "land_and_buildings": "IHT405",
        "bank_accounts": "IHT406",
        "nsandi": "IHT406",
        "household_goods": "IHT407",
        "gifts": "IHT403",
        "listed_shares": "IHT411",
        "unlisted_shares": "IHT412",
    }

    # -- Rules ---------------------------------------------------------------
    def _disqualifiers(self, estate: Estate) -> tuple[tuple[str, bool], ...]:
        """Data-driven disqualifier table for excepted status.

        Each entry is (description, disqualified). A fact left as None is
        unknown and disqualifies, because an estate can only be excepted
        when the facts are established (conservative rule).
        """
        gifts = estate.gifts_in_seven_years
        trust = estate.trust_assets_value
        foreign = estate.foreign_assets_value
        grob = estate.gifts_with_reservation

        return (
            (
                "residence nil rate band claimed (requires a full account)",
                estate.rnrb_claimed,
            ),
            (
                "gifts with reservation of benefit present or unknown",
                grob is None or grob,
            ),
            (
                "foreign assets unknown or above the 100000 limit",
                foreign is None
                or foreign > self.excepted_foreign_property_limit.value,
            ),
            (
                "settled property unknown or above the 250000 limit",
                trust is None
                or trust > self.excepted_trust_property_limit.value,
            ),
            (
                "more than one trust, or trust structure unknown",
                trust is not None
                and trust > 0
                and (estate.trust_count is None or estate.trust_count > 1),
            ),
            (
                "specified lifetime transfers in the seven years before "
                "death unknown or above the 250000 limit",
                gifts is None
                or gifts > self.excepted_specified_transfers_limit.value,
            ),
        )

    def is_excepted(self, estate: Estate) -> bool:
        """Excepted estate test for deaths on or after 1 January 2022.

        Implements the Inheritance Tax (Delivery of Accounts) (Excepted
        Estates) Regulations 2004 (SI 2004/2543), as amended for deaths
        on or after 1 January 2022 by SI 2021/1167. Guidance:
        https://www.gov.uk/valuing-estate-of-someone-who-died/
        check-type-of-estate (fetched 2026-07-06).

        Categories:
        - Category 1 (low value): gross estate value plus specified
          transfers within the nil rate band (plus a transferred nil
          rate band only when 100 per cent is transferred from one
          predeceased spouse or civil partner; a partial transfer
          requires a full account).
        - Category 2 (exempt): gross estate plus specified transfers
          within 3000000 AND the net chargeable value after spouse and
          charity exemptions within the nil rate band.

        Disqualifiers (any true, or any fact UNKNOWN, means NOT
        excepted, so must_file_iht400): gifts with reservation of
        benefit; foreign assets above 100000; settled property above
        250000 or held in more than one trust; specified lifetime
        transfers above 250000 in the seven years before death; a
        residence nil rate band claim.
        """
        if any(disqualified for _, disqualified in self._disqualifiers(estate)):
            return False

        gross = (
            estate.gross_value
            if estate.gross_value is not None
            else estate.net_value
        )
        gifts = estate.gifts_in_seven_years or Decimal("0")

        usable_tnrb = (
            estate.tnrb_pct if estate.tnrb_pct == Decimal("1") else Decimal("0")
        )
        available_nrb = self.nrb.value * (1 + usable_tnrb)

        gross_plus_gifts = gross + gifts
        if gross_plus_gifts <= available_nrb:
            return True  # Category 1: low value excepted estate
        if (
            gross_plus_gifts <= self.excepted_exempt_estate_limit.value
            and gross_plus_gifts - estate.exempt_transfers <= available_nrb
        ):
            return True  # Category 2: exempt excepted estate
        return False

    def required_schedules(self, estate: Estate) -> tuple[str, ...]:
        """Derive the supplementary schedules from claims and categories."""
        codes: set[str] = set()

        if estate.tnrb_pct > 0:
            codes.add("IHT402")
        if estate.rnrb_claimed:
            codes.add("IHT435")
            if estate.trnrb_pct > 0:
                codes.add("IHT436")
        if (estate.gifts_in_seven_years or Decimal("0")) > 0 or (
            estate.gifts_with_reservation is True
        ):
            codes.add("IHT403")

        for asset in estate.assets:
            schedule = self.CATEGORY_SCHEDULE_MAP.get(asset.category.value)
            if schedule is not None:
                codes.add(schedule)

        return tuple(sorted(codes))


ENGLAND_WALES = EnglandWales()

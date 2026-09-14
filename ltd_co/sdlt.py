"""
SDLT for England & Northern Ireland — personal additional dwelling vs company.

Personal additional dwelling: residential bands + ADS (5% from 31 Oct 2024).
Company:
  - Higher rates (same as ADS) always apply to company purchases of dwellings.
  - If consideration > £500,000 and rental-business relief is OFF, the 17%
    envelope rate (FA 2003 Sch 4A) applies to the whole price.
  - Rental-business relief (Sch 4A para 5) default ON for this landlord MVP,
    so companies pay higher rates, not the 17% flat rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ltd_co.money import ZERO, clamp0, money, money0
from ltd_co.rates import RatePack, SdltBand


@dataclass(frozen=True)
class SdltBandCharge:
    band: str
    slice_amount: Decimal
    rate: Decimal
    tax: Decimal

    def to_dict(self) -> dict:
        from ltd_co.money import to_float

        return {
            "band": self.band,
            "slice": to_float(self.slice_amount),
            "rate": to_float(self.rate, places=4),
            "tax": to_float(self.tax),
        }


@dataclass(frozen=True)
class SdltResult:
    consideration: Decimal
    purchaser: str
    regime: str
    rental_business_relief: bool | None
    total: Decimal
    breakdown: tuple[SdltBandCharge, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        from ltd_co.money import to_float

        return {
            "consideration": to_float(self.consideration),
            "purchaser": self.purchaser,
            "regime": self.regime,
            "rentalBusinessRelief": self.rental_business_relief,
            "total": to_float(self.total),
            "breakdown": [b.to_dict() for b in self.breakdown],
            "jurisdiction": "england-ni",
            "notes": list(self.notes),
        }


def _banded(
    price: Decimal,
    bands: tuple[SdltBand, ...],
    surcharge: Decimal,
) -> tuple[Decimal, list[SdltBandCharge]]:
    remaining = price
    prev = ZERO
    total = ZERO
    rows: list[SdltBandCharge] = []
    for band in bands:
        cap = band.up_to
        width = remaining if cap is None else (cap - prev)
        if width < 0:
            width = ZERO
        taxable = remaining if remaining < width else width
        if taxable <= 0:
            break
        rate = band.rate + surcharge
        tax = money(taxable * rate)
        if cap is None:
            label = f"Over {prev:,.0f}"
        else:
            label = f"{prev + 1:,.0f} - {cap:,.0f}"
        if surcharge > 0:
            label = f"{label} (incl. ADS {surcharge})"
        if tax > 0 or rate > 0:
            rows.append(
                SdltBandCharge(
                    band=label,
                    slice_amount=money(taxable),
                    rate=rate,
                    tax=tax,
                )
            )
        total = money(total + tax)
        remaining = money(remaining - taxable)
        prev = cap if cap is not None else prev
        if remaining <= 0:
            break
    return money0(total), rows


def compute_sdlt(
    *,
    consideration: Decimal,
    packs: RatePack,
    purchaser: str = "personal_additional",
    rental_business_relief: bool | None = None,
) -> SdltResult:
    """
    purchaser: 'personal_additional' | 'company'
    """
    price = clamp0(consideration)
    notes: list[str] = []
    sdlt = packs.sdlt
    relief = (
        sdlt.rental_business_relief_default
        if rental_business_relief is None
        else bool(rental_business_relief)
    )

    if price < sdlt.minimum_consideration:
        notes.append(
            f"Consideration below £{sdlt.minimum_consideration} higher-rates minimum; "
            "returning £0 (MVP does not model sub-threshold edge cases)."
        )
        return SdltResult(
            consideration=price,
            purchaser=purchaser,
            regime="below_minimum",
            rental_business_relief=relief if purchaser == "company" else None,
            total=ZERO,
            breakdown=(),
            notes=tuple(notes),
        )

    if purchaser == "company":
        over_envelope = (
            price >= sdlt.corporate_envelope_threshold
            if sdlt.corporate_envelope_threshold_inclusive
            else price > sdlt.corporate_envelope_threshold
        )
        if over_envelope and not relief:
            tax = money0(price * sdlt.corporate_envelope_flat_rate)
            notes.append(
                "Rental-business relief OFF and consideration above the envelope "
                f"threshold (£{sdlt.corporate_envelope_threshold}): FA 2003 Sch 4A "
                f"flat rate {sdlt.corporate_envelope_flat_rate} on the whole price."
            )
            row = SdltBandCharge(
                band=f"Envelope flat rate {sdlt.corporate_envelope_flat_rate}",
                slice_amount=price,
                rate=sdlt.corporate_envelope_flat_rate,
                tax=tax,
            )
            return SdltResult(
                consideration=price,
                purchaser="company",
                regime="corporate_envelope_flat",
                rental_business_relief=False,
                total=tax,
                breakdown=(row,),
                notes=tuple(notes),
            )
        if over_envelope and relief:
            notes.append(
                "Rental-business relief ON (FA 2003 Sch 4A para 5 default for this MVP): "
                "17% envelope rate disapplied; higher rates (ADS-equivalent) apply."
            )
        else:
            notes.append(
                "Company dwelling purchase: higher rates apply "
                "(companies do not get main-residence treatment)."
            )
        total, rows = _banded(
            price, sdlt.residential_bands, sdlt.additional_dwelling_surcharge
        )
        return SdltResult(
            consideration=price,
            purchaser="company",
            regime="higher_rates_rental_relief" if relief else "higher_rates",
            rental_business_relief=relief,
            total=total,
            breakdown=tuple(rows),
            notes=tuple(notes),
        )

    if purchaser != "personal_additional":
        raise ValueError("purchaser must be 'personal_additional' or 'company'")

    notes.append(
        f"Personal additional dwelling: residential bands + {sdlt.additional_dwelling_surcharge} ADS. "
        "England & Northern Ireland only."
    )
    total, rows = _banded(
        price, sdlt.residential_bands, sdlt.additional_dwelling_surcharge
    )
    return SdltResult(
        consideration=price,
        purchaser="personal_additional",
        regime="higher_rates_ads",
        rental_business_relief=None,
        total=total,
        breakdown=tuple(rows),
        notes=tuple(notes),
    )


def compare_sdlt(
    *,
    consideration: Decimal,
    packs: RatePack,
    rental_business_relief: bool | None = None,
) -> dict:
    personal = compute_sdlt(
        consideration=consideration,
        packs=packs,
        purchaser="personal_additional",
    )
    company = compute_sdlt(
        consideration=consideration,
        packs=packs,
        purchaser="company",
        rental_business_relief=rental_business_relief,
    )
    delta = money(company.total - personal.total)
    from ltd_co.money import to_float

    return {
        "consideration": to_float(clamp0(consideration)),
        "personalAdditional": personal.to_dict(),
        "company": company.to_dict(),
        "deltaCompanyMinusPersonal": to_float(delta),
        "rentalBusinessReliefApplied": company.rental_business_relief,
    }

"""
Corporation tax with associated-company threshold division and marginal relief.

CTA 2010 ss18A–18E (FY2023 onwards). Limits are divided by (1 + N) where N is
the number of *other* associated companies. 12-month AP assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ltd_co.money import ZERO, clamp0, money, ratio
from ltd_co.rates import RatePack


@dataclass(frozen=True)
class CorporationTaxResult:
    taxable_profits: Decimal
    augmented_profits: Decimal
    associated_companies: int
    divisor: int
    lower_limit: Decimal
    upper_limit: Decimal
    band: str  # small_profits | marginal_relief | main_rate | loss
    main_rate_tax: Decimal
    marginal_relief: Decimal
    corporation_tax: Decimal
    effective_rate: Decimal
    losses_carried_forward: Decimal
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        from ltd_co.money import to_float

        return {
            "taxableProfits": to_float(self.taxable_profits),
            "augmentedProfits": to_float(self.augmented_profits),
            "associatedCompanies": self.associated_companies,
            "divisor": self.divisor,
            "lowerLimit": to_float(self.lower_limit),
            "upperLimit": to_float(self.upper_limit),
            "band": self.band,
            "mainRateTax": to_float(self.main_rate_tax),
            "marginalRelief": to_float(self.marginal_relief),
            "corporationTax": to_float(self.corporation_tax),
            "effectiveRate": to_float(self.effective_rate, places=6),
            "lossesCarriedForward": to_float(self.losses_carried_forward),
            "notes": list(self.notes),
        }


def associated_divisor(associated_companies: int) -> int:
    if associated_companies < 0:
        raise ValueError("associatedCompanies must be >= 0 (count of other associated companies)")
    return associated_companies + 1


def compute_corporation_tax(
    *,
    taxable_profits: Decimal,
    packs: RatePack,
    associated_companies: int = 0,
    augmented_profits: Decimal | None = None,
    losses_brought_forward: Decimal = ZERO,
) -> CorporationTaxResult:
    notes: list[str] = []
    ct = packs.corporation_tax
    divisor = associated_divisor(associated_companies)
    lower = money(ct.lower_limit / divisor)
    upper = money(ct.upper_limit / divisor)

    profits_in = money(taxable_profits)
    bf = clamp0(losses_brought_forward)
    loss_cf = ZERO

    if profits_in < 0:
        loss_cf = money(-profits_in + bf)
        taxable = ZERO
        notes.append("Current-year loss: no CT due; losses carried forward.")
    elif bf > 0:
        if bf >= profits_in:
            loss_cf = money(bf - profits_in)
            taxable = ZERO
            notes.append("Losses brought forward absorbed current-year profits.")
        else:
            taxable = money(profits_in - bf)
    else:
        taxable = profits_in if profits_in > 0 else ZERO

    aug = money(augmented_profits) if augmented_profits is not None else taxable
    if aug < taxable:
        aug = taxable
        notes.append("Augmented profits raised to taxable profits (cannot be lower).")

    if taxable <= 0:
        return CorporationTaxResult(
            taxable_profits=ZERO,
            augmented_profits=aug if aug > 0 else ZERO,
            associated_companies=associated_companies,
            divisor=divisor,
            lower_limit=lower,
            upper_limit=upper,
            band="loss",
            main_rate_tax=ZERO,
            marginal_relief=ZERO,
            corporation_tax=ZERO,
            effective_rate=ZERO,
            losses_carried_forward=loss_cf,
            notes=tuple(notes),
        )

    main_rate_tax = money(taxable * ct.main_rate)

    if aug <= lower:
        tax = money(taxable * ct.small_profits_rate)
        mr = ZERO
        band = "small_profits"
        notes.append(
            f"Augmented profits ≤ lower limit £{lower} "
            f"(£{ct.lower_limit} / {divisor} associated-company divisor)."
        )
    elif aug >= upper:
        tax = main_rate_tax
        mr = ZERO
        band = "main_rate"
        notes.append(
            f"Augmented profits ≥ upper limit £{upper} "
            f"(£{ct.upper_limit} / {divisor}); main rate {ct.main_rate}."
        )
    else:
        # MR = (U - A) × (N / A) × F
        F = ratio(ct.mr_numerator, ct.mr_denominator)
        if aug == 0:
            mr = ZERO
        else:
            mr = money((upper - aug) * (taxable / aug) * F)
        tax = money(main_rate_tax - mr)
        if tax < 0:
            tax = ZERO
        band = "marginal_relief"
        notes.append(
            "Marginal relief = (upper − augmented) × (taxable / augmented) × "
            f"{ct.mr_numerator}/{ct.mr_denominator}."
        )

    effective = ZERO if taxable == 0 else (tax / taxable)

    return CorporationTaxResult(
        taxable_profits=taxable,
        augmented_profits=aug,
        associated_companies=associated_companies,
        divisor=divisor,
        lower_limit=lower,
        upper_limit=upper,
        band=band,
        main_rate_tax=main_rate_tax,
        marginal_relief=mr,
        corporation_tax=tax,
        effective_rate=effective,
        losses_carried_forward=loss_cf,
        notes=tuple(notes),
    )

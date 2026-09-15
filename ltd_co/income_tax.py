"""
England / NI / Wales income tax for the Ltd Co calculator.

Stacking order (ITA 2007 s16): non-savings, then savings, then dividends.
Personal allowance is tapered by £1 per £2 of adjusted net income above £100,000.
Dividend allowance uses band width at 0%.

Scottish rates are out of scope for this landlord MVP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ltd_co.money import ZERO, clamp0, money
from ltd_co.rates import RatePack


@dataclass
class BandCharge:
    band: str
    kind: str
    amount: Decimal
    rate: Decimal
    tax: Decimal

    def to_dict(self) -> dict:
        from ltd_co.money import to_float

        return {
            "band": self.band,
            "kind": self.kind,
            "amount": to_float(self.amount),
            "rate": to_float(self.rate, places=4),
            "tax": to_float(self.tax),
        }


@dataclass
class IncomeTaxResult:
    non_savings_income: Decimal
    savings_income: Decimal
    dividend_income: Decimal
    adjusted_net_income: Decimal
    personal_allowance: Decimal
    taxable_income: Decimal
    tax_before_reducers: Decimal
    section24_reducer: Decimal
    section24_reducer_applied: Decimal
    income_tax: Decimal
    breakdown: list[BandCharge] = field(default_factory=list)
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        from ltd_co.money import to_float

        return {
            "nonSavingsIncome": to_float(self.non_savings_income),
            "savingsIncome": to_float(self.savings_income),
            "dividendIncome": to_float(self.dividend_income),
            "adjustedNetIncome": to_float(self.adjusted_net_income),
            "personalAllowance": to_float(self.personal_allowance),
            "taxableIncome": to_float(self.taxable_income),
            "taxBeforeReducers": to_float(self.tax_before_reducers),
            "section24Reducer": to_float(self.section24_reducer),
            "section24ReducerApplied": to_float(self.section24_reducer_applied),
            "incomeTax": to_float(self.income_tax),
            "breakdown": [b.to_dict() for b in self.breakdown],
            "notes": list(self.notes),
        }


def personal_allowance(adjusted_net_income: Decimal, packs: RatePack) -> Decimal:
    it = packs.income_tax
    ani = clamp0(adjusted_net_income)
    pa = it.personal_allowance
    if ani <= it.pa_taper_start:
        return pa
    excess = ani - it.pa_taper_start
    # ITA 2007 s35: reduction is 50% of the excess (implemented as num/den).
    reduction = money(excess * it.pa_taper_num / it.pa_taper_den)
    reduced = money(pa - reduction)
    return reduced if reduced > 0 else ZERO


def _band_name(gross_pos: Decimal, pa: Decimal, packs: RatePack) -> str:
    it = packs.income_tax
    if gross_pos < pa:
        return "personal_allowance"
    if gross_pos < pa + it.basic_rate_band:
        return "basic"
    if gross_pos < it.additional_rate_threshold:
        return "higher"
    return "additional"


def _ns_rate(band: str, packs: RatePack) -> Decimal:
    it = packs.income_tax
    return {
        "personal_allowance": ZERO,
        "basic": it.basic_rate,
        "higher": it.higher_rate,
        "additional": it.additional_rate,
    }[band]


def _div_rate(band: str, packs: RatePack) -> Decimal:
    d = packs.dividends
    return {
        "personal_allowance": ZERO,
        "basic": d.ordinary_rate,
        "higher": d.upper_rate,
        "additional": d.additional_rate,
    }[band]


def _sav_rate(band: str, packs: RatePack) -> Decimal:
    return _ns_rate(band, packs)


def _remaining_in_band(gross_pos: Decimal, pa: Decimal, packs: RatePack) -> Decimal:
    it = packs.income_tax
    band = _band_name(gross_pos, pa, packs)
    if band == "personal_allowance":
        return pa - gross_pos
    if band == "basic":
        return (pa + it.basic_rate_band) - gross_pos
    if band == "higher":
        return it.additional_rate_threshold - gross_pos
    return Decimal("Infinity")


def compute_income_tax(
    *,
    non_savings_income: Decimal,
    packs: RatePack,
    savings_income: Decimal = ZERO,
    dividend_income: Decimal = ZERO,
    section24_reducer: Decimal = ZERO,
) -> IncomeTaxResult:
    ns = clamp0(non_savings_income)
    sav = clamp0(savings_income)
    div = clamp0(dividend_income)
    ani = money(ns + sav + div)
    pa = personal_allowance(ani, packs)

    breakdown: list[BandCharge] = []
    cursor = ZERO
    notes: list[str] = []

    def consume(amount: Decimal, kind: str, rate_fn, allowance_left: Decimal | None = None) -> Decimal:
        nonlocal cursor
        remaining = amount
        tax = ZERO
        allow = allowance_left
        while remaining > 0:
            band = _band_name(cursor, pa, packs)
            band_left = _remaining_in_band(cursor, pa, packs)
            if band_left == Decimal("Infinity"):
                take = remaining
            else:
                take = remaining if remaining < band_left else band_left
            if take <= 0:
                break
            rate = rate_fn(band, packs)
            taxed_amount = take
            applied_rate = rate
            if allow is not None and allow > 0 and kind == "dividend":
                free = take if take < allow else allow
                if free > 0:
                    breakdown.append(
                        BandCharge(
                            band=band,
                            kind="dividend_allowance",
                            amount=money(free),
                            rate=ZERO,
                            tax=ZERO,
                        )
                    )
                    allow = money(allow - free)
                    taxed_amount = money(take - free)
                    cursor = money(cursor + free)
                    remaining = money(remaining - free)
                    if taxed_amount <= 0:
                        continue
                    # rest of `take` at the band rate
                    take_paid = taxed_amount
                    tax_part = money(take_paid * rate)
                    tax = money(tax + tax_part)
                    breakdown.append(
                        BandCharge(
                            band=band,
                            kind=kind,
                            amount=take_paid,
                            rate=applied_rate,
                            tax=tax_part,
                        )
                    )
                    cursor = money(cursor + take_paid)
                    remaining = money(remaining - take_paid)
                    continue
            tax_part = money(take * applied_rate)
            tax = money(tax + tax_part)
            if take > 0:
                breakdown.append(
                    BandCharge(
                        band=band,
                        kind=kind,
                        amount=money(take),
                        rate=applied_rate,
                        tax=tax_part,
                    )
                )
            cursor = money(cursor + take)
            remaining = money(remaining - take)
        return tax

    # Savings: starting rate of 0% on up to £5,000 of savings if non-savings
    # taxable income is below that limit. PSA then applies at 0% by band.
    tax_ns = consume(ns, "non_savings", _ns_rate)

    # Taxable non-savings (after PA) for starting-rate eligibility.
    taxable_ns = ns - pa
    if taxable_ns < 0:
        taxable_ns = ZERO
    starting_left = packs.savings.starting_rate_limit - taxable_ns
    if starting_left < 0:
        starting_left = ZERO

    tax_sav = ZERO
    if sav > 0:
        # Apply 0% starting rate on savings first (occupies income from the bottom
        # of the savings slice, still advancing the cursor).
        start_take = sav if sav < starting_left else starting_left
        if start_take > 0:
            # Consume at 0% without using the generic band rates.
            remaining_start = start_take
            while remaining_start > 0:
                band = _band_name(cursor, pa, packs)
                band_left = _remaining_in_band(cursor, pa, packs)
                take = remaining_start if band_left == Decimal("Infinity") or remaining_start < band_left else band_left
                breakdown.append(
                    BandCharge(band=band, kind="savings_starting_rate", amount=money(take), rate=ZERO, tax=ZERO)
                )
                cursor = money(cursor + take)
                remaining_start = money(remaining_start - take)
            sav_rest = money(sav - start_take)
        else:
            sav_rest = sav

        # Personal savings allowance depends on the highest non-dividend band
        # the taxpayer falls into after this income. Use ANI vs thresholds.
        it = packs.income_tax
        # Highest rate on non-dividend income (ns+sav) determines PSA.
        top = money(ns + sav)
        if top > it.additional_rate_threshold:
            psa = packs.savings.psa_additional
        elif top > (pa + it.basic_rate_band):
            psa = packs.savings.psa_higher
        else:
            psa = packs.savings.psa_basic

        if sav_rest > 0 and psa > 0:
            psa_take = sav_rest if sav_rest < psa else psa
            remaining_psa = psa_take
            while remaining_psa > 0:
                band = _band_name(cursor, pa, packs)
                band_left = _remaining_in_band(cursor, pa, packs)
                take = remaining_psa if band_left == Decimal("Infinity") or remaining_psa < band_left else band_left
                breakdown.append(
                    BandCharge(band=band, kind="personal_savings_allowance", amount=money(take), rate=ZERO, tax=ZERO)
                )
                cursor = money(cursor + take)
                remaining_psa = money(remaining_psa - take)
            sav_rest = money(sav_rest - psa_take)

        if sav_rest > 0:
            tax_sav = consume(sav_rest, "savings", _sav_rate)

    tax_div = consume(div, "dividend", _div_rate, allowance_left=packs.dividends.allowance) if div > 0 else ZERO

    tax_before = money(tax_ns + tax_sav + tax_div)
    reducer = clamp0(section24_reducer)
    applied = reducer if reducer < tax_before else tax_before
    if reducer > tax_before and reducer > 0:
        notes.append(
            "Section 24 reducer capped at income tax liability — it cannot create a refund."
        )
    income_tax = money(tax_before - applied)
    taxable = money(ani - pa) if ani > pa else ZERO

    return IncomeTaxResult(
        non_savings_income=ns,
        savings_income=sav,
        dividend_income=div,
        adjusted_net_income=ani,
        personal_allowance=pa,
        taxable_income=taxable,
        tax_before_reducers=tax_before,
        section24_reducer=reducer,
        section24_reducer_applied=applied,
        income_tax=income_tax,
        breakdown=breakdown,
        notes=tuple(notes),
    )

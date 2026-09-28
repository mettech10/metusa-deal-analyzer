"""
Incorporating a property you already own — keep personally vs move into a company.

Most landlords asking "personal or Ltd?" already own the property, so the
question is whether the company's lower running tax repays the one-off cost
of moving it in:

- CGT: the transfer is a disposal at market value (TCGA 1992 s17/s18,
  connected parties). Gain above the £3,000 annual exempt amount is taxed at
  18% within the remaining basic rate band and 24% above. Incorporation
  relief (s162) can roll the gain into the shares, but only if the letting
  is a business (HMRC/Ramsay test) and it is claimed on the Self Assessment
  return for transfers from 6 April 2026.
- SDLT: the company pays on market value (FA 2003 s53), at company rates.
  Partnership relief (FA 2003 Sch 15) can reduce this for a genuine
  partnership.
- Refinancing: early repayment charge on the personal mortgage plus
  company lending, legal and valuation fees.

Operating years reuse compare_paths (same Section 24, CT, dividend and
2027/28 property-rate logic); only year 0 differs. Soft lean only.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ltd_co.compare import _soft_lean, compare_paths
from ltd_co.income_tax import personal_allowance
from ltd_co.money import D, ZERO, clamp0, money, to_float
from ltd_co.npv import break_even_year, cumulative, npv
from ltd_co.rates import RatePack
from ltd_co.sdlt import compute_sdlt

_DEFAULT_CGT = {
    "annual_exempt_amount": D("3000"),
    "residential_basic_rate": D("0.18"),
    "residential_higher_rate": D("0.24"),
}


def _cgt_rates(packs: RatePack) -> dict[str, Decimal]:
    cg = packs.capital_gains
    if cg is None:
        return dict(_DEFAULT_CGT)
    return {
        "annual_exempt_amount": cg.annual_exempt_amount,
        "residential_basic_rate": cg.residential_basic_rate,
        "residential_higher_rate": cg.residential_higher_rate,
    }


def compute_transfer_cgt(
    *,
    market_value: Decimal,
    base_cost: Decimal,
    disposal_costs: Decimal,
    taxable_income: Decimal,
    other_gains: Decimal,
    incorporation_relief: bool,
    packs: RatePack,
) -> dict[str, Any]:
    rates = _cgt_rates(packs)
    gain = clamp0(market_value - base_cost - disposal_costs)
    if incorporation_relief:
        return {
            "gain": to_float(gain),
            "annualExemptAmountUsed": 0.0,
            "taxableGain": 0.0,
            "basicRatePortion": 0.0,
            "higherRatePortion": 0.0,
            "tax": 0.0,
            "incorporationRelief": True,
            "deferredGain": to_float(gain),
            "notes": [
                "Incorporation relief (TCGA 1992 s162) rolls the gain into the company shares: no CGT now, "
                "but the shares' base cost is reduced by the deferred gain.",
                "Only available if the letting is a business (HMRC's Ramsay test) and all business assets "
                "pass to the company for shares. From 6 April 2026 it must be claimed on your Self "
                "Assessment return for the year of transfer.",
            ],
        }
    aea = rates["annual_exempt_amount"]
    aea_left = clamp0(aea - clamp0(other_gains))
    aea_used = gain if gain < aea_left else aea_left
    taxable_gain = money(gain - aea_used)
    # Gains sit on top of taxable income; other net gains use the band first.
    band = packs.income_tax.basic_rate_band
    band_left = clamp0(band - clamp0(taxable_income) - clamp0(other_gains - aea))
    basic_part = taxable_gain if taxable_gain < band_left else band_left
    higher_part = money(taxable_gain - basic_part)
    tax = money(
        basic_part * rates["residential_basic_rate"] + higher_part * rates["residential_higher_rate"]
    )
    return {
        "gain": to_float(gain),
        "annualExemptAmountUsed": to_float(aea_used),
        "taxableGain": to_float(taxable_gain),
        "basicRatePortion": to_float(basic_part),
        "higherRatePortion": to_float(higher_part),
        "tax": to_float(tax),
        "incorporationRelief": False,
        "deferredGain": 0.0,
        "notes": [
            "Transfer to your own company is a disposal at market value. Residential CGT is reported "
            "and paid within 60 days of completion.",
        ],
    }


def compare_incorporation(payload: dict[str, Any], packs: RatePack) -> dict[str, Any]:
    prop = payload.get("property") or {}
    fin = payload.get("financing") or {}
    landlord = payload.get("landlord") or {}
    company = payload.get("company") or {}
    reliefs = payload.get("reliefs") or {}

    market_value = clamp0(prop.get("marketValue") or 0)
    if market_value <= 0:
        raise ValueError("property.marketValue is required")
    base_cost = money(
        clamp0(prop.get("originalPurchasePrice") or 0)
        + clamp0(prop.get("purchaseCosts") or 0)
        + clamp0(prop.get("capitalImprovements") or 0)
    )
    if base_cost <= 0:
        raise ValueError("property.originalPurchasePrice is required")
    mortgage = clamp0(fin.get("outstandingMortgage") or 0)
    if mortgage > market_value:
        raise ValueError("financing.outstandingMortgage cannot exceed marketValue")

    incorporation_relief = bool(reliefs.get("incorporationRelief"))
    partnership_relief = bool(reliefs.get("partnershipSdltRelief"))
    other_income = clamp0(landlord.get("otherNonSavingsIncome", landlord.get("otherIncome", 0)))

    # Operating years: same engine as a new purchase, priced at market value
    # with the existing mortgage carried across. Year 0 is replaced below.
    synthetic = {
        "property": {
            "purchasePrice": to_float(market_value),
            "annualRent": prop.get("annualRent"),
            "monthlyRent": prop.get("monthlyRent"),
            "annualOperatingExpenses": prop.get("annualOperatingExpenses") or 0,
        },
        "financing": {
            "loanAmount": to_float(mortgage),
            "personalInterestRate": fin.get("personalInterestRate", "0.045"),
            "companyInterestRate": fin.get("companyInterestRate", "0.055"),
        },
        "landlord": landlord,
        "company": {**company, "formationCost": 0},
        "growth": payload.get("growth") or {},
        "horizonYears": payload.get("horizonYears") or 10,
        "discountRate": payload.get("discountRate", "0.05"),
        "ratePolicy": payload.get("ratePolicy") or "legislated",
    }
    ops = compare_paths(synthetic, packs)
    years_a = ops["paths"]["A"]["years"][1:]
    years_b = ops["paths"]["B"]["years"][1:]

    # Year-1 taxable income sets how much of the gain falls in the basic band.
    y1_profit = D(str(years_a[0].get("propertyProfit", 0))) if years_a else ZERO
    ani = money(other_income + clamp0(y1_profit))
    taxable_income = clamp0(ani - personal_allowance(ani, packs))

    cgt = compute_transfer_cgt(
        market_value=market_value,
        base_cost=base_cost,
        disposal_costs=clamp0(fin.get("transferLegalFees") or 0),
        taxable_income=taxable_income,
        other_gains=clamp0(landlord.get("otherGainsThisYear") or 0),
        incorporation_relief=incorporation_relief,
        packs=packs,
    )
    if partnership_relief:
        sdlt_total = ZERO
        sdlt_detail: dict[str, Any] = {
            "total": 0.0,
            "partnershipRelief": True,
            "notes": [
                "Partnership relief (FA 2003 Sch 15) can reduce SDLT on transfer to nil, but only for a "
                "genuine partnership that has actually traded as one. Get advice before relying on it.",
            ],
        }
    else:
        sdlt = compute_sdlt(
            consideration=market_value,
            packs=packs,
            purchaser="company",
            rental_business_relief=company.get("rentalBusinessRelief"),
        )
        sdlt_total = sdlt.total
        sdlt_detail = {
            **sdlt.to_dict(),
            "partnershipRelief": False,
            "notes": list(sdlt.to_dict().get("notes") or [])
            + ["The company pays SDLT on market value because it is connected to you (FA 2003 s53)."],
        }

    costs = {
        "cgt": D(str(cgt["tax"])),
        "sdlt": sdlt_total,
        "earlyRepaymentCharge": clamp0(fin.get("earlyRepaymentCharge") or 0),
        "refinanceFees": clamp0(fin.get("refinanceFees") or 0),
        "transferLegalFees": clamp0(fin.get("transferLegalFees") or 0),
        "formationCost": clamp0(company.get("formationCost") or 0),
    }
    transfer_total = money(sum(costs.values(), ZERO))

    cash_a = [ZERO] + [D(str(y["cashToIndividual"])) for y in years_a]
    cash_b = [money(-transfer_total)] + [D(str(y["cashToIndividual"])) for y in years_b]
    discount = D(str(payload.get("discountRate", "0.05")))
    npv_a = npv(cash_a, discount)
    npv_b = npv(cash_b, discount)
    be = break_even_year(cash_a, cash_b)
    equity = money(market_value - mortgage)

    meta = _soft_lean(npv_a, npv_b, equity, be)
    meta["disclaimers"] = [
        "Illustrative only — not tax, legal or financial advice. Incorporation is irreversible in practice; "
        "take regulated advice first.",
        "Incorporation relief and partnership SDLT relief depend on facts (a letting business; a genuine "
        "partnership). They are off unless you switch them on.",
        "Models one property. Does not model CGT on a later sale, IHT, ATED, lender consent, or a portfolio "
        "moving together.",
        "Year 0 is the cost of moving the property in; the personal path has no year-0 cost because you "
        "already own it.",
    ]

    return {
        "mode": "existing_property",
        "transfer": {
            "marketValue": to_float(market_value),
            "baseCost": to_float(base_cost),
            "outstandingMortgage": to_float(mortgage),
            "costs": {k: to_float(v) for k, v in costs.items()},
            "total": to_float(transfer_total),
            "cgt": cgt,
            "sdlt": sdlt_detail,
            "taxableIncomeUsedForCgtBand": to_float(taxable_income),
        },
        "paths": {
            "A": {
                "id": "path_a_keep_personal",
                "label": "Keep holding personally",
                "years": [{"year": 0, "cashToIndividual": 0.0}] + years_a,
                "cumulativeCash": [to_float(x) for x in cumulative(cash_a)],
                "npv": to_float(npv_a),
            },
            "B": {
                "id": "path_b_incorporate",
                "label": "Move into a limited company",
                "years": [{"year": 0, "cashToIndividual": to_float(-transfer_total)}] + years_b,
                "cumulativeCash": [to_float(x) for x in cumulative(cash_b)],
                "npv": to_float(npv_b),
            },
        },
        "horizonYears": ops["horizonYears"],
        "discountRate": ops["discountRate"],
        "ratePolicy": ops["ratePolicy"],
        "ratePacksUsed": ops["ratePacksUsed"],
        "npv": {
            "pathA": to_float(npv_a),
            "pathB": to_float(npv_b),
            "deltaPathBMinusPathA": to_float(money(npv_b - npv_a)),
        },
        "breakEven": {
            "year": be,
            "note": "First year where cumulative cash after incorporating (net of the transfer cost) "
            "catches keeping the property personally. Null if it doesn't within the horizon.",
        },
        "metadata": meta,
    }

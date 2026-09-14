"""
Path A (personal) vs Path B (limited company) — landlord MVP.

Path A: individual holds the dwelling. Section 24 applies. ADS SDLT.
Path B: company holds the dwelling. Interest deductible for CT. Dividend lens.
        SDLT higher rates with rental-business relief default ON.

Multi-year cash to the individual, NPV, break-even. Soft lean in metadata only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ltd_co.corporation_tax import CorporationTaxResult, compute_corporation_tax
from ltd_co.dividends import extract_dividends
from ltd_co.income_tax import compute_income_tax
from ltd_co.money import D, ZERO, clamp0, money, to_float
from ltd_co.npv import break_even_year, cumulative, npv
from ltd_co.rates import RatePack
from ltd_co.sdlt import compute_sdlt
from ltd_co.section24 import compute_section24


def _annual_rent(payload: dict) -> Decimal:
    if payload.get("annualRent") is not None:
        return clamp0(payload["annualRent"])
    if payload.get("monthlyRent") is not None:
        return money(D(payload["monthlyRent"]) * 12)
    return ZERO


def _growth(base: Decimal, rate: Decimal, year_index: int) -> Decimal:
    """year_index 1 = first operating year (no growth yet)."""
    if year_index <= 1 or rate == 0:
        return money(base)
    return money(base * ((1 + rate) ** (year_index - 1)))


def _loan(purchase_price: Decimal, financing: dict) -> Decimal:
    if financing.get("loanAmount") is not None:
        return clamp0(financing["loanAmount"])
    if financing.get("depositAmount") is not None:
        dep = clamp0(financing["depositAmount"])
        loan = money(purchase_price - dep)
        return loan if loan > 0 else ZERO
    ltv = D(financing.get("ltv", "0.75"))
    if ltv < 0 or ltv > 1:
        raise ValueError("ltv must be between 0 and 1")
    return money(purchase_price * ltv)


def _deposit(purchase_price: Decimal, loan: Decimal) -> Decimal:
    dep = money(purchase_price - loan)
    return dep if dep > 0 else ZERO


def _interest(loan: Decimal, rate: Decimal) -> Decimal:
    return money(loan * rate)


@dataclass
class YearRow:
    year: int
    rent: Decimal
    operating_expenses: Decimal
    finance_costs: Decimal
    tax: Decimal
    cash_to_individual: Decimal
    extra: dict

    def to_dict(self) -> dict:
        out = {
            "year": self.year,
            "rent": to_float(self.rent),
            "operatingExpenses": to_float(self.operating_expenses),
            "financeCosts": to_float(self.finance_costs),
            "tax": to_float(self.tax),
            "cashToIndividual": to_float(self.cash_to_individual),
        }
        out.update(self.extra)
        return out


def _soft_lean(
    npv_a: Decimal,
    npv_b: Decimal,
    capital_a: Decimal,
    break_even: int | None,
) -> dict[str, Any]:
    delta = money(npv_b - npv_a)
    threshold = money(max(D(1000), abs(capital_a) * D("0.02")))
    if abs(delta) < threshold:
        lean = "neutral"
        rationale = (
            f"NPV difference (£{to_float(delta):,.2f}) is inside the soft "
            f"materiality band (£{to_float(threshold):,.2f}). No lean."
        )
    elif delta > 0:
        lean = "path_b_company"
        rationale = (
            f"Path B (company) NPV is £{to_float(delta):,.2f} higher on these "
            "inputs. Soft numerical lean only — not a recommendation."
        )
    else:
        lean = "path_a_personal"
        rationale = (
            f"Path A (personal) NPV is £{to_float(-delta):,.2f} higher on these "
            "inputs. Soft numerical lean only — not a recommendation."
        )
    return {
        "lean": lean,
        "leanStrength": "soft",
        "notAdvice": True,
        "npvDeltaPathBMinusPathA": to_float(delta),
        "materialityBand": to_float(threshold),
        "breakEvenYear": break_even,
        "rationale": rationale,
        "disclaimers": [
            "Illustrative calculation using a pinned rate pack. Not tax, legal or financial advice.",
            "Section 24, CT, dividend and SDLT rules are simplified for a single UK residential let in England/NI.",
            "Does not model CGT on sale, incorporation of an existing portfolio, ATED, non-resident surcharges, Scotland/Wales, or MTD.",
            "A soft lean is a numerical hint, not a product verdict and not a recommendation to incorporate or not.",
        ],
    }


def compare_paths(payload: dict[str, Any], packs: RatePack) -> dict[str, Any]:
    property_in = payload.get("property") or {}
    financing = payload.get("financing") or {}
    landlord = payload.get("landlord") or {}
    company = payload.get("company") or {}
    growth = payload.get("growth") or {}

    purchase = clamp0(property_in.get("purchasePrice") or 0)
    if purchase <= 0:
        raise ValueError("property.purchasePrice is required")

    rent0 = _annual_rent(property_in)
    opex0 = clamp0(property_in.get("annualOperatingExpenses") or 0)
    legal = clamp0(property_in.get("legalFees") or 0)
    other_costs = clamp0(property_in.get("otherPurchaseCosts") or 0)

    horizon = int(payload.get("horizonYears") or 10)
    if horizon < 1 or horizon > 40:
        raise ValueError("horizonYears must be between 1 and 40")
    discount = D(payload.get("discountRate", "0.05"))

    personal_rate = D(financing.get("personalInterestRate", "0.045"))
    company_rate = D(financing.get("companyInterestRate", "0.055"))
    loan = _loan(purchase, financing)
    deposit = _deposit(purchase, loan)

    other_income = clamp0(
        landlord.get("otherNonSavingsIncome", landlord.get("otherIncome", 0))
    )
    savings_income = clamp0(landlord.get("savingsIncome") or 0)
    other_dividends = clamp0(landlord.get("dividendIncome") or 0)
    s24_bf = clamp0(landlord.get("financeCostsBroughtForward") or 0)
    loss_bf = clamp0(landlord.get("propertyLossesBroughtForward") or 0)

    associated = int(company.get("associatedCompanies") or 0)
    relief_in = company.get("rentalBusinessRelief")
    relief = packs.sdlt.rental_business_relief_default if relief_in is None else bool(relief_in)
    formation = clamp0(company.get("formationCost") or 0)
    compliance = clamp0(company.get("annualComplianceCost") or 0)
    extract_policy = company.get("extractDividends", "all")
    ct_loss_bf = clamp0(company.get("ctLossesBroughtForward") or 0)

    rent_g = D(growth.get("rentGrowth") or 0)
    opex_g = D(growth.get("expenseGrowth") or 0)

    sdlt_a = compute_sdlt(
        consideration=purchase, packs=packs, purchaser="personal_additional"
    )
    sdlt_b = compute_sdlt(
        consideration=purchase,
        packs=packs,
        purchaser="company",
        rental_business_relief=relief,
    )

    year0_a = money(-(deposit + sdlt_a.total + legal + other_costs))
    year0_b = money(-(deposit + sdlt_b.total + legal + other_costs + formation))

    rows_a: list[YearRow] = [
        YearRow(
            year=0,
            rent=ZERO,
            operating_expenses=ZERO,
            finance_costs=ZERO,
            tax=ZERO,
            cash_to_individual=year0_a,
            extra={
                "label": "acquisition",
                "deposit": to_float(deposit),
                "sdlt": to_float(sdlt_a.total),
                "legalFees": to_float(legal),
                "otherPurchaseCosts": to_float(other_costs),
            },
        )
    ]
    rows_b: list[YearRow] = [
        YearRow(
            year=0,
            rent=ZERO,
            operating_expenses=ZERO,
            finance_costs=ZERO,
            tax=ZERO,
            cash_to_individual=year0_b,
            extra={
                "label": "acquisition",
                "deposit": to_float(deposit),
                "sdlt": to_float(sdlt_b.total),
                "legalFees": to_float(legal),
                "otherPurchaseCosts": to_float(other_costs),
                "formationCost": to_float(formation),
            },
        )
    ]

    cash_a = [year0_a]
    cash_b = [year0_b]
    s24_carry = s24_bf
    loss_carry = loss_bf
    ct_loss_carry = ct_loss_bf

    interest_a = _interest(loan, personal_rate)
    interest_b = _interest(loan, company_rate)

    extraction_lens_year1: dict[str, Any] | None = None

    for y in range(1, horizon + 1):
        rent = _growth(rent0, rent_g, y)
        opex = _growth(opex0, opex_g, y)

        s24 = compute_section24(
            rental_income=rent,
            allowable_non_finance_expenses=opex,
            finance_costs=interest_a,
            packs=packs,
            other_non_savings_income=other_income,
            savings_income=savings_income,
            dividend_income=other_dividends,
            finance_costs_brought_forward=s24_carry,
            property_losses_brought_forward=loss_carry,
        )
        it_a = compute_income_tax(
            non_savings_income=money(other_income + s24.property_profit),
            savings_income=savings_income,
            dividend_income=other_dividends,
            section24_reducer=s24.tax_reducer,
            packs=packs,
        )
        # Tax attributable to the property is total tax minus tax on other income alone.
        it_other = compute_income_tax(
            non_savings_income=other_income,
            savings_income=savings_income,
            dividend_income=other_dividends,
            packs=packs,
        )
        property_it = money(it_a.income_tax - it_other.income_tax)
        if property_it < 0:
            property_it = ZERO

        cash_path_a = money(rent - opex - interest_a - property_it)
        rows_a.append(
            YearRow(
                year=y,
                rent=rent,
                operating_expenses=opex,
                finance_costs=interest_a,
                tax=property_it,
                cash_to_individual=cash_path_a,
                extra={
                    "label": "operating",
                    "propertyProfit": to_float(s24.property_profit),
                    "section24": {
                        "bindingLimb": s24.binding_limb,
                        "actualAmount": to_float(s24.actual_amount),
                        "taxReducer": to_float(s24.tax_reducer),
                        "taxReducerApplied": to_float(it_a.section24_reducer_applied),
                        "financeCostsCarriedForward": to_float(s24.finance_costs_carried_forward),
                    },
                    "incomeTaxTotal": to_float(it_a.income_tax),
                    "incomeTaxOnOtherIncome": to_float(it_other.income_tax),
                },
            )
        )
        cash_a.append(cash_path_a)
        s24_carry = s24.finance_costs_carried_forward
        loss_carry = s24.property_loss_carried_forward

        # Path B: interest deductible; compliance is a deductible overhead.
        ct_profit = money(rent - opex - interest_b - compliance)
        ct: CorporationTaxResult = compute_corporation_tax(
            taxable_profits=ct_profit,
            packs=packs,
            associated_companies=associated,
            losses_brought_forward=ct_loss_carry,
        )
        distributable = money(ct.taxable_profits - ct.corporation_tax)
        if distributable < 0:
            distributable = ZERO
        extraction = extract_dividends(
            distributable=distributable,
            packs=packs,
            other_non_savings_income=other_income,
            savings_income=savings_income,
            other_dividend_income=other_dividends,
            extract=extract_policy,
        )
        # Individual also funds any cash shortfall in the company (negative
        # pre-tax cash) — interest and opex are real cash even if CT is nil.
        company_cash_before_extract = money(rent - opex - interest_b - compliance - ct.corporation_tax)
        # If extracting all, shareholder receives `net_to_shareholder`; retained
        # stays in the company (not cash to individual).
        cash_path_b = extraction.net_to_shareholder
        if extract_policy == "none":
            cash_path_b = ZERO

        if y == 1:
            retained_alt = extract_dividends(
                distributable=distributable,
                packs=packs,
                other_non_savings_income=other_income,
                savings_income=savings_income,
                other_dividend_income=other_dividends,
                extract="none",
            )
            extraction_lens_year1 = {
                "extractAll": extraction.to_dict(),
                "retainAll": {
                    "postCtProfit": to_float(distributable),
                    "netToShareholder": to_float(retained_alt.net_to_shareholder),
                    "wealthRetainedInCompany": to_float(distributable),
                    "notes": [
                        "Retained profits are company wealth, not cash in the shareholder's pocket.",
                        "Path comparison uses the requested extraction policy for cash-to-individual.",
                    ],
                },
                "policyUsed": extract_policy if not isinstance(extract_policy, (int, float, Decimal)) else "amount",
            }

        rows_b.append(
            YearRow(
                year=y,
                rent=rent,
                operating_expenses=opex,
                finance_costs=interest_b,
                tax=money(ct.corporation_tax + extraction.dividend_tax),
                cash_to_individual=cash_path_b,
                extra={
                    "label": "operating",
                    "complianceCost": to_float(compliance),
                    "ctProfit": to_float(ct.taxable_profits),
                    "corporationTax": to_float(ct.corporation_tax),
                    "ctBand": ct.band,
                    "ctLowerLimit": to_float(ct.lower_limit),
                    "ctUpperLimit": to_float(ct.upper_limit),
                    "associatedCompanies": associated,
                    "distributable": to_float(distributable),
                    "dividendExtracted": to_float(extraction.extracted),
                    "dividendTax": to_float(extraction.dividend_tax),
                    "retainedInCompany": to_float(extraction.retained),
                    "companyCashBeforeExtract": to_float(company_cash_before_extract),
                },
            )
        )
        cash_b.append(cash_path_b)
        ct_loss_carry = ct.losses_carried_forward

    npv_a = npv(cash_a, discount)
    npv_b = npv(cash_b, discount)
    be = break_even_year(cash_a, cash_b)
    capital_a = money(deposit + sdlt_a.total + legal + other_costs)

    return {
        "paths": {
            "A": {
                "id": "path_a_personal",
                "label": "Path A — hold personally",
                "acquisition": {
                    "purchasePrice": to_float(purchase),
                    "loan": to_float(loan),
                    "deposit": to_float(deposit),
                    "interestRate": to_float(personal_rate, places=4),
                    "annualFinanceCosts": to_float(interest_a),
                    "sdlt": sdlt_a.to_dict(),
                },
                "years": [r.to_dict() for r in rows_a],
                "cumulativeCash": [to_float(x) for x in cumulative(cash_a)],
                "npv": to_float(npv_a),
            },
            "B": {
                "id": "path_b_company",
                "label": "Path B — buy in a limited company",
                "acquisition": {
                    "purchasePrice": to_float(purchase),
                    "loan": to_float(loan),
                    "deposit": to_float(deposit),
                    "interestRate": to_float(company_rate, places=4),
                    "annualFinanceCosts": to_float(interest_b),
                    "sdlt": sdlt_b.to_dict(),
                    "formationCost": to_float(formation),
                    "annualComplianceCost": to_float(compliance),
                    "associatedCompanies": associated,
                    "rentalBusinessRelief": relief,
                },
                "years": [r.to_dict() for r in rows_b],
                "cumulativeCash": [to_float(x) for x in cumulative(cash_b)],
                "npv": to_float(npv_b),
            },
        },
        "horizonYears": horizon,
        "discountRate": to_float(discount, places=4),
        "npv": {
            "pathA": to_float(npv_a),
            "pathB": to_float(npv_b),
            "deltaPathBMinusPathA": to_float(money(npv_b - npv_a)),
        },
        "breakEven": {
            "year": be,
            "note": (
                "First year (0 = acquisition) where cumulative cash to the individual "
                "on Path B is at least Path A. Null if Path B does not catch up inside the horizon."
            ),
        },
        "extractionLens": extraction_lens_year1,
        "sdltComparison": {
            "personalAdditional": to_float(sdlt_a.total),
            "company": to_float(sdlt_b.total),
            "deltaCompanyMinusPersonal": to_float(money(sdlt_b.total - sdlt_a.total)),
            "rentalBusinessRelief": relief,
        },
        "metadata": _soft_lean(npv_a, npv_b, capital_a, be),
    }

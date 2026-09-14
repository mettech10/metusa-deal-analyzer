"""Dividend extraction lens: CT already paid; this is the shareholder's dividend tax."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ltd_co.income_tax import IncomeTaxResult, compute_income_tax
from ltd_co.money import ZERO, clamp0, money
from ltd_co.rates import RatePack


@dataclass(frozen=True)
class DividendExtractionResult:
    distributable: Decimal
    extracted: Decimal
    retained: Decimal
    other_non_savings_income: Decimal
    shareholder_tax_without_dividend: Decimal
    shareholder_tax_with_dividend: Decimal
    dividend_tax: Decimal
    net_to_shareholder: Decimal
    income_tax: IncomeTaxResult
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        from ltd_co.money import to_float

        return {
            "distributable": to_float(self.distributable),
            "extracted": to_float(self.extracted),
            "retained": to_float(self.retained),
            "otherNonSavingsIncome": to_float(self.other_non_savings_income),
            "shareholderTaxWithoutDividend": to_float(self.shareholder_tax_without_dividend),
            "shareholderTaxWithDividend": to_float(self.shareholder_tax_with_dividend),
            "dividendTax": to_float(self.dividend_tax),
            "netToShareholder": to_float(self.net_to_shareholder),
            "incomeTax": self.income_tax.to_dict(),
            "notes": list(self.notes),
        }


def extract_dividends(
    *,
    distributable: Decimal,
    packs: RatePack,
    other_non_savings_income: Decimal = ZERO,
    savings_income: Decimal = ZERO,
    other_dividend_income: Decimal = ZERO,
    extract: str | Decimal = "all",
) -> DividendExtractionResult:
    notes: list[str] = []
    pot = clamp0(distributable)
    if extract == "all" or extract is None:
        taken = pot
    elif extract == "none":
        taken = ZERO
        notes.append("Extraction policy 'none': profits retained in the company.")
    else:
        taken = clamp0(extract)
        if taken > pot:
            taken = pot
            notes.append("Requested extraction capped at post-CT distributable profits.")

    retained = money(pot - taken)
    other_ns = clamp0(other_non_savings_income)
    savings = clamp0(savings_income)
    other_div = clamp0(other_dividend_income)

    without = compute_income_tax(
        non_savings_income=other_ns,
        savings_income=savings,
        dividend_income=other_div,
        packs=packs,
    )
    with_div = compute_income_tax(
        non_savings_income=other_ns,
        savings_income=savings,
        dividend_income=money(other_div + taken),
        packs=packs,
    )
    div_tax = money(with_div.income_tax - without.income_tax)
    if div_tax < 0:
        div_tax = ZERO
    net = money(taken - div_tax)
    notes.append(
        "Dividends are not deductible for CT. Dividend allowance uses band width at 0% "
        f"(£{packs.dividends.allowance} in this pack)."
    )
    notes.append(
        f"2026/27 ordinary/upper/additional dividend rates: "
        f"{packs.dividends.ordinary_rate}/{packs.dividends.upper_rate}/{packs.dividends.additional_rate}."
    )

    return DividendExtractionResult(
        distributable=pot,
        extracted=taken,
        retained=retained,
        other_non_savings_income=other_ns,
        shareholder_tax_without_dividend=without.income_tax,
        shareholder_tax_with_dividend=with_div.income_tax,
        dividend_tax=div_tax,
        net_to_shareholder=net,
        income_tax=with_div,
        notes=tuple(notes),
    )

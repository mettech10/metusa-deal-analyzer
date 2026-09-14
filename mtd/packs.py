"""Immutable quarter-pack snapshots (not an HMRC submission)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from mtd.categories import CATEGORIES, RESIDENTIAL_FINANCE_CODES
from mtd.models import LedgerEntry, MtdProperty, PropertyBusiness
from mtd.quarters import deadline_for_quarter, resolve_quarter, tax_year_label

DISCLAIMER = (
    "Metalyzi MTD Pack v1 is a record-keeping snapshot only. "
    "It does not submit quarterly updates or a tax return to HMRC."
)


def _sum_by_category(entries: Iterable[LedgerEntry]) -> dict[str, int]:
    totals = {c["code"]: 0 for c in CATEGORIES}
    for entry in entries:
        if entry.voided_at:
            continue
        totals.setdefault(entry.category_code, 0)
        totals[entry.category_code] += int(entry.amount_pence)
    return totals


def _finance_block(totals: dict[str, int]) -> dict[str, int]:
    period = totals.get("residential_finance_costs", 0)
    brought = totals.get("residential_finance_costs_bf", 0)
    return {
        "periodPence": period,
        "broughtForwardPence": brought,
        "totalPence": period + brought,
        "nonResidentialFinancePence": totals.get("non_residential_finance_costs", 0),
    }


def build_snapshot(
    *,
    business: PropertyBusiness,
    properties: list[MtdProperty],
    entries: list[LedgerEntry],
    tax_year: str,
    quarter: int,
    basis: str,
    generated_at: datetime | None = None,
    generated_by: str,
) -> dict[str, Any]:
    period_start, period_end = resolve_quarter(tax_year, quarter, basis)  # type: ignore[arg-type]
    year_start = date(int(tax_year.split("-")[0]), 4, 6)
    live = [e for e in entries if e.voided_at is None]
    period_entries = [e for e in live if period_start <= e.entry_date <= period_end]
    ytd_entries = [e for e in live if year_start <= e.entry_date <= period_end]
    period_totals = _sum_by_category(period_entries)
    ytd_totals = _sum_by_category(ytd_entries)
    income_period = sum(period_totals[c["code"]] for c in CATEGORIES if c["kind"] == "income")
    expense_period = sum(period_totals[c["code"]] for c in CATEGORIES if c["kind"] == "expense")
    income_ytd = sum(ytd_totals[c["code"]] for c in CATEGORIES if c["kind"] == "income")
    expense_ytd = sum(ytd_totals[c["code"]] for c in CATEGORIES if c["kind"] == "expense")
    generated = generated_at or datetime.now(timezone.utc)
    return {
        "schemaVersion": 1,
        "packType": "mtd_quarter_pack",
        "disclaimer": DISCLAIMER,
        "hmrcSubmit": False,
        "business": {
            "id": business.id,
            "name": business.name,
            "orgId": business.org_id,
            "basis": basis,
            "taxYearStart": business.tax_year_start.isoformat(),
            "country": business.country,
        },
        "properties": [
            {
                "id": p.id,
                "propertyId": p.property_id,
                "label": p.label,
                "address": p.address,
                "postcode": p.postcode,
                "occupancyType": p.occupancy_type,
            }
            for p in properties
        ],
        "taxYear": tax_year,
        "taxYearLabel": tax_year_label(year_start),
        "quarter": quarter,
        "basis": basis,
        "periodStart": period_start.isoformat(),
        "periodEnd": period_end.isoformat(),
        "filingDeadline": deadline_for_quarter(tax_year, quarter).isoformat(),
        "periodTotalsPence": period_totals,
        "yearToDateTotalsPence": ytd_totals,
        "periodNetPence": income_period - expense_period,
        "yearToDateNetPence": income_ytd - expense_ytd,
        "residentialFinance": {
            "period": _finance_block(period_totals),
            "yearToDate": _finance_block(ytd_totals),
            "excludedFromProfitDeduction": True,
            "note": (
                "Residential finance costs are reported separately from "
                "non-residential finance costs (SA105 box 26)."
            ),
        },
        "entryCount": len(period_entries),
        "yearToDateEntryCount": len(ytd_entries),
        "entries": [
            {
                "id": e.id,
                "date": e.entry_date.isoformat(),
                "propertyId": e.property_id,
                "categoryCode": e.category_code,
                "amountPence": e.amount_pence,
                "description": e.description,
                "counterparty": e.counterparty,
                "source": e.source,
                "isResidentialFinance": e.category_code in RESIDENTIAL_FINANCE_CODES,
            }
            for e in sorted(period_entries, key=lambda x: (x.entry_date, x.created_at, x.id))
        ],
        "generatedAt": generated.isoformat(),
        "generatedBy": generated_by,
    }


def snapshot_to_csv(snapshot: dict[str, Any]) -> str:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Metalyzi MTD Quarter Pack v1"])
    writer.writerow(["disclaimer", snapshot.get("disclaimer", DISCLAIMER)])
    writer.writerow(["hmrcSubmit", "false"])
    writer.writerow(["business", snapshot.get("business", {}).get("name")])
    writer.writerow(["taxYear", snapshot.get("taxYear")])
    writer.writerow(["quarter", snapshot.get("quarter")])
    writer.writerow(["basis", snapshot.get("basis")])
    writer.writerow(["periodStart", snapshot.get("periodStart")])
    writer.writerow(["periodEnd", snapshot.get("periodEnd")])
    writer.writerow([])
    writer.writerow(["section", "categoryCode", "periodPence", "yearToDatePence", "isResidentialFinance"])
    period = snapshot.get("periodTotalsPence") or {}
    ytd = snapshot.get("yearToDateTotalsPence") or {}
    for cat in CATEGORIES:
        writer.writerow(
            [
                cat["kind"],
                cat["code"],
                period.get(cat["code"], 0),
                ytd.get(cat["code"], 0),
                str(bool(cat.get("isResidentialFinance"))).lower(),
            ]
        )
    writer.writerow([])
    writer.writerow(["entries"])
    writer.writerow(
        ["date", "propertyId", "categoryCode", "amountPence", "description", "counterparty", "source", "isResidentialFinance"]
    )
    for entry in snapshot.get("entries") or []:
        writer.writerow(
            [
                entry.get("date"),
                entry.get("propertyId") or "",
                entry.get("categoryCode"),
                entry.get("amountPence"),
                entry.get("description") or "",
                entry.get("counterparty") or "",
                entry.get("source"),
                str(bool(entry.get("isResidentialFinance"))).lower(),
            ]
        )
    return buf.getvalue()

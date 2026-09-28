"""UK private-rented obligation catalogue (MVP).

Codes are the product-fixed set. Licensing *geo* lookup is intentionally
absent — LIC_HMO / LIC_SEL are tracked as certificates the landlord records,
not inferred from postcode.
"""

from datetime import date
from typing import Optional

# Reminder ladder: T-90 through due date, then the first overdue day.
REMINDER_OFFSET_DAYS = (-90, -60, -30, -14, -7, 0, 1)

REMINDER_OFFSET_CODES = {
    -90: "t_minus_90",
    -60: "t_minus_60",
    -30: "t_minus_30",
    -14: "t_minus_14",
    -7: "t_minus_7",
    0: "t_zero",
    1: "overdue",
}

# Default window used by the status engine when a code does not override it.
DEFAULT_DUE_SOON_DAYS = 90

CATALOGUE = {
    "GAS": {
        "code": "GAS",
        "name": "Gas Safety Certificate (CP12)",
        "jurisdiction": "UK",
        "defaultValidityYears": 1,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Annual gas safety check by a Gas Safe registered engineer. "
            "A copy must be given to tenants within 28 days of the check."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "EICR": {
        "code": "EICR",
        "name": "Electrical Installation Condition Report",
        "jurisdiction": "England",
        "defaultValidityYears": 5,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Private rented electrical safety report. Typically valid for 5 years "
            "(or sooner if the report recommends an earlier reinspection)."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "EPC": {
        "code": "EPC",
        "name": "Energy Performance Certificate",
        "jurisdiction": "UK",
        "defaultValidityYears": 10,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Energy Performance Certificate, valid 10 years. Private rented "
            "properties in England and Wales must currently meet a minimum rating of E, "
            "rising to C for all tenancies by 1 October 2030 (track that with EPC_2030)."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "DEP": {
        "code": "DEP",
        "name": "Tenancy Deposit Protection",
        "jurisdiction": "UK",
        "defaultValidityYears": None,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Protect a tenancy deposit in a government-authorised scheme and serve "
            "prescribed information within 30 days of receiving the deposit. "
            "Tracked per tenancy — no automatic expiry."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "HTR": {
        "code": "HTR",
        "name": "How to Rent guide (tenancies before 1 May 2026)",
        "jurisdiction": "England",
        "defaultValidityYears": None,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "No longer required from 1 May 2026, when the Renters' Rights Act "
            "replaced it with a written statement of terms (TERMS) for new tenancies "
            "and the Information Sheet (RRA_INFO) for existing ones. Keep for records "
            "of earlier tenancies."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "LIC_HMO": {
        "code": "LIC_HMO",
        "name": "HMO licence",
        "jurisdiction": "England_Wales",
        "defaultValidityYears": 5,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Mandatory or additional HMO licence issued by the local authority. "
            "Typically granted for up to 5 years. This MVP records the certificate "
            "the landlord supplies — it does not look up licensing geographies."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "LIC_SEL": {
        "code": "LIC_SEL",
        "name": "Selective licence",
        "jurisdiction": "England",
        "defaultValidityYears": 5,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Selective licensing scheme licence for privately rented homes in "
            "designated areas. Typically granted for up to 5 years. This MVP "
            "does not infer scheme boundaries from postcode."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "SMOKE_CO": {
        "code": "SMOKE_CO",
        "name": "Smoke and carbon monoxide alarms",
        "jurisdiction": "England",
        "defaultValidityYears": None,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "A smoke alarm on every storey with living accommodation and a CO alarm in "
            "any room with a fixed combustion appliance (not gas cookers). Check they "
            "work on the day each tenancy starts, and repair faults as soon as reasonably "
            "practicable (Smoke and Carbon Monoxide Alarm (Amendment) Regulations 2022). "
            "Tracked per tenancy."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "RTR": {
        "code": "RTR",
        "name": "Right to Rent check",
        "jurisdiction": "England",
        "defaultValidityYears": None,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Check every adult occupier's right to rent before the tenancy starts "
            "(no more than 28 days before for time-limited permission). For time-limited "
            "permission, set the expiry to the earlier of the permission end date or 12 "
            "months, and re-check before it. Keep evidence for the tenancy plus a year."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "TERMS": {
        "code": "TERMS",
        "name": "Written statement of terms (tenancies from 1 May 2026)",
        "jurisdiction": "England",
        "defaultValidityYears": None,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Renters' Rights Act: tenancies starting on or after 1 May 2026 need a "
            "written statement of the terms before the tenancy begins. It can be part of "
            "the tenancy agreement. Tracked per tenancy."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "RRA_INFO": {
        "code": "RRA_INFO",
        "name": "Renters' Rights Act Information Sheet (tenancies before 1 May 2026)",
        "jurisdiction": "England",
        "defaultValidityYears": None,
        "fixedDueDate": "2026-05-31",
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Existing tenants (tenancy began before 1 May 2026) had to receive the "
            "government's Renters' Rights Act Information Sheet 2026 by 31 May 2026. "
            "Record when you served it."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "EPC_2030": {
        "code": "EPC_2030",
        "name": "EPC C by 1 October 2030",
        "jurisdiction": "England_Wales",
        "defaultValidityYears": None,
        "fixedDueDate": "2030-10-01",
        "dueSoonDays": 365,
        "description": (
            "All private rented homes must reach EPC C by 1 October 2030 (Warm Homes "
            "Plan, confirmed January 2026). Spending is capped at £10,000 per property "
            "(or 10% of value under £100,000), and penalties go up to £30,000. Track "
            "upgrade works here if the current rating is D or below."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
    "PRS_DB": {
        "code": "PRS_DB",
        "name": "PRS Database registration",
        "jurisdiction": "England",
        "defaultValidityYears": None,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Renters' Rights Act: landlords must register themselves and each rented "
            "property, with compliance details, on the Private Rented Sector Database. "
            "Registration opens by region from 15 December 2026 (West Midlands first) and "
            "carries a fee."
        ),
        "reminderOffsetsDays": list(REMINDER_OFFSET_DAYS),
    },
}

CATALOGUE_CODES = frozenset(CATALOGUE.keys())


def get_catalogue_item(code: str) -> Optional[dict]:
    if not code:
        return None
    return CATALOGUE.get(str(code).strip().upper())


def add_years(d: date, years: int) -> date:
    """Add calendar years, clamping 29 Feb to 28 Feb on non-leap targets."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def default_expires_on(code: str, issued_on: Optional[date]) -> Optional[date]:
    """Derive expiresOn from issuedOn using the catalogue validity period."""
    item = get_catalogue_item(code)
    if not item:
        return None
    if item.get("fixedDueDate"):
        # Statutory deadlines (e.g. EPC C by 1 Oct 2030) don't depend on issue date.
        return date.fromisoformat(item["fixedDueDate"])
    if issued_on is None:
        return None
    years = item.get("defaultValidityYears")
    if not years:
        return None
    return add_years(issued_on, int(years))

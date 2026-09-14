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
            "properties in England and Wales must currently meet a minimum rating of E."
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
        "name": "How to Rent guide",
        "jurisdiction": "England",
        "defaultValidityYears": None,
        "dueSoonDays": DEFAULT_DUE_SOON_DAYS,
        "description": (
            "Give the latest government How to Rent guide at the start of an "
            "assured shorthold tenancy in England, and again when it is updated. "
            "Tracked per tenancy — no automatic expiry."
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
    if not item or issued_on is None:
        return None
    years = item.get("defaultValidityYears")
    if not years:
        return None
    return add_years(issued_on, int(years))

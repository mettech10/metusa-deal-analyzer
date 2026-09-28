"""Obligation status engine: valid | due_soon | overdue."""

from datetime import date
from typing import Optional

from compliance.catalogue import DEFAULT_DUE_SOON_DAYS, get_catalogue_item

STATUSES = ("valid", "due_soon", "overdue")


def compute_status(
    expires_on: Optional[date],
    issued_on: Optional[date] = None,
    *,
    as_of: Optional[date] = None,
    code: Optional[str] = None,
    due_soon_days: Optional[int] = None,
) -> str:
    """Classify an obligation instance.

    Rules (MVP):
    - No issue date and no expiry → overdue (nothing on file).
    - Issued, no expiry (DEP / HTR style) → valid.
    - Deadline items (catalogue fixedDueDate) → valid once done (issued).
    - as_of > expires_on → overdue.
    - 0 <= days remaining <= due_soon window → due_soon.
    - days remaining > window → valid.
    """
    today = as_of or date.today()
    item = get_catalogue_item(code) if code else None
    if item and item.get("fixedDueDate") and issued_on is not None:
        # Deadline items (RRA_INFO by 31 May 2026, EPC C by 1 Oct 2030): the date
        # is when to act by, not a certificate expiry. Recorded as done = compliant.
        return "valid"
    window = due_soon_days
    if window is None and item:
        window = item.get("dueSoonDays")
    if window is None:
        window = DEFAULT_DUE_SOON_DAYS

    if expires_on is None:
        if issued_on is None:
            return "overdue"
        return "valid"

    remaining = (expires_on - today).days
    if remaining < 0:
        return "overdue"
    if remaining <= int(window):
        return "due_soon"
    return "valid"

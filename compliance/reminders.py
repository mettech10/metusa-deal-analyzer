"""Reminder stub scheduling for T-90 .. overdue."""

from datetime import date, timedelta
from typing import Iterable, Optional

from compliance.catalogue import (
    REMINDER_OFFSET_CODES,
    REMINDER_OFFSET_DAYS,
    get_catalogue_item,
)


def reminder_offsets_for(code: str) -> tuple[int, ...]:
    item = get_catalogue_item(code)
    if item and item.get("reminderOffsetsDays"):
        return tuple(int(x) for x in item["reminderOffsetsDays"])
    return REMINDER_OFFSET_DAYS


def build_reminder_stubs(
    expires_on: Optional[date],
    code: str,
    *,
    as_of: Optional[date] = None,
) -> list[dict]:
    """Return unsaved reminder stub dicts for an obligation.

    Past non-overdue offsets are marked skipped so a late-created certificate
    does not fire a storm of historical T-90..T-7 emails. The overdue stub
    stays pending if the expiry is already in the past.
    """
    if expires_on is None:
        return []

    today = as_of or date.today()
    stubs = []
    for offset in reminder_offsets_for(code):
        scheduled = expires_on + timedelta(days=offset)
        offset_code = REMINDER_OFFSET_CODES.get(offset, f"offset_{offset}")
        if scheduled < today and offset <= 0:
            status = "skipped"
        else:
            status = "pending"
        stubs.append({
            "offsetCode": offset_code,
            "offsetDays": offset,
            "scheduledFor": scheduled.isoformat(),
            "status": status,
            "channel": "email",
            "sentAt": None,
            "lastError": None,
        })
    return stubs


def due_stub_filter(stubs: Iterable[dict], as_of: Optional[date] = None) -> list[dict]:
    """Pending stubs whose scheduled date is today or earlier."""
    today = as_of or date.today()
    due = []
    for stub in stubs:
        if stub.get("status") != "pending":
            continue
        scheduled = stub.get("scheduledFor")
        if not scheduled:
            continue
        if isinstance(scheduled, date):
            scheduled_date = scheduled
        else:
            scheduled_date = date.fromisoformat(str(scheduled)[:10])
        if scheduled_date <= today:
            due.append(stub)
    return due

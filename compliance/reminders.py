"""Reminder stub scheduling for T-90 .. overdue, plus weekly overdue re-queue.

in_app is a supported channel value for later FE work; the backend seeds
email stubs only. Dispatch never emails in_app rows.
"""

from datetime import date, timedelta
from typing import Iterable, Optional

from compliance.catalogue import (
    REMINDER_OFFSET_CODES,
    REMINDER_OFFSET_DAYS,
    get_catalogue_item,
)

CHANNELS = ("email", "in_app")
DEFAULT_CHANNEL = "email"
OVERDUE_OFFSET_CODES = frozenset({"overdue", "overdue_weekly"})
OVERDUE_WEEKLY_CODE = "overdue_weekly"
OVERDUE_WEEKLY_DAYS = 7


def reminder_offsets_for(code: str) -> tuple[int, ...]:
    item = get_catalogue_item(code)
    if item and item.get("reminderOffsetsDays"):
        return tuple(int(x) for x in item["reminderOffsetsDays"])
    return REMINDER_OFFSET_DAYS


def _stub(
    *,
    offset_code: str,
    offset_days: int,
    scheduled: date,
    status: str,
    channel: str,
) -> dict:
    return {
        "offsetCode": offset_code,
        "offsetDays": offset_days,
        "scheduledFor": scheduled.isoformat(),
        "status": status,
        "channel": channel,
        "sentAt": None,
        "lastError": None,
    }


def build_reminder_stubs(
    expires_on: Optional[date],
    code: str,
    *,
    as_of: Optional[date] = None,
    channel: str = DEFAULT_CHANNEL,
) -> list[dict]:
    """Return unsaved reminder stub dicts for an obligation.

    Past non-overdue offsets are marked skipped so a late-created certificate
    does not fire a storm of historical T-90..T-7 emails. The overdue stub
    stays pending if the expiry is already in the past. Weekly overdue pings
    are enqueued by the dispatcher, not generated here.
    """
    if expires_on is None:
        return []
    channel = (channel or DEFAULT_CHANNEL).lower()
    if channel not in CHANNELS:
        channel = DEFAULT_CHANNEL

    today = as_of or date.today()
    stubs = []
    for offset in reminder_offsets_for(code):
        scheduled = expires_on + timedelta(days=offset)
        offset_code = REMINDER_OFFSET_CODES.get(offset, f"offset_{offset}")
        if scheduled < today and offset <= 0:
            status = "skipped"
        else:
            status = "pending"
        stubs.append(_stub(
            offset_code=offset_code,
            offset_days=offset,
            scheduled=scheduled,
            status=status,
            channel=channel,
        ))
    return stubs


def next_weekly_overdue_date(last_scheduled: date, as_of: date) -> date:
    """Next weekly ping strictly after as_of, stepping 7 days from last send."""
    nxt = last_scheduled + timedelta(days=OVERDUE_WEEKLY_DAYS)
    while nxt <= as_of:
        nxt += timedelta(days=OVERDUE_WEEKLY_DAYS)
    return nxt


def build_weekly_overdue_stub(
    expires_on: date,
    last_scheduled: date,
    *,
    as_of: Optional[date] = None,
    channel: str = DEFAULT_CHANNEL,
) -> dict:
    today = as_of or date.today()
    scheduled = next_weekly_overdue_date(last_scheduled, today)
    offset_days = (scheduled - expires_on).days
    return _stub(
        offset_code=OVERDUE_WEEKLY_CODE,
        offset_days=offset_days,
        scheduled=scheduled,
        status="pending",
        channel=channel or DEFAULT_CHANNEL,
    )


def is_overdue_ping(reminder: dict) -> bool:
    code = reminder.get("offsetCode") or reminder.get("offset_code") or ""
    return code in OVERDUE_OFFSET_CODES


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

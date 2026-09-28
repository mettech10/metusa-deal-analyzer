"""Compliance Cockpit — status engine, catalogue, reminder stubs."""

from datetime import date

from compliance.catalogue import (
    CATALOGUE_CODES,
    add_years,
    default_expires_on,
    get_catalogue_item,
)
from compliance.reminders import (
    build_reminder_stubs,
    build_weekly_overdue_stub,
    due_stub_filter,
    next_weekly_overdue_date,
)
from compliance.status import compute_status


def test_catalogue_has_required_codes():
    assert CATALOGUE_CODES == {
        "GAS", "EICR", "EPC", "DEP", "HTR", "LIC_HMO", "LIC_SEL",
        "SMOKE_CO", "RTR", "TERMS", "RRA_INFO", "EPC_2030", "PRS_DB",
    }
    for code in CATALOGUE_CODES:
        item = get_catalogue_item(code.lower())
        assert item is not None
        assert item["code"] == code


def test_default_expiry_gas_one_year():
    issued = date(2026, 3, 1)
    assert default_expires_on("GAS", issued) == date(2027, 3, 1)


def test_default_expiry_eicr_five_years():
    assert default_expires_on("EICR", date(2024, 6, 15)) == date(2029, 6, 15)


def test_default_expiry_leap_day():
    assert add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)


def test_dep_and_htr_have_no_automatic_expiry():
    assert default_expires_on("DEP", date(2026, 1, 1)) is None
    assert default_expires_on("HTR", date(2026, 1, 1)) is None


def test_status_missing_certificate_is_overdue():
    assert compute_status(None, None, as_of=date(2026, 9, 14)) == "overdue"


def test_status_issued_without_expiry_is_valid():
    assert compute_status(None, date(2026, 1, 1), as_of=date(2026, 9, 14), code="DEP") == "valid"


def test_status_valid_outside_window():
    assert compute_status(
        date(2027, 1, 1), date(2026, 1, 1),
        as_of=date(2026, 6, 1), code="GAS",
    ) == "valid"


def test_status_due_soon_at_t_minus_90():
    assert compute_status(
        date(2026, 12, 1), date(2025, 12, 1),
        as_of=date(2026, 9, 2),  # 90 days before 1 Dec
        code="GAS",
    ) == "due_soon"


def test_status_due_soon_on_expiry_day():
    assert compute_status(
        date(2026, 9, 14), date(2025, 9, 14),
        as_of=date(2026, 9, 14), code="GAS",
    ) == "due_soon"


def test_status_overdue_after_expiry():
    assert compute_status(
        date(2026, 9, 13), date(2025, 9, 13),
        as_of=date(2026, 9, 14), code="GAS",
    ) == "overdue"


def test_reminder_stubs_cover_t90_to_overdue():
    stubs = build_reminder_stubs(date(2026, 12, 31), "GAS", as_of=date(2026, 1, 1))
    offsets = [s["offsetDays"] for s in stubs]
    assert offsets == [-90, -60, -30, -14, -7, 0, 1]
    assert {s["offsetCode"] for s in stubs} == {
        "t_minus_90", "t_minus_60", "t_minus_30", "t_minus_14",
        "t_minus_7", "t_zero", "overdue",
    }
    assert all(s["status"] == "pending" for s in stubs)
    assert all(s["channel"] == "email" for s in stubs)


def test_past_offsets_are_skipped_when_created_late():
    stubs = build_reminder_stubs(date(2026, 9, 20), "GAS", as_of=date(2026, 9, 14))
    by_code = {s["offsetCode"]: s for s in stubs}
    assert by_code["t_minus_90"]["status"] == "skipped"
    assert by_code["t_minus_7"]["status"] == "skipped"  # T-7 was 13 Sep
    assert by_code["t_zero"]["status"] == "pending"
    assert by_code["overdue"]["status"] == "pending"


def test_already_overdue_keeps_overdue_stub_pending():
    stubs = build_reminder_stubs(date(2026, 1, 1), "EPC", as_of=date(2026, 9, 14))
    by_code = {s["offsetCode"]: s for s in stubs}
    assert by_code["t_zero"]["status"] == "skipped"
    assert by_code["overdue"]["status"] == "pending"
    due = due_stub_filter(stubs, as_of=date(2026, 9, 14))
    assert [s["offsetCode"] for s in due] == ["overdue"]


def test_no_reminders_without_expiry():
    assert build_reminder_stubs(None, "DEP", as_of=date(2026, 9, 14)) == []


def test_weekly_overdue_skips_missed_weeks():
    # last ping 2 Sep, as_of 14 Sep → 9 Sep is in the past, next is 16 Sep
    assert next_weekly_overdue_date(date(2026, 9, 2), date(2026, 9, 14)) == date(2026, 9, 16)


def test_weekly_overdue_stub_shape():
    stub = build_weekly_overdue_stub(
        date(2026, 9, 1), date(2026, 9, 2), as_of=date(2026, 9, 2),
    )
    assert stub["offsetCode"] == "overdue_weekly"
    assert stub["channel"] == "email"
    assert stub["status"] == "pending"
    assert stub["scheduledFor"] == "2026-09-09"
    assert stub["offsetDays"] == 8


def test_in_app_channel_can_be_seeded_without_email():
    stubs = build_reminder_stubs(
        date(2026, 12, 31), "GAS", as_of=date(2026, 1, 1), channel="in_app",
    )
    assert stubs
    assert all(s["channel"] == "in_app" for s in stubs)



# ── 2026 catalogue: Renters' Rights Act, alarms, Right to Rent, EPC 2030 ──

def test_deadline_items_default_to_their_statutory_date():
    assert default_expires_on("EPC_2030", None) == date(2030, 10, 1)
    assert default_expires_on("RRA_INFO", date(2026, 5, 20)) == date(2026, 5, 31)
    assert default_expires_on("TERMS", date(2026, 6, 1)) is None


def test_deadline_item_is_compliant_once_done_even_after_the_date():
    from compliance.status import compute_status

    served_on_time = compute_status(date(2026, 5, 31), date(2026, 5, 20), as_of=date(2026, 9, 28), code="RRA_INFO")
    assert served_on_time == "valid"
    not_served = compute_status(date(2026, 5, 31), None, as_of=date(2026, 9, 28), code="RRA_INFO")
    assert not_served == "overdue"
    # EPC C 2030 sits in "due soon" for its final year, then overdue if not done.
    assert compute_status(date(2030, 10, 1), None, as_of=date(2030, 1, 1), code="EPC_2030") == "due_soon"


def test_how_to_rent_is_marked_as_replaced():
    from compliance.catalogue import get_catalogue_item

    htr = get_catalogue_item("HTR")
    assert "1 May 2026" in htr["description"]
    assert "TERMS" in htr["description"] and "RRA_INFO" in htr["description"]

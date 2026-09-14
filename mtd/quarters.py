"""UK tax-year quarters for MTD property updates.

Standard (HMRC default): 6 Apr–5 Jul, 6 Jul–5 Oct, 6 Oct–5 Jan, 6 Jan–5 Apr.
Calendar election: 1 Apr–30 Jun, 1 Jul–30 Sep, 1 Oct–31 Dec, 1 Jan–31 Mar.
Deadlines are 7 Aug / 7 Nov / 7 Feb / 7 May regardless of basis.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

QuarterBasis = Literal["standard", "calendar"]


def parse_tax_year_start(value: date | str | None) -> date:
    if value is None:
        today = date.today()
        year = today.year if today >= date(today.year, 4, 6) else today.year - 1
        return date(year, 4, 6)
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def tax_year_label(start: date) -> str:
    yy = start.year
    return f"{yy}-{str(yy + 1)[2:]}"


def tax_year_start_from_label(label: str) -> date:
    year = int(label.split("-")[0])
    return date(year, 4, 6)


def tax_year_for_date(d: date) -> str:
    start_year = d.year if d >= date(d.year, 4, 6) else d.year - 1
    return tax_year_label(date(start_year, 4, 6))


def quarter_windows(start_year: int, basis: QuarterBasis) -> list[tuple[int, date, date]]:
    y = start_year
    if basis == "calendar":
        return [
            (1, date(y, 4, 1), date(y, 6, 30)),
            (2, date(y, 7, 1), date(y, 9, 30)),
            (3, date(y, 10, 1), date(y, 12, 31)),
            (4, date(y + 1, 1, 1), date(y + 1, 3, 31)),
        ]
    return [
        (1, date(y, 4, 6), date(y, 7, 5)),
        (2, date(y, 7, 6), date(y, 10, 5)),
        (3, date(y, 10, 6), date(y + 1, 1, 5)),
        (4, date(y + 1, 1, 6), date(y + 1, 4, 5)),
    ]


def resolve_quarter(
    tax_year: str,
    quarter: int,
    basis: QuarterBasis = "standard",
) -> tuple[date, date]:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1-4")
    start_year = int(tax_year.split("-")[0])
    for q, start, end in quarter_windows(start_year, basis):
        if q == quarter:
            return start, end
    raise ValueError("unknown quarter")


def deadline_for_quarter(tax_year: str, quarter: int) -> date:
    start_year = int(tax_year.split("-")[0])
    mapping = {
        1: date(start_year, 8, 7),
        2: date(start_year, 11, 7),
        3: date(start_year + 1, 2, 7),
        4: date(start_year + 1, 5, 7),
    }
    return mapping[quarter]

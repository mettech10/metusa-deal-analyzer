"""NPV and break-even helpers."""

from __future__ import annotations

from decimal import Decimal

from ltd_co.money import D, ZERO, money


def npv(cashflows: list[Decimal], discount_rate: Decimal) -> Decimal:
    """Year 0 undiscounted; year n discounted by (1+r)^n."""
    r = D(discount_rate)
    total = ZERO
    for t, cf in enumerate(cashflows):
        if t == 0:
            total = money(total + cf)
        else:
            total = money(total + D(cf) / ((1 + r) ** t))
    return total


def cumulative(cashflows: list[Decimal]) -> list[Decimal]:
    out: list[Decimal] = []
    running = ZERO
    for cf in cashflows:
        running = money(running + cf)
        out.append(running)
    return out


def break_even_year(
    cash_a: list[Decimal],
    cash_b: list[Decimal],
) -> int | None:
    """
    First year t (0-indexed, including acquisition) where cumulative B >= cumulative A.
    None if B never catches A inside the horizon.
    """
    if len(cash_a) != len(cash_b):
        raise ValueError("cashflow series must be the same length")
    cum_a = cumulative(cash_a)
    cum_b = cumulative(cash_b)
    for t, (a, b) in enumerate(zip(cum_a, cum_b)):
        if b >= a:
            return t
    return None

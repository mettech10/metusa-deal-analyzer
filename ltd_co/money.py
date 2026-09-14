"""Penny-safe money helpers for the Ltd Co calculator."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

TWOPLACE = Decimal("0.01")
ZERO = Decimal("0.00")


def D(value: Any) -> Decimal:
    """Coerce int/float/str/Decimal to Decimal without binary-float artefacts."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return ZERO
    if isinstance(value, bool):
        raise TypeError("boolean is not a money value")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def money(value: Any) -> Decimal:
    """Round to the nearest penny (HMRC-style half-up)."""
    return D(value).quantize(TWOPLACE, rounding=ROUND_HALF_UP)


def money0(value: Any) -> Decimal:
    """Round to the nearest pound (SDLT returns)."""
    return D(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def clamp0(value: Any) -> Decimal:
    v = money(value)
    return v if v > 0 else ZERO


def ratio(num: int | Decimal, den: int | Decimal) -> Decimal:
    return D(num) / D(den)


def to_float(value: Decimal | None, places: int = 2) -> float:
    if value is None:
        return 0.0
    q = Decimal("1").scaleb(-places)
    return float(D(value).quantize(q, rounding=ROUND_HALF_UP))


def to_json_number(value: Any, places: int = 2) -> float:
    return to_float(money(value) if places == 2 else D(value), places=places)

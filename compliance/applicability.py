"""Applicability for obligation instances.

Values: ``required`` | ``not_applicable`` | ``unknown``.
``applicable`` is accepted as an alias of ``required``.

Statutory safety: GAS may be not-applicable only with a reason
(e.g. "no gas supply"). EICR and EPC cannot be marked N/A.
"""

from __future__ import annotations

APPLICABILITIES = ("required", "not_applicable", "unknown")

# England PRS: electrical + EPC always apply to a rented home.
NA_FORBIDDEN = frozenset({"EICR", "EPC"})
# GAS N/A is allowed only with a reason (no gas supply).
NA_REASON_REQUIRED = frozenset({"GAS"})

_ALIASES = {
    "applicable": "required",
    "required": "required",
    "not_applicable": "not_applicable",
    "not-applicable": "not_applicable",
    "n_a": "not_applicable",
    "na": "not_applicable",
    "unknown": "unknown",
    "check": "unknown",
    "check_unknown": "unknown",
}


def normalize_applicability(value) -> str:
    raw = str(value or "required").strip().lower().replace(" ", "_")
    mapped = _ALIASES.get(raw)
    if mapped is None:
        raise ValueError(
            "applicability must be required, not_applicable, or unknown"
        )
    return mapped


def normalize_reason(value) -> str:
    return " ".join(str(value or "").split())


def validate_applicability(
    code: str,
    applicability: str,
    reason: str = "",
) -> tuple[str, str]:
    """Return (applicability, reason). Raises ValueError on statutory breach."""
    code = (code or "").strip().upper()
    app = normalize_applicability(applicability)
    why = normalize_reason(reason)
    if app != "not_applicable":
        return app, why if app == "not_applicable" else (why if why else "")

    if code in NA_FORBIDDEN:
        raise ValueError(
            f"{code} cannot be marked not applicable — it applies to rented homes"
        )
    if code in NA_REASON_REQUIRED and len(why) < 3:
        raise ValueError(
            "GAS not-applicable needs a reason (e.g. 'no gas supply')"
        )
    return app, why


def suppresses_reminders(applicability: str) -> bool:
    return normalize_applicability(applicability) == "not_applicable"

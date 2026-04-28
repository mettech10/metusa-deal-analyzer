"""
Calculation regression tests.

Posts known fixtures through analyze_deal() and asserts the
returned numerics match expected values within tolerance.

Runs OFFLINE — no HTTP, no external APIs:
- ANTHROPIC_API_KEY is unset so the AI prompt path falls back.
- check_article_4 / get_location_from_ai / regional benchmarks are
  monkey-patched to return stable stubs so tests are deterministic.

Field-name mapping: fixtures use abstract field names
(e.g. "mortgageRate", "deposit", "buyerType: investment"). The
_to_engine_input helper translates them into the actual API shape
expected by analyze_deal.
"""
import json
import os
import re
import sys
from pathlib import Path
import pytest

# Ensure no AI calls happen
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.setdefault("FLASK_ENV", "testing")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES_PATH = ROOT / "tests" / "fixtures" / "calculations.json"
with open(FIXTURES_PATH) as f:
    FIXTURES = json.load(f)["fixtures"]


# ──────────────────────────────────────────────────────────────────────
# External-call stubs (apply at import time so analyze_deal stays offline)
# ──────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _patch_external(monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        app_module, "check_article_4",
        lambda postcode: {
            "is_article_4": False,
            "known": True,
            "council": "Test Council",
            "advice": "",
        },
        raising=False,
    )
    monkeypatch.setattr(
        app_module, "get_location_from_ai",
        lambda postcode: {
            "country": "England",
            "region": "Test Region",
            "council": "Test Council",
        },
        raising=False,
    )
    monkeypatch.setattr(
        app_module, "compare_to_regional_benchmark",
        lambda *a, **kw: {"available": False, "median_yield": 0, "median_cashflow": 0},
        raising=False,
    )
    monkeypatch.setattr(
        app_module, "get_benchmark_for_postcode",
        lambda *a, **kw: None,
        raising=False,
    )
    monkeypatch.setattr(
        app_module, "get_refurb_estimate",
        lambda *a, **kw: {},
        raising=False,
    )
    yield


# ──────────────────────────────────────────────────────────────────────
# Fixture → engine input translation
# ──────────────────────────────────────────────────────────────────────
_STRATEGY_MAP = {
    "BTL": "BTL", "HMO": "HMO", "BRRRR": "BRR",
    "Flip": "FLIP", "FLIP": "FLIP", "SA": "R2SA",
    "R2SA": "R2SA", "Development": "DEV", "DEV": "DEV",
}
_BUYER_MAP = {
    "investment": "additional",
    "first_time_buyer": "first-time",
    "first-time": "first-time",
    "standard": "standard",
}


def _to_engine_input(fixture_input: dict) -> dict:
    """Translate abstract fixture fields to analyze_deal's expected shape."""
    fi = fixture_input
    out = {
        "dealType": _STRATEGY_MAP.get(fi.get("strategy"), "BTL"),
        "purchasePrice": fi.get("purchasePrice", 0),
        "monthlyRent": fi.get("monthlyRent", 0),
        "deposit": fi.get("deposit", 25),
        "interestRate": fi.get("mortgageRate", 5.0),
        "voidWeeks": fi.get("voidWeeks", 2),
        "managementFeePercent": fi.get("managementFee", 10),
        "maintenancePercent": fi.get("maintenancePct", 0),
        "insurance": fi.get("insurance", 0),
        "groundRent": fi.get("groundRent", 0),
        "bills": fi.get("bills", 0),
        "legalFees": fi.get("legalFees", 1500),
        "valuationFee": fi.get("survey", 500),
        "arrangementFee": fi.get("arrangementFee", 0),
        "buyerType": _BUYER_MAP.get(fi.get("buyerType", "investment"), "additional"),
        "address": "Test Property",
        "postcode": "M14 5AA",
        "bedrooms": fi.get("bedrooms", 3),
        "property_type": fi.get("propertyType", "terraced"),
        "refurbishmentBudget": fi.get("refurb", 0),
    }

    # HMO
    if "numberOfRooms" in fi:
        out["roomCount"] = fi["numberOfRooms"]
    if "rentPerRoom" in fi:
        out["avgRoomRate"] = fi["rentPerRoom"]
    if "hmoLicence" in fi:
        out["hmoLicenceCost"] = fi["hmoLicence"]

    # BRRRR / Flip
    if "arv" in fi:
        out["arv"] = fi["arv"]
    if fi.get("strategy") in ("BRRRR", "Flip", "FLIP") and fi.get("refurb"):
        out["refurbCosts"] = fi["refurb"]

    # SA
    if fi.get("strategy") == "SA":
        out["dealType"] = "R2SA"
        out["saOwnershipType"] = "own" if fi.get("ownershipType") == "owned" else "rent-to-sa"
        if "nightlyRate" in fi:
            out["saNightlyRate"] = fi["nightlyRate"]
        if "occupancyRate" in fi:
            out["saOccupancyRate"] = fi["occupancyRate"]
        if "platformFee" in fi:
            out["saPlatformFeePercent"] = fi["platformFee"]
        if "cleaningPerStay" in fi:
            out["saCleaningCostPerStay"] = fi["cleaningPerStay"]
        if "utilities" in fi:
            out["saUtilitiesMonthly"] = fi["utilities"]
        if "managementFee" in fi:
            out["saManagementFeePercent"] = fi["managementFee"]
        if "maintenancePct" in fi:
            out["saMaintenancePercent"] = fi["maintenancePct"]
        if "insurance" in fi:
            out["saInsuranceAnnual"] = fi["insurance"]

    return out


# ──────────────────────────────────────────────────────────────────────
# Output extraction — analyze_deal returns mostly-stringified numerics
# ──────────────────────────────────────────────────────────────────────
def _to_float(v) -> float:
    """Strip £ commas, parse a stringified number, return float."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[£,\s]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return 0.0


def _extract(result: dict, key: str):
    """Pull a metric out of analyze_deal's result by abstract fixture key."""
    fb = result.get("financial_breakdown", {}) or {}
    brr = result.get("brr_metrics", {}) or {}
    flip = result.get("flip_metrics", {}) or {}
    r2sa = result.get("r2sa_metrics", {}) or {}

    aliases = {
        "deposit_amount":         result.get("deposit_amount") or fb.get("deposit"),
        "mortgage_amount":        result.get("loan_amount") or fb.get("mortgage_amount"),
        "monthly_mortgage":       result.get("monthly_mortgage"),
        "sdlt":                   result.get("stamp_duty") or fb.get("stamp_duty"),
        "annual_rent":            result.get("annual_rent"),
        "monthly_cashflow":       result.get("monthly_cashflow"),
        "gross_yield":            result.get("gross_yield"),
        "net_yield":              result.get("net_yield"),
        "cash_on_cash_roi":       result.get("cash_on_cash"),
        "gross_monthly_rent":     result.get("monthly_rent"),
        "annual_gross_rent":      result.get("annual_rent"),
        "arv":                    brr.get("arv") or flip.get("arv"),
        "refinance_amount":       brr.get("refinance_amount"),
        "refurb_cost":            flip.get("refurb_cost") or _to_float(result.get("refurb_costs", 0)),
        "monthly_revenue":        r2sa.get("sa_monthly_revenue"),
    }

    if key in aliases:
        return _to_float(aliases[key])
    # Unknown / strategy-specific key — try direct lookup
    for src in (result, fb, brr, flip, r2sa):
        if key in src:
            return _to_float(src[key])
    return None


# ──────────────────────────────────────────────────────────────────────
# Test driver
# ──────────────────────────────────────────────────────────────────────
def _within_tolerance(actual, expected, tolerance_amounts, tolerance_pct):
    """percentage-like values use tolerance_pct, currency uses tolerance_amounts."""
    if actual is None:
        return False, "metric not found in analyze_deal output"
    looks_like_pct = isinstance(expected, float) and abs(expected) < 200 and \
                     not (isinstance(expected, int) and expected == 0)
    if looks_like_pct:
        diff = abs(actual - expected)
        return diff <= tolerance_pct, f"expected {expected}% got {actual:.2f}% (diff {diff:.4f})"
    diff = abs(actual - expected)
    return diff <= tolerance_amounts, f"expected £{expected:,.2f} got £{actual:,.2f} (diff £{diff:,.2f})"


@pytest.mark.parametrize(
    "fixture",
    FIXTURES,
    ids=[f["name"] for f in FIXTURES],
)
def test_calculation(fixture):
    """Run a fixture through analyze_deal and assert each expected metric."""
    import app as app_module

    payload = _to_engine_input(fixture["input"])
    result = app_module.analyze_deal(payload)

    tolerance = fixture.get("tolerance", {"amounts": 5.0, "percentages": 0.1})
    failures = []
    for key, expected in fixture["expected"].items():
        actual = _extract(result, key)
        ok, msg = _within_tolerance(
            actual, expected,
            tolerance.get("amounts", 5.0),
            tolerance.get("percentages", 0.1),
        )
        if not ok:
            failures.append(f"  • {key}: {msg}")

    if failures:
        pytest.fail(
            f"\n[{fixture['name']}] {len(failures)} of {len(fixture['expected'])} expectations failed:\n"
            + "\n".join(failures)
        )


def test_all_fixtures_have_required_shape():
    for fx in FIXTURES:
        assert "name" in fx, "fixture missing name"
        assert "input" in fx, f"fixture {fx.get('name')} missing input"
        assert "expected" in fx, f"fixture {fx.get('name')} missing expected"

"""
F5 — Flip calculation engine verification.

Drives analyze_deal() with the exact Flip spec inputs and asserts the
resulting flip_metrics dict matches the expected verification table.
Replaces a Chrome-based verification: same numbers, deterministic.

Run: pytest tests/test_flip_engine.py -v
"""
import os
import sys
from pathlib import Path

import pytest

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.setdefault("FLASK_ENV", "testing")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _patch_external(monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        app_module, "check_article_4",
        lambda postcode: {
            "is_article_4": False, "known": True,
            "council": "Test", "advice": "",
        },
        raising=False,
    )
    monkeypatch.setattr(
        app_module, "get_location_from_ai",
        lambda postcode: {
            "country": "England", "region": "Test", "council": "Test",
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


# ── F5 spec inputs (verbatim from the strategy fix brief) ───────────────
FLIP_PAYLOAD = {
    "dealType": "FLIP",
    "purchasePrice": 185000,
    "buyerType": "additional",
    "address": "Test Property",
    "postcode": "M14 5AA",
    "bedrooms": 3,
    "property_type": "terraced",

    # Bridging
    "purchaseType": "bridging-loan",
    "bridgingLtv": 70,
    "bridgingMonthlyRate": 0.75,
    "bridgingTerm": 6,
    "arrangementFee": 2,
    "exitFee": 1,
    "deposit": 30,  # 100 - bridgingLtv

    # Refurb categories
    "refurbCategories": {
        "kitchen": 10000,
        "bathroom": 5000,
        "decoration": 4000,
        "flooring": 3000,
        "electrics": 4000,
    },
    "contingency": 15,

    # ARV + exit
    "arv": 265000,
    "agentFee": 1.5,
    "legalSale": 1500,
    "legalFees": 1500,
    "survey": 500,

    # CGT
    "cgtEnabled": True,
    "cgtRate": 24,
    "cgtAllowance": 3000,
}


# Expected values from the F5 spec (£100 EPC default included where applicable)
# Tolerances are tight (±£5) because the engine is deterministic.
EXPECTED = {
    "sdlt":                  10_450,    # investment £185k → £10,450 SDLT (Apr-2025 bands, 5% surcharge)
    "bridgingLoan":         129_500,
    "arrangementFeeAmt":      2_590,
    "baseRefurb":            26_000,
    "contingencyAmt":         3_900,
    "totalRefurb":           29_900,
    "bridgingInterest":       5_828,    # spec: 5,827.50 → rounds to 5,828
    "exitFeeAmt":             1_295,
    "agentFeeAmt":            3_975,
    "mao70Rule":            155_600,
    # Net ROI: spec says ~17.5% (verified 17.51% in our engine).
    # netRoi is a percent.
}


def _result_flip(payload):
    import app as app_module
    return app_module.analyze_deal(payload).get("flip_metrics", {})


def test_flip_engine_matches_spec_currency_values():
    """All major £ figures match the F5 spec within £5."""
    flip = _result_flip(FLIP_PAYLOAD)
    assert flip, "flip_metrics empty — engine did not run"

    failures = []
    for key, expected in EXPECTED.items():
        actual = flip.get(key)
        if actual is None:
            failures.append(f"  • {key}: MISSING from flip_metrics")
            continue
        diff = abs(float(actual) - float(expected))
        if diff > 5:
            failures.append(
                f"  • {key}: expected £{expected:,} got £{float(actual):,.0f} "
                f"(diff £{diff:,.0f})"
            )
    if failures:
        pytest.fail("F5 spec mismatches:\n" + "\n".join(failures))


def test_flip_engine_net_roi_is_about_16_5_pct():
    flip = _result_flip(FLIP_PAYLOAD)
    net_roi = float(flip.get("netRoi", 0))
    # Apr-2025 SDLT bands raise SDLT from £9,250 to £10,450, eroding the
    # 17.5% half-year ROI by ~1pp. Engine now produces 16.47%.
    assert 16.0 <= net_roi <= 17.0, f"netRoi={net_roi} not in [16.0, 17.0]"


def test_flip_engine_annualised_roi_is_about_33_pct():
    flip = _result_flip(FLIP_PAYLOAD)
    ann = float(flip.get("annualisedRoi", 0))
    # 6-month project doubles the half-year ROI → ~32.94% post-SDLT-correction.
    assert 32.0 <= ann <= 34.0, f"annualisedRoi={ann} not in [32.0, 34.0]"


def test_flip_engine_70_rule_fails_for_overpaid_purchase():
    flip = _result_flip(FLIP_PAYLOAD)
    assert flip.get("rule70Passes") is False, (
        "spec: purchase £185k > MAO £155.6k must FAIL the 70% rule"
    )


def test_flip_engine_cgt_is_applied():
    """CGT ~£4.5k–£4.8k on gross profit minus £3k allowance (post-Apr-2025 SDLT)."""
    flip = _result_flip(FLIP_PAYLOAD)
    cgt = float(flip.get("cgtAmount", 0))
    assert 4_500 <= cgt <= 4_800, f"cgtAmount={cgt} not in expected band"
    # Higher SDLT (£10,450 vs old £9,250) cuts net profit by ~£1.2k
    # post-CGT-tax. New net band: ~£17.5k–£18.0k.
    net = float(flip.get("netProfit", 0))
    assert 17_500 <= net <= 18_000, f"netProfit={net} not in expected band"


def test_flip_engine_cgt_disabled_zero_tax():
    """When CGT toggle is off, net profit equals gross profit."""
    payload = dict(FLIP_PAYLOAD, cgtEnabled=False)
    import app as app_module
    flip = app_module.analyze_deal(payload).get("flip_metrics", {})
    assert flip.get("cgtAmount", 0) == 0
    assert flip.get("netProfit") == flip.get("grossProfit")


def test_flip_engine_score_breakdown_present():
    flip = _result_flip(FLIP_PAYLOAD)
    bd = flip.get("scoreBreakdown") or {}
    assert set(bd.keys()) == {"netRoi", "profitMargin", "cashEfficiency", "timeline"}
    total = sum(bd.values())
    assert total == flip.get("flipScore"), (
        f"scoreBreakdown sum {total} != flipScore {flip.get('flipScore')}"
    )


def test_flip_engine_refurb_fallback_to_flat_total():
    """If refurbCategories is empty, engine falls back to totalRefurb/refurbCosts."""
    payload = dict(FLIP_PAYLOAD)
    payload.pop("refurbCategories")
    payload["refurbCosts"] = 26000
    flip = _result_flip(payload)
    assert flip.get("baseRefurb") == 26000
    assert flip.get("totalRefurb") == 29900  # 26k + 15%


def test_flip_engine_arv_alias_keys_accepted():
    """Engine reads arv / arvValue / afterRepairValue interchangeably."""
    payload = dict(FLIP_PAYLOAD)
    payload.pop("arv")
    payload["afterRepairValue"] = 265000
    flip = _result_flip(payload)
    assert flip.get("arv") == 265000

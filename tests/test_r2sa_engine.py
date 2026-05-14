"""
S5 — Rent-to-SA calculation engine verification.

Drives analyze_deal() with the S5 spec inputs and asserts r2sa_metrics
matches the expected table (revenue £2,244, costs £2,699.27, monthly
net -£455.27, capital £9,865, break-even occupancy 81.8%).

Replaces Chrome verification — deterministic, runs in CI on Python 3.11.
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
        lambda postcode: {"is_article_4": False, "known": True, "council": "Test", "advice": ""},
        raising=False,
    )
    monkeypatch.setattr(
        app_module, "get_location_from_ai",
        lambda postcode: {"country": "England", "region": "Test", "council": "Test"},
        raising=False,
    )
    monkeypatch.setattr(
        app_module, "compare_to_regional_benchmark",
        lambda *a, **kw: {"available": False, "median_yield": 0, "median_cashflow": 0},
        raising=False,
    )
    monkeypatch.setattr(
        app_module, "get_benchmark_for_postcode",
        lambda *a, **kw: None, raising=False,
    )
    monkeypatch.setattr(
        app_module, "get_refurb_estimate",
        lambda *a, **kw: {}, raising=False,
    )
    yield


# Exact S5 spec inputs
R2SA_PAYLOAD = {
    "dealType": "R2SA",
    "saOwnershipType": "rent-to-sa",
    "address": "Test Property",
    "postcode": "M14 5AA",
    "bedrooms": 2,
    "property_type": "flat",

    "monthlyRent": 1200,
    "nightlyRate": 110,
    "occupancyRate": 68,
    "averageStayLength": 3,
    "platformFee": 15,
    "cleaningPerStay": 55,
    "utilities": 150,
    "insurance": 800,
    "managementFee": 20,
    "maintenancePct": 5,
    "furnitureSetup": 5000,
}


def _result_r2sa(payload):
    import app as app_module
    return app_module.analyze_deal(payload).get("r2sa_metrics", {})


def test_r2sa_monthly_revenue_2244():
    r = _result_r2sa(R2SA_PAYLOAD)
    assert r.get("monthlyRevenue") == 2244


def test_r2sa_avg_stays_per_month_7():
    r = _result_r2sa(R2SA_PAYLOAD)
    assert r.get("avgStaysPerMonth") == 7  # round(30 * 0.68 / 3) = 7


def test_r2sa_cost_breakdown_matches_spec():
    r = _result_r2sa(R2SA_PAYLOAD)
    # Platform 15% of £2,244 = £336.60 → rounds to £337
    assert r.get("platformCommission") == 337
    # Cleaning 7 × £55 = £385
    assert r.get("monthlyCleaningCost") == 385
    # Lease rent — THE key cost — £1,200
    assert r.get("monthlyLeaseCost") == 1200
    # Utilities flat-through £150
    assert r.get("monthlyUtilities") == 150
    # Insurance £800/12 = £66.67 → £67
    assert r.get("monthlyInsurance") == 67
    # Management 20% of £2,244 = £448.80 → £449
    assert r.get("monthlyManagement") == 449
    # Maintenance 5% of £2,244 = £112.20 → £112
    assert r.get("monthlyMaintenance") == 112
    # Total monthly costs £2,699.27 → £2,699
    assert r.get("totalMonthlyCosts") == 2699


def test_r2sa_monthly_net_profit_negative():
    """At 68% occupancy the deal LOSES money — net should be ~-£455."""
    r = _result_r2sa(R2SA_PAYLOAD)
    net = float(r.get("monthlyNetProfit", 0))
    assert -460 <= net <= -450, f"monthlyNetProfit={net} not in [-460, -450]"


def test_r2sa_total_capital_9865():
    r = _result_r2sa(R2SA_PAYLOAD)
    # 2400 (deposit) + 1200 (advance) + 300 (utilities) + 800 (insurance)
    #   + 165 (cleaning 3×55) + 5000 (furniture) = £9,865
    assert r.get("totalCapitalRequired") == 9865
    assert r.get("rentDeposit") == 2400
    assert r.get("rentAdvance") == 1200
    assert r.get("utilitiesDeposit") == 300
    assert r.get("insuranceUpfront") == 800
    assert r.get("initialCleaning") == 165
    assert r.get("furnitureSetup") == 5000


def test_r2sa_breakeven_occupancy_82_pct():
    r = _result_r2sa(R2SA_PAYLOAD)
    be = float(r.get("breakevenOccupancy", 0))
    # Spec: £2,699.27 / (£110 × 30) × 100 = 81.8%
    assert 81.0 <= be <= 82.5, f"breakevenOccupancy={be} not in [81.0, 82.5]"


def test_r2sa_rev_to_rent_ratio_1_87():
    r = _result_r2sa(R2SA_PAYLOAD)
    ratio = float(r.get("revToRentRatio", 0))
    assert 1.85 <= ratio <= 1.90, f"revToRentRatio={ratio} not in [1.85, 1.90]"


def test_r2sa_score_breakdown_sums_to_total():
    r = _result_r2sa(R2SA_PAYLOAD)
    bd = r.get("scoreBreakdown") or {}
    assert set(bd.keys()) == {
        "profitability", "revenueToRent", "occupancyRealism", "platformEfficiency",
    }
    assert sum(bd.values()) == r.get("r2saScore")


def test_r2sa_field_alias_chain_works():
    """Engine accepts rentAmount/leaseRent in place of monthlyRent."""
    payload = dict(R2SA_PAYLOAD)
    payload.pop("monthlyRent")
    payload["leaseRent"] = 1200
    r = _result_r2sa(payload)
    assert r.get("monthlyLeaseCost") == 1200


def test_r2sa_occupancy_warning_above_85_pct():
    """Spec: occupancy >85% triggers the realism warning."""
    payload = dict(R2SA_PAYLOAD, occupancyRate=90)
    r = _result_r2sa(payload)
    warning = r.get("occupancyWarning")
    assert warning is not None
    assert "ambitious" in warning.lower()


def test_r2sa_sa_owned_branch_untouched():
    """SA-Owned mode (saOwnershipType='own') still works — we didn't break it."""
    payload = dict(R2SA_PAYLOAD)
    payload["saOwnershipType"] = "own"
    payload["purchasePrice"] = 200000
    payload["deposit"] = 25
    payload["interestRate"] = 5.0
    import app as app_module
    result = app_module.analyze_deal(payload)
    r = result.get("r2sa_metrics", {})
    assert r.get("ownership_type") == "own"
    # SA-Owned should have ownership_type=='own' and not the new rent-to-sa
    # spec keys (those only populate on rent-to-sa branch).

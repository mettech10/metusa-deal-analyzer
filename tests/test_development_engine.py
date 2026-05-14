"""
D5 — Development calculation engine verification.

Drives analyze_deal() with the D5 spec inputs (£350k land / 620m² GIA /
£1.6k/m² build / 18-month / 70% LTC / £2.2M GDV) and asserts dev_metrics
matches the spec verification table:
  TDC £1,732,644 · Total Project Cost £1,987,572 · Gross Profit £212,428
  Profit/GDV 9.66% (RED) · LTGDV 55.13% (GREEN) · ROE 40.87% · RLV £122,428

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


# Exact D5 spec inputs — site M14 5AA, mixed 8-unit scheme
DEV_PAYLOAD = {
    "dealType": "DEV",
    "buyerType": "additional",
    "address": "Test Site",
    "postcode": "M14 5AA",
    "purchasePrice": 350000,
    "landPrice": 350000,

    "units": [
        {"count": 4, "sizeM2": 60, "salePricePerUnit": 0},   # GDV set globally
        {"count": 3, "sizeM2": 90, "salePricePerUnit": 0},
        {"count": 1, "sizeM2": 110, "salePricePerUnit": 0},
    ],
    "buildCostPerM2": 1600,
    "contingency": 10,
    "professionalFees": 12,
    "cil": 50000,
    "s106": 80000,
    "buildingRegs": 3000,

    "financeLtc": 70,
    "financeRate": 8,
    "projectDuration": 18,
    "arrangementFee": 2,
    "exitFee": 1,
    "monitoringSurveyor": 5000,

    "agentFee": 1.5,
    "legalPerUnit": 1500,
    "marketing": 15000,
    "warranty": 1000,
    "legalPurchase": 3000,
    "survey": 5000,

    "gdv": 2200000,
}


def _result_dev(payload):
    import app as app_module
    return app_module.analyze_deal(payload).get("dev_metrics", {})


def test_dev_gia_and_units_summed_from_unit_mix():
    """When totalGia not supplied, engine derives 620m² from unit mix."""
    d = _result_dev(DEV_PAYLOAD)
    assert d.get("totalGia") == 620   # 4×60 + 3×90 + 1×110
    assert d.get("totalUnits") == 8


def test_dev_construction_stack():
    d = _result_dev(DEV_PAYLOAD)
    assert d.get("baseBuildCost") == 992_000    # 1600 × 620
    assert d.get("contingencyAmt") == 99_200    # 10% of base
    assert d.get("totalConstruction") == 1_091_200
    assert d.get("professionalFees") == 130_944   # 12% of construction


def test_dev_acquisition_stack():
    d = _result_dev(DEV_PAYLOAD)
    assert d.get("sdlt") == 19_500   # investment SDLT on £350k
    assert d.get("totalAcquisition") == 377_500   # land + sdlt + legal + survey
    assert d.get("planningObligations") == 133_000   # 50k CIL + 80k s106 + 3k regs
    assert d.get("totalDevCosts") == 1_732_644


def test_dev_finance_stack():
    d = _result_dev(DEV_PAYLOAD)
    assert d.get("devLoan") == 1_212_851
    assert d.get("devEquity") == 519_793
    assert d.get("rolledInterest") == 145_542   # loan × 8% × 18/12
    assert d.get("arrangementFeeAmt") == 24_257
    assert d.get("exitFeeAmt") == 12_129
    assert d.get("totalFinance") == 186_928


def test_dev_exit_costs_and_total_project_cost():
    d = _result_dev(DEV_PAYLOAD)
    assert d.get("agentFeeAmt") == 33_000        # 1.5% × £2.2M
    assert d.get("salesLegal") == 12_000          # 8 × £1,500
    assert d.get("warrantyTotal") == 8_000        # 8 × £1,000
    assert d.get("totalExit") == 68_000           # agent + legal + warranty + £15k mkt
    assert d.get("totalProjectCost") == 1_987_572


def test_dev_profit_metrics_match_spec():
    d = _result_dev(DEV_PAYLOAD)
    assert d.get("grossProfit") == 212_428
    assert abs(float(d.get("profitOnGdv", 0)) - 9.66) < 0.01
    assert abs(float(d.get("profitOnCost", 0)) - 10.69) < 0.01
    assert abs(float(d.get("ltgdv", 0)) - 55.13) < 0.05
    assert abs(float(d.get("roe", 0)) - 40.87) < 0.05


def test_dev_residual_land_value():
    d = _result_dev(DEV_PAYLOAD)
    assert d.get("residualLandValue") == 122_428
    # Land paid £350k, RLV £122,428 → over-paying by £227,572
    assert d.get("landPremium") == -227_572


def test_dev_viability_flags():
    d = _result_dev(DEV_PAYLOAD)
    # Profit on GDV 9.66% → red (target 20%, lender floor 15%)
    assert d.get("profitGdvFlag") == "red"
    # Profit on cost 10.69% → red (target 25%, lender floor 18%)
    assert d.get("profitCostFlag") == "red"
    # LTGDV 55.1% → green (cap 65%)
    assert d.get("ltgdvFlag") == "green"


def test_dev_score_breakdown_sums_to_total():
    d = _result_dev(DEV_PAYLOAD)
    bd = d.get("scoreBreakdown") or {}
    assert set(bd.keys()) == {
        "profitOnGdv", "profitOnCost", "returnOnEquity", "ltgdv",
    }
    assert sum(bd.values()) == d.get("devScore")


def test_dev_field_alias_chain_works():
    """Engine accepts loanToCost/ltc in place of financeLtc."""
    payload = dict(DEV_PAYLOAD)
    payload.pop("financeLtc")
    payload["ltc"] = 70
    d = _result_dev(payload)
    assert d.get("ltcPct") == 70


def test_dev_verdict_avoid_for_low_profit_on_cost():
    """10.69% PoC is below the 15% review threshold → AVOID."""
    import app as app_module
    result = app_module.analyze_deal(DEV_PAYLOAD)
    assert result.get("verdict") == "AVOID"


def test_dev_does_not_break_btl_payload():
    """Regression: a BTL payload should NOT populate dev_metrics."""
    import app as app_module
    btl = {
        "dealType": "BTL",
        "purchasePrice": 200000,
        "monthlyRent": 1200,
        "deposit": 25,
        "interestRate": 5.0,
        "buyerType": "additional",
        "address": "Test", "postcode": "M14 5AA", "bedrooms": 3,
        "property_type": "terraced",
    }
    result = app_module.analyze_deal(btl)
    assert result.get("dev_metrics") == {}
    assert result.get("verdict") in {"PROCEED", "REVIEW", "AVOID"}

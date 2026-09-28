"""Incorporating an existing property: transfer costs + keep-vs-incorporate NPV.

Figures are worked by hand in the comments.
"""

from __future__ import annotations

import pytest
from flask import Flask

from ltd_co.engine import dispatch
from ltd_co.flask_api import ltd_co_bp

BASE = {
    "property": {
        "marketValue": 250000,
        "originalPurchasePrice": 150000,
        "purchaseCosts": 5000,
        "monthlyRent": 1250,
        "annualOperatingExpenses": 3000,
    },
    "financing": {
        "outstandingMortgage": 187500,
        "personalInterestRate": 0.045,
        "companyInterestRate": 0.055,
        "earlyRepaymentCharge": 2812.5,
        "refinanceFees": 1995,
        "transferLegalFees": 1500,
    },
    "landlord": {"otherNonSavingsIncome": 60000},
    "company": {"formationCost": 100, "annualComplianceCost": 1200, "extractDividends": "all"},
    "horizonYears": 10,
    "discountRate": 0.05,
}


def run(**overrides):
    payload = {**BASE}
    for key, value in overrides.items():
        payload[key] = {**BASE.get(key, {}), **value} if isinstance(value, dict) else value
    return dispatch("incorporation", payload)


def test_higher_rate_transfer_costs_by_hand():
    out = run()
    t = out["transfer"]
    # Gain = 250,000 - (150,000 + 5,000) - 1,500 legal = 93,500
    assert t["cgt"]["gain"] == pytest.approx(93500)
    # ANI 60,000 + 12,000 profit = 72,000 -> taxable 59,430, basic band used up.
    assert t["taxableIncomeUsedForCgtBand"] == pytest.approx(59430)
    # (93,500 - 3,000) x 24% = 21,720
    assert t["cgt"]["taxableGain"] == pytest.approx(90500)
    assert t["cgt"]["basicRatePortion"] == 0
    assert t["cgt"]["tax"] == pytest.approx(21720)
    # Company SDLT on 250k: 125k x 5% + 125k x 7% = 15,000
    assert t["costs"]["sdlt"] == pytest.approx(15000)
    assert t["total"] == pytest.approx(21720 + 15000 + 2812.5 + 1995 + 1500 + 100)
    # Personal path has no year-0 cost; incorporating starts at -transfer total.
    assert out["paths"]["A"]["years"][0]["cashToIndividual"] == 0
    assert out["paths"]["B"]["years"][0]["cashToIndividual"] == pytest.approx(-t["total"])
    assert out["metadata"]["lean"] == "path_a_personal"
    assert out["breakEven"]["year"] is None


def test_basic_rate_band_splits_the_gain():
    out = run(landlord={"otherNonSavingsIncome": 20000})
    cgt = out["transfer"]["cgt"]
    # ANI 32,000 -> taxable 19,430 -> 18,270 of basic band left.
    assert cgt["basicRatePortion"] == pytest.approx(18270)
    assert cgt["higherRatePortion"] == pytest.approx(72230)
    assert cgt["tax"] == pytest.approx(18270 * 0.18 + 72230 * 0.24)


def test_other_gains_use_the_annual_exempt_amount_first():
    out = run(landlord={"otherNonSavingsIncome": 60000, "otherGainsThisYear": 5000})
    cgt = out["transfer"]["cgt"]
    assert cgt["annualExemptAmountUsed"] == 0
    assert cgt["taxableGain"] == pytest.approx(93500)


def test_reliefs_are_opt_in_and_zero_the_right_tax():
    out = run(reliefs={"incorporationRelief": True, "partnershipSdltRelief": True})
    t = out["transfer"]
    assert t["cgt"]["tax"] == 0
    assert t["cgt"]["deferredGain"] == pytest.approx(93500)
    assert any("6 April 2026" in n for n in t["cgt"]["notes"])
    assert t["costs"]["sdlt"] == 0
    assert t["total"] == pytest.approx(2812.5 + 1995 + 1500 + 100)


def test_operating_years_match_the_purchase_engine():
    out = run()
    y1a = out["paths"]["A"]["years"][1]
    # Same Section 24 year-1 figures as the new-purchase compare test.
    assert y1a["tax"] == pytest.approx(3112.5, abs=0.01)
    assert out["paths"]["A"]["years"][2]["taxYear"] == "2027/28"


@pytest.mark.parametrize(
    "bad,match",
    [
        ({"property": {"marketValue": 0}}, "marketValue"),
        ({"property": {"originalPurchasePrice": 0, "purchaseCosts": 0}}, "originalPurchasePrice"),
        ({"financing": {"outstandingMortgage": 300000}}, "outstandingMortgage"),
    ],
)
def test_validation(bad, match):
    with pytest.raises(ValueError, match=match):
        run(**bad)


def test_flask_route():
    app = Flask(__name__)
    app.register_blueprint(ltd_co_bp)
    client = app.test_client()
    ok = client.post("/v1/ltd-co/incorporation", json=BASE)
    assert ok.status_code == 200
    assert ok.get_json()["mode"] == "existing_property"
    bad = client.post("/v1/ltd-co/incorporation", json={"property": {}})
    assert bad.status_code == 400

"""
Ltd Co Calculator golden fixtures.

Offline, no HTTP, no HMRC. Drives the pure `ltd_co` package and the Flask
blueprint mounted on a tiny app (does not import the 10k-line app.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from flask import Flask

from ltd_co.engine import compare, corporation_tax, discovery, dividends, rates, sdlt, section24
from ltd_co.income_tax import compute_income_tax, personal_allowance
from ltd_co.money import D, money
from ltd_co.npv import break_even_year, npv
from ltd_co.rates import DEFAULT_PACK_ID, load_rate_pack
from ltd_co.section24 import compute_section24

ROOT = Path(__file__).resolve().parent
GOLDEN = json.loads((ROOT / "fixtures" / "ltd_co" / "golden.json").read_text())


@pytest.fixture(scope="module")
def packs():
    return load_rate_pack()


def _income_tax_for_s24(fx_input, packs, s24):
    ns = D(fx_input.get("otherNonSavingsIncome") or 0) + s24.property_profit
    return compute_income_tax(
        non_savings_income=ns,
        savings_income=D(fx_input.get("savingsIncome") or 0),
        dividend_income=D(fx_input.get("dividendIncome") or 0),
        section24_reducer=s24.tax_reducer,
        packs=packs,
    )


def _unrestricted_tax(fx_input, packs, s24):
    """Counterfactual: finance costs deducted from property profit (pre-s24)."""
    profit = s24.property_profit - s24.finance_costs_current_year
    if profit < 0:
        profit = D(0)
    ns = D(fx_input.get("otherNonSavingsIncome") or 0) + profit
    return compute_income_tax(
        non_savings_income=ns,
        savings_income=D(fx_input.get("savingsIncome") or 0),
        dividend_income=D(fx_input.get("dividendIncome") or 0),
        packs=packs,
    )


def test_rate_pack_is_pinned(packs):
    pin = packs.pin()
    assert pin["id"] == DEFAULT_PACK_ID
    assert pin["taxYear"] == "2026/27"
    assert pin["status"] == "illustrative"
    assert pin["pinned"] is True
    assert len(pin["sha256"]) == 64
    disc = discovery()
    assert disc["ratePack"]["sha256"] == pin["sha256"]
    assert "hmrc-mtd" in disc["excluded"]
    assert "screener" in disc["excluded"]
    body = rates()
    assert body["ratePack"]["id"] == DEFAULT_PACK_ID
    assert body["raw"]["sdlt"]["rentalBusinessReliefDefault"] is True


@pytest.mark.parametrize("fx", GOLDEN["fixtures"], ids=lambda f: f["id"])
def test_golden_fixture(fx, packs):
    action = fx["action"]
    inp = fx["input"]
    exp = fx["expect"]

    if action == "section-24":
        out = section24(inp)
        s = out["section24"]
        for key in (
            "propertyProfit",
            "actualAmount",
            "taxReducer",
            "financeCostsCarriedForward",
            "relievableAmount",
        ):
            if key in exp:
                assert s[key] == pytest.approx(exp[key], abs=0.01), key
        if "lowerOfThree" in exp:
            for k, v in exp["lowerOfThree"].items():
                if k == "bindingLimb":
                    assert s["lowerOfThree"]["bindingLimb"] == v
                else:
                    assert s["lowerOfThree"][k] == pytest.approx(v, abs=0.01), k
        assert out["ratePack"]["id"] == DEFAULT_PACK_ID
        assert out["ratePack"]["sha256"] == packs.sha256

        s24 = compute_section24(
            rental_income=D(inp["rentalIncome"]),
            allowable_non_finance_expenses=D(inp["allowableNonFinanceExpenses"]),
            finance_costs=D(inp["financeCosts"]),
            packs=packs,
            other_non_savings_income=D(inp.get("otherNonSavingsIncome") or 0),
            finance_costs_brought_forward=D(inp.get("financeCostsBroughtForward") or 0),
        )
        it = _income_tax_for_s24(inp, packs, s24)
        if "incomeTax" in exp:
            assert float(it.income_tax) == pytest.approx(exp["incomeTax"], abs=0.01)
        if "incomeTaxIfInterestDeducted" in exp or "extraTaxVsFullDeduction" in exp:
            unrestricted = _unrestricted_tax(inp, packs, s24)
            if "incomeTaxIfInterestDeducted" in exp:
                assert float(unrestricted.income_tax) == pytest.approx(
                    exp["incomeTaxIfInterestDeducted"], abs=0.01
                )
            extra = float(it.income_tax - unrestricted.income_tax)
            if "extraTaxVsFullDeduction" in exp:
                assert extra == pytest.approx(exp["extraTaxVsFullDeduction"], abs=0.01)
            if "folkloreTwentyPercentOfInterest" in exp:
                # Guard against the folklore shortcut replacing the statute.
                folklore = exp["folkloreTwentyPercentOfInterest"]
                if exp.get("extraTaxVsFullDeduction") != folklore:
                    assert extra == pytest.approx(exp["extraTaxVsFullDeduction"], abs=0.01)
                    assert extra != pytest.approx(folklore, abs=0.01)

    elif action == "corporation-tax":
        out = corporation_tax(inp)["corporationTax"]
        for k, v in exp.items():
            if isinstance(v, str):
                assert out[k] == v
            else:
                assert out[k] == pytest.approx(v, abs=0.01), k

    elif action == "sdlt":
        out = sdlt(inp)["comparison"]
        assert out["personalAdditional"]["total"] == pytest.approx(exp["personalAdditional"], abs=0.01)
        assert out["company"]["total"] == pytest.approx(exp["company"], abs=0.01)
        if "deltaCompanyMinusPersonal" in exp:
            assert out["deltaCompanyMinusPersonal"] == pytest.approx(
                exp["deltaCompanyMinusPersonal"], abs=0.01
            )
        if "companyRegime" in exp:
            assert out["company"]["regime"] == exp["companyRegime"]
        assert out["personalAdditional"]["purchaser"] == "personal_additional"

    elif action == "dividends":
        out = dividends(inp)["dividends"]
        for k, v in exp.items():
            assert out[k] == pytest.approx(v, abs=0.01), k

    else:
        raise AssertionError(f"unknown action {action}")


def test_sdlt_relief_defaults_on(packs):
    on = sdlt({"consideration": 600000})
    assert on["comparison"]["company"]["rentalBusinessRelief"] is True
    assert on["comparison"]["company"]["total"] == pytest.approx(50000, abs=0.01)
    assert on["comparison"]["deltaCompanyMinusPersonal"] == pytest.approx(0, abs=0.01)


def test_pa_taper(packs):
    assert personal_allowance(D(100000), packs) == D("12570")
    assert personal_allowance(D(125140), packs) == D("0")
    assert personal_allowance(D(115000), packs) == D("5070")


def test_npv_and_break_even():
    cfa = [D("-10000"), D("3000"), D("3000"), D("3000")]
    cfb = [D("-12000"), D("4000"), D("4000"), D("4000")]
    assert npv(cfa, D("0.05")) == money(
        D("-10000") + D("3000") / D("1.05") + D("3000") / D("1.05") ** 2 + D("3000") / D("1.05") ** 3
    )
    assert break_even_year(cfa, cfb) == 2
    assert break_even_year(cfa, [D("-20000"), D("100"), D("100"), D("100")]) is None


def test_path_ab_compare_pins_pack_and_soft_lean(packs):
    payload = {
        "horizonYears": 10,
        "discountRate": 0.05,
        "property": {
            "purchasePrice": 250000,
            "monthlyRent": 1200,
            "annualOperatingExpenses": 2400,
        },
        "financing": {
            "ltv": 0.75,
            "personalInterestRate": 0.045,
            "companyInterestRate": 0.055,
        },
        "landlord": {"otherNonSavingsIncome": 60000},
        "company": {
            "associatedCompanies": 0,
            "rentalBusinessRelief": True,
            "formationCost": 165,
            "annualComplianceCost": 1500,
            "extractDividends": "all",
        },
        "growth": {"rentGrowth": 0, "expenseGrowth": 0},
    }
    out = compare(payload)
    assert out["ratePack"]["id"] == DEFAULT_PACK_ID
    assert out["ratePack"]["sha256"] == packs.sha256
    assert out["engine"]["excluded"] == [
        "hmrc-mtd",
        "compliance-module",
        "licensing-geo",
        "screener",
    ]
    meta = out["metadata"]
    assert meta["leanStrength"] == "soft"
    assert meta["notAdvice"] is True
    assert meta["lean"] in ("path_a_personal", "path_b_company", "neutral")
    assert "not a recommendation" in meta["rationale"].lower() or "no lean" in meta["rationale"].lower()
    assert "should" not in meta["rationale"].lower()
    assert out["paths"]["A"]["id"] == "path_a_personal"
    assert out["paths"]["B"]["id"] == "path_b_company"
    assert len(out["paths"]["A"]["years"]) == 11
    assert out["sdltComparison"]["rentalBusinessRelief"] is True
    assert out["sdltComparison"]["deltaCompanyMinusPersonal"] == pytest.approx(0, abs=0.01)

    y1a = out["paths"]["A"]["years"][1]["section24"]
    assert y1a["bindingLimb"] in ("finance_costs", "property_profits", "adjusted_total_income")
    y1b = out["paths"]["B"]["years"][1]
    assert y1b["associatedCompanies"] == 0
    assert "corporationTax" in y1b
    assert out["extractionLens"]["extractAll"]["extracted"] > 0
    # Higher-rate landlord: extra company interest + compliance outweigh s24 drag here.
    assert out["npv"]["pathA"] == pytest.approx(-74025.21, abs=0.05)
    assert out["npv"]["pathB"] == pytest.approx(-76492.30, abs=0.05)
    assert out["metadata"]["lean"] == "path_a_personal"
    assert out["breakEven"]["year"] is None
    y1a_ops = out["paths"]["A"]["years"][1]
    assert y1a_ops["tax"] == pytest.approx(3112.5, abs=0.01)
    assert y1a_ops["section24"]["taxReducer"] == pytest.approx(1687.5, abs=0.01)
    assert y1a_ops["cashToIndividual"] == pytest.approx(450.0, abs=0.01)


def test_path_ab_basic_rate_personal_often_competitive(packs):
    payload = {
        "horizonYears": 8,
        "discountRate": 0.05,
        "property": {
            "purchasePrice": 180000,
            "annualRent": 11400,
            "annualOperatingExpenses": 1800,
        },
        "financing": {
            "ltv": 0.75,
            "personalInterestRate": 0.045,
            "companyInterestRate": 0.06,
        },
        "landlord": {"otherNonSavingsIncome": 25000},
        "company": {
            "associatedCompanies": 1,
            "annualComplianceCost": 1800,
            "formationCost": 165,
            "extractDividends": "all",
        },
    }
    out = compare(payload)
    y1 = out["paths"]["A"]["years"][1]
    # Basic-rate taxpayer: extra s24 drag should be ~0 (finance limb, stays basic).
    assert y1["section24"]["bindingLimb"] == "finance_costs"
    # Associated company splits CT bands.
    assert out["paths"]["B"]["years"][1]["associatedCompanies"] == 1
    assert out["paths"]["B"]["years"][1]["ctLowerLimit"] == pytest.approx(25000, abs=0.01)


def test_flask_blueprint_compare_and_rates():
    from ltd_co.flask_api import ltd_co_api_bp, ltd_co_bp

    app = Flask(__name__)
    app.register_blueprint(ltd_co_bp)
    app.register_blueprint(ltd_co_api_bp)
    client = app.test_client()

    r = client.get("/v1/ltd-co/")
    assert r.status_code == 200
    body = r.get_json()
    assert body["defaultRatePackId"] == DEFAULT_PACK_ID

    r = client.get("/v1/ltd-co")
    assert r.status_code == 200
    assert r.get_json()["defaultRatePackId"] == DEFAULT_PACK_ID

    r = client.get("/api/v1/ltd-co/rates")
    assert r.status_code == 200
    assert r.get_json()["ratePack"]["taxYear"] == "2026/27"

    r = client.post(
        "/v1/ltd-co/section-24",
        json={
            "rentalIncome": 20000,
            "allowableNonFinanceExpenses": 7000,
            "financeCosts": 15000,
            "otherNonSavingsIncome": 36000,
        },
    )
    assert r.status_code == 200
    s = r.get_json()["section24"]
    assert s["financeCostsCarriedForward"] == pytest.approx(2000, abs=0.01)
    assert r.get_json()["ratePack"]["id"] == DEFAULT_PACK_ID

    r = client.post("/v1/ltd-co/compare", json={"property": {"purchasePrice": 0}})
    assert r.status_code == 400

    r = client.post(
        "/api/v1/ltd-co/compare",
        json={
            "horizonYears": 3,
            "property": {
                "purchasePrice": 250000,
                "monthlyRent": 1100,
                "annualOperatingExpenses": 2000,
            },
            "landlord": {"otherNonSavingsIncome": 45000},
        },
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["metadata"]["leanStrength"] == "soft"
    assert data["ratePack"]["sha256"]
    assert data["breakEven"]["year"] is None or isinstance(data["breakEven"]["year"], int)

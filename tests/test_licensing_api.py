"""Flask route tests for POST /v1/licensing/check — offline."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("LICENSING_CHECKER_V1", "true")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from licensing.geo import GeoError  # noqa: E402
from licensing.models import DISCLAIMER_VERSION  # noqa: E402

M14 = {
    "status": 200,
    "result": {
        "postcode": "M14 6LT",
        "quality": 1,
        "longitude": -2.221744,
        "latitude": 53.444792,
        "country": "England",
        "region": "North West",
        "admin_district": "Manchester",
        "admin_ward": "Fallowfield",
        "outcode": "M14",
        "incode": "6LT",
        "codes": {"admin_district": "E08000003"},
    },
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LICENSING_CHECKER_V1", "true")
    import app as app_module

    monkeypatch.setattr("licensing.geo._default_fetch", lambda url: M14)
    monkeypatch.setattr(
        "licensing.article4._default_fetch",
        lambda url, params: {"entities": [], "count": 0},
    )
    monkeypatch.setattr(
        app_module,
        "check_article_4",
        lambda postcode: {
            "is_article_4": False,
            "known": True,
            "council": "Manchester City Council",
            "note": "",
        },
        raising=False,
    )
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_v1_licensing_check_ok(client):
    res = client.post(
        "/v1/licensing/check",
        json={
            "postcode": "M14 6LT",
            "occupants": 5,
            "households": 2,
            "intended_use": "hmo",
            "conversion_from_c3": True,
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["api_version"] == "v1"
    assert body["feature_flag"] == "licensing_checker_v1"
    assert body["disclaimer"]["version"] == DISCLAIMER_VERSION
    assert "deal_impact" in body
    assert body["deal_impact"]["level"] in {"deal_killer", "compliance_cost", "soft_warning", "info"}
    for flag in body["flags"]:
        assert flag["severity"] in {"deal_killer", "compliance_cost", "soft_warning", "info"}
        assert flag["severity_class"] in {"deal_killer", "compliance_cost", "soft_warning", "info"}
        assert isinstance(flag["analyse_hooks"], list)
        for h in flag["analyse_hooks"]:
            assert "id" in h and "kind" in h and "deal_impact" in h
    impact = body["deal_impact"]
    assert impact["verdict"] == impact["level"]
    assert "killers" in impact
    assert "add_capex_lines" in impact["analyse_hooks"]
    assert "add_risk_notes" in impact["analyse_hooks"]


def test_v1_licensing_check_requires_json(client):
    res = client.post("/v1/licensing/check", data="nope", content_type="text/plain")
    assert res.status_code == 400
    body = res.get_json()
    assert body["ok"] is False
    assert body["disclaimer"]["version"] == DISCLAIMER_VERSION


def test_v1_licensing_check_invalid_postcode(client):
    res = client.post("/v1/licensing/check", json={"postcode": "not a postcode"})
    assert res.status_code == 400
    body = res.get_json()
    assert body["error"]["code"] == "invalid_postcode"
    assert body["disclaimer"]["version"] == DISCLAIMER_VERSION


def test_v1_licensing_schemes_inventory(client):
    res = client.get("/v1/licensing/schemes")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["meta"]["la_count"] == 25
    assert body["disclaimer"]["version"] == DISCLAIMER_VERSION


def test_v1_licensing_feature_flag_off(monkeypatch):
    monkeypatch.setenv("LICENSING_CHECKER_V1", "false")
    import app as app_module

    app_module.app.config["TESTING"] = True
    client = app_module.app.test_client()
    res = client.post("/v1/licensing/check", json={"postcode": "M14 6LT"})
    assert res.status_code == 404
    body = res.get_json()
    assert body["error"]["code"] == "feature_disabled"
    assert body["disclaimer"]["version"] == DISCLAIMER_VERSION

"""Flask route tests for POST /v1/licensing/check — offline."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.setdefault("FLASK_ENV", "testing")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from licensing.geo import GeoError  # noqa: E402

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
    import app as app_module

    monkeypatch.setattr(
        "licensing.geo._default_fetch",
        lambda url: M14,
    )
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
        json={"postcode": "M14 6LT", "occupants": 5, "households": 2, "intended_use": "hmo"},
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["api_version"] == "v1"
    assert "freshness" in body
    assert "overall_confidence" in body["freshness"]
    assert isinstance(body["flags"], list)
    assert body["flags"]
    for flag in body["flags"]:
        assert "severity" in flag
        assert "confidence" in flag
        assert "sources" in flag
        assert "analyse_hooks" in flag
        assert "freshness" in flag


def test_v1_licensing_check_requires_json(client):
    res = client.post("/v1/licensing/check", data="nope", content_type="text/plain")
    assert res.status_code == 400
    assert res.get_json()["ok"] is False


def test_v1_licensing_check_invalid_postcode(client, monkeypatch):
    def boom(url):
        raise GeoError("bad", code="invalid_postcode")

    monkeypatch.setattr("licensing.geo._default_fetch", boom)
    res = client.post("/v1/licensing/check", json={"postcode": "not a postcode"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "invalid_postcode"


def test_v1_licensing_schemes_inventory(client):
    res = client.get("/v1/licensing/schemes")
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["meta"]["la_count"] == 25

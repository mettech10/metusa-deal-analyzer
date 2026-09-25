"""Applicability persistence, statutory GAS reason, no N/A reminders."""

import os
import sys
from pathlib import Path

os.environ.setdefault("FLASK_ENV", "testing")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from flask import Flask

from compliance.applicability import validate_applicability
from compliance.blueprint import bp
from compliance.store import create_obligation, reset_memory_store, update_obligation


@pytest.fixture(autouse=True)
def _memory():
    reset_memory_store()
    yield
    reset_memory_store()


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(bp)
    return app.test_client()


def test_gas_na_requires_reason():
    with pytest.raises(ValueError, match="reason"):
        validate_applicability("GAS", "not_applicable", "")
    app, reason = validate_applicability("GAS", "not_applicable", "no gas supply")
    assert app == "not_applicable"
    assert "gas" in reason.lower()


def test_eicr_cannot_be_na():
    with pytest.raises(ValueError, match="cannot be marked not applicable"):
        validate_applicability("EICR", "not_applicable", "n/a")


def test_applicable_alias_is_required():
    app, _ = validate_applicability("DEP", "applicable", "")
    assert app == "required"


def test_create_na_gas_persists_and_skips_reminders():
    row = create_obligation(
        "user-1",
        property_id="11111111-1111-4111-8111-111111111111",
        code="GAS",
        issued_on="2026-09-01",
        applicability="not_applicable",
        applicability_reason="no gas supply",
    )
    assert row["applicability"] == "not_applicable"
    assert row["status"] == "not_applicable"
    assert row["applicabilityReason"] == "no gas supply"
    assert row["reminders"] == []


def test_patch_na_via_api(client):
    created = create_obligation(
        "user-1",
        property_id="11111111-1111-4111-8111-111111111111",
        code="DEP",
        issued_on="2026-09-01",
    )
    assert created["reminders"] == []  # DEP has no auto expiry
    res = client.patch(
        f"/v1/compliance/obligations/{created['id']}",
        headers={"X-User-Id": "user-1"},
        json={"applicability": "not_applicable"},
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    body = res.get_json()["obligation"]
    assert body["applicability"] == "not_applicable"
    assert body["status"] == "not_applicable"


def test_patch_gas_na_without_reason_is_400(client):
    created = create_obligation(
        "user-1",
        property_id="11111111-1111-4111-8111-111111111111",
        code="GAS",
        issued_on="2026-09-01",
    )
    res = client.patch(
        f"/v1/compliance/obligations/{created['id']}",
        headers={"X-User-Id": "user-1"},
        json={"applicability": "not_applicable"},
    )
    assert res.status_code == 400
    assert "reason" in res.get_json()["message"].lower()


def test_update_to_na_clears_pending_reminders():
    row = create_obligation(
        "user-1",
        property_id="11111111-1111-4111-8111-111111111111",
        code="GAS",
        issued_on="2026-09-01",
        expires_on="2027-09-01",
    )
    assert any(r["status"] == "pending" for r in row["reminders"])
    updated = update_obligation(
        "user-1",
        row["id"],
        {"applicability": "not_applicable", "applicabilityReason": "no gas supply"},
    )
    assert updated["status"] == "not_applicable"
    assert updated["reminders"] == []

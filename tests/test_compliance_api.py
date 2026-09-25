"""HTTP tests for /v1/compliance/* (Flask test client, in-memory store)."""

import base64
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("FLASK_ENV", "testing")
os.environ["COMPLIANCE_FORCE_MEMORY_STORE"] = "1"
os.environ["COMPLIANCE_CRON_SECRET"] = "test-cron-secret"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask import Flask  # noqa: E402

from compliance.blueprint import register_compliance  # noqa: E402
from compliance.store import reset_memory_store  # noqa: E402
from compliance import store  # noqa: E402
from compliance.storage import reset_memory_blobs  # noqa: E402

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"
PROPERTY_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture
def client():
    reset_memory_store()
    reset_memory_blobs()
    os.environ.pop("BREVO_API_KEY", None)
    app = Flask(__name__)
    app.config["TESTING"] = True
    register_compliance(app)
    return app.test_client()


def auth(user=USER_A, **extra):
    headers = {"X-User-Id": user, "Content-Type": "application/json"}
    headers.update(extra)
    return headers


def test_health_and_catalogue_are_public(client):
    health = client.get("/v1/compliance/health")
    assert health.status_code == 200
    body = health.get_json()
    assert body["success"] is True
    assert "GAS" in body["catalogueCodes"]

    cat = client.get("/v1/compliance/catalogue")
    assert cat.status_code == 200
    payload = cat.get_json()
    codes = {item["code"] for item in payload["items"]}
    assert codes == {"GAS", "EICR", "EPC", "DEP", "HTR", "LIC_HMO", "LIC_SEL"}
    assert payload["catalogue"] == payload["items"]


def test_protected_routes_require_auth(client):
    assert client.get("/v1/compliance/obligations").status_code == 401
    assert client.get("/v1/compliance/dashboard").status_code == 401
    assert client.post("/v1/compliance/obligations", json={
        "propertyId": PROPERTY_ID, "code": "GAS",
    }).status_code == 401


def test_create_gas_derives_expiry_and_reminders(client):
    resp = client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID,
        "code": "gas",
        "issuedOn": "2026-01-01",
        "notes": "Boiler service",
    })
    assert resp.status_code == 201, resp.get_json()
    obl = resp.get_json()["obligation"]
    assert obl["code"] == "GAS"
    assert obl["propertyId"] == PROPERTY_ID
    assert obl["expiresOn"] == "2027-01-01"
    assert obl["status"] in ("valid", "due_soon", "overdue")
    offsets = [r["offsetDays"] for r in obl["reminders"]]
    assert offsets == [-90, -60, -30, -14, -7, 0, 1]


def test_status_filter_and_property_link(client):
    client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID,
        "code": "EPC",
        "issuedOn": "2015-01-01",
        "expiresOn": "2025-01-01",
    })
    client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID,
        "code": "DEP",
        "issuedOn": "2026-04-01",
    })

    overdue = client.get(
        "/v1/compliance/obligations?status=overdue&asOf=2026-09-14",
        headers=auth(),
    )
    assert overdue.status_code == 200
    codes = {o["code"] for o in overdue.get_json()["obligations"]}
    assert codes == {"EPC"}

    by_prop = client.get(
        f"/v1/compliance/properties/{PROPERTY_ID}/obligations",
        headers=auth(),
    )
    assert by_prop.get_json()["count"] == 2


def test_cannot_read_another_users_obligation(client):
    created = client.post("/v1/compliance/obligations", headers=auth(USER_A), json={
        "propertyId": PROPERTY_ID, "code": "HTR", "issuedOn": "2026-01-01",
    }).get_json()["obligation"]
    oid = created["id"]

    other = client.get(f"/v1/compliance/obligations/{oid}", headers=auth(USER_B))
    assert other.status_code == 404

    own = client.get(f"/v1/compliance/obligations/{oid}", headers=auth(USER_A))
    assert own.status_code == 200
    assert own.get_json()["obligation"]["status"] == "valid"


def test_unknown_code_rejected(client):
    resp = client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID, "code": "MTD",
    })
    assert resp.status_code == 400
    assert "Unknown catalogue code" in resp.get_json()["message"]


def test_missing_property_id_rejected(client):
    resp = client.post("/v1/compliance/obligations", headers=auth(), json={
        "code": "GAS",
    })
    assert resp.status_code == 400


def test_invalid_property_id_rejected(client):
    resp = client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": "not-a-uuid", "code": "GAS",
    })
    assert resp.status_code == 400
    assert "UUID" in resp.get_json()["message"]


def test_patch_expiry_reschedules_pending_reminders(client):
    created = client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID,
        "code": "LIC_HMO",
        "issuedOn": "2024-01-01",
        "expiresOn": "2029-01-01",
    }).get_json()["obligation"]
    oid = created["id"]

    patched = client.patch(
        f"/v1/compliance/obligations/{oid}?asOf=2026-01-01",
        headers=auth(),
        json={"expiresOn": "2026-06-01"},
    )
    assert patched.status_code == 200
    reminders = patched.get_json()["obligation"]["reminders"]
    scheduled = {r["offsetCode"]: r["scheduledFor"] for r in reminders}
    assert scheduled["t_minus_90"] == "2026-03-03"
    assert scheduled["overdue"] == "2026-06-02"


def test_evidence_upload_and_download(client):
    created = client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID, "code": "GAS", "issuedOn": "2026-01-01",
    }).get_json()["obligation"]
    oid = created["id"]

    payload = base64.b64encode(b"%PDF-1.4 fake-cert").decode()
    up = client.post(
        f"/v1/compliance/obligations/{oid}/evidence",
        headers=auth(),
        json={
            "filename": "gas-cp12.pdf",
            "contentType": "application/pdf",
            "dataBase64": payload,
        },
    )
    assert up.status_code == 201, up.get_json()
    evidence = up.get_json()["evidence"]
    assert evidence["filename"] == "gas-cp12.pdf"
    assert evidence["storageKey"].startswith(f"{USER_A}/")
    assert f"/{oid}/" in evidence["storageKey"]

    listed = client.get(
        f"/v1/compliance/obligations/{oid}/evidence", headers=auth(),
    )
    assert listed.get_json()["evidence"][0]["id"] == evidence["id"]

    downloaded = client.get(
        f"/v1/compliance/obligations/{oid}/evidence/{evidence['id']}/download",
        headers=auth(),
    )
    assert downloaded.status_code == 200
    assert downloaded.data == b"%PDF-1.4 fake-cert"


def test_rejected_evidence_type(client):
    created = client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID, "code": "EICR", "issuedOn": "2026-01-01",
    }).get_json()["obligation"]
    resp = client.post(
        f"/v1/compliance/obligations/{created['id']}/evidence",
        headers=auth(),
        json={
            "filename": "notes.exe",
            "contentType": "application/x-msdownload",
            "dataBase64": base64.b64encode(b"MZ").decode(),
        },
    )
    assert resp.status_code == 400


def test_dashboard_counts(client):
    client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID,
        "code": "EPC",
        "expiresOn": "2024-01-01",
    })
    client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID,
        "code": "GAS",
        "expiresOn": "2026-10-01",
    })
    dash = client.get(
        "/v1/compliance/dashboard?asOf=2026-09-14", headers=auth(),
    )
    counts = dash.get_json()["counts"]
    assert counts["overdue"] == 1
    assert counts["due_soon"] == 1


def test_reminder_dispatch_requires_cron_secret(client):
    assert client.post("/v1/compliance/reminders/dispatch").status_code == 401
    bad = client.post(
        "/v1/compliance/reminders/dispatch",
        headers={"X-Cron-Secret": "nope"},
    )
    assert bad.status_code == 401


def test_reminder_dispatch_skips_email_without_brevo_and_queues_weekly(client):
    client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID,
        "code": "GAS",
        "expiresOn": "2026-09-01",
    })
    resp = client.post(
        "/v1/compliance/reminders/dispatch?asOf=2026-09-14",
        headers={"X-Cron-Secret": "test-cron-secret"},
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["due"] >= 1
    assert body["dispatched"][0]["skipped"] is True
    assert body["dispatched"][0]["delivered"] is False
    assert body["dispatched"][0]["status"] == "skipped"
    assert body["email"]["configured"] is False
    assert "BREVO_API_KEY" in body["note"]
    assert body["queuedWeekly"]
    assert body["queuedWeekly"][0]["offsetCode"] == "overdue_weekly"
    assert body["queuedWeekly"][0]["scheduledFor"] == "2026-09-16"

    skipped = client.get(
        "/v1/compliance/reminders?status=skipped", headers=auth(),
    )
    assert skipped.get_json()["count"] >= 1
    weekly = client.get(
        "/v1/compliance/reminders?status=pending", headers=auth(),
    )
    codes = {r["offsetCode"] for r in weekly.get_json()["reminders"]}
    assert "overdue_weekly" in codes

    # Re-run the same day does not duplicate the weekly stub
    again = client.post(
        "/v1/compliance/reminders/dispatch?asOf=2026-09-14",
        headers={"X-Cron-Secret": "test-cron-secret"},
    )
    assert again.get_json()["queuedWeekly"] == []


def test_delete_obligation(client):
    created = client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID, "code": "LIC_SEL", "issuedOn": "2026-01-01",
    }).get_json()["obligation"]
    oid = created["id"]
    deleted = client.delete(f"/v1/compliance/obligations/{oid}", headers=auth())
    assert deleted.status_code == 200
    missing = client.get(f"/v1/compliance/obligations/{oid}", headers=auth())
    assert missing.status_code == 404


def test_main_flask_app_exposes_compliance_routes():
    """The production app.py blueprint registration must stay wired."""
    from app import app as real_app
    rc = real_app.test_client()
    health = rc.get("/v1/compliance/health")
    assert health.status_code == 200
    assert health.get_json()["service"] == "compliance"
    cat = rc.get("/v1/compliance/catalogue")
    assert {i["code"] for i in cat.get_json()["items"]} >= {"GAS", "LIC_HMO"}
    unauth = rc.get("/v1/compliance/dashboard")
    assert unauth.status_code == 401


def test_in_app_channel_is_not_emailed_by_dispatch(client):
    created = client.post("/v1/compliance/obligations", headers=auth(), json={
        "propertyId": PROPERTY_ID, "code": "GAS", "issuedOn": "2026-01-01",
    }).get_json()["obligation"]
    from compliance.store import add_reminder_stub
    add_reminder_stub(created, {
        "offsetCode": "overdue",
        "offsetDays": 1,
        "scheduledFor": "2026-09-01",
        "status": "pending",
        "channel": "in_app",
    })
    listed = client.get(
        "/v1/compliance/reminders?channel=in_app", headers=auth(),
    )
    assert listed.get_json()["count"] == 1
    assert listed.get_json()["reminders"][0]["channel"] == "in_app"

    client.post(
        "/v1/compliance/reminders/dispatch?asOf=2026-09-14",
        headers={"X-Cron-Secret": "test-cron-secret"},
    )
    still = client.get(
        "/v1/compliance/reminders?channel=in_app&status=pending", headers=auth(),
    )
    assert still.get_json()["count"] == 1


def test_health_documents_evidence_prefix_and_channels(client):
    health = client.get("/v1/compliance/health").get_json()
    assert health["evidence"]["bucket"] == "compliance-evidence"
    assert "{userId}" in health["evidence"]["keyPrefix"]
    assert "in_app" in health["channels"]
    cat = client.get("/v1/compliance/catalogue").get_json()
    assert cat["overdueWeeklyDays"] == 7
    assert "in_app" in cat["channels"]
    assert cat["catalogue"] == cat["items"]


def test_health_reports_memory_store_ready_in_tests(client):
    health = client.get("/v1/compliance/health").get_json()
    assert health["success"] is True
    assert health["store"] == "memory"
    assert health["storeProbe"]["ready"] is True
    assert health["status"] == "ok"
    assert health["auth"]["gotrue"] == "/auth/v1/user"
    assert health["auth"]["apikeySource"] in ("service", "anon", "none")
    assert health["auth"]["ready"] is False or health["auth"]["ready"] is True
    assert "supabaseHost" in health["auth"]
    assert "service-role-key" not in str(health["auth"])


def test_dashboard_store_error_is_json_503(client, monkeypatch):
    def boom(*args, **kwargs):
        raise store.ComplianceStoreError(
            "Apply supabase/migrations/20260914_compliance_cockpit.sql",
            status_code=503,
        )

    monkeypatch.setattr(store, "list_obligations", boom)
    resp = client.get("/v1/compliance/dashboard", headers=auth())
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["error"] == "compliance_store_unavailable"
    assert "20260914_compliance_cockpit" in body["message"]


def test_property_obligations_store_error_is_json_503(client, monkeypatch):
    def boom(*args, **kwargs):
        raise store.ComplianceStoreError(
            "Apply supabase/migrations/20260914_compliance_cockpit.sql",
            status_code=503,
        )

    monkeypatch.setattr(store, "list_obligations", boom)
    resp = client.get(
        f"/v1/compliance/properties/{PROPERTY_ID}/obligations",
        headers=auth(),
    )
    assert resp.status_code == 503
    assert "20260914" in resp.get_json()["message"]


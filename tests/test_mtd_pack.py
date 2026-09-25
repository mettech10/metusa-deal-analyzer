"""MTD Pack v1 API tests — org-scoped records, CSV, packs, share links.

Uses a dedicated Flask app (does not import the deal-analyser app.py).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from flask import Flask

from mtd.blueprint import configure_mtd, mtd_bp
from mtd.categories import CATEGORIES, RESIDENTIAL_FINANCE_CODES, is_residential_finance
from mtd.pdf import build_simple_pdf
from mtd.quarters import resolve_quarter, tax_year_for_date
from mtd.service import MtdService
from mtd.store import InMemoryMtdStore

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = (ROOT / "tests" / "fixtures" / "mtd_sample.csv").read_text(encoding="utf-8")


def make_app(service: MtdService | None = None) -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["MTD_SERVICE"] = service or MtdService(InMemoryMtdStore())
    configure_mtd(app)
    app.register_blueprint(mtd_bp)
    return app


@pytest.fixture
def service() -> MtdService:
    return MtdService(InMemoryMtdStore())


@pytest.fixture
def client(service: MtdService):
    return make_app(service).test_client()


def auth(user: str, org: str | None = None) -> dict[str, str]:
    headers = {
        "X-Mtd-User-Id": user,
        "X-Mtd-User-Email": f"{user}@example.com",
        "Content-Type": "application/json",
    }
    if org:
        headers["X-Mtd-Org-Id"] = org
    return headers


def create_business(client, user="alice", **body):
    payload = {"name": "Alice UK property", "taxYearStart": "2026-04-06", "basis": "standard"}
    payload.update(body)
    res = client.post("/v1/mtd/businesses", headers=auth(user), json=payload)
    assert res.status_code == 201, res.get_data(as_text=True)
    return res.get_json()


# ── catalogue / health ────────────────────────────────────────────────
def test_health_and_no_hmrc_submit(client):
    res = client.get("/v1/mtd/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["hmrcSubmit"] is False
    assert data["openBanking"] is False
    assert data["auth"]["gotrue"] == "/auth/v1/user"
    assert data["auth"]["apikeySource"] in ("service", "anon", "none")
    assert "supabaseHost" in data["auth"]
    assert "ready" in data["auth"]


def test_category_catalogue_sa105_and_residential_finance_separate(client):
    res = client.get("/v1/mtd/categories")
    assert res.status_code == 200
    data = res.get_json()
    codes = {c["code"]: c for c in data["categories"]}
    assert "uk_rent_income" in codes
    assert codes["uk_rent_income"]["sa105Box"] == "20"
    assert codes["non_residential_finance_costs"]["sa105Box"] == "26"
    assert codes["non_residential_finance_costs"]["isResidentialFinance"] is False
    assert codes["residential_finance_costs"]["sa105Box"] == "44"
    assert codes["residential_finance_costs"]["isResidentialFinance"] is True
    assert codes["residential_finance_costs"]["kind"] == "residential_finance"
    assert codes["residential_finance_costs_bf"]["isResidentialFinance"] is True
    # Must not share HMRC field with commercial finance
    assert (
        codes["residential_finance_costs"]["hmrcField"]
        != codes["non_residential_finance_costs"]["hmrcField"]
    )
    assert RESIDENTIAL_FINANCE_CODES == {
        "residential_finance_costs",
        "residential_finance_costs_bf",
    }
    assert is_residential_finance("mortgage interest")


def test_standard_quarters():
    start, end = resolve_quarter("2026-27", 1, "standard")
    assert str(start) == "2026-04-06"
    assert str(end) == "2026-07-05"
    assert tax_year_for_date(__import__("datetime").date(2026, 4, 5)) == "2025-26"


# ── auth / org scope ──────────────────────────────────────────────────
def test_unauthorised_without_user(client):
    res = client.get("/v1/mtd/businesses")
    assert res.status_code == 401
    assert res.get_json()["error"] == "Unauthorised"


def test_bearer_without_apikey_is_503_not_401(monkeypatch):
    """Production (not TESTING) + Bearer + missing apikey → 503, not 401."""
    app = Flask(__name__)
    app.config["TESTING"] = False
    app.config["MTD_SERVICE"] = MtdService(InMemoryMtdStore())
    configure_mtd(app)
    app.register_blueprint(mtd_bp)
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://lftlugydvvcjtujalzwh.supabase.co")
    for name in (
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    res = app.test_client().get(
        "/v1/mtd/businesses",
        headers={"Authorization": "Bearer user-access-jwt"},
    )
    assert res.status_code == 503
    body = res.get_json()
    assert body["code"] == "auth_not_configured"
    assert "missing anon key" in body["error"]


def test_org_auto_provision_and_isolation(client):
    a = create_business(client, "alice")
    b = create_business(client, "bob", name="Bob property")
    alice_list = client.get("/v1/mtd/businesses", headers=auth("alice")).get_json()["businesses"]
    bob_list = client.get("/v1/mtd/businesses", headers=auth("bob")).get_json()["businesses"]
    assert {row["id"] for row in alice_list} == {a["id"]}
    assert {row["id"] for row in bob_list} == {b["id"]}
    peek = client.get(f"/v1/mtd/businesses/{a['id']}", headers=auth("bob"))
    assert peek.status_code == 404


def test_current_org_members(client):
    create_business(client, "alice")
    org = client.get("/v1/mtd/orgs/current", headers=auth("alice")).get_json()
    assert org["role"] == "owner"
    assert any(m["userId"] == "alice" for m in org["members"])


# ── property + ledger ─────────────────────────────────────────────────
def test_property_link_and_ledger_pence(client):
    biz = create_business(client)
    portfolio_id = "11111111-1111-1111-1111-111111111111"
    prop_res = client.post(
        f"/v1/mtd/businesses/{biz['id']}/properties",
        headers=auth("alice"),
        json={
            "label": "12 High Street",
            "address": "12 High Street, Leeds",
            "postcode": "LS1 1AA",
            "propertyId": portfolio_id,
            "occupancyType": "residential",
        },
    )
    assert prop_res.status_code == 201
    prop = prop_res.get_json()
    assert prop["propertyId"] == portfolio_id
    entry_res = client.post(
        f"/v1/mtd/businesses/{biz['id']}/ledger",
        headers=auth("alice"),
        json={
            "date": "2026-05-01",
            "propertyId": prop["id"],
            "categoryCode": "uk_rent_income",
            "amountPence": 95000,
            "description": "May rent",
            "source": "manual",
        },
    )
    assert entry_res.status_code == 201, entry_res.get_data(as_text=True)
    entry = entry_res.get_json()
    assert entry["amountPence"] == 95000
    assert entry["source"] == "manual"
    assert entry["propertyId"] == prop["id"]
    assert isinstance(entry["amountPence"], int)

    bad = client.post(
        f"/v1/mtd/businesses/{biz['id']}/ledger",
        headers=auth("alice"),
        json={
            "date": "2026-05-01",
            "categoryCode": "uk_rent_income",
            "amountPence": 12.5,
        },
    )
    assert bad.status_code == 400


def test_unknown_category_rejected(client):
    biz = create_business(client)
    res = client.post(
        f"/v1/mtd/businesses/{biz['id']}/ledger",
        headers=auth("alice"),
        json={"date": "2026-05-01", "categoryCode": "snacks", "amountPence": 100},
    )
    assert res.status_code == 400


# ── CSV import ────────────────────────────────────────────────────────
def test_csv_preview_and_idempotent_commit(client):
    biz = create_business(client)
    preview = client.post(
        f"/v1/mtd/businesses/{biz['id']}/imports/preview",
        headers=auth("alice"),
        json={"csv": SAMPLE_CSV, "filename": "mtd_sample.csv"},
    )
    assert preview.status_code == 200, preview.get_data(as_text=True)
    pdata = preview.get_json()
    assert pdata["readyToCommit"] is True
    assert pdata["validCount"] == 4
    codes = {row["mapped"]["categoryCode"] for row in pdata["rows"]}
    assert "residential_finance_costs" in codes
    assert "repairs_and_maintenance" in codes
    assert "premises_running_costs" in codes
    assert all(isinstance(row["mapped"]["amountPence"], int) for row in pdata["rows"])

    first = client.post(
        f"/v1/mtd/businesses/{biz['id']}/imports/commit",
        headers=auth("alice"),
        json={"csv": SAMPLE_CSV, "filename": "mtd_sample.csv"},
    )
    assert first.status_code == 201
    fdata = first.get_json()
    assert fdata["idempotent"] is False
    assert fdata["createdCount"] == 4

    second = client.post(
        f"/v1/mtd/businesses/{biz['id']}/imports/commit",
        headers=auth("alice"),
        json={"csv": SAMPLE_CSV, "filename": "mtd_sample.csv"},
    )
    assert second.status_code == 200
    sdata = second.get_json()
    assert sdata["idempotent"] is True
    assert sdata["createdCount"] == 0

    ledger = client.get(
        f"/v1/mtd/businesses/{biz['id']}/ledger", headers=auth("alice")
    ).get_json()["entries"]
    assert len(ledger) == 4
    assert all(e["source"] == "csv" for e in ledger)
    rf = [e for e in ledger if e["categoryCode"] == "residential_finance_costs"]
    assert rf and rf[0]["amountPence"] == 32000


def test_csv_preview_rejects_bad_category(client):
    biz = create_business(client)
    csv_text = "date,category,amount_pence\n2026-04-10,not-a-box,100\n"
    preview = client.post(
        f"/v1/mtd/businesses/{biz['id']}/imports/preview",
        headers=auth("alice"),
        json={"csv": csv_text},
    ).get_json()
    assert preview["readyToCommit"] is False
    assert preview["invalidCount"] == 1
    commit = client.post(
        f"/v1/mtd/businesses/{biz['id']}/imports/commit",
        headers=auth("alice"),
        json={"csv": csv_text},
    )
    assert commit.status_code == 400


# ── quarter packs ─────────────────────────────────────────────────────
def _seeded_business(client):
    biz = create_business(client)
    client.post(
        f"/v1/mtd/businesses/{biz['id']}/imports/commit",
        headers=auth("alice"),
        json={"csv": SAMPLE_CSV},
    )
    return biz


def test_quarter_pack_immutable_snapshot_and_exports(client):
    biz = _seeded_business(client)
    created = client.post(
        f"/v1/mtd/businesses/{biz['id']}/packs",
        headers=auth("alice"),
        json={"taxYear": "2026-27", "quarter": 1, "basis": "standard"},
    )
    assert created.status_code == 201, created.get_data(as_text=True)
    pack = created.get_json()
    assert pack["immutable"] is True
    assert pack["hmrcSubmit"] is False
    snap = pack["snapshot"]
    assert snap["periodTotalsPence"]["uk_rent_income"] == 125000
    assert snap["periodTotalsPence"]["residential_finance_costs"] == 32000
    assert snap["residentialFinance"]["excludedFromProfitDeduction"] is True
    # Residential finance is NOT deducted in the expense net
    assert snap["periodNetPence"] == 125000 - (4500 + 12000)
    assert snap["residentialFinance"]["period"]["periodPence"] == 32000

    again = client.post(
        f"/v1/mtd/businesses/{biz['id']}/packs",
        headers=auth("alice"),
        json={"taxYear": "2026-27", "quarter": 1, "basis": "standard"},
    )
    assert again.status_code == 409

    # Later ledger edits must not mutate the snapshot
    client.post(
        f"/v1/mtd/businesses/{biz['id']}/ledger",
        headers=auth("alice"),
        json={
            "date": "2026-05-20",
            "categoryCode": "uk_rent_income",
            "amountPence": 1,
            "source": "manual",
        },
    )
    fetched = client.get(f"/v1/mtd/packs/{pack['id']}", headers=auth("alice")).get_json()
    assert fetched["snapshot"]["periodTotalsPence"]["uk_rent_income"] == 125000

    js = client.get(f"/v1/mtd/packs/{pack['id']}/export.json", headers=auth("alice"))
    assert js.status_code == 200
    assert js.mimetype == "application/json"
    exported = json.loads(js.get_data(as_text=True))
    assert exported["hmrcSubmit"] is False

    csv_res = client.get(f"/v1/mtd/packs/{pack['id']}/export.csv", headers=auth("alice"))
    assert csv_res.status_code == 200
    csv_body = csv_res.get_data(as_text=True)
    assert "residential_finance_costs" in csv_body
    assert "true" in csv_body.lower() or "residential" in csv_body.lower()

    pdf_res = client.get(f"/v1/mtd/packs/{pack['id']}/export.pdf", headers=auth("alice"))
    assert pdf_res.status_code == 200
    pdf_bytes = pdf_res.get_data()
    assert pdf_bytes.startswith(b"%PDF")
    assert b"%%EOF" in pdf_bytes


def test_minimal_pdf_writer():
    blob = build_simple_pdf("Test", ["hello", "world"])
    assert blob.startswith(b"%PDF-1.4")
    assert b"Helvetica" in blob


# ── share links ───────────────────────────────────────────────────────
def test_share_link_readonly_and_expiry(client, service: MtdService):
    biz = _seeded_business(client)
    pack = client.post(
        f"/v1/mtd/businesses/{biz['id']}/packs",
        headers=auth("alice"),
        json={"taxYear": "2026-27", "quarter": 1},
    ).get_json()
    share = client.post(
        f"/v1/mtd/packs/{pack['id']}/share",
        headers=auth("alice"),
        json={"expiresInDays": 7},
    )
    assert share.status_code == 201
    token = share.get_json()["token"]
    assert token
    public = client.get(f"/v1/mtd/share/{token}")
    assert public.status_code == 200
    body = public.get_json()
    assert body["readonly"] is True
    assert body["pack"]["snapshot"]["periodTotalsPence"]["uk_rent_income"] == 125000

    # Bob cannot use Alice's pack id, but can read the share token
    assert client.get(f"/v1/mtd/packs/{pack['id']}", headers=auth("bob")).status_code == 404
    assert client.get(f"/v1/mtd/share/{token}").status_code == 200

    # Expiry
    stored = service.store.get_share(share.get_json()["id"])
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    expired = client.get(f"/v1/mtd/share/{token}")
    assert expired.status_code == 410

    # Revoke a fresh link
    share2 = client.post(
        f"/v1/mtd/packs/{pack['id']}/share",
        headers=auth("alice"),
        json={"expiresInDays": 3},
    ).get_json()
    revoke = client.delete(f"/v1/mtd/share-links/{share2['id']}", headers=auth("alice"))
    assert revoke.status_code == 200
    gone = client.get(f"/v1/mtd/share/{share2['token']}")
    assert gone.status_code == 404


# ── open banking stub ─────────────────────────────────────────────────
def test_open_banking_stub(client):
    biz = create_business(client)
    status = client.get("/v1/mtd/open-banking/status", headers=auth("alice"))
    assert status.status_code == 200
    assert status.get_json()["available"] is False
    sync = client.post(
        "/v1/mtd/open-banking/sync",
        headers=auth("alice"),
        json={"businessId": biz["id"]},
    )
    assert sync.status_code == 501
    assert "Open Banking" in sync.get_json()["error"]

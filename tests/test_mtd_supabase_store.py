"""MTD persistence: backend selection, the production memory-store guard, and
an end-to-end run of the Supabase store against a real PostgREST.

The PostgREST tests are skipped unless ``MTD_PGREST_URL`` and
``MTD_PGREST_KEY`` point at a database with
``supabase/migrations/20260914_mtd_pack_v1.sql`` applied and the two
``auth.users`` rows below inserted.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from flask import Flask

from mtd.blueprint import configure_mtd, mtd_bp
from mtd.service import MtdService
from mtd.store import InMemoryMtdStore, MtdStoreError
from mtd.supabase_store import SupabaseMtdStore, _dt

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_CSV = (ROOT / "tests" / "fixtures" / "mtd_sample.csv").read_text(encoding="utf-8")

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"


def _app(service: MtdService | None, *, testing: bool = True) -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = testing
    if service is not None:
        app.config["MTD_SERVICE"] = service
    configure_mtd(app)
    app.register_blueprint(mtd_bp)
    return app


def _auth(user: str) -> dict[str, str]:
    return {"X-Mtd-User-Id": user, "Content-Type": "application/json"}


# ── backend selection + guard (no network) ────────────────────────────
def test_configure_uses_supabase_store_when_service_key_set(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.delenv("MTD_FORCE_MEMORY_STORE", raising=False)
    app = _app(None)
    store = app.config["MTD_SERVICE"].store
    assert isinstance(store, SupabaseMtdStore)
    assert store.rest_url == "https://example.supabase.co/rest/v1"


def test_configure_never_uses_anon_key_for_storage(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    for name in ("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert isinstance(_app(None).config["MTD_SERVICE"].store, InMemoryMtdStore)


def test_memory_store_refused_outside_dev(monkeypatch):
    """Production must never accept records it will lose on restart."""
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.delenv("MTD_ALLOW_MEMORY_STORE", raising=False)
    client = _app(MtdService(InMemoryMtdStore()), testing=False).test_client()

    res = client.get("/v1/mtd/businesses", headers={"Authorization": "Bearer x"})
    assert res.status_code == 503
    assert res.get_json()["code"] == "storage_unavailable"

    health = client.get("/v1/mtd/health").get_json()
    assert health["store"] == "memory"
    assert health["persistent"] is False
    assert health["writesAccepted"] is False
    assert health["status"] == "degraded"


def test_memory_store_allowed_in_development(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "development")
    client = _app(MtdService(InMemoryMtdStore()), testing=False).test_client()
    res = client.get("/v1/mtd/businesses")
    assert res.status_code == 401  # reaches auth instead of the storage guard
    assert client.get("/v1/mtd/health").get_json()["writesAccepted"] is True


class _BrokenStore(InMemoryMtdStore):
    backend = "supabase"

    def default_org_id(self, user_id):
        raise MtdStoreError("MTD storage unreachable (mtd_org_members)")


def test_store_outage_is_503_not_500():
    client = _app(MtdService(_BrokenStore())).test_client()
    res = client.get("/v1/mtd/businesses", headers=_auth(ALICE))
    assert res.status_code == 503
    assert res.get_json()["code"] == "storage_unavailable"


@pytest.mark.parametrize(
    "raw",
    [
        "2026-09-28T10:00:00.12345+00:00",
        "2026-09-28T10:00:00+00:00",
        "2026-09-28T10:00:00Z",
        "2026-09-28T10:00:00.123456789+00:00",
    ],
)
def test_postgres_timestamps_parse(raw):
    parsed = _dt(raw)
    assert parsed.tzinfo is not None
    assert (parsed.year, parsed.month, parsed.day, parsed.hour) == (2026, 9, 28, 10)


# ── real PostgREST (opt-in) ───────────────────────────────────────────
PGREST_URL = os.environ.get("MTD_PGREST_URL")
PGREST_KEY = os.environ.get("MTD_PGREST_KEY")
needs_pgrest = pytest.mark.skipif(
    not (PGREST_URL and PGREST_KEY), reason="MTD_PGREST_URL / MTD_PGREST_KEY not set"
)


def _store() -> SupabaseMtdStore:
    return SupabaseMtdStore(key=PGREST_KEY, rest_url=PGREST_URL)


@pytest.fixture
def pg_client():
    return _app(MtdService(_store())).test_client()


@needs_pgrest
def test_records_survive_a_server_restart(pg_client):
    name = f"Restart test {uuid.uuid4().hex[:8]}"
    created = pg_client.post(
        "/v1/mtd/businesses",
        headers=_auth(ALICE),
        json={"name": name, "taxYearStart": "2026-04-06", "basis": "standard"},
    )
    assert created.status_code == 201, created.get_data(as_text=True)
    biz_id = created.get_json()["id"]
    entry = pg_client.post(
        f"/v1/mtd/businesses/{biz_id}/ledger",
        headers=_auth(ALICE),
        json={"date": "2026-07-10", "categoryCode": "uk_rent_income", "amountPence": 95000},
    )
    assert entry.status_code == 201, entry.get_data(as_text=True)

    # A brand-new app + store = what Render does on deploy / spin-down.
    restarted = _app(MtdService(_store())).test_client()
    names = [b["name"] for b in restarted.get("/v1/mtd/businesses", headers=_auth(ALICE)).get_json()["businesses"]]
    assert name in names
    ledger = restarted.get(f"/v1/mtd/businesses/{biz_id}/ledger", headers=_auth(ALICE)).get_json()
    rows = ledger.get("entries", ledger.get("ledger", []))
    assert [r["amountPence"] for r in rows] == [95000]


@needs_pgrest
def test_full_quarter_flow_on_postgrest(pg_client):
    biz = pg_client.post(
        "/v1/mtd/businesses",
        headers=_auth(ALICE),
        json={"name": f"Flow {uuid.uuid4().hex[:8]}", "taxYearStart": "2026-04-06"},
    ).get_json()
    bid = biz["id"]

    prop = pg_client.post(
        f"/v1/mtd/businesses/{bid}/properties",
        headers=_auth(ALICE),
        json={"label": "Flat 1", "postcode": "BL4 8LQ"},
    )
    assert prop.status_code == 201, prop.get_data(as_text=True)

    first = pg_client.post(
        f"/v1/mtd/businesses/{bid}/imports/commit", headers=_auth(ALICE), json={"csv": SAMPLE_CSV}
    )
    assert first.status_code == 201, first.get_data(as_text=True)
    assert first.get_json()["createdCount"] == 4
    again = pg_client.post(
        f"/v1/mtd/businesses/{bid}/imports/commit", headers=_auth(ALICE), json={"csv": SAMPLE_CSV}
    )
    assert again.status_code == 200
    assert again.get_json()["idempotent"] is True

    pack = pg_client.post(
        f"/v1/mtd/businesses/{bid}/packs",
        headers=_auth(ALICE),
        json={"taxYear": "2026-27", "quarter": 1, "basis": "standard"},
    )
    assert pack.status_code == 201, pack.get_data(as_text=True)
    pack = pack.get_json()
    snap = pack["snapshot"]
    assert snap["periodTotalsPence"]["uk_rent_income"] == 125000
    assert snap["periodNetPence"] == 125000 - (4500 + 12000)

    dup = pg_client.post(
        f"/v1/mtd/businesses/{bid}/packs",
        headers=_auth(ALICE),
        json={"taxYear": "2026-27", "quarter": 1, "basis": "standard"},
    )
    assert dup.status_code == 409

    for fmt in ("json", "csv", "pdf"):
        assert pg_client.get(f"/v1/mtd/packs/{pack['id']}/export.{fmt}", headers=_auth(ALICE)).status_code == 200

    # Org isolation holds in the database store too.
    assert pg_client.get(f"/v1/mtd/packs/{pack['id']}", headers=_auth(BOB)).status_code == 404
    assert pg_client.get(f"/v1/mtd/businesses/{bid}", headers=_auth(BOB)).status_code == 404

    share = pg_client.post(
        f"/v1/mtd/packs/{pack['id']}/share", headers=_auth(ALICE), json={"expiresInDays": 7}
    ).get_json()
    assert pg_client.get(f"/v1/mtd/share/{share['token']}").status_code == 200

    store = _store()
    stored = store.get_share(share["id"])
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    store.save_share(stored)
    assert pg_client.get(f"/v1/mtd/share/{share['token']}").status_code == 410

    fresh = pg_client.post(
        f"/v1/mtd/packs/{pack['id']}/share", headers=_auth(ALICE), json={"expiresInDays": 3}
    ).get_json()
    assert pg_client.delete(f"/v1/mtd/share-links/{fresh['id']}", headers=_auth(ALICE)).status_code == 200
    assert pg_client.get(f"/v1/mtd/share/{fresh['token']}").status_code == 404

    # Packs are permanent records, so the business can be archived, not deleted.
    blocked = pg_client.delete(f"/v1/mtd/businesses/{bid}", headers=_auth(ALICE))
    assert blocked.status_code == 409
    assert "archive" in blocked.get_json()["error"].lower()


@needs_pgrest
def test_void_and_bad_ids_on_postgrest(pg_client):
    bid = pg_client.post(
        "/v1/mtd/businesses", headers=_auth(ALICE), json={"name": f"Void {uuid.uuid4().hex[:8]}"}
    ).get_json()["id"]
    entry = pg_client.post(
        f"/v1/mtd/businesses/{bid}/ledger",
        headers=_auth(ALICE),
        json={"date": "2026-08-01", "categoryCode": "repairs_and_maintenance", "amountPence": 1234},
    ).get_json()
    assert pg_client.delete(f"/v1/mtd/ledger/{entry['id']}", headers=_auth(ALICE)).status_code in (200, 204)
    ledger = pg_client.get(f"/v1/mtd/businesses/{bid}/ledger", headers=_auth(ALICE)).get_json()
    assert ledger.get("entries", ledger.get("ledger", [])) == []

    # Non-UUID path ids are "not found", not a 500 from Postgres.
    assert pg_client.get("/v1/mtd/businesses/not-a-uuid", headers=_auth(ALICE)).status_code == 404
    assert pg_client.get("/v1/mtd/packs/not-a-uuid", headers=_auth(ALICE)).status_code == 404

    # Ledger pointing at a property from another business is rejected.
    bad = pg_client.post(
        f"/v1/mtd/businesses/{bid}/ledger",
        headers=_auth(ALICE),
        json={
            "date": "2026-08-01",
            "categoryCode": "uk_rent_income",
            "amountPence": 1,
            "propertyId": str(uuid.uuid4()),
        },
    )
    assert bad.status_code == 400


@needs_pgrest
def test_ledger_reads_page_past_1000_rows():
    store = _store()
    service = MtdService(store)
    ctx = service.ensure_org(ALICE)
    biz = service.create_business(ctx, {"name": f"Bulk {uuid.uuid4().hex[:8]}"})
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "org_id": ctx.org_id,
            "business_id": biz["id"],
            "entry_date": "2026-06-01",
            "amount_pence": 100,
            "category_code": "uk_rent_income",
            "source": "manual",
            "fingerprint": f"bulk-{biz['id']}-{i}",
            "created_by": ALICE,
            "created_at": now,
            "updated_at": now,
        }
        for i in range(1005)
    ]
    resp = requests.post(
        f"{PGREST_URL}/mtd_ledger_entries",
        json=rows,
        headers={"apikey": PGREST_KEY, "Authorization": f"Bearer {PGREST_KEY}"},
        timeout=30,
    )
    assert resp.status_code in (200, 201), resp.text
    assert len(store.list_entries(ctx.org_id, biz["id"])) == 1005

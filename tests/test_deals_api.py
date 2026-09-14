"""
Screener handoff — POST /v1/deals

Offline tests: auth and persistence are stubbed. No HTTP to Supabase.

Curl (against a running Flask + real token):

    curl -sS -X POST http://localhost:5002/v1/deals \\
      -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \\
      -H "Content-Type: application/json" \\
      -H "Idempotency-Key: screener:rightmove:12345678" \\
      -d '{
        "source": "screener",
        "schemaVersion": 1,
        "strategyHint": "BTL",
        "listing": {
          "source": "rightmove",
          "sourceListingId": "12345678",
          "listingUrl": "https://www.rightmove.co.uk/properties/12345678",
          "address": "42 Oakfield Avenue, Manchester",
          "postcode": "M14 6LT",
          "priceGbp": 185000,
          "bedrooms": 3,
          "propertyType": "terraced",
          "rentPcmGbp": 950,
          "photos": ["https://cdn.example/1.jpg"]
        }
      }'
"""
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.setdefault("FLASK_ENV", "testing")
# Force the in-memory store even if a developer machine has Supabase env vars.
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_KEY", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
os.environ.pop("NEXT_PUBLIC_SUPABASE_URL", None)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deals_api import (  # noqa: E402
    DealValidationError,
    build_deep_link_path,
    map_strategy_hint,
    normalise_address,
    normalise_postcode,
    property_key,
    reset_memory_store,
    strip_photos,
    validate_screener_payload,
)

TEST_USER = {"id": "11111111-1111-1111-1111-111111111111", "email": "tester@metalyzi.co.uk"}

SCREENER_BODY = {
    "source": "screener",
    "schemaVersion": 1,
    "strategyHint": "BTL",
    "listing": {
        "source": "rightmove",
        "sourceListingId": "12345678",
        "listingUrl": "https://www.rightmove.co.uk/properties/12345678",
        "address": "42 Oakfield Avenue, Manchester",
        "postcode": "M14 6LT",
        "priceGbp": 185000,
        "bedrooms": 3,
        "propertyType": "terraced",
        "rentPcmGbp": 950,
        "photos": ["https://cdn.example/1.jpg"],
        "images": ["https://cdn.example/2.jpg"],
        "floorplans": ["https://cdn.example/fp.jpg"],
    },
}


@pytest.fixture
def store():
    return reset_memory_store()


@pytest.fixture
def client(monkeypatch, store):
    import deals_api
    import app as app_module

    monkeypatch.setattr(deals_api, "fetch_supabase_user", lambda token: TEST_USER if token == "test-token" else None)
    monkeypatch.setattr(deals_api, "get_store", lambda: store)
    app_module.app.config["TESTING"] = True
    app_module.limiter.enabled = False
    return app_module.app.test_client()


def _post(client, body=None, token="test-token", idem=None, headers=None):
    hdrs = {"Content-Type": "application/json"}
    if token is not None:
        hdrs["Authorization"] = f"Bearer {token}"
    if idem:
        hdrs["Idempotency-Key"] = idem
    if headers:
        hdrs.update(headers)
    return client.post("/v1/deals", json=body if body is not None else SCREENER_BODY, headers=hdrs)


# ── Unit: identity + mapping ──────────────────────────────────────────────

def test_normalise_postcode_canonical_form():
    assert normalise_postcode("m146lt") == "M14 6LT"
    assert normalise_postcode("M14 6LT") == "M14 6LT"
    assert normalise_postcode("not a postcode") == ""


def test_property_key_stable_and_shared_with_discovery_algorithm():
    addr = "42 Oakfield Avenue, Manchester"
    pc = "M14 6LT"
    key_a = property_key(addr, pc)
    key_b = property_key("42 Oakfield Avenue, Manchester M14 6LT", "m14 6lt")
    assert key_a == key_b
    assert len(key_a) == 64
    assert normalise_address("42 Oakfield Avenue, Manchester M14 6LT") == "42 OAKFIELD AVENUE MANCHESTER"


@pytest.mark.parametrize("raw,expected", [
    ("BTL", "btl"),
    ("btl", "btl"),
    ("Buy-to-let", "btl"),
    ("HMO", "hmo"),
    ("BRRRR", "brrrr"),
    ("BRR", "brrrr"),
    ("FLIP", "flip"),
    ("SA", "sa"),
    ("R2SA", "sa"),
    ("development", "development"),
    ("DEV", "development"),
])
def test_strategy_hint_maps_to_lowercase_enums(raw, expected):
    assert map_strategy_hint(raw) == expected


def test_strategy_hint_rejects_unknown():
    with pytest.raises(DealValidationError) as exc:
        map_strategy_hint("auction")
    assert "strategyHint" in exc.value.fields


def test_strip_photos_drops_image_keys():
    cleaned = strip_photos({
        "address": "x",
        "photos": ["a"],
        "images": ["b"],
        "floorplans": ["c"],
        "nested": {"thumbnailUrl": "d", "priceGbp": 1},
    })
    assert "photos" not in cleaned
    assert "images" not in cleaned
    assert "floorplans" not in cleaned
    assert "thumbnailUrl" not in cleaned["nested"]
    assert cleaned["nested"]["priceGbp"] == 1


def test_screener_requires_rent():
    body = {
        "source": "screener",
        "schemaVersion": 1,
        "strategyHint": "btl",
        "listing": {"address": "1 High St", "postcode": "M1 1AA", "priceGbp": 100000},
    }
    with pytest.raises(DealValidationError) as exc:
        validate_screener_payload(body)
    assert "rentPcmGbp" in exc.value.fields


def test_deep_link_matches_frontend_analyse_query():
    path = build_deep_link_path(
        "deal-1",
        "btl",
        listing_url="https://www.rightmove.co.uk/properties/12345678",
        property_id="prop-1",
    )
    assert path.startswith("/analyse?")
    parsed = urlparse(path)
    qs = parse_qs(parsed.query)
    assert qs["dealId"] == ["deal-1"]
    assert qs["strategy"] == ["btl"]
    assert qs["propertyId"] == ["prop-1"]
    assert qs["url"] == ["https://www.rightmove.co.uk/properties/12345678"]


# ── HTTP: auth + validation ───────────────────────────────────────────────

def test_unauthenticated_is_401(client):
    res = _post(client, token=None)
    assert res.status_code == 401
    assert res.get_json()["error"] == "unauthorised"


def test_invalid_token_is_401(client):
    res = _post(client, token="nope")
    assert res.status_code == 401


def test_rejects_non_screener_source(client):
    body = {**SCREENER_BODY, "source": "manual"}
    res = _post(client, body)
    assert res.status_code == 400
    assert "screener" in res.get_json()["message"]


def test_rejects_missing_rent(client):
    listing = {k: v for k, v in SCREENER_BODY["listing"].items() if k != "rentPcmGbp"}
    body = {**SCREENER_BODY, "listing": listing}
    res = _post(client, body)
    data = res.get_json()
    assert res.status_code == 400
    assert data["error"] == "validation_error"
    assert "rentPcmGbp" in data["fields"]


def test_rejects_schema_version_other_than_1(client):
    res = _post(client, {**SCREENER_BODY, "schemaVersion": 2})
    assert res.status_code == 400
    assert "schemaVersion" in res.get_json()["fields"]


# ── HTTP: happy path + property spine + idempotency ───────────────────────

def test_creates_deal_and_property(client, store):
    res = _post(client)
    assert res.status_code == 201
    data = res.get_json()
    assert set(data) >= {"dealId", "propertyId", "status", "deepLinkPath"}
    assert data["status"] == "created"
    assert data["deepLinkPath"].startswith("/analyse?")
    assert "dealId=" in data["deepLinkPath"]
    assert "strategy=btl" in data["deepLinkPath"]
    assert data["propertyId"]
    stored = store.deals[data["dealId"]]
    assert stored["strategy"] == "btl"
    assert stored["listing"]["rentPcmGbp"] == 950
    assert "photos" not in stored["listing"]
    assert "images" not in stored["listing"]
    assert "floorplans" not in stored["listing"]


def test_same_address_reuses_property_id(client, store):
    first = _post(client, idem="screener:rightmove:aaa").get_json()
    body = {
        **SCREENER_BODY,
        "listing": {**SCREENER_BODY["listing"], "sourceListingId": "999", "rentPcmGbp": 1000},
    }
    second = _post(client, body, idem="screener:rightmove:999").get_json()
    assert first["propertyId"] == second["propertyId"]
    assert first["dealId"] != second["dealId"]
    assert len(store.properties) == 1


def test_idempotency_key_returns_existing(client):
    key = "screener:rightmove:12345678"
    first = _post(client, idem=key)
    second = _post(client, idem=key)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.get_json()["dealId"] == second.get_json()["dealId"]
    assert second.get_json()["status"] == "existing"


def test_synthesised_idempotency_without_header(client):
    first = _post(client)
    second = _post(client)
    assert first.get_json()["dealId"] == second.get_json()["dealId"]
    assert second.get_json()["status"] == "existing"


def test_property_id_omitted_without_address_and_postcode(client):
    body = {
        "source": "screener",
        "schemaVersion": 1,
        "strategyHint": "hmo",
        "listing": {
            "source": "zoopla",
            "sourceListingId": "z-1",
            "listingUrl": "https://www.zoopla.co.uk/for-sale/details/1",
            "rentPcmGbp": 400,
        },
    }
    res = _post(client, body, idem="screener:zoopla:z-1")
    data = res.get_json()
    assert res.status_code == 201
    assert "propertyId" not in data
    assert data["status"] == "created"


def test_uppercase_strategy_stored_lowercase(client):
    body = {**SCREENER_BODY, "strategyHint": "BRRRR"}
    data = _post(client, body, idem="screener:rightmove:brrrr-1").get_json()
    assert "strategy=brrrr" in data["deepLinkPath"]

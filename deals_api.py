"""
Screener → Analyser handoff (POST /v1/deals) + shared property spine.

This is intentionally a thin scaffold: it persists a schemaVersion-1 listing
(photos stripped), resolves or creates a canonical propertyId from
address/postcode, and returns a metalyzi.co.uk deep link. It does NOT run
screening, MTD, compliance, ltd-co, or licensing.

Curl (production):

    curl -sS -X POST "$BACKEND_API_URL/v1/deals" \\
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
          "rentPcmGbp": 950
        }
      }'

Response:

    {
      "dealId": "<uuid>",
      "propertyId": "<uuid>",
      "status": "created",
      "deepLinkPath": "/analyse?dealId=<uuid>&strategy=btl&propertyId=<uuid>&url=..."
    }

Repeat the same Idempotency-Key (or omit it and send the same source +
sourceListingId) to receive status=existing with the original dealId.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import requests
from flask import jsonify, request

# ── Strategy enums (lowercase; the frontend may send BTL / BRRRR / R2SA) ──

ALLOWED_STRATEGIES = ("btl", "hmo", "brrrr", "flip", "sa", "development")

_STRATEGY_ALIASES = {
    "btl": "btl",
    "buy-to-let": "btl",
    "buytolet": "btl",
    "hmo": "hmo",
    "brr": "brrrr",
    "brrr": "brrrr",
    "brrrr": "brrrr",
    "flip": "flip",
    "sa": "sa",
    "r2sa": "sa",
    "r-2-sa": "sa",
    "serviced-accommodation": "sa",
    "servicedaccommodation": "sa",
    "short-let": "sa",
    "shortlet": "sa",
    "development": "development",
    "dev": "development",
}

PHOTO_KEYS = frozenset({
    "photos", "images", "imageUrls", "image_urls", "imageUrl", "image_url",
    "thumbnails", "thumbnailUrl", "thumbnail_url", "thumbnail",
    "floorplans", "floorPlans", "floor_plans", "gallery", "media",
    "pictures", "photoUrls", "photo_urls", "photoUrl", "heroImage",
})

# Same identity algorithm as dealcheck-uk/lib/discovery/ingest.ts so the
# Analyser and Discovery/Screener share one property spine.
UK_POSTCODE_RE = re.compile(
    r"([A-Z]{1,2}[0-9][0-9A-Z]?)\s*([0-9][A-Z]{2})",
    re.IGNORECASE,
)

_IDEMPOTENCY_RE = re.compile(r"^screener:[A-Za-z0-9._-]+:[A-Za-z0-9._-]+$")
_MAX_BODY_BYTES = 64 * 1024
_MAX_IDEMPOTENCY_KEY = 200

_store_lock = threading.Lock()
_memory_store: Optional["InMemoryDealStore"] = None


class DealValidationError(Exception):
    def __init__(self, message: str, fields: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.fields = fields or []


# ── Property identity (shared spine) ──────────────────────────────────────

def normalise_postcode(raw: Any) -> str:
    """Canonical UK postcode, e.g. 'M14 6LT'. Empty string if not parseable."""
    if not raw:
        return ""
    match = UK_POSTCODE_RE.search(str(raw).upper())
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2)}"


def normalise_address(raw: Any) -> str:
    """Uppercase, punctuation stripped, trailing postcode removed."""
    if not raw:
        return ""
    text = str(raw).upper()
    # Match dealcheck-uk: first postcode only (JS String.replace without /g).
    text = UK_POSTCODE_RE.sub(" ", text, count=1)
    text = re.sub(r"[.,;:'\"()]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def postcode_district(postcode: str) -> str:
    if not postcode:
        return ""
    return postcode.split()[0].upper() if postcode.split() else ""


def property_key(address: str, postcode: str) -> str:
    """sha256(normalised address | postcode) — the canonical property identity."""
    normalised_pc = normalise_postcode(postcode) or str(postcode or "").upper()
    payload = f"{normalise_address(address)}|{normalised_pc}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Listing normalisation ─────────────────────────────────────────────────

def strip_photos(value: Any) -> Any:
    """Drop image/gallery keys from a listing payload (recursive)."""
    if isinstance(value, dict):
        return {k: strip_photos(v) for k, v in value.items() if k not in PHOTO_KEYS}
    if isinstance(value, list):
        return [strip_photos(v) for v in value]
    return value


def map_strategy_hint(raw: Any) -> str:
    if raw is None or str(raw).strip() == "":
        raise DealValidationError("strategyHint is required", ["strategyHint"])
    token = str(raw).strip().lower().replace("_", "-")
    token = re.sub(r"\s+", "-", token)
    mapped = _STRATEGY_ALIASES.get(token) or _STRATEGY_ALIASES.get(token.replace("-", ""))
    if not mapped:
        allowed = "|".join(ALLOWED_STRATEGIES)
        raise DealValidationError(
            f"strategyHint must map to one of: {allowed}",
            ["strategyHint"],
        )
    return mapped


def _as_number(value: Any) -> Optional[float]:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if float("-inf") < float(value) < float("inf") else None
    if isinstance(value, str):
        cleaned = value.strip().replace("£", "").replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _as_int(value: Any) -> Optional[int]:
    number = _as_number(value)
    if number is None:
        return None
    return int(number)


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    text = value.strip()
    return text or None


def _first(*values: Any) -> Any:
    for value in values:
        if value is None or value == "":
            continue
        return value
    return None


def _extract_listing_id_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    patterns = (
        r"/properties/(\d+)",
        r"/for-sale/details/(\d+)",
        r"/to-rent/details/(\d+)",
        r"/details/(\d+)",
        r"/property/(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _infer_listing_source(listing: dict, listing_url: Optional[str]) -> str:
    raw = _as_str(_first(
        listing.get("source"),
        listing.get("listingSource"),
        listing.get("portal"),
        listing.get("listing_source"),
    ))
    if raw:
        return raw.lower()
    url = (listing_url or "").lower()
    if "rightmove" in url:
        return "rightmove"
    if "zoopla" in url:
        return "zoopla"
    if "onthemarket" in url:
        return "onthemarket"
    return "unknown"


def normalise_listing(raw_listing: dict, extra: dict | None = None) -> dict:
    """Flatten aliases into a schemaVersion-1 listing and strip photos."""
    extra = extra or {}
    merged = {**raw_listing, **{
        k: v for k, v in extra.items() if v is not None and k not in raw_listing
    }}
    merged = strip_photos(merged)
    if not isinstance(merged, dict):
        raise DealValidationError("listing must be an object", ["listing"])

    listing_url = _as_str(_first(
        merged.get("listingUrl"), merged.get("url"), merged.get("listing_url"),
    ))
    source_listing_id = _as_str(_first(
        merged.get("sourceListingId"),
        merged.get("listingId"),
        merged.get("listing_id"),
        _extract_listing_id_from_url(listing_url),
    ))
    address = _as_str(_first(merged.get("address"), merged.get("displayAddress")))
    postcode = normalise_postcode(_first(
        merged.get("postcode"), address,
    )) or _as_str(merged.get("postcode"))
    if postcode:
        postcode = postcode.upper()

    price = _as_number(_first(
        merged.get("priceGbp"), merged.get("price"), merged.get("purchasePrice"),
    ))
    rent = _as_number(_first(
        merged.get("rentPcmGbp"), merged.get("monthlyRent"), merged.get("rent"),
    ))

    canonical = {
        "schemaVersion": 1,
        "source": _infer_listing_source(merged, listing_url),
        "sourceListingId": source_listing_id,
        "listingUrl": listing_url,
        "address": address,
        "postcode": postcode,
        "priceGbp": int(price) if price is not None else None,
        "rentPcmGbp": rent,
        "bedrooms": _as_int(merged.get("bedrooms")),
        "bathrooms": _as_int(merged.get("bathrooms")),
        "propertyType": _as_str(_first(merged.get("propertyType"), merged.get("property_type"))),
        "tenure": _as_str(merged.get("tenure")),
        "description": _as_str(merged.get("description")),
    }

    reserved = set(canonical) | {
        "url", "listing_url", "listingId", "listing_id", "displayAddress",
        "price", "purchasePrice", "monthlyRent", "rent", "property_type",
        "listingSource", "portal", "listing_source",
    }
    for key, value in merged.items():
        if key in reserved or key in canonical:
            continue
        canonical[key] = value

    return canonical


def validate_screener_payload(body: dict) -> tuple[str, dict, Optional[str]]:
    """Return (strategy, canonical listing, idempotency key from body identity)."""
    if not isinstance(body, dict):
        raise DealValidationError("JSON object required")

    source = _as_str(body.get("source"))
    if not source:
        raise DealValidationError("source is required", ["source"])
    if source.lower() != "screener":
        raise DealValidationError(
            "only source=screener is supported on this endpoint",
            ["source"],
        )

    schema = body.get("schemaVersion")
    if schema is None:
        raise DealValidationError("schemaVersion is required", ["schemaVersion"])
    try:
        schema_int = int(schema)
    except (TypeError, ValueError):
        raise DealValidationError("schemaVersion must be 1", ["schemaVersion"])
    if schema_int != 1:
        raise DealValidationError("schemaVersion must be 1", ["schemaVersion"])

    listing_raw = body.get("listing")
    if listing_raw is None:
        raise DealValidationError("listing is required", ["listing"])
    if not isinstance(listing_raw, dict):
        raise DealValidationError("listing must be an object", ["listing"])

    extra = {
        "rentPcmGbp": body.get("rentPcmGbp"),
        "strategyHint": body.get("strategyHint"),
        "sourceListingId": body.get("sourceListingId"),
    }
    listing = normalise_listing(listing_raw, extra)
    strategy = map_strategy_hint(_first(body.get("strategyHint"), listing_raw.get("strategyHint")))

    rent = listing.get("rentPcmGbp")
    if rent is None:
        raise DealValidationError(
            "rentPcmGbp is required for the screener handoff",
            ["rentPcmGbp"],
        )
    if rent <= 0:
        raise DealValidationError(
            "rentPcmGbp must be a positive number (GBP per calendar month)",
            ["rentPcmGbp"],
        )

    if not any((listing.get("address"), listing.get("listingUrl"), listing.get("sourceListingId"))):
        raise DealValidationError(
            "listing must include address, listingUrl, or sourceListingId",
            ["listing"],
        )

    idem_from_listing = None
    if listing.get("sourceListingId"):
        idem_from_listing = (
            f"screener:{listing.get('source') or 'unknown'}:{listing['sourceListingId']}"
        )
    return strategy, listing, idem_from_listing


def resolve_idempotency_key(header_value: Optional[str], synthesized: Optional[str]) -> Optional[str]:
    raw = (header_value or "").strip() or synthesized
    if not raw:
        return None
    if len(raw) > _MAX_IDEMPOTENCY_KEY:
        raise DealValidationError(
            f"Idempotency-Key must be at most {_MAX_IDEMPOTENCY_KEY} characters",
            ["Idempotency-Key"],
        )
    # Header may be the documented screener:{source}:{sourceListingId} form,
    # or any other caller-supplied key. Both are accepted; the documented
    # form is used when the header is omitted.
    return raw


def build_deep_link_path(
    deal_id: str,
    strategy: str,
    listing_url: Optional[str] = None,
    property_id: Optional[str] = None,
) -> str:
    """Path-only deep link for metalyzi.co.uk (/analyse?dealId=&strategy=&url=)."""
    params: dict[str, str] = {"dealId": deal_id, "strategy": strategy}
    if property_id:
        params["propertyId"] = property_id
    if listing_url:
        params["url"] = listing_url
    return f"/analyse?{urlencode(params)}"


def handoff_response(deal: dict, status: str) -> dict:
    payload = {
        "dealId": deal["id"],
        "status": status,
        "deepLinkPath": build_deep_link_path(
            deal["id"],
            deal.get("strategy") or "",
            (deal.get("listing") or {}).get("listingUrl"),
            deal.get("property_id"),
        ),
    }
    if deal.get("property_id"):
        payload["propertyId"] = deal["property_id"]
    return payload


# ── Persistence ───────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class InMemoryDealStore:
    """Process-local store used in tests and when Supabase is not configured."""

    def __init__(self):
        self.properties: dict[str, dict] = {}  # property_key -> row
        self.properties_by_id: dict[str, dict] = {}
        self.deals: dict[str, dict] = {}
        self.by_idem: dict[tuple[str, str], str] = {}

    def get_deal_by_idempotency(self, user_id: str, key: str) -> Optional[dict]:
        deal_id = self.by_idem.get((user_id, key))
        if not deal_id:
            return None
        return dict(self.deals[deal_id])

    def resolve_or_create_property(self, listing: dict) -> Optional[str]:
        address = listing.get("address") or ""
        postcode = listing.get("postcode") or ""
        if not address or not postcode:
            return None
        key = property_key(address, postcode)
        existing = self.properties.get(key)
        now = _utcnow()
        if existing:
            existing["last_seen"] = now
            existing["updated_at"] = now
            if listing.get("bedrooms") is not None:
                existing["bedrooms"] = listing["bedrooms"]
            if listing.get("propertyType"):
                existing["property_type"] = listing["propertyType"]
            if listing.get("tenure"):
                existing["tenure"] = listing["tenure"]
            return existing["id"]
        row = {
            "id": _new_id(),
            "property_key": key,
            "canonical_address": normalise_address(address) or address,
            "postcode": normalise_postcode(postcode) or postcode,
            "postcode_district": postcode_district(normalise_postcode(postcode) or postcode),
            "property_type": listing.get("propertyType"),
            "bedrooms": listing.get("bedrooms"),
            "bathrooms": listing.get("bathrooms"),
            "tenure": listing.get("tenure"),
            "status": "active",
            "first_seen": now,
            "last_seen": now,
            "created_at": now,
            "updated_at": now,
        }
        self.properties[key] = row
        self.properties_by_id[row["id"]] = row
        return row["id"]

    def create_deal(self, user_id: str, listing: dict, strategy: str,
                    idempotency_key: Optional[str], property_id: Optional[str]) -> dict:
        now = _utcnow()
        row = {
            "id": _new_id(),
            "user_id": user_id,
            "property_id": property_id,
            "source": "screener",
            "schema_version": 1,
            "strategy": strategy,
            "rent_pcm_gbp": listing.get("rentPcmGbp"),
            "listing": listing,
            "status": "created",
            "idempotency_key": idempotency_key,
            "source_listing_id": listing.get("sourceListingId"),
            "listing_source": listing.get("source"),
            "created_at": now,
            "updated_at": now,
        }
        self.deals[row["id"]] = row
        if idempotency_key:
            self.by_idem[(user_id, idempotency_key)] = row["id"]
        return dict(row)


class SupabaseDealStore:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def get_deal_by_idempotency(self, user_id: str, key: str) -> Optional[dict]:
        resp = requests.get(
            f"{self.url}/rest/v1/deals",
            params={
                "user_id": f"eq.{user_id}",
                "idempotency_key": f"eq.{key}",
                "select": "id,user_id,property_id,source,schema_version,strategy,"
                          "rent_pcm_gbp,listing,status,idempotency_key,"
                          "source_listing_id,listing_source,created_at",
                "limit": "1",
            },
            headers=self._headers(),
            timeout=8,
        )
        resp.raise_for_status()
        rows = resp.json() or []
        return rows[0] if rows else None

    def _get_property_by_key(self, key: str) -> Optional[dict]:
        resp = requests.get(
            f"{self.url}/rest/v1/properties",
            params={"property_key": f"eq.{key}", "select": "id", "limit": "1"},
            headers=self._headers(),
            timeout=8,
        )
        resp.raise_for_status()
        rows = resp.json() or []
        return rows[0] if rows else None

    def resolve_or_create_property(self, listing: dict) -> Optional[str]:
        address = listing.get("address") or ""
        postcode = listing.get("postcode") or ""
        if not address or not postcode:
            return None
        key = property_key(address, postcode)
        existing = self._get_property_by_key(key)
        now = _utcnow()
        if existing:
            requests.patch(
                f"{self.url}/rest/v1/properties",
                params={"id": f"eq.{existing['id']}"},
                json={
                    "last_seen": now,
                    "updated_at": now,
                    "status": "active",
                    **({"bedrooms": listing["bedrooms"]} if listing.get("bedrooms") is not None else {}),
                    **({"property_type": listing["propertyType"]} if listing.get("propertyType") else {}),
                    **({"tenure": listing["tenure"]} if listing.get("tenure") else {}),
                },
                headers=self._headers({"Prefer": "return=minimal"}),
                timeout=8,
            )
            return existing["id"]

        payload = {
            "property_key": key,
            "canonical_address": normalise_address(address) or address,
            "postcode": normalise_postcode(postcode) or postcode,
            "postcode_district": postcode_district(normalise_postcode(postcode) or postcode) or None,
            "property_type": listing.get("propertyType"),
            "bedrooms": listing.get("bedrooms"),
            "bathrooms": listing.get("bathrooms"),
            "tenure": listing.get("tenure"),
            "status": "active",
            "first_seen": now,
            "last_seen": now,
        }
        resp = requests.post(
            f"{self.url}/rest/v1/properties",
            json=payload,
            headers=self._headers({"Prefer": "return=representation"}),
            timeout=8,
        )
        if resp.status_code in (409, 23505) or (
            resp.status_code >= 400 and "duplicate" in (resp.text or "").lower()
        ):
            raced = self._get_property_by_key(key)
            return raced["id"] if raced else None
        resp.raise_for_status()
        rows = resp.json() or []
        if isinstance(rows, list) and rows:
            return rows[0]["id"]
        if isinstance(rows, dict) and rows.get("id"):
            return rows["id"]
        return None

    def create_deal(self, user_id: str, listing: dict, strategy: str,
                    idempotency_key: Optional[str], property_id: Optional[str]) -> dict:
        payload = {
            "user_id": user_id,
            "property_id": property_id,
            "source": "screener",
            "schema_version": 1,
            "strategy": strategy,
            "rent_pcm_gbp": listing.get("rentPcmGbp"),
            "listing": listing,
            "status": "created",
            "idempotency_key": idempotency_key,
            "source_listing_id": listing.get("sourceListingId"),
            "listing_source": listing.get("source"),
        }
        resp = requests.post(
            f"{self.url}/rest/v1/deals",
            json=payload,
            headers=self._headers({"Prefer": "return=representation"}),
            timeout=8,
        )
        if resp.status_code in (409,) and idempotency_key:
            existing = self.get_deal_by_idempotency(user_id, idempotency_key)
            if existing:
                return existing
        resp.raise_for_status()
        rows = resp.json() or []
        row = rows[0] if isinstance(rows, list) else rows
        return row


def _supabase_config() -> tuple[str, str]:
    url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    )
    return url, key


def memory_store() -> InMemoryDealStore:
    global _memory_store
    with _store_lock:
        if _memory_store is None:
            _memory_store = InMemoryDealStore()
        return _memory_store


def reset_memory_store() -> InMemoryDealStore:
    global _memory_store
    with _store_lock:
        _memory_store = InMemoryDealStore()
        return _memory_store


def get_store():
    url, key = _supabase_config()
    if url and key:
        return SupabaseDealStore(url, key)
    return memory_store()


def fetch_supabase_user(access_token: str) -> Optional[dict]:
    """Validate a Supabase access token via Auth. Returns {id, email} or None."""
    url, key = _supabase_config()
    if not url or not key or not access_token:
        return None
    try:
        resp = requests.get(
            f"{url}/auth/v1/user",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=5,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    user_id = data.get("id")
    if not user_id:
        return None
    return {"id": user_id, "email": data.get("email")}


def _bearer_token() -> Optional[str]:
    header = request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        return token or None
    return None


def create_screener_deal(user_id: str, body: dict, idempotency_header: Optional[str]) -> tuple[dict, int]:
    strategy, listing, synthesized_key = validate_screener_payload(body)
    idem_key = resolve_idempotency_key(idempotency_header, synthesized_key)
    store = get_store()

    if idem_key:
        existing = store.get_deal_by_idempotency(user_id, idem_key)
        if existing:
            return handoff_response(existing, "existing"), 200

    property_id = store.resolve_or_create_property(listing)
    deal = store.create_deal(
        user_id=user_id,
        listing=listing,
        strategy=strategy,
        idempotency_key=idem_key,
        property_id=property_id,
    )
    return handoff_response(deal, "created"), 201


def register_deals_routes(app, limiter) -> None:
    """Attach POST /v1/deals to the Flask app."""

    @app.route("/v1/deals", methods=["POST"])
    @limiter.limit("20 per minute")
    def create_deal_v1():
        token = _bearer_token()
        if not token:
            return jsonify({
                "error": "unauthorised",
                "message": "Authorization: Bearer <supabase access token> is required",
            }), 401

        user = fetch_supabase_user(token)
        if not user:
            return jsonify({
                "error": "unauthorised",
                "message": "Invalid or expired access token",
            }), 401

        if not request.is_json:
            return jsonify({
                "error": "validation_error",
                "message": "Content-Type must be application/json",
            }), 400

        body = request.get_json(silent=True)
        if not body:
            return jsonify({
                "error": "validation_error",
                "message": "Invalid JSON body",
            }), 400

        try:
            encoded_len = len(request.get_data(cache=True) or b"")
            if encoded_len > _MAX_BODY_BYTES:
                return jsonify({
                    "error": "validation_error",
                    "message": "Request too large (photos should be stripped before POST)",
                }), 413

            payload, status = create_screener_deal(
                user_id=user["id"],
                body=body,
                idempotency_header=request.headers.get("Idempotency-Key"),
            )
            return jsonify(payload), status
        except DealValidationError as exc:
            return jsonify({
                "error": "validation_error",
                "message": exc.message,
                "fields": exc.fields,
            }), 400
        except requests.HTTPError as exc:
            app.logger.error("[v1/deals] supabase HTTP error: %s", exc)
            return jsonify({
                "error": "storage_unavailable",
                "message": "Could not persist deal. Apply the deals/properties migration and retry.",
            }), 503
        except Exception:
            app.logger.exception("[v1/deals] unexpected error")
            return jsonify({
                "error": "internal_error",
                "message": "An error occurred creating the deal",
            }), 500

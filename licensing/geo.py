"""Postcode → local authority resolution.

Uses postcodes.io, which is backed by ONS Postcode Directory (ONSPD).
UPRN resolution is explicitly out of scope (P4).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests

from licensing.models import GEO_STALE_AFTER_DAYS, Source, component_freshness, isoformat, utcnow

POSTCODES_IO_URL = "https://api.postcodes.io/postcodes/{postcode}"
USER_AGENT = "MetalyziLicensing/0.1 (+https://metalyzi.co.uk)"

# Full UK postcode: outward + inward. Inward is always digit + 2 letters.
_POSTCODE_RE = re.compile(
    r"^([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})$",
    re.IGNORECASE,
)
# Outward-only is accepted for LA resolution via postcodes.io only when a
# full postcode is provided — outward alone is ambiguous. We still parse
# it so we can return a validation error rather than a 502.
_OUTWARD_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?)$", re.IGNORECASE)

Fetcher = Callable[[str], dict[str, Any]]


class GeoError(Exception):
    """Raised when the postcode cannot be resolved. `code` is a stable API code."""

    def __init__(self, message: str, *, code: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


@dataclass
class Location:
    postcode: str
    postcode_outward: str
    postcode_inward: str
    la_name: str
    la_code: str
    admin_ward: Optional[str]
    country: str
    region: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    quality: Optional[int]
    confidence: float
    source: str
    fetched_at: str

    @property
    def is_england(self) -> bool:
        return (self.country or "").strip().lower() == "england"

    def to_dict(self) -> dict[str, Any]:
        return {
            "postcode": self.postcode,
            "postcode_outward": self.postcode_outward,
            "postcode_inward": self.postcode_inward,
            "la_name": self.la_name,
            "la_code": self.la_code,
            "admin_ward": self.admin_ward,
            "country": self.country,
            "region": self.region,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "quality": self.quality,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "fetched_at": self.fetched_at,
            "freshness": component_freshness(
                self.fetched_at,
                stale_after_days=GEO_STALE_AFTER_DAYS,
                basis="live_lookup",
                notes="Resolved via postcodes.io (ONSPD). Live at check time.",
            ).to_dict(),
        }


def normalise_postcode(raw: str) -> str:
    """Return a canonical outward+inward postcode (e.g. 'M14 6LT')."""
    cleaned = re.sub(r"\s+", "", (raw or "")).upper()
    match = _POSTCODE_RE.match(cleaned)
    if not match:
        raise GeoError(
            "A full UK postcode is required (e.g. M14 6LT). Outward-only and UPRN are not accepted.",
            code="invalid_postcode",
        )
    return f"{match.group(1)} {match.group(2)}"


def split_postcode(canonical: str) -> tuple[str, str]:
    outward, inward = canonical.split(" ", 1)
    return outward, inward


def geo_sources() -> list[Source]:
    return [
        Source(
            name="postcodes.io (ONSPD)",
            kind="geo",
            url="https://postcodes.io",
            note="Ideal Postcodes API wrapping the ONS Postcode Directory.",
        )
    ]


def _default_fetch(url: str) -> dict[str, Any]:
    response = requests.get(
        url,
        timeout=8,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise GeoError(
            "Postcode lookup returned a non-JSON response.",
            code="geo_upstream_error",
            http_status=502,
        ) from exc
    if response.status_code == 404:
        raise GeoError(
            "Postcode was not found in ONSPD / postcodes.io.",
            code="postcode_not_found",
            http_status=404,
        )
    if response.status_code != 200:
        raise GeoError(
            "Postcode lookup failed.",
            code="geo_upstream_error",
            http_status=502,
        )
    return payload


def resolve_postcode(
    raw_postcode: str,
    *,
    fetcher: Optional[Fetcher] = None,
    now=None,
) -> Location:
    """Resolve a full UK postcode to the local authority (ONS admin district)."""
    canonical = normalise_postcode(raw_postcode)
    compact = canonical.replace(" ", "")
    url = POSTCODES_IO_URL.format(postcode=compact)
    fetch = fetcher or _default_fetch
    try:
        payload = fetch(url)
    except GeoError:
        raise
    except requests.RequestException as exc:
        raise GeoError(
            "Postcode lookup timed out or could not be reached.",
            code="geo_upstream_error",
            http_status=502,
        ) from exc

    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise GeoError(
            "Postcode lookup returned an unexpected payload.",
            code="geo_upstream_error",
            http_status=502,
        )

    codes = result.get("codes") or {}
    la_name = (result.get("admin_district") or "").strip()
    la_code = (codes.get("admin_district") or "").strip()
    if not la_name or not la_code:
        raise GeoError(
            "Postcode was found but no local authority code was returned.",
            code="geo_incomplete",
            http_status=502,
        )

    quality = result.get("quality")
    # postcodes.io quality 1 = OS matched; higher numbers are interpolated.
    if quality == 1:
        confidence = 0.95
    elif isinstance(quality, int) and quality <= 3:
        confidence = 0.80
    else:
        confidence = 0.65

    outward, inward = split_postcode(canonical)
    fetched_at = isoformat(now or utcnow())
    return Location(
        postcode=result.get("postcode") or canonical,
        postcode_outward=result.get("outcode") or outward,
        postcode_inward=result.get("incode") or inward,
        la_name=la_name,
        la_code=la_code,
        admin_ward=(result.get("admin_ward") or None),
        country=result.get("country") or "Unknown",
        region=result.get("region"),
        latitude=result.get("latitude"),
        longitude=result.get("longitude"),
        quality=quality if isinstance(quality, int) else None,
        confidence=confidence,
        source="postcodes.io",
        fetched_at=fetched_at or isoformat(utcnow()) or "",
    )

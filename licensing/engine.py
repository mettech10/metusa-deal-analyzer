"""Orchestrate a licensing check.

Order: postcode → LA, nation gate, statutory England rules, Article 4 ingest,
curated additional/selective schemes. Freshness/confidence are computed last
so they describe the whole response.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from licensing.article4 import article4_flags, ingest_article4_for_point
from licensing.geo import GeoError, Location, geo_sources, resolve_postcode
from licensing.mandatory import england_mandatory_and_sui_generis_flags, out_of_scope_nation_flag
from licensing.models import (
    Flag,
    confidence_band,
    isoformat,
    utcnow,
)
from licensing.schemes import match_schemes, scheme_flags, schemes_meta

DistrictFallback = Callable[[str], dict[str, Any]]


def run_licensing_check(
    payload: dict[str, Any],
    *,
    geo_fetcher=None,
    article4_fetcher=None,
    district_fallback: Optional[DistrictFallback] = None,
    skip_article4: bool = False,
    now=None,
) -> dict[str, Any]:
    """Run the checker. Raises GeoError for invalid / unresolved postcodes."""
    now = now or utcnow()
    checked_at = isoformat(now)

    postcode = payload.get("postcode")
    if not isinstance(postcode, str) or not postcode.strip():
        raise GeoError("postcode is required", code="invalid_postcode")

    occupants = _optional_int(payload.get("occupants"), field="occupants")
    households = _optional_int(payload.get("households"), field="households")
    sharing = payload.get("sharing_amenities")
    if sharing is not None and not isinstance(sharing, bool):
        raise GeoError("sharing_amenities must be a boolean if supplied", code="invalid_input")
    intended_use = str(payload.get("intended_use") or "unknown").lower()
    if intended_use not in {"hmo", "btl", "sa", "str", "rental", "unknown"}:
        intended_use = "unknown"

    skip_article4 = bool(payload.get("skip_article4") or skip_article4)

    location = resolve_postcode(postcode, fetcher=geo_fetcher, now=now)

    flags: list[Flag] = []
    warnings: list[str] = []
    article4_dict: Optional[dict[str, Any]] = None
    matched_schemes: list[Any] = []

    if not location.is_england:
        flags.append(out_of_scope_nation_flag(location.country))
        warnings.append(
            f"Resolved country is {location.country}; England statutory rules and "
            "English additional/selective seeds are not applied."
        )
    else:
        flags.extend(
            england_mandatory_and_sui_generis_flags(
                occupants=occupants,
                households=households,
                sharing_amenities=sharing,
                intended_use=intended_use,
            )
        )

        fallback_payload = None
        if district_fallback is not None:
            try:
                fallback_payload = district_fallback(location.postcode)
            except Exception:
                fallback_payload = None

        if skip_article4 or location.latitude is None or location.longitude is None:
            article4_dict = {
                "queried": False,
                "ok": False,
                "coverage": "skipped",
                "hit_count": 0,
                "hmo_hit_count": 0,
                "hits": [],
                "confidence": 0.0,
                "note": "Article 4 ingest skipped or coordinates missing.",
            }
            if not skip_article4:
                warnings.append("No coordinates from postcodes.io — Article 4 point query skipped.")
        else:
            a4 = ingest_article4_for_point(
                location.latitude,
                location.longitude,
                fetcher=article4_fetcher,
                now=now,
            )
            article4_dict = a4.to_dict()
            flags.extend(article4_flags(a4, district_fallback=fallback_payload))
            if a4.coverage.startswith("partial_miss"):
                warnings.append(
                    "No planning.data.gov.uk Article 4 hit. Dataset coverage is partial; "
                    "this is not evidence of no direction."
                )

        matched_schemes = match_schemes(la_code=location.la_code, la_name=location.la_name)
        flags.extend(
            scheme_flags(
                matched_schemes,
                occupants=occupants,
                intended_use=intended_use,
                admin_ward=location.admin_ward,
            )
        )

    freshness = _overall_freshness(flags, location)
    return {
        "ok": True,
        "api_version": "v1",
        "checked_at": checked_at,
        "scope": {
            "nation": "England",
            "modules": [
                "postcode_to_la",
                "mandatory_hmo",
                "sui_generis",
                "article4_planning_data",
                "additional_selective_schemes",
            ],
            "exclusions": ["uprn", "con29", "wales", "scotland", "northern_ireland"],
        },
        "location": location.to_dict(),
        "inputs": {
            "postcode": location.postcode,
            "occupants": occupants,
            "households": households,
            "sharing_amenities": sharing,
            "intended_use": intended_use,
        },
        "freshness": freshness,
        "flags": [f.to_dict() for f in flags],
        "article4": article4_dict,
        "schemes": {
            "matched": [s.to_dict() for s in matched_schemes],
            "seed": schemes_meta(),
        },
        "warnings": warnings,
        "sources": [s.to_dict() for s in geo_sources()],
    }


def _optional_int(value: Any, *, field: str) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise GeoError(f"{field} must be an integer", code="invalid_input")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise GeoError(f"{field} must be an integer", code="invalid_input") from exc
    if number < 0 or number > 50:
        raise GeoError(f"{field} is out of range", code="invalid_input")
    return number


def _overall_freshness(flags: list[Flag], location: Location) -> dict[str, Any]:
    """Freshness is first-class: min confidence of material flags + stale roll-up."""
    components = [
        {
            "id": "geo",
            "confidence": location.confidence,
            "confidence_band": confidence_band(location.confidence),
            **location.to_dict()["freshness"],
        }
    ]
    stale_ids: list[str] = []
    if location.to_dict()["freshness"].get("stale"):
        stale_ids.append("geo")

    material_confidences = [location.confidence]
    for flag in flags:
        fresh = flag.freshness.to_dict() if flag.freshness else {}
        components.append(
            {
                "id": flag.id,
                "confidence": round(flag.confidence, 3),
                "confidence_band": confidence_band(flag.confidence),
                "applies": flag.applies,
                "severity": flag.severity,
                **fresh,
            }
        )
        if fresh.get("stale"):
            stale_ids.append(flag.id)
        if flag.applies in {"yes", "possible", "conditional"} and flag.severity in {"high", "medium"}:
            material_confidences.append(flag.confidence)

    overall = min(material_confidences) if material_confidences else 0.0
    return {
        "overall_confidence": round(overall, 3),
        "overall_confidence_band": confidence_band(overall),
        "stale": bool(stale_ids),
        "stale_components": stale_ids,
        "components": components,
        "notes": (
            "overall_confidence is the minimum confidence among location plus "
            "high/medium flags that apply, are possible, or are conditional. "
            "A stale scheme seed does not hide a high-confidence statutory flag — "
            "inspect components[]."
        ),
    }

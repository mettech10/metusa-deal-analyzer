"""Orchestrate a licensing check.

Order: postcode → LA, nation gate, statutory England rules, Article 4 ingest,
curated additional/selective schemes. Freshness/confidence are computed last
so they describe the whole response.

Isolation: this module must never import app.HMO_LICENSING_LOOKUP,
get_hmo_licensing_info, STR_LICENSING_RULES, or any Wales/Scotland seed.
Those tables are legacy area-analysis context only and must not override
/v1/licensing/check.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from licensing.article4 import article4_flags, ingest_article4_for_point
from licensing.article4_register import lookup_verified_article4
from licensing.geo import GeoError, Location, geo_sources, resolve_postcode
from licensing.mandatory import england_mandatory_and_sui_generis_flags, out_of_scope_nation_flag
from licensing.models import (
    FEATURE_FLAG,
    Flag,
    SEVERITY_RANK,
    confidence_band,
    disclaimer_payload,
    isoformat,
    utcnow,
    worst_severity,
)
from licensing.schemes import match_schemes, scheme_flags, schemes_meta

DistrictFallback = Callable[[str], dict[str, Any]]
VerifiedArticle4Lookup = Callable[[str, Optional[str]], Optional[dict[str, Any]]]

# A property needs one licence: an HMO licence (Part 2: mandatory or
# additional) or a selective licence (Part 3). Part 3 excludes HMOs that
# need a Part 2 licence (Housing Act 2004 s79(3)).
_HMO_LICENCE_FLAGS = {"mandatory_hmo_licence", "additional_hmo_licence"}
_SELECTIVE_FLAGS = {"selective_licence"}


def run_licensing_check(
    payload: dict[str, Any],
    *,
    geo_fetcher=None,
    article4_fetcher=None,
    district_fallback: Optional[DistrictFallback] = None,
    verified_article4_lookup: Optional[VerifiedArticle4Lookup] = None,
    skip_article4: bool = False,
    now=None,
) -> dict[str, Any]:
    """Run the checker. Raises GeoError for invalid / unresolved postcodes."""
    now = now or utcnow()
    checked_at = isoformat(now)

    postcode = payload.get("postcode")
    if not isinstance(postcode, str) or not postcode.strip():
        raise GeoError("postcode is required", code="invalid_postcode")

    occupants = _optional_int(payload.get("occupants"), field="occupants", max_value=50)
    households = _optional_int(payload.get("households"), field="households", max_value=50)
    sharing = _optional_bool(payload.get("sharing_amenities"), field="sharing_amenities")
    conversion_from_c3 = _optional_bool(payload.get("conversion_from_c3"), field="conversion_from_c3")
    purpose_built_flat_in_block_of_3_plus = _optional_bool(
        payload.get("purpose_built_flat_in_block_of_3_plus"),
        field="purpose_built_flat_in_block_of_3_plus",
    )
    purpose_built_flat = _optional_bool(payload.get("purpose_built_flat"), field="purpose_built_flat")
    flats_raw = payload.get("self_contained_flats_in_block")
    if flats_raw is None or flats_raw == "":
        flats_raw = payload.get("flats_in_block")
        flats_field = "flats_in_block"
    else:
        flats_field = "self_contained_flats_in_block"
    flats_in_block = _optional_int(flats_raw, field=flats_field, max_value=500)

    intended_use = str(payload.get("intended_use") or "unknown").lower()
    if intended_use not in {"hmo", "btl", "sa", "str", "rental", "c3", "c4", "sui_generis", "unknown"}:
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
            "English additional/selective seeds are not applied. "
            "Legacy HMO_LICENSING_LOOKUP / Wales rows are not consulted."
        )
    else:
        flags.extend(
            england_mandatory_and_sui_generis_flags(
                occupants=occupants,
                households=households,
                sharing_amenities=sharing,
                intended_use=intended_use,
                purpose_built_flat_in_block_of_3_plus=purpose_built_flat_in_block_of_3_plus,
                purpose_built_flat=purpose_built_flat,
                self_contained_flats_in_block=flats_in_block,
            )
        )

        # District-level Article 4: the verified council register first, then
        # the unverified legacy list. Never an LLM answer.
        fallback_payload = None
        lookup = verified_article4_lookup or lookup_verified_article4
        try:
            fallback_payload = _sanitize_article4_fallback(lookup(location.postcode, location.la_code))
        except Exception:
            fallback_payload = None
        if fallback_payload is None and district_fallback is not None:
            try:
                raw_fb = district_fallback(location.postcode)
                fallback_payload = _sanitize_article4_fallback(raw_fb)
                if fallback_payload is not None:
                    fallback_payload["source"] = "static"
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
            flags.extend(
                article4_flags(
                    a4,
                    district_fallback=fallback_payload,
                    conversion_from_c3=conversion_from_c3,
                    intended_use=intended_use,
                )
            )
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
        _apply_one_licence_rule(flags)

    freshness = _overall_freshness(flags, location)
    deal_impact = _roll_up_deal_impact(flags)
    return {
        "ok": True,
        "api_version": "v1",
        "feature_flag": FEATURE_FLAG,
        "checked_at": checked_at,
        "disclaimer": disclaimer_payload(),
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
            "legacy_lookups_excluded": ["HMO_LICENSING_LOOKUP", "STR_LICENSING_RULES", "get_hmo_licensing_info"],
        },
        "location": location.to_dict(),
        "inputs": {
            "postcode": location.postcode,
            "occupants": occupants,
            "households": households,
            "sharing_amenities": sharing,
            "intended_use": intended_use,
            "conversion_from_c3": conversion_from_c3,
            "purpose_built_flat_in_block_of_3_plus": purpose_built_flat_in_block_of_3_plus,
            "purpose_built_flat": purpose_built_flat,
            "self_contained_flats_in_block": flats_in_block,
            "flats_in_block": flats_in_block,
        },
        "deal_impact": deal_impact,
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


def _sanitize_article4_fallback(raw: Any) -> Optional[dict[str, Any]]:
    """Allow only Article 4 district-index fields. Drop licensing-lookup payloads."""
    if not isinstance(raw, dict):
        return None
    if raw.get("tier") or raw.get("rent_smart_wales") or raw.get("scope"):
        return None
    out = {
        "is_article_4": bool(raw.get("is_article_4") or raw.get("isArticle4")),
        "known": bool(raw.get("known")),
        "council": raw.get("council"),
        "note": raw.get("note") or raw.get("advice"),
    }
    if raw.get("source") == "verified_register":
        for key in (
            "source", "status", "district", "district_listed", "verified",
            "last_verified_at", "effective_date", "url",
        ):
            out[key] = raw.get(key)
    return out


def _apply_one_licence_rule(flags: list[Flag]) -> None:
    """Once an HMO licence is certain, selective licensing cannot also apply,
    and additional licensing is covered by the mandatory licence."""
    mandatory_yes = any(f.id == "mandatory_hmo_licence" and f.applies == "yes" for f in flags)
    if not mandatory_yes:
        return
    for f in flags:
        if f.id in _SELECTIVE_FLAGS and f.applies != "no":
            f.applies = "no"
            f.severity = "info"
            f.deal_impact = "info"
            f.summary += (
                " Not needed here: a property that needs an HMO licence is outside "
                "selective licensing (Housing Act 2004 s79(3))."
            )
        elif f.id == "additional_hmo_licence" and f.applies != "no":
            f.applies = "no"
            f.severity = "info"
            f.deal_impact = "info"
            f.summary += (
                " Covered by the mandatory HMO licence, so no separate additional licence. "
                "The council's HMO fee range is used for the fee estimate."
            )


def _optional_bool(value: Any, *, field: str) -> Optional[bool]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    raise GeoError(f"{field} must be a boolean if supplied", code="invalid_input")


def _optional_int(value: Any, *, field: str, max_value: int = 50) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise GeoError(f"{field} must be an integer", code="invalid_input")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise GeoError(f"{field} must be an integer", code="invalid_input") from exc
    if number < 0 or number > max_value:
        raise GeoError(f"{field} is out of range", code="invalid_input")
    return number


def _roll_up_deal_impact(flags: list[Flag]) -> dict[str, Any]:
    material = [
        f for f in flags
        if f.applies in {"yes", "possible", "conditional"}
    ]
    levels = [(f.deal_impact or f.severity) for f in material]
    level = worst_severity(levels)
    drivers = [
        {
            "flag_id": f.id,
            "severity": f.severity,
            "severity_class": f.severity,
            "deal_impact": f.deal_impact or f.severity,
            "applies": f.applies,
        }
        for f in material
        if SEVERITY_RANK.get(f.deal_impact or f.severity, 0) >= SEVERITY_RANK[level]
        and (f.deal_impact or f.severity) == level
    ]
    killers = [
        {
            "flag_id": f.id,
            "title": f.title,
            "summary": f.summary,
            "applies": f.applies,
        }
        for f in material
        if (f.deal_impact or f.severity) == "deal_killer"
    ]

    fee_hooks = []
    capex_lines: list[dict[str, Any]] = []
    risk_notes: list[dict[str, Any]] = []
    seen_fees: set[tuple[str, str]] = set()
    seen_notes: set[str] = set()
    mandatory_yes = any(f.id == "mandatory_hmo_licence" and f.applies == "yes" for f in flags)
    hmo_licence_certain = mandatory_yes or any(
        f.id == "additional_hmo_licence" and f.applies == "yes" for f in flags
    )

    def fee_counts(f: Flag) -> bool:
        if f.id in _SELECTIVE_FLAGS and hmo_licence_certain:
            return False
        if f.id == "additional_hmo_licence" and mandatory_yes:
            return True  # council HMO fee schedule stands in for the mandatory fee
        return f.applies in {"yes", "possible", "conditional"}

    for f in flags:
        for h in f.analyse_hooks:
            payload = h.to_dict()
            if h.kind in {"blocker", "planning", "licence", "cost", "verify", "scope"} and h.deal_impact in {
                "deal_killer",
                "compliance_cost",
                "soft_warning",
            } and f.applies != "no":
                text = h.summary or f.summary
                if text and text not in seen_notes:
                    seen_notes.add(text)
                    risk_notes.append({
                        "id": h.id,
                        "flag_id": f.id,
                        "kind": h.kind,
                        "deal_impact": h.deal_impact,
                        "summary": text,
                    })
            if h.fee and h.fee.include_in_cashflow and fee_counts(f):
                fee_hooks.append({"flag_id": f.id, **payload})
                fee_key = (f.id, h.fee.kind)
                if fee_key in seen_fees:
                    continue
                seen_fees.add(fee_key)
                line = {
                    "id": h.id,
                    "flag_id": f.id,
                    "kind": h.fee.kind,
                    "label": h.summary or f.title,
                    "min_gbp": h.fee.min_gbp,
                    "max_gbp": h.fee.max_gbp,
                    "range_text": h.fee.range_text,
                    "term_years": h.fee.term_years,
                    "known": h.fee.known,
                    "currency": h.fee.currency,
                }
                capex_lines.append(line)

    # One licence per property: the estimate is the range across the licences
    # that could apply, not their sum.
    mins = [line["min_gbp"] for line in capex_lines if line["min_gbp"] is not None]
    maxes = [line["max_gbp"] for line in capex_lines if line["max_gbp"] is not None]
    any_known_fee = bool(mins or maxes)

    return {
        "level": level,
        "verdict": level,
        "killers": killers,
        "drivers": drivers,
        "fee_hooks": fee_hooks,
        "estimated_licence_fees_gbp": {
            "currency": "GBP",
            "min": min(mins) if mins else None,
            "max": max(maxes) if maxes else None,
            "known": any_known_fee,
            "basis": "one_licence",
            "note": (
                "A property needs one licence (HMO or selective), not several. "
                "The range covers whichever applies."
            ),
            "items": capex_lines,
        },
        "analyse_hooks": {
            "add_capex_lines": capex_lines,
            "add_risk_notes": risk_notes,
        },
    }


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
        impact = flag.deal_impact or flag.severity
        components.append(
            {
                "id": flag.id,
                "confidence": round(flag.confidence, 3),
                "confidence_band": confidence_band(flag.confidence),
                "applies": flag.applies,
                "severity": flag.severity,
                "deal_impact": impact,
                **fresh,
            }
        )
        if fresh.get("stale"):
            stale_ids.append(flag.id)
        if flag.applies in {"yes", "possible", "conditional"} and impact in {
            "deal_killer",
            "compliance_cost",
        }:
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
            "deal_killer/compliance_cost flags that apply, are possible, or are conditional. "
            "A stale scheme seed does not hide a high-confidence statutory flag — "
            "inspect components[]."
        ),
    }

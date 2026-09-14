"""Offline tests for the Metalyzi licensing checker (P0–P2).

No live HTTP: postcodes.io and planning.data.gov.uk are stubbed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from licensing.article4 import classify_hmo_relevance, ingest_article4_for_point
from licensing.engine import run_licensing_check
from licensing.geo import GeoError, normalise_postcode
from licensing.mandatory import england_mandatory_and_sui_generis_flags
from licensing.schemes import load_priority_schemes, match_schemes, schemes_meta

ROOT = Path(__file__).resolve().parent.parent

M14_POSTCODES_IO = {
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

OX1_POSTCODES_IO = {
    "status": 200,
    "result": {
        "postcode": "OX1 1BP",
        "quality": 1,
        "longitude": -1.2577,
        "latitude": 51.7520,
        "country": "England",
        "region": "South East",
        "admin_district": "Oxford",
        "admin_ward": "Osney & St Thomas",
        "outcode": "OX1",
        "incode": "1BP",
        "codes": {"admin_district": "E07000178"},
    },
}

EH1_POSTCODES_IO = {
    "status": 200,
    "result": {
        "postcode": "EH1 1YZ",
        "quality": 1,
        "longitude": -3.1883,
        "latitude": 55.9533,
        "country": "Scotland",
        "region": None,
        "admin_district": "City of Edinburgh",
        "admin_ward": "City Centre",
        "outcode": "EH1",
        "incode": "1YZ",
        "codes": {"admin_district": "S12000036"},
    },
}

OXFORD_ARTICLE4 = {
    "entities": [
        {
            "entity": 7010000999,
            "name": "Houses in Multiple Occupation Article 4 Direction",
            "reference": "HMOART4OXFORD",
            "notes": "This Article 4 Direction came into force on 25 February 2012.",
            "description": None,
            "permitted-development-rights": "3L",
            "start-date": "2012-02-25",
            "end-date": "",
            "entry-date": "2012-02-25",
            "organisation-entity": 1,
        }
    ],
    "count": 1,
}

EMPTY_ARTICLE4 = {"entities": [], "count": 0}


def _geo_stub(payload):
    def fetch(url: str):
        if "postcodes" in url and "M146LT" in url.replace(" ", ""):
            return payload if payload is M14_POSTCODES_IO else M14_POSTCODES_IO
        if "OX11BP" in url.replace(" ", "") or "OX1" in url:
            return OX1_POSTCODES_IO
        if "EH11YZ" in url.replace(" ", "") or "EH1" in url:
            return EH1_POSTCODES_IO
        raise GeoError("not found", code="postcode_not_found", http_status=404)

    # specialised per-payload fetcher
    def fetch_one(url: str):
        return payload

    return fetch_one


def _a4_stub(payload):
    def fetch(url, params):
        return payload

    return fetch


# ── Postcode parsing ────────────────────────────────────────────────────────

def test_normalise_postcode_accepts_loose_input():
    assert normalise_postcode("m14 6lt") == "M14 6LT"
    assert normalise_postcode("M146LT") == "M14 6LT"


def test_normalise_postcode_rejects_outward_only():
    with pytest.raises(GeoError) as exc:
        normalise_postcode("M14")
    assert exc.value.code == "invalid_postcode"


# ── Statutory England rules ─────────────────────────────────────────────────

def test_mandatory_hmo_applies_at_five_occupants_two_households():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=5, households=2, sharing_amenities=True, intended_use="hmo"
    )}
    assert flags["mandatory_hmo_licence"].applies == "yes"
    assert flags["mandatory_hmo_licence"].severity == "high"
    assert flags["mandatory_hmo_licence"].confidence >= 0.99
    assert "licence.mandatory_hmo" in flags["mandatory_hmo_licence"].analyse_hooks
    assert flags["sui_generis_hmo"].applies == "no"


def test_sui_generis_applies_at_seven_occupants():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=7, households=2, sharing_amenities=True, intended_use="hmo"
    )}
    assert flags["sui_generis_hmo"].applies == "yes"
    assert flags["sui_generis_hmo"].severity == "high"
    assert flags["planning_use_class"].applies == "yes"
    assert "planning.sui_generis" in flags["sui_generis_hmo"].analyse_hooks


def test_small_hmo_below_mandatory_threshold():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=4, households=2, sharing_amenities=True, intended_use="hmo"
    )}
    assert flags["mandatory_hmo_licence"].applies == "no"
    assert flags["planning_use_class"].id == "planning_use_class"


def test_missing_occupancy_is_conditional():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=None, households=None, sharing_amenities=None, intended_use="unknown"
    )}
    assert flags["mandatory_hmo_licence"].applies == "conditional"
    assert flags["sui_generis_hmo"].applies == "conditional"
    assert all(f.freshness and f.freshness.basis == "statutory" for f in flags.values())


def test_single_household_is_not_hmo():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=6, households=1, sharing_amenities=True, intended_use="btl"
    )}
    assert flags["mandatory_hmo_licence"].applies == "no"
    assert flags["sui_generis_hmo"].applies == "no"


# ── Article 4 classification ────────────────────────────────────────────────

def test_class_l_is_hmo_relevant():
    relevant, reason = classify_hmo_relevance({"permitted-development-rights": "3L", "name": "A4D01"})
    assert relevant is True
    assert "Class L" in reason


def test_fence_direction_is_not_hmo_relevant():
    relevant, _ = classify_hmo_relevance({
        "name": "Land at Fulmer",
        "notes": "means of enclosure",
        "permitted-development-rights": "2A",
    })
    assert relevant is False


def test_article4_ingest_classifies_oxford_hit():
    result = ingest_article4_for_point(51.75, -1.25, fetcher=_a4_stub(OXFORD_ARTICLE4))
    assert result.ok
    assert result.coverage == "partial_hit_hmo"
    assert result.hmo_hits[0].hmo_relevant is True
    assert result.hmo_hits[0].start_date == "2012-02-25"
    assert result.confidence >= 0.8


def test_article4_miss_is_partial_not_absence():
    result = ingest_article4_for_point(53.44, -2.22, fetcher=_a4_stub(EMPTY_ARTICLE4))
    assert result.ok
    assert result.coverage == "partial_miss"
    assert result.confidence <= 0.35


# ── Scheme seed ─────────────────────────────────────────────────────────────

def test_seed_has_about_25_priority_las():
    meta = schemes_meta()
    assert meta["la_count"] == 25
    assert meta["scheme_count"] >= 25
    schemes = load_priority_schemes()
    assert all(s.coverage.kind in {"citywide", "designated_areas", "unknown"} for s in schemes)
    # Never ship invented polygons
    for raw in json.loads((ROOT / "licensing/data/priority_schemes.json").read_text())["schemes"]:
        assert raw.get("coverage", {}).get("boundary_geojson") in (None, {})


def test_match_manchester_by_ons_code():
    hits = match_schemes(la_code="E08000003", la_name="Manchester")
    types = {h.scheme_type for h in hits}
    assert types == {"additional", "selective"}
    assert all(h.coverage.kind == "designated_areas" for h in hits)


def test_liverpool_citywide_selective():
    hits = match_schemes(la_code="E08000012", la_name="Liverpool")
    assert len(hits) == 1
    assert hits[0].scheme_type == "selective"
    assert hits[0].coverage.kind == "citywide"


# ── Full engine (stubbed I/O) ───────────────────────────────────────────────

def test_engine_manchester_hmo_flags_include_hooks_and_freshness():
    result = run_licensing_check(
        {"postcode": "M14 6LT", "occupants": 5, "households": 2, "intended_use": "hmo"},
        geo_fetcher=_geo_stub(M14_POSTCODES_IO),
        article4_fetcher=_a4_stub(EMPTY_ARTICLE4),
    )
    assert result["ok"] is True
    assert result["location"]["la_code"] == "E08000003"
    assert result["location"]["country"] == "England"
    flag_ids = {f["id"] for f in result["flags"]}
    assert "mandatory_hmo_licence" in flag_ids
    assert "additional_hmo_licence" in flag_ids
    assert "selective_licence" in flag_ids
    assert "article4_hmo" in flag_ids
    mandatory = next(f for f in result["flags"] if f["id"] == "mandatory_hmo_licence")
    assert mandatory["applies"] == "yes"
    assert mandatory["sources"]
    assert "licence.mandatory_hmo" in mandatory["analyse_hooks"]
    assert result["freshness"]["overall_confidence_band"] in {"high", "medium", "low", "unknown"}
    assert "components" in result["freshness"]
    # Partial miss must not claim "no Article 4"
    a4 = next(f for f in result["flags"] if f["id"] == "article4_hmo")
    assert a4["applies"] == "possible"
    assert "partial" in result["article4"]["coverage"]
    # Designated additional/selective must not claim address-level yes
    additional = next(f for f in result["flags"] if f["id"] == "additional_hmo_licence")
    assert additional["applies"] == "possible"
    assert additional["spatial_resolution"] == "named_areas_only"


def test_engine_oxford_article4_hit_and_citywide_additional():
    result = run_licensing_check(
        {"postcode": "OX1 1BP", "occupants": 4, "households": 2, "intended_use": "hmo"},
        geo_fetcher=_geo_stub(OX1_POSTCODES_IO),
        article4_fetcher=_a4_stub(OXFORD_ARTICLE4),
    )
    a4 = next(f for f in result["flags"] if f["id"] == "article4_hmo")
    assert a4["applies"] == "yes"
    assert a4["spatial_resolution"] == "point_in_polygon"
    additional = next(f for f in result["flags"] if f["id"] == "additional_hmo_licence")
    assert additional["applies"] == "yes"
    assert additional["spatial_resolution"] == "local_authority"
    mandatory = next(f for f in result["flags"] if f["id"] == "mandatory_hmo_licence")
    assert mandatory["applies"] == "no"


def test_engine_scotland_is_out_of_scope():
    result = run_licensing_check(
        {"postcode": "EH1 1YZ", "occupants": 5, "households": 2},
        geo_fetcher=_geo_stub(EH1_POSTCODES_IO),
        article4_fetcher=_a4_stub(EMPTY_ARTICLE4),
    )
    ids = {f["id"] for f in result["flags"]}
    assert "england_scope" in ids
    assert "mandatory_hmo_licence" not in ids
    assert result["schemes"]["matched"] == []


def test_engine_district_fallback_does_not_invent_polygons():
    def fallback(postcode):
        return {
            "is_article_4": True,
            "known": True,
            "council": "Manchester City Council",
            "note": "district index",
        }

    result = run_licensing_check(
        {"postcode": "M14 6LT"},
        geo_fetcher=_geo_stub(M14_POSTCODES_IO),
        article4_fetcher=_a4_stub(EMPTY_ARTICLE4),
        district_fallback=fallback,
    )
    district = next(f for f in result["flags"] if f["id"] == "article4_hmo_district_index")
    assert district["spatial_resolution"] == "postcode_district"
    assert district["applies"] == "possible"


def test_engine_rejects_missing_postcode():
    with pytest.raises(GeoError) as exc:
        run_licensing_check({})
    assert exc.value.code == "invalid_postcode"

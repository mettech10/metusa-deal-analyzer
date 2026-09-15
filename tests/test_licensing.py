"""Offline tests for the Metalyzi licensing checker (P0–P2).

No live HTTP: postcodes.io and planning.data.gov.uk are stubbed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from licensing import engine as engine_mod
from licensing.article4 import classify_hmo_relevance, ingest_article4_for_point
from licensing.engine import run_licensing_check
from licensing.geo import GeoError, normalise_postcode
from licensing.mandatory import england_mandatory_and_sui_generis_flags
from licensing.models import DISCLAIMER_VERSION, SCHEME_STALE_AFTER_DAYS_COVERED, SCHEME_STALE_AFTER_DAYS_PRIORITY
from licensing.schemes import _flag_for_scheme, load_priority_schemes, match_schemes, schemes_meta

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

CF10_POSTCODES_IO = {
    "status": 200,
    "result": {
        "postcode": "CF10 1EP",
        "quality": 1,
        "longitude": -3.1791,
        "latitude": 51.4816,
        "country": "Wales",
        "region": None,
        "admin_district": "Cardiff",
        "admin_ward": "Cathays",
        "outcode": "CF10",
        "incode": "1EP",
        "codes": {"admin_district": "W06000015"},
    },
}

L1_POSTCODES_IO = {
    "status": 200,
    "result": {
        "postcode": "L1 8JQ",
        "quality": 1,
        "longitude": -2.9916,
        "latitude": 53.4084,
        "country": "England",
        "region": "North West",
        "admin_district": "Liverpool",
        "admin_ward": "City Centre South",
        "outcode": "L1",
        "incode": "8JQ",
        "codes": {"admin_district": "E08000012"},
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
    def fetch_one(url: str):
        return payload

    return fetch_one


def _a4_stub(payload):
    def fetch(url, params):
        return payload

    return fetch


def _hook_ids(flag) -> list[str]:
    hooks = flag["analyse_hooks"] if isinstance(flag, dict) else flag.analyse_hooks
    ids = []
    for h in hooks:
        if isinstance(h, dict):
            ids.append(h["id"])
        elif hasattr(h, "id"):
            ids.append(h.id)
        else:
            ids.append(h)
    return ids


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
        occupants=5, households=2, sharing_amenities=True, intended_use="hmo",
        purpose_built_flat_in_block_of_3_plus=False,
    )}
    assert flags["mandatory_hmo_licence"].applies == "yes"
    assert flags["mandatory_hmo_licence"].severity == "deal_killer"
    assert flags["mandatory_hmo_licence"].confidence >= 0.99
    assert "licence.mandatory_hmo" in _hook_ids(flags["mandatory_hmo_licence"])
    assert "cost.hmo_licence_fee" in _hook_ids(flags["mandatory_hmo_licence"])
    assert flags["sui_generis_hmo"].applies == "no"


def test_purpose_built_flat_block_carve_out():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=5, households=2, sharing_amenities=True, intended_use="hmo",
        purpose_built_flat_in_block_of_3_plus=True,
    )}
    assert flags["mandatory_hmo_licence"].applies == "no"
    assert flags["mandatory_hmo_licence"].severity == "info"
    assert "mhclg" in flags["mandatory_hmo_licence"].summary.lower()
    assert "purpose-built" in flags["mandatory_hmo_licence"].summary.lower()


def test_purpose_built_flat_via_block_count():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=6, households=2, sharing_amenities=True, intended_use="hmo",
        purpose_built_flat=True,
        self_contained_flats_in_block=4,
    )}
    assert flags["mandatory_hmo_licence"].applies == "no"


def test_purpose_built_flat_miss_when_block_too_small():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=5, households=2, sharing_amenities=True, intended_use="hmo",
        purpose_built_flat=True,
        self_contained_flats_in_block=2,
    )}
    assert flags["mandatory_hmo_licence"].applies == "yes"
    assert flags["mandatory_hmo_licence"].severity == "deal_killer"


def test_purpose_built_flat_via_flats_in_block_kwarg():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=5, households=2, sharing_amenities=True, intended_use="hmo",
        purpose_built_flat=True,
        flats_in_block=3,
    )}
    assert flags["mandatory_hmo_licence"].applies == "no"
    assert "mhclg" in flags["mandatory_hmo_licence"].summary.lower()


def test_purpose_built_flat_without_block_count_is_conditional():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=5, households=2, sharing_amenities=True, intended_use="hmo",
        purpose_built_flat=True,
    )}
    assert flags["mandatory_hmo_licence"].applies == "conditional"
    assert flags["mandatory_hmo_licence"].severity == "compliance_cost"
    assert "mhclg" in flags["mandatory_hmo_licence"].summary.lower()


def test_sui_generis_applies_at_seven_occupants():
    flags = {f.id: f for f in england_mandatory_and_sui_generis_flags(
        occupants=7, households=2, sharing_amenities=True, intended_use="hmo"
    )}
    assert flags["sui_generis_hmo"].applies == "yes"
    assert flags["sui_generis_hmo"].severity == "deal_killer"
    assert flags["planning_use_class"].applies == "yes"
    assert "planning.sui_generis" in _hook_ids(flags["sui_generis_hmo"])


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
    load_priority_schemes.cache_clear()
    meta = schemes_meta()
    assert meta["la_count"] == 25
    assert len(meta["priority_las"]) == 25
    codes = {row["la_code"] for row in meta["priority_las"]}
    assert "E08000006" in codes  # Salford
    assert "E09000033" in codes  # Westminster
    assert "E07000178" not in codes  # Oxford swapped out
    schemes = load_priority_schemes()
    assert all(s.la_code.startswith("E") for s in schemes)
    assert all(s.coverage.kind in {"citywide", "designated_areas", "unknown"} for s in schemes)
    for raw in json.loads((ROOT / "licensing/data/priority_schemes.json").read_text())["schemes"]:
        assert raw.get("coverage", {}).get("boundary_geojson") in (None, {})
        assert raw.get("coverage_tier") == "priority"


def test_match_manchester_by_ons_code():
    load_priority_schemes.cache_clear()
    hits = match_schemes(la_code="E08000003", la_name="Manchester")
    types = {h.scheme_type for h in hits}
    assert types == {"additional", "selective"}
    assert all(h.coverage.kind == "designated_areas" for h in hits)
    assert hits[0].stale_after_days() == SCHEME_STALE_AFTER_DAYS_PRIORITY


def test_covered_slo_is_90_days_not_365():
    assert SCHEME_STALE_AFTER_DAYS_PRIORITY == 30
    assert SCHEME_STALE_AFTER_DAYS_COVERED == 90


def test_stale_priority_scheme_is_soft_warning():
    from dataclasses import replace

    hits = match_schemes(la_code="E08000012", la_name="Liverpool")
    assert hits
    scheme = replace(hits[0], last_verified_at="2020-01-01T00:00:00Z")
    flag = _flag_for_scheme(scheme, occupants=3, rentalish=True, admin_ward=None)
    assert flag.freshness and flag.freshness.stale is True
    assert flag.freshness.stale_after_days == SCHEME_STALE_AFTER_DAYS_PRIORITY
    assert flag.severity == "soft_warning"
    assert flag.to_dict()["severity_class"] == "soft_warning"


def test_liverpool_citywide_selective():
    hits = match_schemes(la_code="E08000012", la_name="Liverpool")
    assert len(hits) == 1
    assert hits[0].scheme_type == "selective"
    assert hits[0].coverage.kind == "citywide"


def test_wales_la_code_never_matches_seed():
    assert match_schemes(la_code="W06000015", la_name="Cardiff") == []


# ── Full engine (stubbed I/O) ───────────────────────────────────────────────

def test_engine_manchester_hmo_flags_include_hooks_and_freshness():
    result = run_licensing_check(
        {"postcode": "M14 6LT", "occupants": 5, "households": 2, "intended_use": "hmo"},
        geo_fetcher=_geo_stub(M14_POSTCODES_IO),
        article4_fetcher=_a4_stub(EMPTY_ARTICLE4),
    )
    assert result["ok"] is True
    assert result["disclaimer"]["version"] == DISCLAIMER_VERSION
    assert result["deal_impact"]["level"] in {"deal_killer", "compliance_cost", "soft_warning", "info"}
    assert result["location"]["la_code"] == "E08000003"
    flag_ids = {f["id"] for f in result["flags"]}
    assert "mandatory_hmo_licence" in flag_ids
    assert "additional_hmo_licence" in flag_ids
    assert "selective_licence" in flag_ids
    assert "article4_hmo" in flag_ids
    mandatory = next(f for f in result["flags"] if f["id"] == "mandatory_hmo_licence")
    assert mandatory["applies"] == "yes"
    assert mandatory["severity"] == "deal_killer"
    assert mandatory["deal_impact"] == "deal_killer"
    assert "licence.mandatory_hmo" in _hook_ids(mandatory)
    fee_hook = next(h for h in mandatory["analyse_hooks"] if h["id"] == "cost.hmo_licence_fee")
    assert fee_hook["fee"]["include_in_cashflow"] is True
    additional = next(f for f in result["flags"] if f["id"] == "additional_hmo_licence")
    assert additional["applies"] == "possible"
    assert additional["spatial_resolution"] == "named_areas_only"
    assert additional["freshness"]["stale_after_days"] == 30
    assert additional["severity_class"] == "soft_warning"
    sel_fee = next(h for h in additional["analyse_hooks"] if h["id"] == "cost.hmo_licence_fee")
    assert sel_fee["fee"]["range_text"]
    assert "severity_class" in mandatory
    impact = result["deal_impact"]
    assert impact["verdict"] == impact["level"]
    assert isinstance(impact["killers"], list)
    assert any(k["flag_id"] == "mandatory_hmo_licence" for k in impact["killers"])
    assert "add_capex_lines" in impact["analyse_hooks"]
    assert "add_risk_notes" in impact["analyse_hooks"]
    assert isinstance(impact["estimated_licence_fees_gbp"], dict)


def test_engine_flats_in_block_alias_carve_out():
    result = run_licensing_check(
        {
            "postcode": "M14 6LT",
            "occupants": 5,
            "households": 2,
            "intended_use": "hmo",
            "purpose_built_flat": True,
            "flats_in_block": 8,
        },
        geo_fetcher=_geo_stub(M14_POSTCODES_IO),
        article4_fetcher=_a4_stub(EMPTY_ARTICLE4),
    )
    mandatory = next(f for f in result["flags"] if f["id"] == "mandatory_hmo_licence")
    assert mandatory["applies"] == "no"
    assert result["inputs"]["flats_in_block"] == 8
    assert result["inputs"]["self_contained_flats_in_block"] == 8


def test_engine_conversion_from_c3_makes_article4_deal_killer():
    result = run_licensing_check(
        {
            "postcode": "OX1 1BP",
            "occupants": 4,
            "households": 2,
            "intended_use": "hmo",
            "conversion_from_c3": True,
        },
        geo_fetcher=_geo_stub(OX1_POSTCODES_IO),
        article4_fetcher=_a4_stub(OXFORD_ARTICLE4),
    )
    a4 = next(f for f in result["flags"] if f["id"] == "article4_hmo")
    assert a4["applies"] == "yes"
    assert a4["severity"] == "deal_killer"
    assert a4["spatial_resolution"] == "point_in_polygon"
    assert result["inputs"]["conversion_from_c3"] is True
    # Oxford was swapped out of the priority seed
    assert "additional_hmo_licence" not in {f["id"] for f in result["flags"]}


def test_engine_conversion_from_c3_false_is_not_a_blocker():
    result = run_licensing_check(
        {"postcode": "OX1 1BP", "conversion_from_c3": False, "intended_use": "hmo"},
        geo_fetcher=_geo_stub(OX1_POSTCODES_IO),
        article4_fetcher=_a4_stub(OXFORD_ARTICLE4),
    )
    a4 = next(f for f in result["flags"] if f["id"] == "article4_hmo")
    assert a4["severity"] == "info"
    assert "blocker.planning_permission" not in _hook_ids(a4)


def test_engine_conversion_from_c3_elevates_possible_district_article4():
    def fallback(_postcode):
        return {
            "is_article_4": True,
            "known": True,
            "council": "Manchester City Council",
            "note": "district index",
        }

    result = run_licensing_check(
        {"postcode": "M14 6LT", "intended_use": "hmo", "conversion_from_c3": True},
        geo_fetcher=_geo_stub(M14_POSTCODES_IO),
        article4_fetcher=_a4_stub(EMPTY_ARTICLE4),
        district_fallback=fallback,
    )
    district = next(f for f in result["flags"] if f["id"] == "article4_hmo_district_index")
    assert district["applies"] == "possible"
    assert district["deal_impact"] == "deal_killer"
    assert district["severity_class"] == "deal_killer"


def test_engine_liverpool_citywide_selective_fee_hook():
    result = run_licensing_check(
        {"postcode": "L1 8JQ", "occupants": 3, "households": 2, "intended_use": "btl"},
        geo_fetcher=_geo_stub(L1_POSTCODES_IO),
        article4_fetcher=_a4_stub(EMPTY_ARTICLE4),
    )
    sel = next(f for f in result["flags"] if f["id"] == "selective_licence")
    assert sel["applies"] == "yes"
    assert sel["severity"] == "compliance_cost"
    fee = next(h for h in sel["analyse_hooks"] if h["id"] == "cost.selective_licence_fee")
    assert fee["fee"]["known"] is True
    assert fee["fee"]["min_gbp"] == 400


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
    assert result["disclaimer"]["version"] == DISCLAIMER_VERSION


def test_engine_wales_does_not_use_legacy_lookup():
    result = run_licensing_check(
        {"postcode": "CF10 1EP", "occupants": 5, "households": 2, "intended_use": "hmo"},
        geo_fetcher=_geo_stub(CF10_POSTCODES_IO),
        article4_fetcher=_a4_stub(EMPTY_ARTICLE4),
    )
    assert result["location"]["country"] == "Wales"
    assert result["schemes"]["matched"] == []
    assert {f["id"] for f in result["flags"]} == {"england_scope"}


def test_engine_ignores_licensing_lookup_shaped_fallback():
    def poison(_postcode):
        return {
            "tier": "additional",
            "scope": "Wales Rent Smart Wales",
            "rent_smart_wales": "must register",
            "known": True,
            "is_article_4": True,
        }

    result = run_licensing_check(
        {"postcode": "M14 6LT"},
        geo_fetcher=_geo_stub(M14_POSTCODES_IO),
        article4_fetcher=_a4_stub(EMPTY_ARTICLE4),
        district_fallback=poison,
    )
    assert "article4_hmo_district_index" not in {f["id"] for f in result["flags"]}


def test_engine_source_does_not_import_legacy_lookup():
    assert "app" not in engine_mod.__dict__
    assert not hasattr(engine_mod, "HMO_LICENSING_LOOKUP")
    assert not hasattr(engine_mod, "get_hmo_licensing_info")
    # No runtime import of the Flask app module
    assert all(not name.startswith("app") for name in engine_mod.__dict__ if name != "__doc__")


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


def test_canonical_severity_maps_legacy_high_medium_low():
    from licensing.models import canonical_severity

    assert canonical_severity("high", category="planning") == "deal_killer"
    assert canonical_severity("high", category="licensing") == "compliance_cost"
    assert canonical_severity("medium") == "compliance_cost"
    assert canonical_severity("low") == "info"
    assert canonical_severity("deal_killer") == "deal_killer"


def test_engine_rejects_missing_postcode():
    with pytest.raises(GeoError) as exc:
        run_licensing_check({})
    assert exc.value.code == "invalid_postcode"

# Metalyzi Licensing Checker (P0–P2)

Backend foundations for **England** HMO / planning licensing checks.

- **Endpoint:** `POST /v1/licensing/check`
- **Feature flag:** `licensing_checker_v1` (`LICENSING_CHECKER_V1`, default on)
- **Out of scope:** UPRN (P4), CON29, Wales / Scotland / NI rule engines, any other Metalyzi module

This is a **flags + confidence** API. It does not give legal advice. Absence of a
hit is never treated as “no restriction” unless a national statutory rule says so.

Every check response (including errors) includes a versioned `disclaimer`.

Legacy `HMO_LICENSING_LOOKUP` / `get_hmo_licensing_info` in `app.py` **cannot**
override this endpoint. Those tables include Wales and Scotland rows and are
area-analysis context only.

## Request

```http
POST /v1/licensing/check
Content-Type: application/json
```

```json
{
  "postcode": "M14 6LT",
  "occupants": 5,
  "households": 2,
  "sharing_amenities": true,
  "intended_use": "hmo",
  "conversion_from_c3": true,
  "purpose_built_flat_in_block_of_3_plus": false
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `postcode` | yes | Full UK postcode. Outward-only and UPRN are rejected. |
| `occupants` | no | Headcount. If omitted, occupancy flags are `conditional`. |
| `households` | no | Housing Act household count. |
| `sharing_amenities` | no | Boolean. |
| `intended_use` | no | `hmo` \| `btl` \| `sa` \| `str` \| `rental` \| `unknown` |
| `conversion_from_c3` | no | `true` = C3→C4 conversion play (Article 4 is a deal killer on hit). `false` = continued use. |
| `purpose_built_flat_in_block_of_3_plus` | no | Mandatory HMO carve-out when true. |
| `purpose_built_flat` + `self_contained_flats_in_block` / `flats_in_block` | no | Alternative carve-out (`flats_in_block >= 3`). |
| `skip_article4` | no | Test hook. Skip planning.data.gov.uk. |

## Response (shape)

`disclaimer.version` is `licensing-checker-disclaimer-v1`.

`severity` is kept for FE compatibility (taxonomy values). `severity_class` is
`deal_killer` | `compliance_cost` | `soft_warning` | `info`. Legacy
`high`/`medium`/`low` values are mapped: `high` → `deal_killer` (planning/scope)
or `compliance_cost` (other); `medium` → `compliance_cost`; `low` → `info`.
Stale or partial (`applies` possible/conditional) flags emit
`severity_class=soft_warning` unless they are already a `deal_killer` (Article 4
conversion plays stay elevated). Stale scheme seeds also set `freshness.stale=true`.

Per-flag `analyse_hooks` are objects, not string tags. Top-level `deal_impact`
also carries structured Analyse hooks:

```json
{
  "level": "deal_killer",
  "verdict": "deal_killer",
  "killers": [{"flag_id": "mandatory_hmo_licence", "title": "...", "summary": "...", "applies": "yes"}],
  "estimated_licence_fees_gbp": {"currency": "GBP", "min": 400, "max": 650, "known": true, "items": []},
  "analyse_hooks": {
    "add_capex_lines": [{"id": "cost.selective_licence_fee", "min_gbp": 400, "max_gbp": 650}],
    "add_risk_notes": [{"id": "blocker.unlicensed_hmo", "deal_impact": "deal_killer"}]
  }
}
```

Per-flag hook example:

```json
{
  "id": "cost.hmo_licence_fee",
  "kind": "cost",
  "deal_impact": "compliance_cost",
  "fee": {
    "kind": "hmo_licence",
    "include_in_cashflow": true,
    "range_text": "£700-£1,300",
    "min_gbp": 700,
    "max_gbp": 1300,
    "term_years": 5,
    "known": true
  }
}
```

`applies` is one of `yes` | `no` | `possible` | `conditional`.

`overall_confidence` is the **minimum** confidence among the location lookup and
every `deal_killer` / `compliance_cost` flag that is `yes`, `possible`, or
`conditional`. Inspect `freshness.components[]`.

## What each layer does

### 1. Postcode → local authority

[postcodes.io](https://postcodes.io) (ONSPD). Returns ONS `la_code`, coordinates, country, ward name.

### 2. Mandatory HMO + sui generis (England statute)

| Rule | Trigger | Flag |
| --- | --- | --- |
| Mandatory HMO licence | 5+ people, 2+ households, shared amenities | `mandatory_hmo_licence` `deal_killer` |
| **Carve-out** | Purpose-built flat in a block of 3+ self-contained flats (`purpose_built_flat` + `flats_in_block>=3`) | `applies: no`. If purpose-built but block size unknown: `conditional` citing MHCLG. Additional/selective may still apply. |
| Planning C4 | 3–6 residents, not a single household | `planning_use_class` |
| Sui generis HMO | 7+ residents | `sui_generis_hmo` `deal_killer` |

Non-England postcodes return `england_scope` and stop. They do not apply English
rules and do not consult `HMO_LICENSING_LOOKUP`.

### 3. Article 4 ingest (partial)

Live point query against planning.data.gov.uk `article-4-direction-area`.

`conversion_from_c3=true` (or `intended_use=hmo` when the flag is omitted) treats
an HMO Class L hit as a conversion **deal_killer**. `conversion_from_c3=false`
keeps the hit as information for continued use.

A miss is `applies: possible`, never “no Article 4”.

### 4. Additional / selective schemes (25 priority LAs)

[`licensing/data/priority_schemes.json`](../licensing/data/priority_schemes.json).

Stale SLO: **30 days** for `coverage_tier=priority`, **90 days** for `covered`.

Join key: ONS `la_code` starting with `E`. Wales/Scotland/NI codes are discarded.

- `citywide` → `applies: yes` (medium confidence; seed is not a live scrape)
- `designated_areas` → `applies: possible`, named areas only, no polygons
- `unknown` placeholder → `priority_la_uncurated`
- Unseeded LA → `local_schemes_unseeded`

Inventory: `GET /v1/licensing/schemes` (same feature flag).

## Feature flag

`LICENSING_CHECKER_V1=false` → HTTP 404 `feature_disabled` (disclaimer still present).

## Errors

| HTTP | `error.code` |
| --- | --- |
| 400 | `invalid_postcode`, `invalid_input`, `invalid_json`, `invalid_content_type` |
| 404 | `postcode_not_found`, `feature_disabled` |
| 413 | `payload_too_large` |
| 429 | rate limit (30/min) |
| 502 | `geo_upstream_error`, `geo_incomplete` |

## Tests

```bash
pytest tests/test_licensing.py tests/test_licensing_api.py -v
```

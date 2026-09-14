# Metalyzi Licensing Checker (P0–P2)

Backend foundations for **England** HMO / planning licensing checks.

- **Endpoint:** `POST /v1/licensing/check`
- **Out of scope:** UPRN (P4), CON29, Wales / Scotland / NI rule engines, any other Metalyzi module

This is a **flags + confidence** API. It does not give legal advice. Absence of a
hit is never treated as “no restriction” unless a national statutory rule says so.

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
  "intended_use": "hmo"
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `postcode` | yes | Full UK postcode. Outward-only and UPRN are rejected. |
| `occupants` | no | Headcount. If omitted, occupancy flags are `conditional`. |
| `households` | no | Housing Act household count. |
| `sharing_amenities` | no | Boolean. Default assumed true only when occupancy is supplied for mandatory tests. |
| `intended_use` | no | `hmo` \| `btl` \| `sa` \| `str` \| `rental` \| `unknown` |
| `skip_article4` | no | Test hook. Skip planning.data.gov.uk. |

## Response (shape)

```json
{
  "ok": true,
  "api_version": "v1",
  "checked_at": "2026-09-14T20:00:00Z",
  "scope": {
    "nation": "England",
    "modules": ["postcode_to_la", "mandatory_hmo", "sui_generis", "article4_planning_data", "additional_selective_schemes"],
    "exclusions": ["uprn", "con29", "wales", "scotland", "northern_ireland"]
  },
  "location": {
    "postcode": "M14 6LT",
    "la_name": "Manchester",
    "la_code": "E08000003",
    "country": "England",
    "confidence": 0.95,
    "freshness": {"last_verified_at": "...", "stale": false, "basis": "live_lookup"}
  },
  "freshness": {
    "overall_confidence": 0.45,
    "overall_confidence_band": "low",
    "stale": false,
    "stale_components": [],
    "components": []
  },
  "flags": [
    {
      "id": "mandatory_hmo_licence",
      "category": "licensing",
      "severity": "high",
      "applies": "yes",
      "confidence": 0.99,
      "confidence_band": "high",
      "sources": [{"name": "Housing Act 2004 Part 2", "kind": "legislation", "url": "..."}],
      "analyse_hooks": ["licence.mandatory_hmo", "cost.hmo_licence_fee"],
      "last_verified_at": "2018-10-01T00:00:00+00:00",
      "freshness": {"stale": false, "basis": "statutory"}
    }
  ],
  "article4": {},
  "schemes": {},
  "warnings": []
}
```

`applies` is one of `yes` | `no` | `possible` | `conditional`.

`overall_confidence` is the **minimum** confidence among the location lookup and
every high/medium flag that is `yes`, `possible`, or `conditional`. Inspect
`freshness.components[]` rather than treating the headline number as a pass/fail.

## What each layer does

### 1. Postcode → local authority

[postcodes.io](https://postcodes.io) (ONS Postcode Directory). Returns `la_code`
(ONS admin district), coordinates, country, ward name.

Ward name is a **label** for curator hints. It is not a spatial join.

### 2. Mandatory HMO + sui generis (England statute)

| Rule | Trigger | Flag |
| --- | --- | --- |
| Mandatory HMO licence | 5+ people, 2+ households, shared amenities (2018 Order; no storey test) | `mandatory_hmo_licence` |
| Planning C4 | 3–6 residents, not a single household | `planning_use_class` |
| Sui generis HMO | 7+ residents | `sui_generis_hmo` |

C3 → C4 is permitted development (GPDO Part 3 Class L) unless Article 4 removes it.
C3/C4 → sui generis is **never** PD.

Non-England postcodes return `england_scope` and stop. They do not apply English rules.

### 3. Article 4 ingest (partial)

Live point query:

`GET https://www.planning.data.gov.uk/entity.json?latitude=…&longitude=…&dataset=article-4-direction-area`

HMO relevance is classified from `permitted-development-rights` (Class L / `3L`)
and text (HMO / C3–C4). The MHCLG dataset is **beta and incomplete**. A miss is
`applies: possible` with low confidence, never “no Article 4”.

Optional corroboration: the existing in-repo postcode-district index
(`check_article_4` in `app.py`) is attached as `article4_hmo_district_index`
with `spatial_resolution: postcode_district`. That is not a legal boundary.

Offline helper (does not save geometries):

```bash
python scripts/ingest_article4.py OX1 1BP
```

### 4. Additional / selective schemes (~25 priority LAs)

Curated JSON: [`licensing/data/priority_schemes.json`](../licensing/data/priority_schemes.json).
Editor guide: [`licensing/data/README.md`](../licensing/data/README.md).

- Join key: ONS `la_code`.
- `citywide` → `applies: yes` (still medium confidence; seed is not a live scrape).
- `designated_areas` → `applies: possible`, **no polygons**, named areas only.
- Unseeded LA → `local_schemes_unseeded` (`possible`, low confidence).

Inventory: `GET /v1/licensing/schemes`.

## `analyse_hooks`

Stable IDs for the deal-analyse pipeline (P3+ wiring, not implemented here):

| Hook | Meaning |
| --- | --- |
| `licence.mandatory_hmo` | Mandatory HMO licence in play |
| `licence.additional_hmo` | Additional scheme may apply |
| `licence.selective` | Selective scheme may apply |
| `planning.c3_to_c4` | Small HMO planning route |
| `planning.sui_generis` | Large HMO planning permission |
| `planning.article4_hmo` | Article 4 may remove C3→C4 PD |
| `cost.hmo_licence_fee` | Include licence fee in cashflow |
| `cost.selective_licence_fee` | Include selective fee |
| `blocker.planning_permission` | Planning is a conversion blocker |
| `blocker.unlicensed_hmo` | Operating without a mandatory licence |
| `verify.lpa` | Confirm with the local authority |
| `verify.scheme_boundary` | Need official map / geometry |
| `analyse.need_occupancy` | Ask the user for occupants / households |
| `scope.not_england` | Do not apply England rules |

## Confidence bands

| Band | Score |
| --- | --- |
| high | ≥ 0.85 |
| medium | ≥ 0.55 |
| low | ≥ 0.30 |
| unknown | < 0.30 |

Typical values: statute 0.99, postcodes.io quality-1 0.95, Planning Data HMO hit
0.80, citywide curated scheme ~0.62, designated-area seed ~0.45, Planning Data
miss 0.30.

Scheme seeds go stale after 365 days (`last_verified_at`). Statutory flags never
stale. Live geo / Article 4 lookups use the check timestamp.

## Errors

| HTTP | `error.code` |
| --- | --- |
| 400 | `invalid_postcode`, `invalid_input`, `invalid_json`, `invalid_content_type` |
| 404 | `postcode_not_found` |
| 413 | `payload_too_large` |
| 429 | rate limit (30/min) |
| 502 | `geo_upstream_error`, `geo_incomplete` |

## Tests

```bash
pytest tests/test_licensing.py tests/test_licensing_api.py -v
```

Tests are offline (stubbed postcodes.io + planning.data.gov.uk).

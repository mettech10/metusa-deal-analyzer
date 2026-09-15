# Priority licensing scheme seed

This JSON file is the **curator-facing** register of additional and selective
licensing schemes for **25 priority English local authorities**.

It is **not** a spatial dataset. Runtime `/v1/licensing/check` never reads
`HMO_LICENSING_LOOKUP` in `app.py` (that table includes Wales/Scotland rows).

## Priority set (v2)

Birmingham, Manchester, Salford, Leeds, Nottingham, Liverpool, Sheffield,
Bristol, Newcastle upon Tyne, Leicester, Coventry, Bradford, Newham, Brent,
Waltham Forest, Haringey, Hackney, Tower Hamlets, Croydon, Ealing, Southwark,
Lambeth, Westminster, Camden, Islington.

Swaps vs v1 seed (curator note): dropped Oxford, Cambridge, Reading, Brighton
and Hove, York, Hull, Enfield; added Salford, Leicester, Croydon, Ealing,
Westminster, Camden, Islington as **unknown placeholders** until designation
orders are curated.

## Rules for editors

1. Match `la_code` to the ONS local authority district code (`E06…` / `E07…` / `E08…` / `E09…` only — never `W`/`S`/`N`).
2. `scheme_type` is `additional`, `selective`, or `unknown` (placeholder).
3. `coverage_tier`: `priority` (30-day stale SLO) or `covered` (90-day SLO).
4. `coverage.kind`: `citywide` | `designated_areas` | `unknown`.
5. **Never invent boundaries.** `boundary_geojson` stays null.
6. If you do not have the ward list, leave `named_areas` empty.
7. Update `last_verified_at` when you actually check the council page.
8. A missing or `unknown` row is **not** “no scheme”.

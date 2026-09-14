# Priority licensing scheme seed

This JSON file is the **curator-facing** register of additional and selective
licensing schemes for ~25 priority English local authorities.

It is **not** a spatial dataset.

## Rules for editors

1. Match `la_code` to the ONS local authority district code (`E09…` / `E08…` / `E07…` / `E06…`).
   That is the join key used by `/v1/licensing/check` after postcodes.io resolution.
2. `scheme_type` is `additional` or `selective` (one row per scheme).
3. `coverage.kind`:
   - `citywide` — the published designation is the whole LA.
   - `designated_areas` — only some areas. Put **published names** in `named_areas`.
   - `unknown` — a scheme exists but coverage is not clear enough to say either.
4. **Never invent boundaries.** Leave any future `boundary_geojson` null until an
   official geometry (LPA GeoJSON / designation map) is attached. Named wards are
   labels, not polygons.
5. If you do not have the ward list, leave `named_areas` empty. An empty list with
   `kind: designated_areas` is honest; a guessed list is not.
6. Update `last_verified_at` (ISO-8601 UTC) and `verification_method` when you
   actually check the council page / designation order.
7. Keep `confidence` ≤ 0.70 for curated rows. Live statute and point-in-polygon
   Article 4 hits are allowed to go higher in the API; seeds are not.
8. A missing LA is **not** “no scheme”. The API emits `local_schemes_unseeded`.

## Fields

| Field | Required | Notes |
| --- | --- | --- |
| `la_code` | yes | ONS code |
| `la_name` | yes | Display name; code wins on match |
| `scheme_type` | yes | `additional` \| `selective` |
| `status` | yes | `active` \| `expired` \| `proposed` \| `unknown` |
| `coverage` | yes | See rules above |
| `confidence` | yes | 0–1 |
| `last_verified_at` | yes | ISO timestamp |
| `sources` | yes | At least one URL or note |

Optional: `occupants_threshold`, `term_years`, `start_date`, `end_date`,
`fee_range`, `curator_notes`, `verification_method`.

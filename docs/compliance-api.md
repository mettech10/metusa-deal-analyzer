# Compliance Cockpit MVP — Flask `/v1/compliance`

Auth matches user-data APIs: `Authorization: Bearer <supabase access token>`.
Local tests use `X-User-Id`. Reminder dispatch uses `X-Cron-Secret`
(same pattern as `/api/benchmarks/update`).

Catalogue codes: `GAS`, `EICR`, `EPC`, `DEP`, `HTR`, `LIC_HMO`, `LIC_SEL`.
Status engine: `valid` | `due_soon` | `overdue` (due-soon window = 90 days).
Reminders: T-90, T-60, T-30, T-14, T-7, T-0, overdue (+1 day), then **weekly
while still overdue**. Backend seeds `channel=email`. `channel=in_app` is a
supported stub value for the frontend; dispatch does not email those rows.

## Email (Brevo)

Same secrets as `lib/brevo-email.ts`. Set them on the **Flask** service
(Render), not only Vercel:

| Secret | Required | Default |
|---|---|---|
| `BREVO_API_KEY` | to actually send | — (dispatch skip-sends fail-soft) |
| `BREVO_SENDER_EMAIL` | no | `noreply@metalyzi.co.uk` |
| `BREVO_REPLY_TO_EMAIL` | no | sender |

Recipient is the Supabase Auth email for the obligation's `userId`. Missing
key or missing recipient logs a warning, marks the stub `skipped`, and still
queues the next weekly overdue ping.

Email CTAs open the FE cockpit at `/tools/compliance` (with
`?propertyId=` when the obligation has one). That is a **frontend** path —
Flask APIs stay under `/v1/compliance/*` and do not need renaming for
obligations, dashboard, or reminders.

## API routes (FE)

No route renames. The Next.js page is `/tools/compliance`; the backend is:

| Method | Path |
|---|---|
| GET | `/v1/compliance/catalogue` (`items` and `catalogue` are the same list) |
| GET | `/v1/compliance/dashboard` |
| GET/POST | `/v1/compliance/obligations` |
| GET/PATCH/DELETE | `/v1/compliance/obligations/<id>` |
| GET | `/v1/compliance/properties/<propertyId>/obligations` |
| GET | `/v1/compliance/reminders` |
| POST | `/v1/compliance/reminders/dispatch` (cron) |

## Evidence storage (tenant isolation)

| | |
|---|---|
| Bucket | `compliance-evidence` (private, 10MB, pdf/jpeg/png/webp) |
| Key prefix | `{userId}/{obligationId}/{evidenceId}_{filename}` |
| RLS | `storage.foldername(name)[1] = auth.uid()` |
| API | Flask uses the service role but **refuses** keys outside `{userId}/` |

There is no other user-file blob store in this repo (PDF analyse upload is
ephemeral). This prefix is the tenant-isolation pattern for compliance
evidence; it matches the first-folder-equals-uid convention used in the
storage policies.

Local fallback: `uploads/compliance/{userId}/...` (`COMPLIANCE_UPLOAD_DIR`).

```bash
BASE=http://localhost:5002
TOKEN="YOUR_SUPABASE_ACCESS_TOKEN"
PROP="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

# Catalogue (public) — includes channels + overdueWeeklyDays
curl -s "$BASE/v1/compliance/catalogue" | jq .

# Create a Gas Safe certificate (expiry auto-derived +1 year)
curl -s -X POST "$BASE/v1/compliance/obligations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"propertyId\":\"$PROP\",\"code\":\"GAS\",\"issuedOn\":\"2026-01-01\"}" | jq .

# List by property + computed status
curl -s "$BASE/v1/compliance/properties/$PROP/obligations" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Dashboard counts
curl -s "$BASE/v1/compliance/dashboard?propertyId=$PROP" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Upload evidence (JSON base64; multipart `file` also works)
curl -s -X POST "$BASE/v1/compliance/obligations/<OBLIGATION_ID>/evidence" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"filename":"gas.pdf","contentType":"application/pdf","dataBase64":"JVBERi0x"}' | jq .

# in_app stubs for the FE (not emailed by dispatch)
curl -s "$BASE/v1/compliance/reminders?channel=in_app&status=pending" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Cron: process due email stubs (Brevo if keyed; else skip + weekly re-queue)
curl -s -X POST "$BASE/v1/compliance/reminders/dispatch" \
  -H "X-Cron-Secret: $COMPLIANCE_CRON_SECRET" | jq .
```

## Metalyzi live checklist (P0 2026-09-21)

`GET /v1/compliance/catalogue` is public. Dashboard and property files are
not — they need a user JWT **and** `compliance_*` tables.

Render env (do not invent values; copy from the existing Supabase project):

| Key | Why |
|---|---|
| `SUPABASE_URL` or `NEXT_PUBLIC_SUPABASE_URL` | Auth + PostgREST. **Same project** as Vercel `NEXT_PUBLIC_SUPABASE_URL`. Health `auth.supabaseHost` must be `lftlugydvvcjtujalzwh.supabase.co` (cookie `sb-lftlugydvvcjtujalzwh-auth-token`). |
| `SUPABASE_SERVICE_KEY` or `SUPABASE_SERVICE_ROLE_KEY` | Store writes **and** `/auth/v1/user` apikey (same as `/v1/deals` and `/v1/mtd`). Health `auth.apikeySource` should be `service`, `auth.ready` true. |
| `SUPABASE_ANON_KEY` or `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Fallback apikey only. Must be the project's anon key — **not** the JWT secret and **never** the user access token. Flask does not use `SUPABASE_JWT_SECRET` or JWKS. Missing both service and anon keys is HTTP **503** `auth not configured (missing anon key)`, not 401. |
| `BREVO_API_KEY` (+ optional sender/reply-to) | Reminder emails; skip-sends fail-soft |
| `COMPLIANCE_CRON_SECRET` or `BENCHMARK_CRON_SECRET` | `POST /reminders/dispatch` |
| `CORS_ALLOWED_ORIGINS` | Preview hosts beyond metalyzi.co.uk |

Supabase SQL (Dashboard → SQL, same project as auth):

1. `supabase/migrations/20260914_compliance_cockpit.sql`
2. `supabase/migrations/20260921_compliance_cockpit_grants.sql`

Probe (no auth):

```bash
curl -s https://metusa-deal-analyzer.onrender.com/v1/compliance/health | jq '{status, store, storeProbe, auth}'
curl -s https://metusa-deal-analyzer.onrender.com/v1/mtd/health | jq '{status, auth}'
```

`store: "supabase"` only means credentials exist. Obligations load only when
`storeProbe.ready` is `true`. Fresh-login 401 `Invalid or expired token`
(compliance) and 401 `Unauthorised` (MTD `/api/mtd/businesses` after a 200
`/api/mtd/token`) are the same GoTrue rejection — missing/wrong **apikey**
or a different `SUPABASE_URL` than the browser cookie project. After this
patch: missing apikey is **503** `auth not configured (missing anon key)`;
`auth.apikeySource` must be `service`; `auth.supabaseHost` must equal
`lftlugydvvcjtujalzwh.supabase.co`.

Retest after migrate: Bearer dashboard 200 (empty list ok) → POST GAS on a
portfolio UUID → `GET /properties/<id>/obligations` includes it → FE
`/tools/compliance` counts move off 0. Reminders: cron dispatch + Brevo.

Out of scope: Screener extension, MTD ledger, Ltd Co calc, licensing geo.
In-app notification UI is frontend-owned.

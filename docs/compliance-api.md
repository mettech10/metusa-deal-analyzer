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

Out of scope: Screener extension, MTD ledger, Ltd Co calc, licensing geo.
In-app notification UI is frontend-owned.

# Compliance Cockpit MVP — Flask `/v1/compliance`

Auth matches user-data APIs: `Authorization: Bearer <supabase access token>`.
Local tests use `X-User-Id`. Reminder dispatch uses `X-Cron-Secret`
(same pattern as `/api/benchmarks/update`).

Catalogue codes: `GAS`, `EICR`, `EPC`, `DEP`, `HTR`, `LIC_HMO`, `LIC_SEL`.
Status engine: `valid` | `due_soon` | `overdue` (due-soon window = 90 days).
Reminders: T-90, T-60, T-30, T-14, T-7, T-0, overdue (+1 day). Email is stubbed.

```bash
BASE=http://localhost:5002
TOKEN="YOUR_SUPABASE_ACCESS_TOKEN"
PROP="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

# Catalogue (public)
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

# Cron: process due reminder stubs (email is a TODO stub)
curl -s -X POST "$BASE/v1/compliance/reminders/dispatch" \
  -H "X-Cron-Secret: $COMPLIANCE_CRON_SECRET" | jq .
```

Out of scope: Screener extension, MTD ledger, Ltd Co calc, licensing geo.

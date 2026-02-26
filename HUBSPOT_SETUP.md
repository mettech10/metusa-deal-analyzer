# HubSpot Setup Guide for Metalyzi Waitlist

## 🔴 Most Likely Issue: Custom Properties Don't Exist

The backend code is correct, BUT the custom properties must be **manually created** in HubSpot before the API can use them.

---

## Step-by-Step Setup

### 1. Create Custom Contact Properties in HubSpot

Go to **HubSpot Settings** → **Properties** → **Contact properties** → **Create property**

Create these 3 properties:

#### Property 1: `metalyzi_waitlist`
- **Label:** Metalyzi Waitlist
- **Internal name:** `metalyzi_waitlist`
- **Type:** Single checkbox
- **Options:** Checked = "true", Unchecked = "false"

#### Property 2: `metalyzi_waitlist_date`
- **Label:** Metalyzi Waitlist Date
- **Internal name:** `metalyzi_waitlist_date`
- **Type:** Date picker

#### Property 3: `lead_source`
- **Label:** Lead Source  
- **Internal name:** `lead_source`
- **Type:** Single-line text (or Dropdown)
- **Default value:** Website Waitlist

---

### 2. Get Your HubSpot Private App Token (NOT API Key)

**⚠️ Important:** The code uses **Private App Token**, not the legacy API Key.

1. Go to **HubSpot Settings** → **Integrations** → **Private Apps**
2. Click **Create a private app**
3. Give it a name: "Metalyzi Website"
4. In **Scopes**, enable:
   - `crm.objects.contacts.read`
   - `crm.objects.contacts.write`
5. Click **Create app**
6. Copy the **Access token** (starts with `pat-na-...`)

---

### 3. Add Token to Vercel Environment Variables

```
HUBSPOT_API_KEY=pat-na-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

(Yes, the env variable is still called `HUBSPOT_API_KEY` even though it's a Private App token)

---

### 4. Redeploy to Vercel

After setting the env variable, redeploy your site:

```bash
vercel --prod
```

Or push a new commit to trigger deployment.

---

## Testing

Once configured:

1. Go to your waitlist page
2. Submit a test email
3. Check browser DevTools → Network → `/api/waitlist` response
   - Look for `"hubspot": "synced"` in the response
4. Check HubSpot contacts - the contact should appear with:
   - ✅ Metalyzi Waitlist = checked
   - ✅ Metalyzi Waitlist Date = today's date
   - ✅ Lead Source = Website Waitlist

---

## Troubleshooting

### "Unknown property" errors in Vercel logs
→ You haven't created the custom properties in HubSpot (Step 1)

### "Invalid token" or 401 errors  
→ You're using the legacy API key instead of Private App token (Step 2)

### Contact created but no custom properties
→ Properties exist but workflow isn't triggering → check workflow enrollment criteria

### Nothing in HubSpot at all
→ Check Vercel logs at `/api/waitlist` for `[HubSpot]` tagged messages

---

## Workflow Automation Setup

After contacts are syncing, create a workflow:

1. **HubSpot** → **Automation** → **Workflows** → **Create workflow**
2. **Trigger:** Contact property `metalyzi_waitlist` is equal to `true`
3. **Actions:**
   - Send welcome email
   - Add to list "Metalyzi Waitlist"
   - Set lifecycle stage to "Lead"

---

## Quick Checklist

- [ ] Custom properties created in HubSpot (`metalyzi_waitlist`, `metalyzi_waitlist_date`, `lead_source`)
- [ ] Private App created with contacts read/write scopes
- [ ] Access token copied (not legacy API key)
- [ ] `HUBSPOT_API_KEY` added to Vercel env vars
- [ ] Site redeployed after env var change
- [ ] Test submission made
- [ ] Workflow created with correct trigger

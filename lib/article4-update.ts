/**
 * Article 4 Monthly Update Pipeline
 *
 * There is no single free API that covers every UK Article 4 direction,
 * so we use a hybrid approach:
 *
 *   1. For every council in the article4_areas table, fetch the stored
 *      council_planning_url and look for Article 4 / consultation keywords
 *      that indicate new or changed directions. Flag candidates for
 *      manual review — we never auto-write status changes.
 *
 *   2. Update last_verified_at on rows we successfully checked so the
 *      admin UI can show data freshness.
 *
 *   3. Log the full run (counts + errors + flagged councils) to
 *      article4_update_log.
 *
 *   4. Email a summary to the Metalyzi admin inbox via Brevo.
 *
 * Runs monthly. Exposed as:
 *   - runArticle4Update(supabase) for programmatic use (scripts, API)
 *   - app/api/cron/article4-update/route.ts for Vercel cron
 *   - scripts/update-article4.ts for local/manual runs
 */

import type { SupabaseClient } from "@supabase/supabase-js"

// ── Public types ──────────────────────────────────────────────────────────

export interface Article4UpdateResult {
  runId: string | null
  runDate: string
  areasChecked: number
  areasUpdated: number
  newAreasAdded: number
  areasProposed: number
  flagged: Array<{
    councilName: string
    url: string
    reason: string
  }>
  errors: string[]
  dataSources: string[]
  emailSent: boolean
}

interface Article4Row {
  id: string
  council_name: string
  status: string
  council_planning_url: string | null
  last_verified_at: string | null
  verified: boolean | null
}

// ── Network helper ────────────────────────────────────────────────────────

const FETCH_TIMEOUT_MS = 12_000

async function fetchText(url: string): Promise<{ ok: boolean; body: string; status: number }> {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS)
  try {
    const res = await fetch(url, {
      signal: ctl.signal,
      redirect: "follow",
      headers: {
        // Some councils block default fetch UAs; identify ourselves politely.
        "User-Agent":
          "MetalyziA4Monitor/1.0 (+https://metalyzi.co.uk; contact@metalyzi.co.uk)",
        Accept: "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
      },
    })
    const body = await res.text().catch(() => "")
    return { ok: res.ok, body, status: res.status }
  } catch (err) {
    throw err
  } finally {
    clearTimeout(timer)
  }
}

// ── Keyword heuristic ─────────────────────────────────────────────────────

interface PageSignal {
  hasArticle4: boolean
  hasConsultation: boolean
  hasProposed: boolean
  hasRevoked: boolean
  /** Short phrase lifted from the page for the flag report. */
  snippet: string | null
}

function scanPage(html: string): PageSignal {
  const text = html.toLowerCase()
  const hasArticle4 =
    text.includes("article 4") || text.includes("article&nbsp;4")
  const hasConsultation = text.includes("consultation")
  const hasProposed =
    text.includes("proposed") ||
    text.includes("draft direction") ||
    text.includes("draft article")
  const hasRevoked =
    text.includes("revoked") ||
    text.includes("revocation") ||
    text.includes("withdrawn")

  let snippet: string | null = null
  if (hasArticle4) {
    const idx = text.indexOf("article 4")
    const start = Math.max(0, idx - 60)
    const end = Math.min(text.length, idx + 200)
    snippet = html.slice(start, end).replace(/\s+/g, " ").trim()
  }
  return { hasArticle4, hasConsultation, hasProposed, hasRevoked, snippet }
}

function flagReason(s: PageSignal, status: string): string | null {
  // Active row but page now mentions revocation → manual review.
  if (status === "active" && s.hasArticle4 && s.hasRevoked) {
    return "Page mentions Article 4 AND revocation/withdrawal — verify status"
  }
  // Proposed row — if the page has confirmed language, the direction may
  // have been adopted.
  if (status === "proposed" && s.hasArticle4 && !s.hasProposed && !s.hasConsultation) {
    return "Proposed direction — page no longer mentions 'proposed' or 'consultation' (may have been adopted)"
  }
  // Any row — page mentions a new consultation.
  if (s.hasArticle4 && s.hasConsultation && s.hasProposed && status !== "proposed") {
    return "Page mentions a new Article 4 consultation — check for additional directions"
  }
  return null
}

// ── Email helper (HTML body) ──────────────────────────────────────────────

function buildEmailHtml(r: Article4UpdateResult): string {
  const flaggedRows =
    r.flagged.length === 0
      ? `<tr><td colspan="3" style="padding:12px;color:#4b5563;font-style:italic;">No areas flagged for manual review.</td></tr>`
      : r.flagged
          .map(
            (f) => `
            <tr>
              <td style="padding:8px;border-bottom:1px solid #e5e7eb;">${escapeHtml(
                f.councilName
              )}</td>
              <td style="padding:8px;border-bottom:1px solid #e5e7eb;">${escapeHtml(
                f.reason
              )}</td>
              <td style="padding:8px;border-bottom:1px solid #e5e7eb;">
                <a href="${escapeHtml(f.url)}" style="color:#2563eb;">View</a>
              </td>
            </tr>`
          )
          .join("")

  const errorRows =
    r.errors.length === 0
      ? ""
      : `
        <h3 style="color:#b91c1c;margin-top:24px;">Errors (${r.errors.length})</h3>
        <ul style="color:#4b5563;font-family:ui-monospace,monospace;font-size:12px;">
          ${r.errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}
        </ul>`

  return `
  <div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:680px;margin:0 auto;padding:24px;color:#111827;">
    <h2 style="margin:0 0 8px 0;">Article 4 Monthly Update</h2>
    <p style="color:#6b7280;margin:0 0 24px 0;">Run: ${escapeHtml(r.runDate)}</p>

    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:16px;">
      <tr>
        <td style="padding:12px;background:#f3f4f6;border-radius:6px;">
          <strong>${r.areasChecked}</strong> areas checked &nbsp;·&nbsp;
          <strong>${r.areasUpdated}</strong> last_verified_at updated &nbsp;·&nbsp;
          <strong>${r.flagged.length}</strong> flagged for review &nbsp;·&nbsp;
          <strong>${r.errors.length}</strong> errors
        </td>
      </tr>
    </table>

    <h3 style="margin-top:24px;">Flagged for manual review</h3>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #e5e7eb;border-radius:6px;">
      <thead>
        <tr style="background:#f9fafb;text-align:left;">
          <th style="padding:8px;border-bottom:1px solid #e5e7eb;">Council</th>
          <th style="padding:8px;border-bottom:1px solid #e5e7eb;">Reason</th>
          <th style="padding:8px;border-bottom:1px solid #e5e7eb;">Link</th>
        </tr>
      </thead>
      <tbody>${flaggedRows}</tbody>
    </table>

    ${errorRows}

    <p style="margin-top:32px;font-size:12px;color:#6b7280;">
      Data sourced from council planning documents. Always verify with the local
      planning authority. © Metalyzi — metalyzi.co.uk
    </p>
  </div>`
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

async function sendSummaryEmail(result: Article4UpdateResult): Promise<boolean> {
  const apiKey = process.env.BREVO_API_KEY
  if (!apiKey) {
    console.warn("[article4-update] BREVO_API_KEY not set — skipping summary email")
    return false
  }
  const sender = process.env.BREVO_SENDER_EMAIL ?? "noreply@metalyzi.co.uk"
  const to = process.env.ARTICLE4_UPDATE_EMAIL ?? "contact@metalyzi.co.uk"

  try {
    const res = await fetch("https://api.brevo.com/v3/smtp/email", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": apiKey,
      },
      body: JSON.stringify({
        sender: { name: "Metalyzi A4 Monitor", email: sender },
        to: [{ email: to }],
        subject: `Article 4 Monthly Update — ${result.flagged.length} flagged, ${result.errors.length} errors`,
        htmlContent: buildEmailHtml(result),
      }),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => "")
      console.error("[article4-update] Brevo send failed:", res.status, body)
      return false
    }
    return true
  } catch (err) {
    console.error("[article4-update] Brevo network error:", err)
    return false
  }
}

// ── Main pipeline ─────────────────────────────────────────────────────────

/**
 * Run the monthly Article 4 update.
 *
 * The caller is responsible for supplying a Supabase client with write
 * access (service role) — anon / authenticated can't update rows or
 * insert into article4_update_log.
 */
export async function runArticle4Update(
  supabase: SupabaseClient,
  opts: { sendEmail?: boolean } = {}
): Promise<Article4UpdateResult> {
  const runDate = new Date().toISOString()
  const sendEmail = opts.sendEmail !== false // default true

  const result: Article4UpdateResult = {
    runId: null,
    runDate,
    areasChecked: 0,
    areasUpdated: 0,
    newAreasAdded: 0,
    areasProposed: 0,
    flagged: [],
    errors: [],
    dataSources: ["council_planning_url"],
    emailSent: false,
  }

  // Load every non-revoked area.
  const { data, error } = await supabase
    .from("article4_areas")
    .select("id,council_name,status,council_planning_url,last_verified_at,verified")
    .neq("status", "revoked")

  if (error) {
    result.errors.push(`article4_areas load failed: ${error.message}`)
    await writeLog(supabase, result)
    return result
  }

  const rows = (data ?? []) as unknown as Article4Row[]
  result.areasChecked = rows.length
  result.areasProposed = rows.filter(
    (r) => r.status === "proposed" || r.status === "consultation"
  ).length

  // Check each council URL.
  for (const row of rows) {
    if (!row.council_planning_url) {
      // No URL to check — skip, don't error.
      continue
    }

    try {
      const res = await fetchText(row.council_planning_url)
      if (!res.ok) {
        result.errors.push(
          `${row.council_name}: ${res.status} from ${row.council_planning_url}`
        )
        continue
      }

      const signal = scanPage(res.body)
      const reason = flagReason(signal, row.status)
      if (reason) {
        result.flagged.push({
          councilName: row.council_name,
          url: row.council_planning_url,
          reason,
        })
      }

      // Successful fetch → refresh last_verified_at (separate from the
      // `verified` boolean, which gates admin-confirmed rows).
      const { error: upErr } = await supabase
        .from("article4_areas")
        .update({ last_verified_at: new Date().toISOString() })
        .eq("id", row.id)

      if (upErr) {
        result.errors.push(`${row.council_name}: update failed: ${upErr.message}`)
      } else {
        result.areasUpdated += 1
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      result.errors.push(`${row.council_name}: fetch failed: ${msg}`)
    }
  }

  // Email summary.
  if (sendEmail) {
    result.emailSent = await sendSummaryEmail(result)
  }

  // Audit log.
  await writeLog(supabase, result)

  return result
}

async function writeLog(
  supabase: SupabaseClient,
  r: Article4UpdateResult
): Promise<void> {
  try {
    const { data, error } = await supabase
      .from("article4_update_log")
      .insert({
        run_date: r.runDate,
        areas_checked: r.areasChecked,
        areas_updated: r.areasUpdated,
        new_areas_added: r.newAreasAdded,
        areas_proposed: r.areasProposed,
        errors: r.errors,
        data_sources: r.dataSources,
      })
      .select("id")
      .single()
    if (error) {
      console.error("[article4-update] log write failed:", error.message)
      return
    }
    const row = data as { id: string } | null
    if (row?.id) {
      r.runId = row.id
    }
  } catch (err) {
    console.error("[article4-update] log write threw:", err)
  }
}

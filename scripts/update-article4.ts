/**
 * Standalone runner for the monthly Article 4 update pipeline.
 *
 * Usage:
 *   npx tsx scripts/update-article4.ts           # full run + email
 *   npx tsx scripts/update-article4.ts --no-email  # dry run, no email
 *
 * Required env:
 *   NEXT_PUBLIC_SUPABASE_URL
 *   SUPABASE_SERVICE_ROLE_KEY
 *   BREVO_API_KEY            (optional — skipped with warning if missing)
 *   BREVO_SENDER_EMAIL       (optional — defaults to noreply@metalyzi.co.uk)
 *   ARTICLE4_UPDATE_EMAIL    (optional — defaults to contact@metalyzi.co.uk)
 */

import { createAdminClient } from "@/lib/supabase/admin"
import { runArticle4Update } from "@/lib/article4-update"

async function main() {
  const noEmail = process.argv.includes("--no-email")

  const supabase = createAdminClient()
  const result = await runArticle4Update(supabase, { sendEmail: !noEmail })

  console.log("── Article 4 Monthly Update ──")
  console.log(`Run date:        ${result.runDate}`)
  console.log(`Run ID:          ${result.runId ?? "(log write failed)"}`)
  console.log(`Areas checked:   ${result.areasChecked}`)
  console.log(`Areas updated:   ${result.areasUpdated}`)
  console.log(`Areas proposed:  ${result.areasProposed}`)
  console.log(`Flagged:         ${result.flagged.length}`)
  console.log(`Errors:          ${result.errors.length}`)
  console.log(`Email sent:      ${result.emailSent}`)

  if (result.flagged.length > 0) {
    console.log("\nFlagged for manual review:")
    for (const f of result.flagged) {
      console.log(`  • ${f.councilName}: ${f.reason}`)
      console.log(`    ${f.url}`)
    }
  }

  if (result.errors.length > 0) {
    console.log("\nErrors:")
    for (const e of result.errors) {
      console.log(`  ! ${e}`)
    }
  }

  // Non-zero exit if anything failed so CI/cron can alert.
  process.exit(result.errors.length > 0 ? 1 : 0)
}

main().catch((err) => {
  console.error("[update-article4] fatal:", err)
  process.exit(1)
})

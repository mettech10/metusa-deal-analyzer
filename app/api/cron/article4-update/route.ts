/**
 * Vercel Cron endpoint — monthly Article 4 update.
 *
 * Triggered by vercel.json at "0 3 1 * *" (03:00 UTC on the 1st of each month).
 *
 * Auth: Vercel sends `Authorization: Bearer ${CRON_SECRET}` on cron invocations
 * when CRON_SECRET is set in project env vars. We reject anything else so the
 * endpoint can't be hit from the public internet.
 *
 * Response: always returns JSON with the run summary (even on partial failure)
 * so the admin can see run counts in Vercel's cron execution log.
 */

import { NextResponse } from "next/server"
import { createAdminClient } from "@/lib/supabase/admin"
import { runArticle4Update } from "@/lib/article4-update"

export const runtime = "nodejs"
// Long-running — fetching ~20 council sites at 12s timeout each can run
// past Vercel's default 10s. Max is 300s on Pro. Adjust if needed.
export const maxDuration = 300
export const dynamic = "force-dynamic"

export async function GET(req: Request) {
  // Auth check — Vercel cron sends this header automatically when
  // CRON_SECRET is configured in the project.
  const expected = process.env.CRON_SECRET
  if (expected) {
    const header = req.headers.get("authorization") ?? ""
    if (header !== `Bearer ${expected}`) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 })
    }
  }

  try {
    const supabase = createAdminClient()
    const result = await runArticle4Update(supabase, { sendEmail: true })

    const status = result.errors.length > 0 ? 207 : 200 // 207 = multi-status
    return NextResponse.json(result, { status })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    console.error("[cron/article4-update] fatal:", err)
    return NextResponse.json(
      { error: "article4 update failed", detail: msg },
      { status: 500 }
    )
  }
}

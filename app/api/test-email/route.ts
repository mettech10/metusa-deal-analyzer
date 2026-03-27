/**
 * DEV-ONLY: Manual email preview/trigger route.
 *
 * This route is disabled in production (NODE_ENV === "production").
 * Use it to trigger both verification and welcome emails to a test address
 * so you can preview them in your inbox.
 *
 * Usage:
 *   GET /api/test-email?type=verification&to=you@example.com
 *   GET /api/test-email?type=welcome&to=you@example.com
 *   GET /api/test-email?type=all&to=you@example.com   ← triggers both
 */

import { NextResponse } from "next/server"
import { sendVerificationEmail, sendWelcomeEmail } from "@/lib/brevo-email"

export async function GET(request: Request) {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json(
      { error: "This route is disabled in production." },
      { status: 403 },
    )
  }

  const { searchParams } = new URL(request.url)
  const type = searchParams.get("type") ?? "all"
  const to = searchParams.get("to")

  if (!to || !to.includes("@")) {
    return NextResponse.json(
      {
        error: "Missing or invalid 'to' query param.",
        usage: "GET /api/test-email?type=verification|welcome|all&to=you@example.com",
      },
      { status: 400 },
    )
  }

  const results: Record<string, boolean> = {}

  if (type === "verification" || type === "all") {
    const fakeVerificationUrl =
      `${process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"}/auth/callback?code=TEST_CODE_PLACEHOLDER`
    console.log(`[Test Email] Sending verification email to ${to}`)
    results.verification = await sendVerificationEmail(to, fakeVerificationUrl)
  }

  if (type === "welcome" || type === "all") {
    console.log(`[Test Email] Sending welcome email to ${to}`)
    results.welcome = await sendWelcomeEmail(to)
  }

  const allSent = Object.values(results).every(Boolean)

  return NextResponse.json(
    {
      status: allSent ? "SUCCESS" : "PARTIAL_FAILURE",
      sentTo: to,
      results,
      note: "Check your server console for Brevo API response logs.",
    },
    { status: allSent ? 200 : 500 },
  )
}

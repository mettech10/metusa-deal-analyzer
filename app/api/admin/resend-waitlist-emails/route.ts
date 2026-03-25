import { NextResponse } from "next/server"
import { sendWaitlistWelcomeEmail } from "@/lib/brevo-email"

const PAGE_SIZE = 1000

async function fetchBrevoWaitlistEmails(): Promise<string[]> {
  const apiKey = process.env.BREVO_API_KEY
  if (!apiKey) throw new Error("BREVO_API_KEY not set")

  const emails: string[] = []
  let offset = 0

  while (true) {
    const res = await fetch(
      `https://api.brevo.com/v3/contacts?limit=${PAGE_SIZE}&offset=${offset}&sort=desc`,
      {
        headers: {
          "api-key": apiKey,
          "Content-Type": "application/json",
        },
      },
    )

    if (!res.ok) {
      const body = await res.text()
      throw new Error(`Brevo contacts fetch failed: ${res.status} ${body}`)
    }

    const data = await res.json()
    const contacts: Array<{ email: string; attributes?: Record<string, unknown> }> =
      data.contacts ?? []

    for (const contact of contacts) {
      if (contact.attributes?.WAITLIST === true) {
        emails.push(contact.email)
      }
    }

    // Stop when we've received fewer contacts than the page size
    if (contacts.length < PAGE_SIZE) break
    offset += PAGE_SIZE
  }

  return emails
}

export async function POST(request: Request) {
  // Require admin secret to prevent unauthorized access
  const adminSecret = process.env.ADMIN_SECRET
  if (!adminSecret) {
    return NextResponse.json({ error: "ADMIN_SECRET not configured" }, { status: 500 })
  }

  const authHeader = request.headers.get("authorization")
  if (authHeader !== `Bearer ${adminSecret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  try {
    console.log("[Resend Waitlist Emails] Fetching Brevo waitlist contacts...")
    const emails = await fetchBrevoWaitlistEmails()
    console.log(`[Resend Waitlist Emails] Found ${emails.length} waitlist contacts`)

    const results = { sent: 0, failed: 0, emails: [] as string[] }

    for (const email of emails) {
      const ok = await sendWaitlistWelcomeEmail(email)
      if (ok) {
        results.sent++
        results.emails.push(email)
      } else {
        results.failed++
        console.warn(`[Resend Waitlist Emails] Failed to send to: ${email}`)
      }
    }

    console.log(
      `[Resend Waitlist Emails] Done. Sent: ${results.sent}, Failed: ${results.failed}`,
    )

    return NextResponse.json({
      total: emails.length,
      sent: results.sent,
      failed: results.failed,
      sentTo: results.emails,
    })
  } catch (err) {
    console.error("[Resend Waitlist Emails] Error:", err)
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Internal server error" },
      { status: 500 },
    )
  }
}

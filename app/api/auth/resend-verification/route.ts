import { createAdminClient } from "@/lib/supabase/admin"
import { sendVerificationEmail } from "@/lib/brevo-email"
import { NextResponse } from "next/server"

/**
 * POST /api/auth/resend-verification
 * Resend the Brevo-branded verification email for an unconfirmed account.
 * Uses admin.generateLink so Supabase never sends its own email.
 */
export async function POST(request: Request) {
  try {
    const { email } = await request.json()

    if (!email || !email.includes("@")) {
      return NextResponse.json(
        { error: "Valid email required" },
        { status: 400 }
      )
    }

    const { headers } = await import("next/headers")
    const headersList = await headers()
    const host = headersList.get("host") || ""
    const protocol = headersList.get("x-forwarded-proto") || "https"
    const origin = `${protocol}://${host}`
    const callbackBase =
      process.env.NEXT_PUBLIC_DEV_SUPABASE_REDIRECT_URL ||
      `${origin}/auth/callback`
    const redirectTo = `${callbackBase}?source=email_verify`

    const adminClient = createAdminClient()
    const { data, error } = await adminClient.auth.admin.generateLink({
      type: "signup",
      email,
      options: { redirectTo },
    })

    if (error) {
      console.error("[Resend Verification] generateLink error:", error)
      return NextResponse.json({ error: error.message }, { status: 500 })
    }

    const verificationUrl = data.properties.action_link
    const sent = await sendVerificationEmail(email, verificationUrl)

    if (!sent) {
      return NextResponse.json(
        { error: "Failed to send verification email" },
        { status: 500 }
      )
    }

    return NextResponse.json({ message: "Verification email sent" })
  } catch (err) {
    console.error("[Resend Verification] Unexpected error:", err)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}

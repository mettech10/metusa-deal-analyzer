import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"
import { createAdminClient } from "@/lib/supabase/admin"
import { sendWelcomeEmail } from "@/lib/brevo-email"
import type { EmailOtpType } from "@supabase/supabase-js"

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get("code")
  const token_hash = searchParams.get("token_hash")
  const type = searchParams.get("type")
  const next = searchParams.get("next") ?? "/analyse"

  const supabase = await createClient()
  let sessionData: Awaited<ReturnType<typeof supabase.auth.exchangeCodeForSession>>["data"] | null = null
  let authError: unknown = null

  if (code) {
    // OAuth / PKCE auth code flow
    const { data, error } = await supabase.auth.exchangeCodeForSession(code)
    sessionData = data
    authError = error
  } else if (token_hash && type) {
    // Email OTP / magic-link verification flow (generateLink redirects here)
    const { data, error } = await supabase.auth.verifyOtp({
      type: type as EmailOtpType,
      token_hash,
    })
    sessionData = data
    authError = error
  }

  if (sessionData && !authError) {
    // Password reset flow — send user to the reset password page
    if (type === "recovery") {
      return NextResponse.redirect(`${origin}/reset-password`)
    }

    // Use the user returned directly from the exchange — calling getUser()
    // after exchangeCodeForSession reads from request cookies which don't
    // yet contain the newly-set session, so it would return null.
    const user = sessionData.user

    // Email verification (signup confirmation) — always show success page
    if (type === "signup" || (user?.email_confirmed_at && next === "/analyse")) {
      const isFirstVerification = user?.email && user.email_confirmed_at && !user.user_metadata?.welcome_email_sent
      if (isFirstVerification) {
        console.log(`[Auth Callback] Sending welcome email to ${user.email}`)
        const sent = await sendWelcomeEmail(user.email!).catch((err) => {
          console.error(`[Auth Callback] Welcome email error:`, err)
          return false
        })
        if (sent) {
          const adminClient = createAdminClient()
          await adminClient.auth.admin.updateUserById(user!.id, {
            user_metadata: { ...user!.user_metadata, welcome_email_sent: true },
          })
        } else {
          console.error(`[Auth Callback] Welcome email failed to send to ${user!.email}`)
        }
      } else {
        console.log(`[Auth Callback] Skipping welcome email for ${user?.email} (already sent or email not confirmed)`)
      }
      // Always redirect to success page for email verification
      return NextResponse.redirect(`${origin}/auth/verified`)
    }

    return NextResponse.redirect(`${origin}${next}`)
  }

  // Auth error — redirect to login with error param
  return NextResponse.redirect(`${origin}/login?error=auth`)
}

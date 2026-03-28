import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"
import { sendWelcomeEmail } from "@/lib/brevo-email"

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get("code")
  const next = searchParams.get("next") ?? "/analyse"

  if (code) {
    const supabase = await createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      // Send welcome email only on first-time email confirmation.
      // After exchangeCodeForSession, email_confirmed_at is freshly set —
      // if it was set within the last 60 s this IS the verification click,
      // not a subsequent OAuth/password login via this callback.
      const { data: { user } } = await supabase.auth.getUser()
      if (user?.email && user.email_confirmed_at) {
        const confirmedAgeMs = Date.now() - new Date(user.email_confirmed_at).getTime()
        if (confirmedAgeMs < 60_000) {
          sendWelcomeEmail(user.email).catch(console.error)
        }
      }
      
      // Check if email needs verification (for email/password signups)
      // Google users are pre-verified by Google
      if (provider === "email" && !data.session.user.email_confirmed_at) {
        // Email not verified yet - redirect to verification page
        return NextResponse.redirect(`${origin}/verify-email`)
      }
      
      // Google users or verified email users - go straight to app
      return NextResponse.redirect(`${origin}${next}`)
    }
  }

  // Auth error — redirect to login with error param
  return NextResponse.redirect(`${origin}/login?error=auth`)
}

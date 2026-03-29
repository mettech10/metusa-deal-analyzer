import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"
import { createAdminClient } from "@/lib/supabase/admin"
import { sendWelcomeEmail } from "@/lib/brevo-email"

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get("code")
  const type = searchParams.get("type")
  const next = searchParams.get("next") ?? "/analyse"

  if (code) {
    const supabase = await createClient()
    const { data: sessionData, error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      // Password reset flow — send user to the reset password page
      if (type === "recovery") {
        return NextResponse.redirect(`${origin}/reset-password`)
      }

      // Use the user returned directly from the exchange — calling getUser()
      // after exchangeCodeForSession reads from request cookies which don't
      // yet contain the newly-set session, so it would return null.
      const user = sessionData.user
      const isFirstVerification = user?.email && user.email_confirmed_at && !user.user_metadata?.welcome_email_sent
      if (isFirstVerification) {
        console.log(`[Auth Callback] Sending welcome email to ${user.email}`)
        // Await the email send so it completes before the serverless function exits
        const sent = await sendWelcomeEmail(user.email!).catch((err) => {
          console.error(`[Auth Callback] Welcome email error:`, err)
          return false
        })
        if (sent) {
          // Mark welcome email as sent to prevent duplicates on future logins
          const adminClient = createAdminClient()
          await adminClient.auth.admin.updateUserById(user!.id, {
            user_metadata: { ...user!.user_metadata, welcome_email_sent: true },
          })
        } else {
          console.error(`[Auth Callback] Welcome email failed to send to ${user!.email}`)
        }
        // Redirect to verification success page so the user sees confirmation
        return NextResponse.redirect(`${origin}/verification-success`)
      } else {
        console.log(`[Auth Callback] Skipping welcome email for ${user?.email} (already sent or email not confirmed)`)
      }

      return NextResponse.redirect(`${origin}${next}`)
    }
  }

  // Auth error — redirect to login with error param
  return NextResponse.redirect(`${origin}/login?error=auth`)
}

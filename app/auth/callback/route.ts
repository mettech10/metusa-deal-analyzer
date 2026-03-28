import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"
import { createAdminClient } from "@/lib/supabase/admin"
import { sendWelcomeEmail } from "@/lib/brevo-email"

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get("code")
  const next = searchParams.get("next") ?? "/analyse"

  if (code) {
    const supabase = await createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      // Send welcome email on first-time email confirmation only.
      // Use a metadata flag to reliably detect first verification without
      // relying on clock skew-prone timestamp comparisons.
      const { data: { user } } = await supabase.auth.getUser()
      if (user?.email && user.email_confirmed_at && !user.user_metadata?.welcome_email_sent) {
        console.log(`[Auth Callback] Sending welcome email to ${user.email}`)
        sendWelcomeEmail(user.email).then(async (sent) => {
          if (sent) {
            // Mark welcome email as sent to prevent duplicates on future logins
            const adminClient = createAdminClient()
            await adminClient.auth.admin.updateUserById(user.id, {
              user_metadata: { ...user.user_metadata, welcome_email_sent: true },
            })
          } else {
            console.error(`[Auth Callback] Welcome email failed to send to ${user.email}`)
          }
        }).catch(console.error)
      } else {
        console.log(`[Auth Callback] Skipping welcome email for ${user.email} (already sent or email not confirmed)`)
      }

      return NextResponse.redirect(`${origin}${next}`)
    }
  }

  // Auth error — redirect to login with error param
  return NextResponse.redirect(`${origin}/login?error=auth`)
}

import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"
import { sendSignUpWelcomeEmail } from "@/lib/brevo-email"

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get("code")
  const next = searchParams.get("next") ?? "/analyse"

  if (code) {
    const supabase = await createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      // Send welcome email to new users (created within the last 60 seconds)
      const { data: { user } } = await supabase.auth.getUser()
      if (user?.email) {
        const ageMs = Date.now() - new Date(user.created_at).getTime()
        if (ageMs < 60_000) {
          const name = user.user_metadata?.full_name as string | undefined
          sendSignUpWelcomeEmail(user.email, name).catch(console.error)
        }
      }

      return NextResponse.redirect(`${origin}${next}`)
    }
  }

  // Auth error -- redirect to login with error
  return NextResponse.redirect(`${origin}/login?error=auth`)
}

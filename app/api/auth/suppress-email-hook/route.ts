/**
 * Supabase Auth "Send Email" Hook
 *
 * Supabase calls this endpoint whenever it would normally send an auth email
 * (email confirmation, password reset, magic link, etc.).
 * We return 200 immediately to suppress the default Supabase email.
 *
 * All transactional emails are handled by the app via Brevo (see lib/brevo-email.ts
 * and app/auth/actions.ts → signUpWithEmail).
 *
 * Production setup (one-time, in Supabase Dashboard):
 *   Authentication → Hooks → Send Email
 *   → HTTP (POST) → https://<your-domain>/api/auth/suppress-email-hook
 *   → Add the "Supabase Webhook Secret" header value as SUPABASE_HOOK_SECRET in .env
 */
import { NextResponse } from "next/server"

export async function POST(request: Request) {
  // Optionally verify the hook secret to ensure the request is from Supabase
  const hookSecret = process.env.SUPABASE_HOOK_SECRET
  if (hookSecret) {
    const authHeader = request.headers.get("authorization")
    if (authHeader !== `Bearer ${hookSecret}`) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
    }
  }

  // Consume the body (required) but do nothing — Brevo handles the actual email
  await request.json().catch(() => null)

  return NextResponse.json({ success: true })
}

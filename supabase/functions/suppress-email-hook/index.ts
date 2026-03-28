/**
 * Supabase Auth Hook — Send Email
 *
 * This hook intercepts every email Supabase Auth would send natively
 * (confirmations, password resets, etc.) and does nothing.
 * All transactional emails are handled by the app via Brevo instead.
 *
 * Deploy: supabase functions deploy suppress-email-hook
 * Dashboard: Authentication → Hooks → Send Email → set URL to this function
 */
Deno.serve(async (req: Request) => {
  // Supabase calls this hook with a JSON body describing the email to send.
  // We intentionally swallow it — Brevo handles the actual delivery.
  await req.json().catch(() => null)

  return new Response(JSON.stringify({ success: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  })
})

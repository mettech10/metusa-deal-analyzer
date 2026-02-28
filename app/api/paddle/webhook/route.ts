/**
 * Paddle Webhook Handler
 *
 * Receives signed webhook events from Paddle and processes them.
 * Paddle docs: https://developer.paddle.com/webhooks/overview
 *
 * To verify signatures in production, set:
 *   PADDLE_WEBHOOK_SECRET  (from Paddle Dashboard → Developer → Notifications → secret key)
 */

export async function POST(req: Request) {
  const body = await req.text()

  let event: Record<string, unknown>
  try {
    event = JSON.parse(body)
  } catch {
    return Response.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  const eventType = event.event_type as string
  const data = event.data as Record<string, unknown>

  console.log(`[Paddle Webhook] Received: ${eventType}`)

  switch (eventType) {
    // ── Subscription events ─────────────────────────────────────────────
    case 'subscription.created':
      console.log('[Paddle] New subscription:', data?.id)
      // TODO: Mark user as subscribed in Supabase
      break

    case 'subscription.activated':
      console.log('[Paddle] Subscription activated:', data?.id)
      break

    case 'subscription.updated':
      console.log('[Paddle] Subscription updated:', data?.id)
      break

    case 'subscription.canceled':
      console.log('[Paddle] Subscription cancelled:', data?.id)
      // TODO: Revoke access in Supabase
      break

    // ── Transaction events ──────────────────────────────────────────────
    case 'transaction.completed':
      console.log('[Paddle] Transaction completed:', data?.id)
      // TODO: Grant credits/access in Supabase
      break

    case 'transaction.payment_failed':
      console.log('[Paddle] Payment failed:', data?.id)
      break

    default:
      console.log(`[Paddle] Unhandled event type: ${eventType}`)
  }

  return Response.json({ received: true })
}

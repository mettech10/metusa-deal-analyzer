import Stripe from 'stripe'

/**
 * POST /api/stripe/checkout
 * Creates a Stripe Checkout session and returns the hosted URL.
 *
 * Body: { priceId: string, mode: 'payment' | 'subscription', email?: string }
 */
export async function POST(req: Request) {
  const { priceId, mode, email } = await req.json()

  if (!priceId || !mode) {
    return Response.json({ error: 'priceId and mode are required' }, { status: 400 })
  }

  const secretKey = process.env.STRIPE_SECRET_KEY
  if (!secretKey) {
    console.error('[Stripe] STRIPE_SECRET_KEY is not set')
    return Response.json({ error: 'Payment not configured' }, { status: 500 })
  }

  const stripe = new Stripe(secretKey)

  const origin =
    process.env.NEXT_PUBLIC_APP_URL ??
    (req.headers.get('origin') || 'http://localhost:3000')

  try {
    const session = await stripe.checkout.sessions.create({
      mode,
      line_items: [{ price: priceId, quantity: 1 }],
      ...(email ? { customer_email: email } : {}),
      success_url: `${origin}/analyse?payment=success`,
      cancel_url: `${origin}/#pricing`,
      metadata: { source: 'dealcheck-uk' },
    })

    return Response.json({ url: session.url })
  } catch (err) {
    console.error('[Stripe] Failed to create checkout session:', err)
    return Response.json({ error: 'Failed to create checkout session' }, { status: 500 })
  }
}

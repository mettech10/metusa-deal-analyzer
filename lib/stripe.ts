/**
 * Stripe checkout helper — redirects the user to a hosted Stripe Checkout page.
 *
 * Server-side Stripe calls are handled in app/api/stripe/checkout/route.ts.
 * Set these env vars in your Vercel / Render dashboard:
 *
 *   STRIPE_SECRET_KEY            — secret key from Stripe Dashboard
 *   STRIPE_WEBHOOK_SECRET        — webhook signing secret from Stripe Dashboard
 *   NEXT_PUBLIC_STRIPE_PRICE_PAY_PER_DEAL — price ID for pay-per-deal (one-time)
 *   NEXT_PUBLIC_STRIPE_PRICE_PRO          — price ID for Pro plan (subscription)
 *   NEXT_PUBLIC_STRIPE_PRICE_UNLIMITED    — price ID for Unlimited plan (subscription)
 */

export async function openStripeCheckout(
  priceId: string,
  mode: 'payment' | 'subscription',
  email?: string,
) {
  try {
    const res = await fetch('/api/stripe/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ priceId, mode, email }),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      console.error('[Stripe] Checkout session creation failed:', err)
      alert('Failed to start checkout. Please try again.')
      return
    }

    const { url } = await res.json()
    if (url) {
      window.location.href = url
    }
  } catch (err) {
    console.error('[Stripe] Network error during checkout:', err)
    alert('Failed to start checkout. Please check your connection and try again.')
  }
}

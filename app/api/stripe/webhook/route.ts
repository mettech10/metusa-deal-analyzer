import Stripe from 'stripe'
import { createClient } from '@supabase/supabase-js'
import { sendSubscriptionReceiptEmail } from '@/lib/brevo-email'

/**
 * POST /api/stripe/webhook
 * Handles signed webhook events from Stripe.
 *
 * Set STRIPE_WEBHOOK_SECRET in your environment (from Stripe Dashboard →
 * Developers → Webhooks → your endpoint → Signing secret).
 */
export async function POST(req: Request) {
  const body = await req.text()
  const sig = req.headers.get('stripe-signature') ?? ''

  const secret = process.env.STRIPE_SECRET_KEY
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET

  if (!secret || !webhookSecret) {
    console.error('[Stripe Webhook] Missing STRIPE_SECRET_KEY or STRIPE_WEBHOOK_SECRET')
    return Response.json({ error: 'Not configured' }, { status: 500 })
  }

  const stripe = new Stripe(secret)

  let event: Stripe.Event
  try {
    event = stripe.webhooks.constructEvent(body, sig, webhookSecret)
  } catch (err) {
    console.error('[Stripe Webhook] Signature verification failed:', err)
    return Response.json({ error: 'Invalid signature' }, { status: 400 })
  }

  console.log(`[Stripe Webhook] Received: ${event.type}`)

  // Supabase admin client for updating subscription status
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
  )

  switch (event.type) {
    // ── One-time payment (pay-per-deal) ─────────────────────────────────
    case 'checkout.session.completed': {
      const session = event.data.object as Stripe.Checkout.Session
      if (session.mode === 'payment' && session.customer_email) {
        const { error } = await supabase
          .from('subscriptions')
          .upsert(
            {
              email: session.customer_email,
              stripe_customer: session.customer as string,
              status: 'active',
              plan: 'pay_per_deal',
              updated_at: new Date().toISOString(),
            },
            { onConflict: 'email' },
          )
        if (error) console.error('[Stripe Webhook] Supabase upsert error:', error)

        // Send receipt email
        const amount = session.amount_total != null
          ? `${session.currency?.toUpperCase()} ${(session.amount_total / 100).toFixed(2)}`
          : 'N/A'
        sendSubscriptionReceiptEmail(session.customer_email, 'pay_per_deal', amount).catch(console.error)
      }
      break
    }

    // ── Subscription events ─────────────────────────────────────────────
    case 'customer.subscription.created':
    case 'customer.subscription.updated': {
      const sub = event.data.object as Stripe.Subscription
      const email = await getEmailFromCustomer(stripe, sub.customer as string)
      if (!email) break

      const stripeStatus = sub.status
      const status =
        stripeStatus === 'active' || stripeStatus === 'trialing'
          ? 'active'
          : stripeStatus === 'past_due' || stripeStatus === 'unpaid'
          ? 'paused'
          : 'cancelled'

      const { error } = await supabase
        .from('subscriptions')
        .upsert(
          {
            email,
            stripe_customer: sub.customer as string,
            status,
            plan: 'subscription',
            updated_at: new Date().toISOString(),
          },
          { onConflict: 'email' },
        )
      if (error) console.error('[Stripe Webhook] Supabase upsert error:', error)

      // Send receipt email only on new subscription creation
      if (event.type === 'customer.subscription.created' && status === 'active') {
        const price = sub.items.data[0]?.price
        const unitAmount = price?.unit_amount ?? 0
        const currency = price?.currency?.toUpperCase() ?? 'GBP'
        const interval = price?.recurring?.interval ?? 'month'
        const amount = `${currency} ${(unitAmount / 100).toFixed(2)}/${interval}`
        sendSubscriptionReceiptEmail(email, 'subscription', amount).catch(console.error)
      }
      break
    }

    case 'customer.subscription.deleted': {
      const sub = event.data.object as Stripe.Subscription
      const email = await getEmailFromCustomer(stripe, sub.customer as string)
      if (!email) break

      const { error } = await supabase
        .from('subscriptions')
        .update({ status: 'cancelled', updated_at: new Date().toISOString() })
        .eq('email', email)
      if (error) console.error('[Stripe Webhook] Supabase update error:', error)
      break
    }

    case 'invoice.payment_succeeded':
      console.log('[Stripe] Invoice paid:', (event.data.object as Stripe.Invoice).id)
      break

    case 'invoice.payment_failed':
      console.log('[Stripe] Invoice payment failed:', (event.data.object as Stripe.Invoice).id)
      break

    default:
      console.log(`[Stripe Webhook] Unhandled event: ${event.type}`)
  }

  return Response.json({ received: true })
}

async function getEmailFromCustomer(
  stripe: Stripe,
  customerId: string,
): Promise<string | null> {
  try {
    const customer = await stripe.customers.retrieve(customerId)
    if (customer.deleted) return null
    return (customer as Stripe.Customer).email
  } catch {
    return null
  }
}

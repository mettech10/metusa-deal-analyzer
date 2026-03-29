import { NextResponse } from "next/server"
import Stripe from "stripe"

export async function POST(req: Request) {
  const stripeSecretKey = process.env.STRIPE_SECRET_KEY
  const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET

  if (!stripeSecretKey || !webhookSecret) {
    return NextResponse.json({ error: "Stripe not configured" }, { status: 501 })
  }

  const stripe = new Stripe(stripeSecretKey)
  const body = await req.text()
  const signature = req.headers.get("stripe-signature")

  if (!signature) {
    return NextResponse.json({ error: "Missing stripe-signature header" }, { status: 400 })
  }

  let event: Stripe.Event
  try {
    event = stripe.webhooks.constructEvent(body, signature, webhookSecret)
  } catch (err) {
    console.error("[Stripe Webhook] Signature verification failed:", err)
    return NextResponse.json({ error: "Invalid signature" }, { status: 400 })
  }

  // Handle relevant events
  switch (event.type) {
    case "checkout.session.completed": {
      const session = event.data.object as Stripe.Checkout.Session
      console.log("[Stripe Webhook] Checkout completed:", session.id, "customer:", session.customer_email)
      // TODO: update user subscription in Supabase based on session.customer_email
      break
    }
    case "customer.subscription.deleted": {
      const subscription = event.data.object as Stripe.Subscription
      console.log("[Stripe Webhook] Subscription cancelled:", subscription.id)
      // TODO: revoke user subscription access in Supabase
      break
    }
    default:
      console.log("[Stripe Webhook] Unhandled event type:", event.type)
  }

  return NextResponse.json({ received: true })
}

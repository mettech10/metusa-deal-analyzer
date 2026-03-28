import { NextResponse } from "next/server"
import Stripe from "stripe"
import { createClient } from "@/lib/supabase/server"

export async function POST(req: Request) {
  const stripeSecretKey = process.env.STRIPE_SECRET_KEY
  if (!stripeSecretKey) {
    return NextResponse.json({ error: "Stripe not configured" }, { status: 501 })
  }

  const stripe = new Stripe(stripeSecretKey)

  let priceId: string
  let mode: "payment" | "subscription"
  let email: string | undefined

  try {
    const body = await req.json()
    priceId = body.priceId
    mode = body.mode
    email = body.email
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 })
  }

  if (!priceId || !mode) {
    return NextResponse.json({ error: "priceId and mode are required" }, { status: 400 })
  }

  // Try to get the authenticated user's email if not provided
  if (!email) {
    try {
      const supabase = await createClient()
      const { data: { user } } = await supabase.auth.getUser()
      email = user?.email
    } catch {
      // Not authenticated — proceed without email
    }
  }

  const { origin } = new URL(req.url)

  const session = await stripe.checkout.sessions.create({
    mode,
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: `${origin}/analyse?payment=success`,
    cancel_url: `${origin}/#pricing`,
    ...(email ? { customer_email: email } : {}),
  })

  return NextResponse.json({ url: session.url })
}

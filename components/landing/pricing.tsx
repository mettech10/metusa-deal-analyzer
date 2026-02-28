"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Check } from "lucide-react"
import { openCheckout } from "@/lib/paddle"

// ── Configure your Paddle price IDs ────────────────────────────────────
// Paddle Dashboard → Catalogue → Prices → copy the price ID (e.g. pri_xxx)
// Add to .env.local:
//   NEXT_PUBLIC_PADDLE_PRICE_PAY_PER_DEAL=pri_xxxxxxxxxxxxxxxx
//   NEXT_PUBLIC_PADDLE_PRICE_PRO=pri_xxxxxxxxxxxxxxxx
//   NEXT_PUBLIC_PADDLE_PRICE_UNLIMITED=pri_xxxxxxxxxxxxxxxx

const PRICE_IDS = {
  payPerDeal: process.env.NEXT_PUBLIC_PADDLE_PRICE_PAY_PER_DEAL ?? "",
  pro:        process.env.NEXT_PUBLIC_PADDLE_PRICE_PRO ?? "",
  unlimited:  process.env.NEXT_PUBLIC_PADDLE_PRICE_UNLIMITED ?? "",
}

const plans = [
  {
    name: "Free",
    price: "0",
    period: "forever",
    description: "Try it out with basic analysis",
    features: [
      "1 deal analysis per month",
      "Basic financial calculations",
      "SDLT calculator",
      "Gross yield calculation",
    ],
    cta: "Get Started Free",
    highlighted: false,
    priceId: null,
    href: "/analyse",
  },
  {
    name: "Pay Per Deal",
    price: "2.99",
    period: "per deal",
    description: "Perfect for occasional investors",
    features: [
      "Pay only when you analyse",
      "Full financial breakdown",
      "AI-powered insights",
      "Cash flow projections",
      "PDF report export",
    ],
    cta: "Buy a Credit",
    highlighted: false,
    priceId: PRICE_IDS.payPerDeal,
    href: null,
  },
  {
    name: "Pro",
    price: "19.99",
    period: "per month",
    description: "For serious property investors",
    features: [
      "Unlimited deal analyses",
      "Full AI-powered insights",
      "5-year projections",
      "PDF & Excel export",
      "Deal comparison tool",
      "Priority support",
    ],
    cta: "Go Pro",
    highlighted: true,
    priceId: PRICE_IDS.pro,
    href: null,
  },
  {
    name: "Unlimited",
    price: "49.99",
    period: "per month",
    description: "For teams and professionals",
    features: [
      "Everything in Pro",
      "Team collaboration",
      "API access",
      "Custom branding",
      "Dedicated account manager",
      "White-label reports",
    ],
    cta: "Go Unlimited",
    highlighted: false,
    priceId: PRICE_IDS.unlimited,
    href: null,
  },
]

function PlanButton({ plan }: { plan: (typeof plans)[number] }) {
  // Free plan — just navigate
  if (plan.href) {
    return (
      <Button
        asChild
        variant={plan.highlighted ? "default" : "outline"}
        className="w-full"
      >
        <Link href={plan.href}>{plan.cta}</Link>
      </Button>
    )
  }

  // Paid plan — open Paddle checkout overlay
  return (
    <Button
      variant={plan.highlighted ? "default" : "outline"}
      className="w-full"
      onClick={() => {
        if (!plan.priceId) {
          console.warn(
            `[Paddle] Price ID not yet configured for "${plan.name}". ` +
            `Add it to .env.local as NEXT_PUBLIC_PADDLE_PRICE_XXX`
          )
          alert(
            `Payment for "${plan.name}" is not yet activated.\n` +
            `Add your Paddle price ID to .env.local to enable checkout.`
          )
          return
        }
        openCheckout(plan.priceId)
      }}
    >
      {plan.cta}
    </Button>
  )
}

export function Pricing() {
  return (
    <section id="pricing" className="py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-balance text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Simple, Transparent Pricing
          </h2>
          <p className="mt-4 text-pretty text-lg leading-relaxed text-muted-foreground">
            Start free. Upgrade when you need more power.
          </p>
        </div>

        <div className="mt-16 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`relative flex flex-col rounded-xl border p-6 ${
                plan.highlighted
                  ? "border-primary/50 bg-primary/5 shadow-[0_0_30px_oklch(0.75_0.15_190_/_0.1)]"
                  : "border-border/50 bg-card"
              }`}
            >
              {plan.highlighted && (
                <Badge className="absolute -top-3 left-1/2 -translate-x-1/2">
                  Most Popular
                </Badge>
              )}

              <div className="mb-6">
                <h3 className="text-lg font-semibold text-foreground">{plan.name}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{plan.description}</p>
              </div>

              <div className="mb-6">
                <span className="text-3xl font-bold text-foreground">
                  {"£"}{plan.price}
                </span>
                <span className="text-sm text-muted-foreground">/{plan.period}</span>
              </div>

              <ul className="mb-8 flex flex-1 flex-col gap-3">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2.5 text-sm">
                    <Check className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span className="text-muted-foreground">{feature}</span>
                  </li>
                ))}
              </ul>

              <PlanButton plan={plan} />
            </div>
          ))}
        </div>

        <p className="mt-8 text-center text-xs text-muted-foreground">
          Payments processed securely by{" "}
          <span className="font-medium text-foreground">Paddle</span>. Cancel anytime.
        </p>
      </div>
    </section>
  )
}

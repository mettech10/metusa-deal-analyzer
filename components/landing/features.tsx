"use client"

import {
  Calculator,
  Home,
  TrendingUp,
  Wallet,
  PieChart,
  Sparkles,
} from "lucide-react"
import { motion } from "framer-motion"
import { ScrollReveal, StaggerContainer, StaggerItem, HoverCard } from "@/components/animations"

const features = [
  {
    icon: Calculator,
    title: "SDLT Calculator",
    description:
      "Accurate Stamp Duty calculations for England & NI, including the 5% additional property surcharge for buy-to-let investors.",
  },
  {
    icon: Home,
    title: "Mortgage Costs",
    description:
      "Calculate monthly payments for repayment or interest-only mortgages with customisable rates, terms, and deposit percentages.",
  },
  {
    icon: TrendingUp,
    title: "Rental Yield",
    description:
      "Instantly compute gross and net rental yields factoring in void periods, management fees, and all running costs.",
  },
  {
    icon: Wallet,
    title: "Cash Flow Projection",
    description:
      "See your monthly and annual cash flow after all expenses, with 5-year projections accounting for rent and capital growth.",
  },
  {
    icon: PieChart,
    title: "ROI Analysis",
    description:
      "Cash-on-cash returns, total capital required, and a complete breakdown of every cost from SDLT to refurbishment.",
  },
  {
    icon: Sparkles,
    title: "AI Insights",
    description:
      "Get an AI-generated deal score, strengths, risks, and a personalised recommendation to guide your investment decision.",
  },
]

export function Features() {
  return (
    <section id="features" className="py-24 md:py-32 relative overflow-hidden">
      <div className="mx-auto max-w-7xl px-6">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-balance text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Everything You Need to Evaluate a Deal
          </h2>
          <p className="mt-4 text-pretty text-lg leading-relaxed text-muted-foreground">
            From SDLT to AI-powered insights, get a comprehensive analysis of any
            UK property investment in seconds.
          </p>
        </ScrollReveal>

        <StaggerContainer className="mt-16 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <StaggerItem key={feature.title}>
              <HoverCard>
                <motion.div
                  className="group relative rounded-xl border border-border/50 bg-card p-6 transition-all hover:border-primary/30 hover:bg-card/80"
                  whileHover={{ y: -8 }}
                >
                  <motion.div 
                    className="mb-4 flex size-10 items-center justify-center rounded-lg bg-primary/10"
                    whileHover={{ rotate: [0, -10, 10, 0], scale: 1.1 }}
                    transition={{ duration: 0.5 }}
                  >
                    <feature.icon className="size-5 text-primary" />
                  </motion.div>

                  <h3 className="text-base font-semibold text-foreground group-hover:text-foreground transition-colors">
                    {feature.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground group-hover:text-muted-foreground transition-colors">
                    {feature.description}
                  </p>
                </motion.div>
              </HoverCard>
            </StaggerItem>
          ))}
        </StaggerContainer>
      </div>
    </section>
  )
}

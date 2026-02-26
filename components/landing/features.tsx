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
    color: "#D4AF37",
  },
  {
    icon: Home,
    title: "Mortgage Costs",
    description:
      "Calculate monthly payments for repayment or interest-only mortgages with customisable rates, terms, and deposit percentages.",
    color: "#60A5FA",
  },
  {
    icon: TrendingUp,
    title: "Rental Yield",
    description:
      "Instantly compute gross and net rental yields factoring in void periods, management fees, and all running costs.",
    color: "#34D399",
  },
  {
    icon: Wallet,
    title: "Cash Flow Projection",
    description:
      "See your monthly and annual cash flow after all expenses, with 5-year projections accounting for rent and capital growth.",
    color: "#F472B6",
  },
  {
    icon: PieChart,
    title: "ROI Analysis",
    description:
      "Cash-on-cash returns, total capital required, and a complete breakdown of every cost from SDLT to refurbishment.",
    color: "#A78BFA",
  },
  {
    icon: Sparkles,
    title: "AI Insights",
    description:
      "Get an AI-generated deal score, strengths, risks, and a personalised recommendation to guide your investment decision.",
    color: "#FBBF24",
  },
]

export function Features() {
  return (
    <section id="features" className="py-24 md:py-32 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 -z-10">
        <motion.div
          className="absolute top-20 left-10 w-72 h-72 rounded-full bg-[#D4AF37]/5 blur-3xl"
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{ duration: 8, repeat: Infinity }}
        />
        <motion.div
          className="absolute bottom-20 right-10 w-96 h-96 rounded-full bg-[#D4AF37]/5 blur-3xl"
          animate={{
            scale: [1.2, 1, 1.2],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{ duration: 8, repeat: Infinity, delay: 4 }}
        />
      </div>

      <div className="mx-auto max-w-7xl px-6">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            whileInView={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6 }}
            viewport={{ once: true }}
            className="inline-block mb-4"
          >
            <span className="text-[#D4AF37] text-sm font-semibold tracking-wider uppercase">Features</span>
          </motion.div>
          
          <h2 className="text-balance text-3xl font-bold tracking-tight text-foreground md:text-4xl lg:text-5xl">
            Everything You Need to{" "}
            <span className="text-[#D4AF37]">Evaluate a Deal</span>
          </h2>
          <p className="mt-4 text-pretty text-lg leading-relaxed text-muted-foreground">
            From SDLT to AI-powered insights, get a comprehensive analysis of any
            UK property investment in seconds.
          </p>
        </ScrollReveal>

        <StaggerContainer className="mt-16 grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {features.map((feature, index) => (
            <StaggerItem key={feature.title}>
              <HoverCard>
                <motion.div
                  className="group relative rounded-2xl border border-border/50 bg-card/50 p-6 backdrop-blur-sm overflow-hidden"
                  whileHover={{ 
                    borderColor: `${feature.color}50`,
                    backgroundColor: "rgba(27, 31, 59, 0.8)",
                  }}
                >
                  {/* Animated gradient border on hover */}
                  <motion.div
                    className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                    style={{
                      background: `linear-gradient(135deg, ${feature.color}20 0%, transparent 50%, ${feature.color}10 100%)`,
                    }}
                  />

                  {/* Icon with animation */}
                  <motion.div 
                    className="relative mb-4 flex size-12 items-center justify-center rounded-xl"
                    style={{ backgroundColor: `${feature.color}15` }}
                    whileHover={{ rotate: [0, -10, 10, 0], scale: 1.1 }}
                    transition={{ duration: 0.5 }}
                  >
                    <motion.div
                      animate={{ 
                        rotate: [0, 360],
                      }}
                      transition={{ 
                        duration: 20, 
                        repeat: Infinity, 
                        ease: "linear",
                        delay: index * 0.5 
                      }}
                    >
                      <feature.icon 
                        className="size-6" 
                        style={{ color: feature.color }}
                      />
                    </motion.div>
                  </motion.div>

                  <h3 className="relative text-lg font-semibold text-foreground group-hover:text-white transition-colors">
                    {feature.title}
                  </h3>
                  <p className="relative mt-2 text-sm leading-relaxed text-muted-foreground group-hover:text-white/80 transition-colors">
                    {feature.description}
                  </p>

                  {/* Corner accent */}
                  <motion.div
                    className="absolute -bottom-10 -right-10 w-20 h-20 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ backgroundColor: `${feature.color}20` }}
                    whileHover={{ scale: 2 }}
                  />
                </motion.div>
              </HoverCard>
            </StaggerItem>
          ))}
        </StaggerContainer>
      </div>
    </section>
  )
}

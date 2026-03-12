"use client"

import { ClipboardList, Cpu, FileText } from "lucide-react"
import { motion } from "framer-motion"
import { ScrollReveal, StaggerContainer, StaggerItem } from "@/components/animations"

const steps = [
  {
    step: "01",
    icon: ClipboardList,
    title: "Enter Property Details",
    description:
      "Input the purchase price, rental income, financing details, and running costs. Our smart form pre-fills typical UK defaults to save you time.",
  },
  {
    step: "02",
    icon: Cpu,
    title: "AI Analyses the Deal",
    description:
      "Our engine calculates SDLT, mortgage payments, yields, and cash flow instantly. Then AI reviews the numbers and compares against market benchmarks.",
  },
  {
    step: "03",
    icon: FileText,
    title: "Get Your Report",
    description:
      "Receive a comprehensive breakdown with charts, a deal score out of 100, identified strengths and risks, and a clear investment recommendation.",
  },
]

export function HowItWorks() {
  return (
    <section id="how-it-works" className="border-y border-border/50 bg-card/30 py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-balance text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Three Steps to a Smarter Investment
          </h2>
          <p className="mt-4 text-pretty text-lg leading-relaxed text-muted-foreground">
            No spreadsheets. No guesswork. Just clear, data-driven analysis.
          </p>
        </ScrollReveal>

        <StaggerContainer className="mt-16 grid grid-cols-1 gap-8 md:grid-cols-3">
          {steps.map((step, index) => (
            <StaggerItem key={step.step}>
              <motion.div 
                className="relative flex flex-col items-center text-center"
                whileHover={{ y: -10 }}
                transition={{ duration: 0.3 }}
              >
                {/* Connector line (desktop only) */}
                {index < steps.length - 1 && (
                  <div className="absolute left-[calc(50%+40px)] top-10 hidden h-px w-[calc(100%-80px)] bg-border/60 md:block" />
                )}

                {/* Step number badge */}
                <motion.div 
                  className="relative mb-6 flex size-20 items-center justify-center rounded-2xl border border-border/50 bg-card"
                  whileHover={{ scale: 1.1 }}
                  transition={{ duration: 0.3 }}
                >
                  <step.icon className="size-8 text-primary" />
                  
                  <motion.span 
                    className="absolute -right-2 -top-2 flex size-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground"
                    initial={{ scale: 0 }}
                    whileInView={{ scale: 1 }}
                    transition={{ type: "spring", stiffness: 500, damping: 30, delay: 0.3 + index * 0.2 }}
                    viewport={{ once: true }}
                  >
                    {step.step}
                  </motion.span>
                </motion.div>

                <h3 className="text-lg font-semibold text-foreground">{step.title}</h3>
                <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground">
                  {step.description}
                </p>
              </motion.div>
            </StaggerItem>
          ))}
        </StaggerContainer>
      </div>
    </section>
  )
}

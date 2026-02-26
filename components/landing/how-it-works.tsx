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
    <section id="how-it-works" className="border-y border-border/50 bg-card/30 py-24 md:py-32 relative overflow-hidden">
      {/* Background glow */}
      <div className="absolute inset-0 -z-10">
        <motion.div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-[#D4AF37]/5 blur-3xl"
          animate={{
            scale: [1, 1.1, 1],
            opacity: [0.2, 0.4, 0.2],
          }}
          transition={{ duration: 10, repeat: Infinity }}
        />
      </div>

      <div className="mx-auto max-w-7xl px-6">
        <ScrollReveal className="mx-auto max-w-2xl text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
            viewport={{ once: true }}
            className="inline-block mb-4"
          >
            <span className="text-[#D4AF37] text-sm font-semibold tracking-wider uppercase">Process</span>
          </motion.div>
          
          <h2 className="text-balance text-3xl font-bold tracking-tight text-foreground md:text-4xl lg:text-5xl">
            Three Steps to a{" "}
            <span className="text-[#D4AF37]">Smarter Investment</span>
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
                  <motion.div 
                    className="absolute left-[calc(50%+40px)] top-10 hidden h-px md:block"
                    style={{ 
                      width: "calc(100% - 80px)",
                      background: "linear-gradient(90deg, #D4AF37 0%, #D4AF37 50%, transparent 100%)",
                    }}
                    initial={{ scaleX: 0, originX: 0 }}
                    whileInView={{ scaleX: 1 }}
                    transition={{ duration: 1, delay: 0.5 + index * 0.3 }}
                    viewport={{ once: true }}
                  />
                )}

                {/* Step number badge */}
                <motion.div 
                  className="relative mb-6 flex size-20 items-center justify-center rounded-2xl border border-[#D4AF37]/30 bg-[#1B1F3B]"
                  whileHover={{ 
                    scale: 1.1,
                    boxShadow: "0 0 30px rgba(212, 175, 55, 0.3)",
                  }}
                  transition={{ duration: 0.3 }}
                >
                  <motion.div
                    animate={{ 
                      rotate: [0, 10, -10, 0],
                    }}
                    transition={{ 
                      duration: 4, 
                      repeat: Infinity, 
                      delay: index * 0.5,
                      ease: "easeInOut"
                    }}
                  >
                    <step.icon className="size-8 text-[#D4AF37]" />
                  </motion.div>
                  
                  {/* Step number badge */}
                  <motion.span 
                    className="absolute -right-2 -top-2 flex size-7 items-center justify-center rounded-full bg-[#D4AF37] text-xs font-bold text-[#1B1F3B]"
                    initial={{ scale: 0 }}
                    whileInView={{ scale: 1 }}
                    transition={{ 
                      type: "spring",
                      stiffness: 500,
                      damping: 30,
                      delay: 0.3 + index * 0.2 
                    }}
                    viewport={{ once: true }}
                  >
                    {step.step}
                  </motion.span>

                  {/* Pulse effect */}
                  <motion.div
                    className="absolute inset-0 rounded-2xl bg-[#D4AF37]/20"
                    animate={{
                      scale: [1, 1.2, 1],
                      opacity: [0.5, 0, 0.5],
                    }}
                    transition={{
                      duration: 2,
                      repeat: Infinity,
                      delay: index * 0.5,
                    }}
                  />
                </motion.div>

                <motion.h3 
                  className="text-lg font-semibold text-foreground"
                  initial={{ opacity: 0 }}
                  whileInView={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                  viewport={{ once: true }}
                >
                  {step.title}
                </motion.h3>
                <motion.p 
                  className="mt-2 max-w-xs text-sm leading-relaxed text-muted-foreground"
                  initial={{ opacity: 0 }}
                  whileInView={{ opacity: 1 }}
                  transition={{ delay: 0.4 }}
                  viewport={{ once: true }}
                >
                  {step.description}
                </motion.p>
              </motion.div>
            </StaggerItem>
          ))}
        </StaggerContainer>
      </div>
    </section>
  )
}

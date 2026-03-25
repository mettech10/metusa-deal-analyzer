"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ArrowRight, Sparkles } from "lucide-react"
import { motion } from "framer-motion"
import { ScrollReveal, PulseElement } from "@/components/animations"

export function CTA() {
  return (
    <section className="py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <ScrollReveal>
          <motion.div 
            className="relative overflow-hidden rounded-2xl border border-primary/20 bg-primary/5 px-8 py-16 text-center md:px-16 md:py-20"
            whileHover={{ scale: 1.01 }}
            transition={{ duration: 0.3 }}
          >
            {/* Glow effect */}
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,oklch(0.75_0.15_190_/_0.08)_0%,transparent_70%)]" />

            <div className="relative">
              <motion.div 
                className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary"
                initial={{ scale: 0.9, opacity: 0 }}
                whileInView={{ scale: 1, opacity: 1 }}
                transition={{ type: "spring", stiffness: 400, damping: 20 }}
                viewport={{ once: true }}
              >
                <motion.div
                  animate={{ rotate: [0, 20, -20, 0], scale: [1, 1.2, 1] }}
                  transition={{ duration: 2, repeat: Infinity }}
                >
                  <Sparkles className="size-4" />
                </motion.div>
                Launching Soon
              </motion.div>

              <motion.h2 
                className="text-balance text-3xl font-bold tracking-tight text-foreground md:text-4xl"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.2 }}
                viewport={{ once: true }}
              >
                Get Early Access to Metalyzi
              </motion.h2>

              <motion.p 
                className="mx-auto mt-4 max-w-xl text-pretty text-lg leading-relaxed text-muted-foreground"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.4 }}
                viewport={{ once: true }}
              >
                Join the waitlist for exclusive early access to AI-powered property deal analysis.
                Be the first to transform how you evaluate investment opportunities.
              </motion.p>

              <motion.div 
                className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.6 }}
                viewport={{ once: true }}
              >
                <PulseElement>
                  <Button asChild size="xl">
                    <Link href="/waitlist">
                      Join Waitlist
                      <motion.span
                        animate={{ x: [0, 5, 0] }}
                        transition={{ duration: 1.5, repeat: Infinity }}
                      >
                        <ArrowRight className="size-4 ml-2" />
                      </motion.span>
                    </Link>
                  </Button>
                </PulseElement>
                
                <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
                  <Button asChild size="xl" variant="outline">
                    <Link href="/analyse">
                      Try Demo
                    </Link>
                  </Button>
                </motion.div>
              </motion.div>
            </div>
          </motion.div>
        </ScrollReveal>
      </div>
    </section>
  )
}

"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ArrowRight, Sparkles } from "lucide-react"
import { motion } from "framer-motion"
import { ScrollReveal, PulseElement } from "@/components/animations"

export function CTA() {
  return (
    <section className="py-24 md:py-32 relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 -z-10">
        <motion.div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] rounded-full bg-[#D4AF37]/5 blur-3xl"
          animate={{
            scale: [1, 1.2, 1],
            opacity: [0.2, 0.4, 0.2],
          }}
          transition={{ duration: 8, repeat: Infinity }}
        />
      </div>

      <div className="mx-auto max-w-7xl px-6">
        <ScrollReveal>
          <motion.div 
            className="relative overflow-hidden rounded-3xl border border-[#D4AF37]/30 bg-gradient-to-br from-[#1B1F3B] via-[#1B1F3B] to-[#2d3561] px-8 py-16 text-center md:px-16 md:py-20 shadow-2xl shadow-[#D4AF37]/10"
            whileHover={{ 
              borderColor: "rgba(212, 175, 55, 0.5)",
              boxShadow: "0 25px 50px -12px rgba(212, 175, 55, 0.25)",
            }}
            transition={{ duration: 0.3 }}
          >
            {/* Animated gradient border */}
            <motion.div
              className="absolute inset-0 rounded-3xl"
              style={{
                background: "linear-gradient(135deg, transparent 40%, rgba(212, 175, 55, 0.1) 50%, transparent 60%)",
                backgroundSize: "200% 200%",
              }}
              animate={{
                backgroundPosition: ["0% 0%", "100% 100%", "0% 0%"],
              }}
              transition={{ duration: 5, repeat: Infinity, ease: "linear" }}
            />

            {/* Glow effect with animation */}
            <motion.div 
              className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,oklch(0.75_0.15_190_/_0.15)_0%,transparent_70%)]"
              animate={{
                scale: [1, 1.1, 1],
                opacity: [0.8, 1, 0.8],
              }}
              transition={{
                duration: 4,
                repeat: Infinity,
                ease: "easeInOut",
              }}
            />

            {/* Floating particles */}
            {[...Array(4)].map((_, i) => (
              <motion.div
                key={i}
                className="absolute w-2 h-2 rounded-full bg-[#D4AF37]/40"
                style={{
                  left: `${20 + i * 20}%`,
                  top: `${30 + (i % 2) * 40}%`,
                }}
                animate={{
                  y: [0, -20, 0],
                  opacity: [0.2, 0.6, 0.2],
                }}
                transition={{
                  duration: 3,
                  delay: i * 0.5,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
              />
            ))}

            <div className="relative">
              <motion.div 
                className="mb-4 inline-flex items-center gap-2 rounded-full border border-[#D4AF37]/30 bg-[#D4AF37]/10 px-4 py-1.5 text-sm font-medium text-[#D4AF37]"
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
                className="text-balance text-3xl font-bold tracking-tight text-white md:text-4xl lg:text-5xl"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.2 }}
                viewport={{ once: true }}
              >
                Get Early Access to{" "}
                <span className="text-[#D4AF37]">Metalyzi</span>
              </motion.h2>

              <motion.p 
                className="mx-auto mt-4 max-w-xl text-pretty text-lg leading-relaxed text-white/70"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.4 }}
                viewport={{ once: true }}
              >
                Join the waitlist for exclusive early access and 30% off the launch price.
                Be the first to analyse deals like a pro.
              </motion.p>

              <motion.div 
                className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.6 }}
                viewport={{ once: true }}
              >
                <PulseElement>
                  <Button asChild size="xl" className="bg-[#D4AF37] text-[#1B1F3B] hover:bg-[#D4AF37]/90 shadow-lg shadow-[#D4AF37]/30">
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
                  <Button asChild size="xl" variant="outline" className="border-white/30 hover:bg-white/10 text-white">
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

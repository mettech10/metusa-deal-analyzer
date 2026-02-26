"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ArrowRight, Sparkles } from "lucide-react"
import { motion } from "framer-motion"
import { 
  HeroText, 
  fadeInUp, 
  fadeInDown, 
  scaleIn, 
  staggerContainer,
  staggerItem,
  FloatingElement,
  PulseElement,
  AnimatedNumber,
  HoverCard 
} from "@/components/animations"

export function Hero() {
  return (
    <section className="relative overflow-hidden min-h-screen flex items-center justify-center">
      {/* Animated gradient background */}
      <motion.div
        className="absolute inset-0 -z-20"
        style={{
          background: "linear-gradient(135deg, #1B1F3B 0%, #2d3561 25%, #1B1F3B 50%, #3d4171 75%, #1B1F3B 100%)",
          backgroundSize: "400% 400%",
        }}
        animate={{
          backgroundPosition: ["0% 50%", "100% 50%", "0% 50%"],
        }}
        transition={{
          duration: 20,
          repeat: Infinity,
          ease: "linear",
        }}
      />

      {/* Grid background with pulse */}
      <motion.div
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          backgroundImage:
            "linear-gradient(to right, oklch(0.25 0.02 260 / 0.3) 1px, transparent 1px), linear-gradient(to bottom, oklch(0.25 0.02 260 / 0.3) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: [0.3, 0.5, 0.3] }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* Floating particles */}
      <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        {[...Array(6)].map((_, i) => (
          <div
            key={i}
            className="absolute"
            style={{
              left: `${15 + i * 15}%`,
              top: `${20 + (i % 3) * 25}%`,
            }}
          >
            <FloatingElement>
              <motion.div
                className="h-2 w-2 rounded-full bg-[#D4AF37]/30"
                animate={{
                  scale: [1, 1.5, 1],
                  opacity: [0.3, 0.6, 0.3],
                }}
                transition={{
                  duration: 3,
                  delay: i * 0.5,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
              />
            </FloatingElement>
          </div>
        ))}
      </div>

      {/* Radial glow with animation */}
      <motion.div 
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_center,oklch(0.75_0.15_190_/_0.15)_0%,transparent_70%)]"
        animate={{
          scale: [1, 1.1, 1],
          opacity: [0.8, 1, 0.8],
        }}
        transition={{
          duration: 6,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      <div className="relative mx-auto flex max-w-7xl flex-col items-center px-6 pb-24 pt-20 text-center md:pb-32 md:pt-28">
        {/* Animated Badge */}
        <motion.div
          initial={{ opacity: 0, y: -30, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
        >
          <Badge
            variant="outline"
            className="mb-6 gap-1.5 border-[#D4AF37]/50 bg-[#D4AF37]/10 px-4 py-1.5 text-[#D4AF37] shadow-lg shadow-[#D4AF37]/20"
          >
            <motion.div
              animate={{ rotate: [0, 15, -15, 0] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            >
              <Sparkles className="size-4" />
            </motion.div>
            AI-Powered Property Analysis
          </Badge>
        </motion.div>

        {/* Animated Headline */}
        <div className="max-w-4xl text-balance text-4xl font-bold tracking-tight text-foreground md:text-6xl lg:text-7xl">
          <HeroText text="Know Your Numbers" className="text-white" delay={0.4} />
          <motion.div
            initial={{ opacity: 0, x: -50 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 1.2, ease: [0.22, 1, 0.36, 1] }}
            className="text-[#D4AF37] mt-2"
          >
            Before You Invest
          </motion.div>
        </div>

        {/* Animated Subtitle */}
        <motion.p
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 1.6, ease: [0.22, 1, 0.36, 1] }}
          className="mt-6 max-w-2xl text-pretty text-lg leading-relaxed text-muted-foreground md:text-xl"
        >
          Analyse any UK property deal in seconds. Get instant SDLT calculations,
          rental yield, cash flow projections, and AI-powered investment insights
          that help you make smarter decisions.
        </motion.p>

        {/* Animated Buttons */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 2, ease: [0.22, 1, 0.36, 1] }}
          className="mt-10 flex flex-col items-center gap-4 sm:flex-row"
        >
          <PulseElement>
            <Button asChild size="xl" className="bg-[#D4AF37] text-[#1B1F3B] hover:bg-[#D4AF37]/90 shadow-lg shadow-[#D4AF37]/30">
              <Link href="/analyse">
                Analyse a Deal
                <motion.span
                  animate={{ x: [0, 5, 0] }}
                  transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                >
                  <ArrowRight className="size-4 ml-2" />
                </motion.span>
              </Link>
            </Button>
          </PulseElement>
          
          <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
            <Button asChild variant="outline" size="lg" className="border-white/30 hover:bg-white/10">
              <a href="#features">See How It Works</a>
            </Button>
          </motion.div>
        </motion.div>

        {/* Animated Stats Bar */}
        <motion.div
          initial={{ opacity: 0, y: 60 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 1, delay: 2.4, ease: [0.22, 1, 0.36, 1] }}
          className="mt-20 grid w-full max-w-3xl grid-cols-1 gap-8 rounded-2xl border border-[#D4AF37]/20 bg-[#1B1F3B]/60 backdrop-blur-md px-8 py-8 shadow-2xl shadow-[#D4AF37]/10 sm:grid-cols-3"
        >
          {[
            { value: 10000, suffix: "+", label: "Deals Analysed" },
            { value: 98, suffix: "%", label: "Calculation Accuracy" },
            { value: 4, suffix: "+ hrs", label: "Saved Per Deal" },
          ].map((stat, i) => (
            <motion.div
              key={i}
              className="flex flex-col items-center gap-2"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.5, delay: 2.6 + i * 0.2 }}
              whileHover={{ scale: 1.05, y: -5 }}
            >
              <span className="text-3xl font-bold text-[#D4AF37] md:text-4xl">
                {stat.value.toLocaleString()}{stat.suffix}
              </span>
              <span className="text-sm text-white/70 font-medium">{stat.label}</span>
            </motion.div>
          ))}
        </motion.div>

        {/* Scroll indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 3.5 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2"
        >
          <motion.div
            animate={{ y: [0, 10, 0] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            className="flex flex-col items-center gap-2"
          >
            <span className="text-xs text-white/50">Scroll to explore</span>
            <motion.div className="h-8 w-5 rounded-full border-2 border-white/30 flex justify-center pt-2">
              <motion.div
                animate={{ y: [0, 8, 0], opacity: [1, 0.3, 1] }}
                transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                className="h-1.5 w-1.5 rounded-full bg-[#D4AF37]"
              />
            </motion.div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  )
}

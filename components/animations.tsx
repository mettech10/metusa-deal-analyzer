"use client"

import { motion, useInView, Variants } from "framer-motion"
import { useRef, ReactNode } from "react"

// Bold, dynamic animation variants
export const fadeInUp: Variants = {
  hidden: { opacity: 0, y: 60 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] },
  },
}

export const fadeInDown: Variants = {
  hidden: { opacity: 0, y: -60 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] },
  },
}

export const fadeInLeft: Variants = {
  hidden: { opacity: 0, x: -60 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] },
  },
}

export const fadeInRight: Variants = {
  hidden: { opacity: 0, x: 60 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] },
  },
}

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.8 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  },
}

export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.15,
      delayChildren: 0.1,
    },
  },
}

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 40, scale: 0.95 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  },
}

export const floatAnimation = {
  y: [0, -15, 0],
  transition: {
    duration: 4,
    repeat: Infinity,
    ease: "easeInOut" as const,
  },
}

export const pulseAnimation = {
  scale: [1, 1.05, 1],
  transition: {
    duration: 2,
    repeat: Infinity,
    ease: "easeInOut" as const,
  },
}

export const shimmerAnimation = {
  backgroundPosition: ["-200% 0", "200% 0"],
  transition: {
    duration: 3,
    repeat: Infinity,
    ease: "linear",
  },
}

// Animated number counter
export function AnimatedNumber({ value, prefix = "", suffix = "" }: { value: number; prefix?: string; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const isInView = useInView(ref, { once: true, margin: "-100px" })

  return (
    <motion.span
      ref={ref}
      initial={{ opacity: 0, scale: 0.5 }}
      animate={isInView ? { opacity: 1, scale: 1 } : {}}
      transition={{ duration: 0.5, ease: "backOut" }}
      className="inline-block"
    >
      {prefix}{value}{suffix}
    </motion.span>
  )
}

// Scroll-triggered reveal component
export function ScrollReveal({ 
  children, 
  variants = fadeInUp,
  className = "",
  delay = 0 
}: { 
  children: ReactNode
  variants?: Variants
  className?: string
  delay?: number 
}) {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref, { once: true, margin: "-100px" })

  return (
    <motion.div
      ref={ref}
      initial="hidden"
      animate={isInView ? "visible" : "hidden"}
      variants={variants}
      className={className}
      style={{ transitionDelay: `${delay}s` }}
    >
      {children}
    </motion.div>
  )
}

// Stagger container for lists
export function StaggerContainer({ 
  children, 
  className = "" 
}: { 
  children: ReactNode
  className?: string 
}) {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref, { once: true, margin: "-50px" })

  return (
    <motion.div
      ref={ref}
      initial="hidden"
      animate={isInView ? "visible" : "hidden"}
      variants={staggerContainer}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// Stagger item for use inside StaggerContainer
export function StaggerItem({ 
  children, 
  className = "" 
}: { 
  children: ReactNode
  className?: string 
}) {
  return (
    <motion.div variants={staggerItem} className={className}>
      {children}
    </motion.div>
  )
}

// Floating animation wrapper
export function FloatingElement({ 
  children, 
  className = "" 
}: { 
  children: ReactNode
  className?: string 
}) {
  return (
    <motion.div
      animate={floatAnimation}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// Pulse animation for CTAs
export function PulseElement({ 
  children, 
  className = "" 
}: { 
  children: ReactNode
  className?: string 
}) {
  return (
    <motion.div
      animate={pulseAnimation}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// Hero text animation with character stagger
export function HeroText({ 
  text, 
  className = "",
  delay = 0 
}: { 
  text: string
  className?: string
  delay?: number 
}) {
  const words = text.split(" ")

  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: {
          transition: {
            staggerChildren: 0.08,
            delayChildren: delay,
          },
        },
      }}
      className={className}
    >
      {words.map((word, i) => (
        <motion.span
          key={i}
          variants={{
            hidden: { opacity: 0, y: 50, rotateX: -90 },
            visible: {
              opacity: 1,
              y: 0,
              rotateX: 0,
              transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
            },
          }}
          className="inline-block mr-[0.25em]"
          style={{ perspective: "1000px" }}
        >
          {word}
        </motion.span>
      ))}
    </motion.div>
  )
}

// Background gradient animation
export function AnimatedBackground() {
  return (
    <motion.div
      className="absolute inset-0 -z-10"
      style={{
        background: "linear-gradient(135deg, #1B1F3B 0%, #2d3561 25%, #1B1F3B 50%, #3d4171 75%, #1B1F3B 100%)",
        backgroundSize: "400% 400%",
      }}
      animate={{
        backgroundPosition: ["0% 50%", "100% 50%", "0% 50%"],
      }}
      transition={{
        duration: 15,
        repeat: Infinity,
        ease: "linear",
      }}
    />
  )
}

// Card hover animation
export function HoverCard({ 
  children, 
  className = "" 
}: { 
  children: ReactNode
  className?: string 
}) {
  return (
    <motion.div
      whileHover={{ 
        y: -8, 
        scale: 1.02,
        boxShadow: "0 20px 40px rgba(0,0,0,0.2)",
      }}
      whileTap={{ scale: 0.98 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// Magnetic button effect
export function MagneticButton({ 
  children, 
  className = "" 
}: { 
  children: ReactNode
  className?: string 
}) {
  return (
    <motion.button
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      transition={{ type: "spring", stiffness: 400, damping: 17 }}
      className={className}
    >
      {children}
    </motion.button>
  )
}

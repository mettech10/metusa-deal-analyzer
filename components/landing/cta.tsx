import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ArrowRight, Sparkles } from "lucide-react"

export function CTA() {
  return (
    <section className="py-24 md:py-32">
      <div className="mx-auto max-w-7xl px-6">
        <div className="relative overflow-hidden rounded-2xl border border-primary/20 bg-primary/5 px-8 py-16 text-center md:px-16 md:py-20">
          {/* Glow effect */}
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,oklch(0.75_0.15_190_/_0.08)_0%,transparent_70%)]" />

          <div className="relative">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary">
              <Sparkles className="size-4" />
              Launching Soon
            </div>
            <h2 className="text-balance text-3xl font-bold tracking-tight text-foreground md:text-4xl">
              Get Early Access to Metalyzi
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-pretty text-lg leading-relaxed text-muted-foreground">
              Join the waitlist for exclusive early access and 30% off the launch price.
              Be the first to analyse deals like a pro.
            </p>
            <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
              <Button asChild size="xl">
                <Link href="/waitlist">
                  Join Waitlist
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
              <Button asChild size="xl" variant="outline">
                <Link href="/analyse">
                  Try Demo
                </Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

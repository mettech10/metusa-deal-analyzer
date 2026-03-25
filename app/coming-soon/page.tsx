import Link from "next/link"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Mail } from "lucide-react"

export default function ComingSoonPage() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <Image
              src="/logo.png"
              alt="Metalyzi Logo"
              width={32}
              height={32}
              className="rounded-lg object-contain"
            />
            <span className="text-lg font-semibold tracking-tight text-foreground">
              Metalyzi
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="text-center">
          {/* Status Badge */}
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-4 py-2 text-sm font-medium text-primary">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-primary"></span>
            </span>
            Work in Progress
          </div>

          {/* Main Message */}
          <h1 className="mb-4 text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
            Something Amazing is Coming
          </h1>
          
          <p className="mx-auto mb-8 max-w-md text-lg text-muted-foreground">
            We're building the future of property deal analysis. 
            Join our waitlist to be the first to know when we launch.
          </p>

          {/* CTA Button */}
          <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Button asChild size="xl" className="w-full sm:w-auto">
              <Link href="/waitlist">
                <Mail className="mr-2 size-5" />
                Join the Waitlist
              </Link>
            </Button>
          </div>

          {/* Timeline */}
          <div className="mt-12 text-sm text-muted-foreground">
            <p>Expected Launch: Q3 2026</p>
            <p className="mt-1">Private Beta: Q2 2026</p>
          </div>
        </div>
      </main>
    </div>
  )
}
"use client"

import { useState } from "react"
import Link from "next/link"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ArrowLeft, Loader2, CheckCircle, Mail } from "lucide-react"

export default function WaitlistPage() {
  const [email, setEmail] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isSubmitted, setIsSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!email || !email.includes("@")) {
      setError("Please enter a valid email address")
      return
    }

    setIsLoading(true)

    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      })

      if (!res.ok) {
        throw new Error("Failed to join waitlist. Please try again.")
      }

      setIsSubmitted(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top Bar */}
      <header className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <Image
              src="/logo.png"
              alt="Metalyzi Logo"
              width={28}
              height={28}
              className="rounded-lg object-contain"
            />
            <span className="text-sm font-semibold text-foreground">
              Metalyzi
            </span>
          </Link>
          <Button asChild variant="ghost" size="sm">
            <Link href="/">
              <ArrowLeft className="size-3.5" />
              Back
            </Link>
          </Button>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          {!isSubmitted ? (
            <>
              {/* Header */}
              <div className="mb-8 text-center">
                <div className="mx-auto mb-4 flex size-16 items-center justify-center rounded-2xl bg-primary/10">
                  <Mail className="size-8 text-primary" />
                </div>
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
                  Join the Waitlist
                </h1>
                <p className="mt-3 text-muted-foreground">
                  Get early access to Metalyzi and be the first to experience AI-powered property deal analysis.
                </p>
              </div>

              {/* Benefits */}
              <div className="mb-8 rounded-xl border border-border/50 bg-card/50 p-5">
                <h3 className="mb-3 text-sm font-semibold text-foreground">
                  What you&apos;ll get:
                </h3>
                <ul className="space-y-2.5 text-sm text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <CheckCircle className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span>Early access 48 hours before public launch</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span>Direct input on product features and roadmap</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span>Sample deal analysis reports and guides</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle className="mt-0.5 size-4 shrink-0 text-primary" />
                    <span>Exclusive property investment insights newsletter</span>
                  </li>
                </ul>
              </div>

              {/* Form */}
              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="email" className="text-sm font-medium text-foreground">
                    Email Address
                  </Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={isLoading}
                    className="h-12"
                  />
                </div>

                {error && (
                  <p className="text-sm text-destructive">{error}</p>
                )}

                <Button type="submit" size="xl" className="w-full" disabled={isLoading}>
                  {isLoading ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      Joining...
                    </>
                  ) : (
                    "Join Waitlist"
                  )}
                </Button>
              </form>

              <p className="mt-6 text-center text-xs text-muted-foreground">
                No spam. Unsubscribe anytime. We respect your privacy.
              </p>
            </>
          ) : (
            /* Success State */
            <div className="text-center">
              <div className="mx-auto mb-6 flex size-20 items-center justify-center rounded-full bg-primary/10">
                <CheckCircle className="size-10 text-primary" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground">
                You&apos;re on the list!
              </h1>
              <p className="mt-3 text-muted-foreground">
                Thanks for joining. We&apos;ll email you at{" "}
                <span className="font-medium text-foreground">{email}</span> when Metalyzi
                is ready.
              </p>
              <div className="mt-8">
                <Button asChild variant="outline" size="lg" className="w-full">
                  <Link href="/">Back to Home</Link>
                </Button>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

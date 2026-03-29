"use client"

import { useState, Suspense } from "react"
import Link from "next/link"
import Image from "next/image"
import { useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { ArrowLeft, Mail, Loader2, CheckCircle2 } from "lucide-react"
import { Separator } from "@/components/ui/separator"

function VerifyEmailContent() {
  const searchParams = useSearchParams()
  const email = searchParams.get("email") ?? ""

  const [loading, setLoading] = useState(false)
  const [resent, setResent] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleResend() {
    setError(null)
    setLoading(true)
    try {
      const res = await fetch("/api/auth/resend-verification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || "Failed to resend")
      }
      setResent(true)
    } catch (err: any) {
      setError(err.message || "Failed to send. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top bar */}
      <header className="border-b border-border/50 bg-background/80 backdrop-blur-xl">
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
            <Link href="/login">
              <ArrowLeft className="size-3.5" />
              Back to login
            </Link>
          </Button>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-md text-center">
          {/* Icon */}
          <div className="mx-auto mb-6 flex size-16 items-center justify-center rounded-full bg-primary/10">
            <Mail className="size-8 text-primary" />
          </div>

          {/* Heading */}
          <h1 className="mb-3 text-2xl font-bold tracking-tight text-foreground">
            Verify your email address
          </h1>

          {/* Subtext */}
          <p className="mb-2 text-sm text-muted-foreground leading-relaxed">
            {email ? (
              <>
                We&apos;ve sent a verification link to{" "}
                <span className="font-medium text-foreground">{email}</span>.
              </>
            ) : (
              "We've sent a verification link to your email address."
            )}
            {" "}Please check your inbox and click the link to activate your account.
          </p>

          <p className="mb-8 text-xs text-muted-foreground">
            Didn&apos;t receive it? Check your spam folder or use the button below.
          </p>

          <Separator className="mb-8" />

          {/* Resend section */}
          {resent ? (
            <div className="flex items-center justify-center gap-2 rounded-lg border border-border/50 bg-card px-4 py-3 text-sm text-foreground">
              <CheckCircle2 className="size-4 text-primary" />
              Verification email resent successfully.
            </div>
          ) : (
            <>
              {error && (
                <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              )}
              <Button
                onClick={handleResend}
                disabled={loading || !email}
                size="lg"
                className="w-full"
              >
                {loading ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Sending...
                  </>
                ) : (
                  "Resend Email"
                )}
              </Button>
              <p className="mt-3 text-xs text-muted-foreground">
                Still having trouble?{" "}
                <a
                  href="mailto:support@metalyzi.co.uk"
                  className="text-primary hover:underline"
                >
                  Contact support
                </a>
              </p>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function VerifyEmailLoading() {
  return (
    <div className="flex min-h-screen flex-col bg-background items-center justify-center">
      <div className="flex items-center gap-2">
        <Loader2 className="size-6 animate-spin text-primary" />
        <span className="text-muted-foreground">Loading...</span>
      </div>
    </div>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<VerifyEmailLoading />}>
      <VerifyEmailContent />
    </Suspense>
  )
}

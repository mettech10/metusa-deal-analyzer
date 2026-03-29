"use client"

import { useState } from "react"
import Link from "next/link"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { XCircle, Loader2, CheckCircle2 } from "lucide-react"
import { toast } from "sonner"

export default function VerificationFailedPage() {
  const [email, setEmail] = useState("")
  const [loading, setLoading] = useState(false)
  const [resent, setResent] = useState(false)

  async function resendVerification() {
    if (!email) {
      toast.error("Please enter your email")
      return
    }

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
      toast.success("Verification email sent!")
    } catch (error: any) {
      toast.error(error.message || "Failed to send")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4 bg-background">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2">
            <Image src="/logo.png" alt="Metalyzi" width={48} height={48} />
          </div>
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
            <XCircle className="h-8 w-8 text-destructive" />
          </div>
          <CardTitle className="text-2xl">Verification Failed</CardTitle>
          <CardDescription>
            This link may have expired or already been used. Please request a new verification email.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {resent ? (
            <div className="flex items-center justify-center gap-2 rounded-lg bg-green-500/10 p-4 text-green-500">
              <CheckCircle2 className="h-5 w-5" />
              <span>Verification email sent!</span>
            </div>
          ) : (
            <div className="space-y-2">
              <Input
                type="email"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Button
                onClick={resendVerification}
                disabled={loading}
                className="w-full"
              >
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Sending...
                  </>
                ) : (
                  "Resend Verification Email"
                )}
              </Button>
            </div>
          )}

          <Button asChild variant="outline" className="w-full">
            <Link href="/login">Back to Login</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

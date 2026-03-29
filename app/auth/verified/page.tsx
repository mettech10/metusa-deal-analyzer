"use client"

import Link from "next/link"
import { CheckCircle2 } from "lucide-react"
import { Button } from "@/components/ui/button"

export default function VerifiedPage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4 bg-background">
      <div className="w-full max-w-md text-center space-y-6">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-500/10">
          <CheckCircle2 className="h-8 w-8 text-green-500" />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">Verification Successful!</h1>
          <p className="text-sm text-muted-foreground">
            Your email has been verified. You can now log in to your Metalyzi account.
          </p>
        </div>
        <p className="text-sm text-muted-foreground">
          A welcome email has been sent to your inbox with everything you need to get started.
        </p>
        <div className="space-y-3">
          <Button asChild className="w-full">
            <Link href="/login">Log In</Link>
          </Button>
          <Button asChild variant="outline" className="w-full">
            <Link href="/">Go Back</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}

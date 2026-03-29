"use client"

import Link from "next/link"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { ArrowLeft } from "lucide-react"

function CheckIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className="size-8 text-primary"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" opacity="0.3" />
      <path
        d="M7.5 12.5l3 3 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function VerificationSuccessPage() {
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
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-md text-center">
          {/* Logo */}
          <div className="mx-auto mb-6 flex size-16 items-center justify-center rounded-xl bg-primary/10">
            <Image
              src="/logo.png"
              alt="Metalyzi Logo"
              width={48}
              height={48}
              className="rounded-lg object-contain"
            />
          </div>

          {/* Success icon */}
          <div className="mx-auto mb-6 flex size-14 items-center justify-center rounded-full bg-primary/10">
            <CheckIcon />
          </div>

          {/* Heading */}
          <h1 className="mb-3 text-2xl font-bold tracking-tight text-foreground">
            Email verified successfully
          </h1>

          {/* Subtext */}
          <p className="mb-8 text-sm text-muted-foreground leading-relaxed">
            Your Metalyzi account is now active. You&apos;re ready to start
            analysing property deals.
          </p>

          {/* CTA */}
          <Button asChild size="lg" className="w-full">
            <Link href="/login">Log In</Link>
          </Button>
        </div>
      </main>
    </div>
  )
}

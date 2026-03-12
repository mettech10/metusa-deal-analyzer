"use client"

import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Menu, X, User, LogOut } from "lucide-react"
import { signOut } from "@/app/auth/actions"

interface NavbarProps {
  user?: { email?: string; name?: string } | null
}

export function Navbar({ user }: NavbarProps) {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/50 bg-background/80 backdrop-blur-xl">
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary">
            <svg viewBox="0 0 56 52" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              {/* Accent dash */}
              <line x1="3" y1="14" x2="10" y2="11" strokeWidth="2.5"/>
              {/* Building 1: hollow box */}
              <rect x="3" y="24" width="9" height="22" rx="0.8"/>
              {/* Building 2: tall */}
              <rect x="15" y="10" width="5" height="36" rx="0.8"/>
              {/* Building 3: medium */}
              <rect x="23" y="16" width="5" height="30" rx="0.8"/>
              {/* D-arc right */}
              <line x1="31" y1="8" x2="31" y2="46"/>
              <path d="M31 8 Q53 8 53 27 Q53 46 31 46"/>
            </svg>
          </div>
          <span className="text-lg font-semibold tracking-tight text-foreground">
            Metalyzi
          </span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden items-center gap-8 md:flex">
          <a
            href="#features"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Features
          </a>
          <a
            href="#how-it-works"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            How It Works
          </a>
          <a
            href="#pricing"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Pricing
          </a>
          <Link
            href="/waitlist"
            className="text-sm font-medium text-primary transition-colors hover:text-primary/80"
          >
            Waitlist
          </Link>
        </div>

        {/* Desktop auth area */}
        <div className="hidden items-center gap-3 md:flex">
          {user ? (
            <>
              <Button asChild size="default">
                <Link href="/analyse">Analyse a Deal</Link>
              </Button>
              <div className="flex items-center gap-2 rounded-md border border-border/50 bg-card px-3 py-1.5">
                <div className="flex size-6 items-center justify-center rounded-full bg-primary/20">
                  <User className="size-3 text-primary" />
                </div>
                <span className="max-w-[120px] truncate text-xs text-muted-foreground">
                  {user.name || user.email}
                </span>
              </div>
              <form action={signOut}>
                <Button variant="ghost" size="sm" type="submit">
                  <LogOut className="size-3.5" />
                  <span className="sr-only">Sign out</span>
                </Button>
              </form>
            </>
          ) : (
            <Button asChild size="default" variant="outline">
              <Link href="/login">
                <User className="size-4" />
                Log In / Sign Up
              </Link>
            </Button>
          )}
        </div>

        {/* Mobile toggle */}
        <button
          type="button"
          className="text-foreground md:hidden"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle menu"
        >
          {mobileOpen ? (
            <X className="size-5" />
          ) : (
            <Menu className="size-5" />
          )}
        </button>
      </nav>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="border-t border-border/50 bg-background px-6 py-4 md:hidden">
          <div className="flex flex-col gap-4">
            <a
              href="#features"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setMobileOpen(false)}
            >
              Features
            </a>
            <a
              href="#how-it-works"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setMobileOpen(false)}
            >
              How It Works
            </a>
            <a
              href="#pricing"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setMobileOpen(false)}
            >
              Pricing
            </a>
            <Link
              href="/waitlist"
              className="text-sm font-medium text-primary transition-colors hover:text-primary/80"
              onClick={() => setMobileOpen(false)}
            >
              Join Waitlist
            </Link>

            {user ? (
              <>
                <div className="flex items-center gap-2 py-1 text-sm text-muted-foreground">
                  <User className="size-3.5" />
                  <span className="truncate">
                    {user.name || user.email}
                  </span>
                </div>
                <Button
                  asChild
                  size="default"
                  className="w-full"
                  onClick={() => setMobileOpen(false)}
                >
                  <Link href="/analyse">Analyse a Deal</Link>
                </Button>
                <form action={signOut}>
                  <Button
                    variant="outline"
                    size="default"
                    className="w-full"
                    type="submit"
                  >
                    <LogOut className="size-4" />
                    Sign Out
                  </Button>
                </form>
              </>
            ) : (
              <Button
                asChild
                size="default"
                variant="outline"
                className="w-full"
              >
                <Link href="/login">
                  <User className="size-4" />
                  Log In / Sign Up
                </Link>
              </Button>
            )}
          </div>
        </div>
      )}
    </header>
  )
}

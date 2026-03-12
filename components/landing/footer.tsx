
export function Footer() {
  return (
    <footer className="border-t border-border/50 py-12">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-6 px-6 md:flex-row">
        <div className="flex items-center gap-2.5">
          <div className="flex size-7 items-center justify-center rounded-lg bg-primary">
            <svg viewBox="0 0 56 52" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
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
          <span className="text-sm font-semibold text-foreground">Metalyzi</span>
        </div>
        <div className="flex items-center gap-6">
          <a
            href="#features"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Features
          </a>
          <a
            href="#pricing"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Pricing
          </a>
          <a
            href="#"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Privacy
          </a>
          <a
            href="#"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Terms
          </a>
        </div>
        <p className="text-xs text-muted-foreground">
          {"© 2026 Metalyzi. All rights reserved."}
        </p>
      </div>
    </footer>
  )
}

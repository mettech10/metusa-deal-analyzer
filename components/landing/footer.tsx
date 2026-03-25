import Image from "next/image"

export function Footer() {
  return (
    <footer className="border-t border-border/50 py-12">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-6 px-6 md:flex-row">
        <div className="flex items-center gap-2.5">
          <Image
            src="/logo.png"
            alt="Metalyzi Logo"
            width={28}
            height={28}
            className="rounded-lg object-contain"
          />
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
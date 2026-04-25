"use client"

import { useState, useCallback, useEffect } from "react"
import dynamic from "next/dynamic"
import { createClient as createSupabaseClient } from "@/lib/supabase/client"
import {
  checkArticle4,
  type Article4CheckResult,
} from "@/lib/article4-service"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Separator } from "@/components/ui/separator"
import { DealScore } from "./deal-score"
import { DevelopmentResults } from "./development-results"
import { PropertyComparables } from "./property-comparables"
import { HmoComparables } from "./hmo-comparables"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
} from "recharts"
import type { PropertyFormData, CalculationResults, BackendResults, RiskFlag, RegionalBenchmark, SensitivityResult } from "@/lib/types"
import { formatCurrency, formatPercent, calculateDealScore } from "@/lib/calculations"
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  PoundSterling,
  Home,
  Percent,
  AlertTriangle,
  CheckCircle2,
  Sparkles,
  Loader2,
  MapPin,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  BarChart3,
  Hammer,
  Building2,
  Users,
  Flag,
  BarChart2,
  SlidersHorizontal,
  Info,
} from "lucide-react"

interface AnalysisResultsProps {
  data: PropertyFormData
  results: CalculationResults
  aiText: string
  aiLoading: boolean
  backendData?: BackendResults | null
}

const CHART_COLORS = [
  "oklch(0.75 0.15 190)",
  "oklch(0.7 0.15 160)",
  "oklch(0.75 0.12 85)",
  "oklch(0.65 0.15 250)",
  "oklch(0.65 0.12 310)",
]

function MetricCard({
  label,
  value,
  sub,
  positive,
  icon: Icon,
}: {
  label: string
  value: string
  sub?: string
  positive?: boolean
  icon: React.ElementType
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border/50 bg-card p-4">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
        <Icon className="size-4 text-primary" />
      </div>
      <div className="flex flex-col gap-0.5">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span
          className={`text-lg font-semibold ${
            positive === true
              ? "text-success"
              : positive === false
              ? "text-destructive"
              : "text-foreground"
          }`}
        >
          {value}
        </span>
        {sub && <span className="text-xs text-muted-foreground">{sub}</span>}
      </div>
    </div>
  )
}

function parseAIAnalysis(text: string) {
  const dealScoreMatch =
    text.match(/Deal Score:\s*(\d+)/i) ||
    text.match(/⭐\s*SCORE:\s*(\d+)/i) ||
    text.match(/SCORE:\s*(\d+)/i)
  const score = dealScoreMatch ? parseInt(dealScoreMatch[1], 10) : null

  const sections: { heading: string; content: string }[] = []
  const lines = text.split("\n")
  let currentHeading = ""
  let currentContent: string[] = []

  for (const line of lines) {
    const headingMatch = line.match(/^#+\s+(.+)/) || line.match(/^\*\*(.+?)\*\*/)
    if (headingMatch) {
      if (currentHeading) {
        sections.push({ heading: currentHeading, content: currentContent.join("\n").trim() })
      }
      currentHeading = headingMatch[1].replace(/\*\*/g, "").trim()
      currentContent = []
    } else {
      currentContent.push(line)
    }
  }
  if (currentHeading) {
    sections.push({ heading: currentHeading, content: currentContent.join("\n").trim() })
  }

  return { score, sections, rawText: text }
}

// ── Verdict Banner ─────────────────────────────────────────────────────────
function VerdictBanner({
  verdict,
  score,
  label,
}: {
  verdict?: string
  score?: number
  label?: string
}) {
  if (!verdict) return null

  const config =
    {
      PROCEED: {
        bg: "bg-success/10 border-success/30",
        text: "text-success",
        badge: "bg-success/20 text-success border-success/30",
        icon: <CheckCircle2 className="size-5" />,
        title: "Proceed",
        desc: "This deal meets investment targets. Strong fundamentals.",
      },
      REVIEW: {
        bg: "bg-warning/10 border-warning/30",
        text: "text-warning",
        badge: "bg-warning/20 text-warning border-warning/30",
        icon: <AlertTriangle className="size-5" />,
        title: "Review",
        desc: "Borderline deal. Investigate further before committing.",
      },
      AVOID: {
        bg: "bg-destructive/10 border-destructive/30",
        text: "text-destructive",
        badge: "bg-destructive/20 text-destructive border-destructive/30",
        icon: <ShieldAlert className="size-5" />,
        title: "Avoid",
        desc: "Numbers don't stack up. High risk or poor returns.",
      },
    }[verdict] ?? {
      bg: "bg-muted/40 border-border/50",
      text: "text-foreground",
      badge: "bg-muted text-foreground border-border",
      icon: null,
      title: verdict,
      desc: "",
    }

  return (
    <div className={`flex items-center gap-4 rounded-xl border px-5 py-4 ${config.bg}`}>
      <div className={config.text}>{config.icon}</div>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className={`text-lg font-bold ${config.text}`}>{config.title}</span>
          {label && (
            <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${config.badge}`}>
              {label}
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground">{config.desc}</p>
      </div>
      {score !== undefined && (
        <div className="text-right">
          <div className={`text-3xl font-bold ${config.text}`}>{score}</div>
          <div className="text-xs text-muted-foreground">/ 100</div>
        </div>
      )}
    </div>
  )
}

// ── Location Card ──────────────────────────────────────────────────────────
function LocationCard({ location }: { location?: BackendResults["location"] }) {
  if (!location?.council && !location?.region) return null
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <MapPin className="size-4 text-primary" />
          <CardTitle className="text-sm">Location & Council</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-6 text-sm">
          {location.country && (
            <div>
              <span className="text-muted-foreground">Country </span>
              <span className="font-medium">{location.country}</span>
            </div>
          )}
          {location.region && (
            <div>
              <span className="text-muted-foreground">Region </span>
              <span className="font-medium">{location.region}</span>
            </div>
          )}
          {location.council && (
            <div>
              <span className="text-muted-foreground">Council </span>
              <span className="font-medium">{location.council}</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Article 4 Card ─────────────────────────────────────────────────────────
//
// Queries the Metalyzi Supabase `article4_areas` table via the browser
// anon client. Falls back to the Flask backend's legacy `article_4`
// advice text when the lookup can't resolve the postcode.
//
// Embeds a compact Leaflet mini-map (200px) showing the council centres
// for matched areas — loaded via next/dynamic so Leaflet doesn't touch
// `window` during SSR.
const Article4MiniMap = dynamic(
  () => import("@/components/article4/Article4Map"),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-[200px] w-full items-center justify-center rounded-lg bg-muted text-xs text-muted-foreground">
        Loading map…
      </div>
    ),
  }
)

// Planning-route guidance keyed off the development construction type.
// New-build / extension almost always need Full Planning Permission;
// conversions may have permitted-development rights via Class MA (commercial→
// residential) or Class Q (agricultural→residential) but with strict criteria;
// refurbishment alone is typically minor works only.
const DEV_PLANNING_ROUTE: Record<
  string,
  { label: string; route: string; detail: string; tone: "info" | "warn" }
> = {
  "new-build-traditional": {
    label: "New build (traditional)",
    route: "Full Planning Permission required",
    detail:
      "Greenfield/brownfield new-build typically requires a full PP application (8–13 weeks at the LPA, longer if called in). Budget design+planning fees of 6–10% of build cost and expect S106 / CIL contributions on schemes of 10+ units.",
    tone: "warn",
  },
  "new-build-timber-frame": {
    label: "New build (timber frame)",
    route: "Full Planning Permission required",
    detail:
      "Same PP route as traditional new-build — the structural method does not change planning consent requirements. NHBC / LABC warranty cover is essential for lender acceptance on resale.",
    tone: "warn",
  },
  "new-build-modular": {
    label: "New build (modular / MMC)",
    route: "Full Planning Permission required",
    detail:
      "Modular construction follows the standard PP route. Some LPAs view MMC favourably for sustainability scoring, but condition discharge can still trigger delays — confirm cladding and fire-safety standards (Building Safety Act) at submission.",
    tone: "warn",
  },
  conversion: {
    label: "Change-of-use conversion",
    route: "Possible Permitted Development (Class MA / Class Q) — verify",
    detail:
      "Commercial→residential conversions may use Class MA (E-class to C3) with a Prior Approval, subject to size cap (≤1,500 m² per building) and 2-year vacancy rule. Agricultural→residential uses Class Q (≤5 dwellings, ≤865 m²). Many LPAs have removed PD rights via Article 4 — always run a Prior Approval check before exchanging.",
    tone: "info",
  },
  extension: {
    label: "Extension / upward development",
    route: "Householder PP or Class A/AA Permitted Development",
    detail:
      "Single-storey rear extensions may fall under Class A PD (subject to size limits and neighbour consultation). Upward extensions (Class AA) allow 1–2 storeys on existing dwellings with Prior Approval. Anything outside these envelopes needs full Householder PP.",
    tone: "info",
  },
  refurbishment: {
    label: "Internal refurbishment",
    route: "Building Regs only (typically no planning needed)",
    detail:
      "Pure internal refurb without change of use, external alteration, or extension generally needs only Building Regulations approval. Listed buildings, conservation areas, and HMO conversions (C3→C4) override this — verify locally.",
    tone: "info",
  },
}

function Article4Card({
  postcode,
  legacy,
  investmentType,
  devConstructionType,
}: {
  postcode?: string
  legacy?: BackendResults["article_4"]
  investmentType?: string
  devConstructionType?: string
}) {
  const [result, setResult] = useState<Article4CheckResult | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    if (!postcode) {
      setLoading(false)
      return
    }
    ;(async () => {
      try {
        const supabase = createSupabaseClient()
        const r = await checkArticle4(supabase, postcode)
        if (!cancelled) setResult(r)
      } catch {
        // Fail-soft — keep result null, fall through to legacy/unknown.
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [postcode])

  // Derive a 3-state display: active / proposed / clear / unknown.
  // A missing result (no postcode or lookup failed) → unknown.
  const status: "active" | "proposed" | "clear" | "unknown" = !result
    ? "unknown"
    : result.status === "active"
    ? "active"
    : result.status === "proposed"
    ? "proposed"
    : result.status === "none"
    ? "clear"
    : "unknown"

  const cfg = {
    active: {
      bg: "bg-destructive/10 border-destructive/30",
      badgeCls: "bg-destructive/20 text-destructive border-destructive/40",
      icon: <ShieldAlert className="size-4 text-destructive" />,
      label: "Article 4 in Force",
      titleCls: "text-destructive",
    },
    proposed: {
      bg: "bg-warning/10 border-warning/30",
      badgeCls: "bg-warning/20 text-warning border-warning/40",
      icon: <ShieldAlert className="size-4 text-warning" />,
      label: "Article 4 Proposed",
      titleCls: "text-warning",
    },
    unknown: {
      bg: "bg-warning/10 border-warning/30",
      badgeCls: "bg-warning/20 text-warning border-warning/40",
      icon: <ShieldQuestion className="size-4 text-warning" />,
      label: "Status Unconfirmed",
      titleCls: "text-warning",
    },
    clear: {
      bg: "bg-success/10 border-success/30",
      badgeCls: "bg-success/20 text-success border-success/40",
      icon: <ShieldCheck className="size-4 text-success" />,
      label: "No Article 4 Restrictions",
      titleCls: "text-success",
    },
  }[status]

  const showMap =
    status === "active" || status === "proposed"
      ? result?.areas.some(
          (a) =>
            a.approximateCenterLat != null && a.approximateCenterLng != null
        )
      : false

  const subject =
    showMap && result
      ? (() => {
          const first = result.areas.find(
            (a) =>
              a.approximateCenterLat != null && a.approximateCenterLng != null
          )
          return first
            ? {
                lat: first.approximateCenterLat as number,
                lng: first.approximateCenterLng as number,
                label: `${result.district ?? ""} area`,
              }
            : null
        })()
      : null

  return (
    <Card className={`border ${cfg.bg}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          {cfg.icon}
          <CardTitle className={`text-sm ${cfg.titleCls}`}>
            Article 4 & Planning
          </CardTitle>
          <span
            className={`ml-auto rounded-full border px-2 py-0.5 text-xs font-medium ${cfg.badgeCls}`}
          >
            {cfg.label}
          </span>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {loading && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            Checking Article 4 database…
          </div>
        )}

        {!loading && result && (
          <p className="text-foreground">{result.summary}</p>
        )}

        {!loading && !result && legacy?.note && (
          <p className="text-muted-foreground">{legacy.note}</p>
        )}

        {/* Matched council areas */}
        {!loading && result && result.areas.length > 0 && (
          <div className="flex flex-col gap-2">
            {result.areas.map((a) => (
              <div
                key={a.id}
                className="rounded-lg border bg-card p-3 text-xs"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-foreground">
                    {a.councilName}
                  </p>
                  <span
                    className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase ${
                      a.status === "active"
                        ? "bg-destructive/20 text-destructive border-destructive/40"
                        : "bg-warning/20 text-warning border-warning/40"
                    }`}
                  >
                    {a.status}
                  </span>
                </div>
                {a.directionType && (
                  <p className="mt-1 text-muted-foreground">
                    {a.directionType}
                  </p>
                )}
                {a.impactDescription && (
                  <p className="mt-1 text-muted-foreground">
                    {a.impactDescription}
                  </p>
                )}
                {a.effectiveDate && a.status === "active" && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Effective: {a.effectiveDate}
                  </p>
                )}
                {a.consultationEndDate && a.status !== "active" && (
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Consultation ends: {a.consultationEndDate}
                  </p>
                )}
                {a.councilPlanningUrl && (
                  <a
                    href={a.councilPlanningUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                  >
                    View council planning page ↗
                  </a>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Embedded mini-map for active/proposed */}
        {!loading && showMap && subject && (
          <div className="rounded-lg overflow-hidden border">
            <Article4MiniMap
              subject={subject}
              height={200}
              compact
            />
          </div>
        )}

        {/* HMO guidance — show only when active and strategy is HMO-relevant.
            For development schemes we suppress this in favour of the
            construction-type-specific Development Planning Route block below. */}
        {status === "active" && investmentType !== "development" && (
          <div className="rounded-lg bg-card p-3">
            <p className="mb-1 text-xs font-semibold text-foreground">
              HMO Guidance
            </p>
            <p className="text-muted-foreground">
              C3→C4 HMO conversion in this area requires full planning
              permission — not permitted development. Budget for an 8–13
              week planning application and additional professional fees.
              Consider an alternative strategy (BTL, supported housing) or
              a different postcode.
            </p>
          </div>
        )}

        {/* Development Planning Route — only shown for development schemes.
            Maps the user's selected devConstructionType to the most likely
            consent pathway (Full PP, Class MA / Class Q PD, householder PD,
            or Building Regs-only) so the investor sees the right call before
            committing capital. Article 4 status above takes precedence: an
            active direction can strip back PD rights even on conversions. */}
        {!loading && investmentType === "development" && (() => {
          const route =
            (devConstructionType && DEV_PLANNING_ROUTE[devConstructionType]) ||
            null
          if (!route) {
            return (
              <div className="rounded-lg bg-card p-3">
                <p className="mb-1 text-xs font-semibold text-foreground">
                  Development Planning Route
                </p>
                <p className="text-muted-foreground">
                  Select a construction type on the input form to see the
                  expected planning consent pathway for this scheme.
                </p>
              </div>
            )
          }
          const toneCls =
            route.tone === "warn"
              ? "border-warning/30 bg-warning/5"
              : "border-primary/30 bg-primary/5"
          return (
            <div className={`rounded-lg border p-3 ${toneCls}`}>
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="text-xs font-semibold text-foreground">
                  Development Planning Route
                </p>
                <span className="rounded-full border border-border/60 bg-card px-2 py-0.5 text-[10px] font-medium uppercase text-muted-foreground">
                  {route.label}
                </span>
              </div>
              <p className="text-foreground">{route.route}</p>
              <p className="mt-1 text-muted-foreground">{route.detail}</p>
              {status === "active" && (
                <p className="mt-2 rounded border border-destructive/30 bg-destructive/10 p-2 text-[11px] text-destructive">
                  Article 4 is in force at this postcode — assume any permitted
                  development rights above are restricted or removed. Confirm
                  the exact direction with the LPA before relying on a Prior
                  Approval route.
                </p>
              )}
            </div>
          )
        })()}

        {/* Legacy Flask advice — only shown if we couldn't run the lookup */}
        {!loading && !result && legacy?.advice && (
          <p className="text-foreground">{legacy.advice}</p>
        )}
        {!loading && !result && legacy?.hmo_guidance && (
          <div className="rounded-lg bg-card p-3">
            <p className="mb-1 text-xs font-semibold text-foreground">
              HMO Guidance
            </p>
            <p className="text-muted-foreground">{legacy.hmo_guidance}</p>
          </div>
        )}

        <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground">
          <span>
            Always verify with the local planning authority before
            proceeding.
          </span>
          <a
            href="/article4-map"
            className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
          >
            <MapPin className="size-3" />
            Full UK map
          </a>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Strategy Suitability ───────────────────────────────────────────────────
function StrategySuitability({
  strategies,
}: {
  strategies?: BackendResults["strategy_recommendations"]
}) {
  if (!strategies || Object.keys(strategies).length === 0) return null

  const labels: Record<string, string> = {
    BTL: "Buy-to-Let",
    HMO: "HMO",
    BRR: "BRR",
    FLIP: "Flip",
    R2SA: "Rent-to-SA",
    SOCIAL_HOUSING: "Social Housing",
  }

  const entries = Object.entries(strategies) as [
    string,
    { suitable: boolean; note: string },
  ][]

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Building2 className="size-4 text-primary" />
          <CardTitle className="text-sm">Strategy Suitability</CardTitle>
        </div>
        <CardDescription className="text-xs">
          How this property performs across investment strategies
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-2">
          {entries.map(([key, val]) => (
            <div
              key={key}
              className={`flex items-start gap-3 rounded-lg border p-3 ${
                val.suitable
                  ? "border-success/30 bg-success/5"
                  : "border-border/50 bg-muted/20"
              }`}
            >
              <div className="mt-0.5">
                {val.suitable ? (
                  <CheckCircle2 className="size-4 text-success" />
                ) : (
                  <AlertTriangle className="size-4 text-muted-foreground" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <span className="text-sm font-medium text-foreground">
                  {labels[key] || key}
                </span>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                  {val.note}
                </p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ── House Valuation ────────────────────────────────────────────────────────
function HouseValuationCard({
  valuation,
  purchasePrice,
}: {
  valuation?: BackendResults["house_valuation"]
  purchasePrice?: number
}) {
  if (!valuation) return null

  const estimate = valuation.estimate
  const diff = purchasePrice ? estimate - purchasePrice : null
  const pct =
    purchasePrice && purchasePrice > 0
      ? ((estimate - purchasePrice) / purchasePrice) * 100
      : null
  const isUnder = diff !== null && diff > 0
  const isOver = diff !== null && diff < 0

  const confidenceColor =
    valuation.confidence === "High"
      ? "text-success"
      : valuation.confidence === "Medium"
        ? "text-warning"
        : "text-muted-foreground"

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Home className="size-4 text-primary" />
          <CardTitle className="text-sm">House Valuation</CardTitle>
          {valuation.source && (
            <span className="ml-auto text-xs text-muted-foreground">
              {valuation.source}
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-end gap-8">
          <div>
            <p className="text-xs text-muted-foreground">Estimated Value</p>
            <p className="text-2xl font-bold text-foreground">
              {formatCurrency(estimate)}
            </p>
            <p className={`text-xs font-medium ${confidenceColor}`}>
              {valuation.confidence} confidence
            </p>
          </div>
          {diff !== null && pct !== null && (
            <div>
              <p className="text-xs text-muted-foreground">vs Purchase Price</p>
              <p
                className={`text-lg font-semibold ${
                  isUnder
                    ? "text-success"
                    : isOver
                      ? "text-destructive"
                      : "text-foreground"
                }`}
              >
                {diff > 0 ? "+" : ""}
                {formatCurrency(diff)} ({pct > 0 ? "+" : ""}
                {pct.toFixed(1)}%)
              </p>
              <p className="text-xs text-muted-foreground">
                {isUnder
                  ? "Below market — potential uplift"
                  : isOver
                    ? "Above market estimate"
                    : "At market value"}
              </p>
            </div>
          )}
        </div>
        {valuation.note && (
          <p className="mt-3 border-t border-border/40 pt-3 text-xs text-muted-foreground">
            {valuation.note}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ── Sold Comparables ───────────────────────────────────────────────────────
function SoldComparablesTable({
  comparables,
}: {
  comparables?: BackendResults["sold_comparables"]
}) {
  if (!comparables || comparables.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="size-4 text-primary" />
          <CardTitle className="text-sm">Comparable Sold Prices</CardTitle>
          <Badge variant="outline" className="ml-auto text-xs">
            {comparables.length} sales
          </Badge>
        </div>
        <CardDescription className="text-xs">
          Recent sold prices in this postcode area
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 text-left">
                <th className="pb-2 pr-4 text-xs font-medium text-muted-foreground">
                  Address
                </th>
                <th className="pb-2 pr-4 text-right text-xs font-medium text-muted-foreground">
                  Price
                </th>
                <th className="pb-2 pr-4 text-xs font-medium text-muted-foreground">
                  Type
                </th>
                <th className="pb-2 text-right text-xs font-medium text-muted-foreground">
                  Date
                </th>
              </tr>
            </thead>
            <tbody>
              {comparables.slice(0, 6).map((sale, i) => (
                <tr key={i} className="border-b border-border/20 last:border-0">
                  <td className="py-2 pr-4 text-foreground">
                    <span className="line-clamp-1 block max-w-[180px]">
                      {sale.address}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right font-medium text-foreground">
                    {formatCurrency(sale.price)}
                  </td>
                  <td className="py-2 pr-4 text-muted-foreground">
                    {sale.type || "—"}
                  </td>
                  <td className="py-2 text-right text-muted-foreground">
                    {sale.date || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Rent Comparables ───────────────────────────────────────────────────────
function RentComparablesTable({
  comparables,
}: {
  comparables?: BackendResults["rent_comparables"]
}) {
  if (!comparables || comparables.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Users className="size-4 text-primary" />
          <CardTitle className="text-sm">Comparable Rental Prices</CardTitle>
          <Badge variant="outline" className="ml-auto text-xs">
            {comparables.length} listings
          </Badge>
        </div>
        <CardDescription className="text-xs">
          Current rental market in this area
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 text-left">
                <th className="pb-2 pr-4 text-xs font-medium text-muted-foreground">
                  Address
                </th>
                <th className="pb-2 pr-4 text-right text-xs font-medium text-muted-foreground">
                  Rent/mo
                </th>
                <th className="pb-2 pr-4 text-xs font-medium text-muted-foreground">
                  Beds
                </th>
                <th className="pb-2 text-xs font-medium text-muted-foreground">
                  Source
                </th>
              </tr>
            </thead>
            <tbody>
              {comparables.slice(0, 6).map((rent, i) => (
                <tr key={i} className="border-b border-border/20 last:border-0">
                  <td className="py-2 pr-4 text-foreground">
                    <span className="line-clamp-1 block max-w-[180px]">
                      {rent.address}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right font-medium text-foreground">
                    {formatCurrency(rent.monthly_rent)}/mo
                  </td>
                  <td className="py-2 pr-4 text-muted-foreground">
                    {rent.bedrooms ?? "—"}
                  </td>
                  <td className="py-2 text-xs text-muted-foreground">
                    {rent.source || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Refurb Estimates ───────────────────────────────────────────────────────
function RefurbEstimatesCard({
  estimates,
}: {
  estimates?: BackendResults["refurb_estimates"]
}) {
  if (!estimates) return null

  const levels: {
    key: keyof NonNullable<BackendResults["refurb_estimates"]>
    label: string
    desc: string
    color: string
  }[] = [
    {
      key: "light",
      label: "Light (Cosmetic)",
      desc: "Redecorate, carpets, minor fixtures",
      color: "text-success",
    },
    {
      key: "medium",
      label: "Medium (Standard)",
      desc: "New kitchen, bathroom, replastering",
      color: "text-warning",
    },
    {
      key: "heavy",
      label: "Heavy (Full Refurb)",
      desc: "Rewire, new heating, full strip-out",
      color: "text-orange-500",
    },
    {
      key: "structural",
      label: "Structural",
      desc: "Load-bearing walls, foundations, extensions",
      color: "text-destructive",
    },
  ]

  const available = levels.filter((l) => estimates[l.key])
  if (available.length === 0) return null

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Hammer className="size-4 text-primary" />
          <CardTitle className="text-sm">Refurbishment Cost Estimates</CardTitle>
        </div>
        <CardDescription className="text-xs">
          Based on property size and location
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {available.map(({ key, label, desc, color }) => {
            const d = estimates[key]!
            return (
              <div
                key={key}
                className="flex flex-col gap-1 rounded-lg border border-border/50 bg-muted/20 p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-foreground">{label}</span>
                  <span className={`text-sm font-bold ${color}`}>
                    {formatCurrency(d.total)}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{desc}</p>
                {(d.per_sqft_mid || d.per_sqm) && (
                  <p className="text-xs text-muted-foreground">
                    ~£{d.per_sqft_mid ?? d.per_sqm}/sqft
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ── AI Insights ────────────────────────────────────────────────────────────
function AIInsightsCard({
  strengths,
  risks,
  nextSteps,
  area,
}: {
  strengths?: string[]
  risks?: string[]
  nextSteps?: string[]
  area?: string
}) {
  return (
    <div className="flex flex-col gap-4">
      {strengths && strengths.length > 0 && (
        <Card className="border-success/20">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="size-4 text-success" />
              <CardTitle className="text-sm text-success">Strengths</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2">
              {strengths.map((s, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-sm text-muted-foreground"
                >
                  <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-success" />
                  {s.replace(/^[•\-]\s*/, "").trim()}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {risks && risks.length > 0 && (
        <Card className="border-warning/20">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="size-4 text-warning" />
              <CardTitle className="text-sm text-warning">Risks & Concerns</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2">
              {risks.map((r, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-sm text-muted-foreground"
                >
                  <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-warning" />
                  {r.replace(/^[•\-]\s*/, "").trim()}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {area && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <MapPin className="size-4 text-primary" />
              <CardTitle className="text-sm">Area Analysis</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed text-muted-foreground">{area}</p>
          </CardContent>
        </Card>
      )}

      {nextSteps && nextSteps.length > 0 && (
        <Card className="border-primary/20">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <BarChart3 className="size-4 text-primary" />
              <CardTitle className="text-sm">Recommended Next Steps</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-2">
              {nextSteps.map((step, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 text-sm text-muted-foreground"
                >
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
                    {i + 1}
                  </span>
                  {step.replace(/^\d+\.\s*/, "").trim()}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ── Risk Flags Panel ───────────────────────────────────────────────────────
function RiskFlagsPanel({ flags }: { flags?: RiskFlag[] }) {
  if (!flags || flags.length === 0) return null

  const severityConfig = {
    HIGH: { border: "border-destructive/40", bg: "bg-destructive/5", badge: "bg-destructive/20 text-destructive border-destructive/30", dot: "bg-destructive" },
    MEDIUM: { border: "border-warning/40", bg: "bg-warning/5", badge: "bg-warning/20 text-warning border-warning/30", dot: "bg-warning" },
    LOW: { border: "border-success/40", bg: "bg-success/5", badge: "bg-success/20 text-success border-success/30", dot: "bg-success" },
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Flag className="size-4 text-primary" />
          <CardTitle className="text-sm">Risk Flags</CardTitle>
        </div>
        <CardDescription>Automated risk assessment based on deal metrics</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-3">
          {flags.map((flag) => {
            const cfg = severityConfig[flag.severity] ?? severityConfig.LOW
            return (
              <div
                key={flag.id}
                className={`rounded-lg border p-4 ${cfg.border} ${cfg.bg}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className={`mt-0.5 size-2 shrink-0 rounded-full ${cfg.dot}`} />
                    <span className="text-sm font-semibold text-foreground">{flag.name}</span>
                  </div>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium ${cfg.badge}`}>
                    {flag.severity}
                  </span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{flag.description}</p>
                {flag.mitigation && (
                  <div className="mt-2 flex items-start gap-1.5">
                    <Info className="mt-0.5 size-3 shrink-0 text-primary" />
                    <p className="text-xs text-primary/80">{flag.mitigation}</p>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Regional Benchmark Panel ────────────────────────────────────────────────
function RegionalBenchmarkPanel({ benchmark }: { benchmark?: RegionalBenchmark }) {
  if (!benchmark) return null

  const yieldAbove = benchmark.yield_difference >= 0
  const cashflowAbove = benchmark.cashflow_difference >= 0

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <BarChart2 className="size-4 text-primary" />
          <CardTitle className="text-sm">Live Regional Benchmarks</CardTitle>
        </div>
        <CardDescription>
          {benchmark.region_name} · {benchmark.postcode_area} · {benchmark.data_source}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="mb-4 grid grid-cols-2 gap-4">
          {/* Yield comparison */}
          <div className="rounded-lg border border-border/50 bg-card p-4">
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Gross Yield vs Regional Median</p>
            <div className="flex items-baseline gap-1">
              <span className={`text-xl font-bold ${yieldAbove ? "text-success" : "text-destructive"}`}>
                {benchmark.your_yield.toFixed(1)}%
              </span>
              <span className="text-xs text-muted-foreground">
                {yieldAbove ? "▲" : "▼"} {Math.abs(benchmark.yield_difference).toFixed(1)}pp vs {benchmark.regional_median_yield.toFixed(1)}%
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{benchmark.yield_vs_median_label}</p>
            <div className="mt-2 overflow-hidden rounded-full bg-muted/40 h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all ${yieldAbove ? "bg-success" : "bg-destructive"}`}
                style={{ width: `${Math.min(100, benchmark.yield_percentile)}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">Top {(100 - benchmark.yield_percentile).toFixed(0)}% of area deals</p>
          </div>

          {/* Cashflow comparison */}
          <div className="rounded-lg border border-border/50 bg-card p-4">
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Cashflow vs Regional Average</p>
            <div className="flex items-baseline gap-1">
              <span className={`text-xl font-bold ${cashflowAbove ? "text-success" : "text-destructive"}`}>
                £{Math.round(benchmark.your_cashflow).toLocaleString()}/mo
              </span>
              <span className="text-xs text-muted-foreground">
                {cashflowAbove ? "▲" : "▼"} £{Math.abs(Math.round(benchmark.cashflow_difference)).toLocaleString()} vs avg
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{benchmark.cashflow_vs_avg_label}</p>
            <div className="mt-2 overflow-hidden rounded-full bg-muted/40 h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all ${cashflowAbove ? "bg-success" : "bg-destructive"}`}
                style={{ width: `${Math.min(100, benchmark.cashflow_percentile)}%` }}
              />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">Beats {benchmark.cashflow_percentile.toFixed(0)}% of comparable properties</p>
          </div>
        </div>

        {benchmark.summary && (
          <p className="rounded-md bg-muted/30 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
            {benchmark.summary}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

// ── Sensitivity Analysis Panel ──────────────────────────────────────────────
const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_API_URL ||
  "https://metusa-deal-analyzer.onrender.com"

function SensitivityAnalysisPanel({
  baseFormData,
  baseResults,
}: {
  baseFormData: PropertyFormData
  baseResults: CalculationResults
}) {
  const [mortgageRate, setMortgageRate] = useState<number>(baseFormData.interestRate ?? 3.75)
  const [monthlyRent, setMonthlyRent] = useState<number>(baseFormData.monthlyRent ?? 0)
  const [vacancyRate, setVacancyRate] = useState<number>(
    baseFormData.voidWeeks ? Math.round((baseFormData.voidWeeks / 52) * 100 * 10) / 10 : 4.2
  )
  const [sensitivityResult, setSensitivityResult] = useState<SensitivityResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const runSensitivity = useCallback(
    async (rate: number, rent: number, vacancy: number) => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`${BACKEND_URL}/api/sensitivity-analysis`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...baseFormData,
            override_mortgage_rate: rate,
            override_monthly_rent: rent,
            override_vacancy_rate: vacancy,
          }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => null)
          throw new Error(err?.message || "Sensitivity analysis failed")
        }
        const data = await res.json()
        if (data.success) {
          setSensitivityResult({
            applied: data.scenario,
            deal_score: data.metrics?.deal_score ?? 0,
            monthly_cashflow: data.metrics?.monthly_cashflow ?? 0,
            gross_yield: data.metrics?.gross_yield ?? 0,
            net_yield: data.metrics?.net_yield ?? 0,
            cash_on_cash: data.metrics?.cash_on_cash ?? 0,
            verdict: data.metrics?.verdict ?? "REVIEW",
            risk_level: data.metrics?.risk_level ?? "MEDIUM",
            risk_flags: data.risk_flags ?? [],
            regional_benchmark: data.regional_benchmark ?? null,
          })
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Request failed")
      } finally {
        setLoading(false)
      }
    },
    [baseFormData]
  )

  const scenario = sensitivityResult
  const cashflow = scenario?.monthly_cashflow ?? baseResults.monthlyCashFlow
  const yield_ = scenario?.gross_yield ?? baseResults.grossYield
  const coc = scenario?.cash_on_cash ?? baseResults.cashOnCashReturn
  const verdict = scenario?.verdict

  const verdictColor = verdict === "PROCEED" ? "text-success" : verdict === "AVOID" ? "text-destructive" : "text-warning"

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="size-4 text-primary" />
          <CardTitle className="text-sm">Sensitivity Analysis — What If?</CardTitle>
        </div>
        <CardDescription>Adjust key variables to stress-test this deal in real time</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col gap-5">
          {/* ── Sliders ── */}
          <div className="flex flex-col gap-4">
            {/* Mortgage Rate */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="text-xs font-medium text-foreground">Mortgage Rate</label>
                <span className="text-xs font-semibold text-primary">{mortgageRate.toFixed(2)}%</span>
              </div>
              <input
                type="range"
                min={0.5}
                max={12}
                step={0.25}
                value={mortgageRate}
                onChange={(e) => setMortgageRate(parseFloat(e.target.value))}
                className="w-full accent-primary"
              />
              <div className="flex justify-between text-xs text-muted-foreground"><span>0.5%</span><span>12%</span></div>
            </div>

            {/* Monthly Rent */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="text-xs font-medium text-foreground">Monthly Rent</label>
                <span className="text-xs font-semibold text-primary">£{monthlyRent.toLocaleString()}</span>
              </div>
              <input
                type="range"
                min={200}
                max={Math.max(5000, Math.round((baseFormData.monthlyRent ?? 1000) * 2))}
                step={50}
                value={monthlyRent}
                onChange={(e) => setMonthlyRent(parseFloat(e.target.value))}
                className="w-full accent-primary"
              />
              <div className="flex justify-between text-xs text-muted-foreground"><span>£200</span><span>£{Math.max(5000, Math.round((baseFormData.monthlyRent ?? 1000) * 2)).toLocaleString()}</span></div>
            </div>

            {/* Vacancy Rate */}
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="text-xs font-medium text-foreground">Vacancy Rate</label>
                <span className="text-xs font-semibold text-primary">{vacancyRate.toFixed(1)}%</span>
              </div>
              <input
                type="range"
                min={0}
                max={25}
                step={0.5}
                value={vacancyRate}
                onChange={(e) => setVacancyRate(parseFloat(e.target.value))}
                className="w-full accent-primary"
              />
              <div className="flex justify-between text-xs text-muted-foreground"><span>0%</span><span>25%</span></div>
            </div>
          </div>

          {/* ── Run Button ── */}
          <button
            onClick={() => runSensitivity(mortgageRate, monthlyRent, vacancyRate)}
            disabled={loading}
            className="flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-60"
          >
            {loading ? <Loader2 className="size-4 animate-spin" /> : <SlidersHorizontal className="size-4" />}
            {loading ? "Calculating..." : "Run Scenario"}
          </button>

          {error && (
            <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>
          )}

          {/* ── Scenario Results ── */}
          {(scenario || !loading) && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg border border-border/50 bg-card p-3 text-center">
                <p className="text-xs text-muted-foreground">Monthly Cashflow</p>
                <p className={`mt-1 text-base font-bold ${cashflow >= 0 ? "text-success" : "text-destructive"}`}>
                  {cashflow >= 0 ? "+" : ""}£{Math.round(cashflow).toLocaleString()}
                </p>
              </div>
              <div className="rounded-lg border border-border/50 bg-card p-3 text-center">
                <p className="text-xs text-muted-foreground">Gross Yield</p>
                <p className="mt-1 text-base font-bold text-foreground">{yield_.toFixed(2)}%</p>
              </div>
              <div className="rounded-lg border border-border/50 bg-card p-3 text-center">
                <p className="text-xs text-muted-foreground">Cash-on-Cash</p>
                <p className="mt-1 text-base font-bold text-foreground">{coc.toFixed(2)}%</p>
              </div>
              <div className="rounded-lg border border-border/50 bg-card p-3 text-center">
                <p className="text-xs text-muted-foreground">Verdict</p>
                <p className={`mt-1 text-base font-bold ${verdictColor}`}>
                  {verdict ?? "—"}
                </p>
              </div>
            </div>
          )}

          {/* Risk flags from scenario */}
          {scenario?.risk_flags && scenario.risk_flags.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Scenario Risk Flags</p>
              <div className="flex flex-wrap gap-2">
                {scenario.risk_flags.map((flag) => (
                  <span
                    key={flag.id}
                    className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                      flag.severity === "HIGH" ? "border-destructive/30 bg-destructive/10 text-destructive" :
                      flag.severity === "MEDIUM" ? "border-warning/30 bg-warning/10 text-warning" :
                      "border-success/30 bg-success/10 text-success"
                    }`}
                  >
                    {flag.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────
export function AnalysisResults({
  data,
  results,
  aiText,
  aiLoading,
  backendData,
}: AnalysisResultsProps) {
  const parsedAI = parseAIAnalysis(aiText)
  const dealScore =
    backendData?.deal_score ??
    parsedAI.score ??
    calculateDealScore(results.cashOnCashReturn)

  const verdict = backendData?.verdict
  const verdictLabel = backendData?.deal_score_label

  const cashFlowData = [
    {
      name: "Monthly",
      Income: Math.round(results.monthlyIncome),
      Mortgage: Math.round(results.monthlyMortgagePayment),
      "Running Costs": Math.round(results.monthlyRunningCosts),
    },
  ]

  const costBreakdown = [
    { name: "Deposit", value: results.depositAmount },
    { name: "SDLT", value: results.sdltAmount },
    { name: "Legal", value: data.legalFees },
    { name: "Survey", value: data.surveyCosts },
    ...(data.refurbishmentBudget > 0
      ? [{ name: "Refurb", value: data.refurbishmentBudget }]
      : []),
  ].filter((item) => item.value > 0)

  const projectionData = results.fiveYearProjection.map((year) => ({
    name: `Year ${year.year}`,
    Equity: year.equity,
    "Cumulative Cash Flow": year.cumulativeCashFlow,
    "Total Return": year.totalReturn,
  }))

  const hasSoldComparables = (backendData?.sold_comparables?.length ?? 0) > 0
  const hasRentComparables = (backendData?.rent_comparables?.length ?? 0) > 0
  const hasRefurb = !!backendData?.refurb_estimates && Object.keys(backendData.refurb_estimates).length > 0
  const hasStrategies =
    !!backendData?.strategy_recommendations &&
    Object.keys(backendData.strategy_recommendations).length > 0
  const hasArticle4 = !!backendData?.article_4
  const hasLocation = !!(backendData?.location?.council || backendData?.location?.region)
  const hasValuation = !!backendData?.house_valuation
  const hasAIInsights = !!(
    backendData?.ai_strengths?.length ||
    backendData?.ai_risks?.length ||
    backendData?.ai_next_steps?.length ||
    backendData?.ai_area
  )
  const hasRiskFlags = (backendData?.risk_flags?.length ?? 0) > 0
  const hasBenchmark = !!backendData?.regional_benchmark

  return (
    <div className="flex flex-col gap-6">

      {/* ── Verdict Banner ──────────────────────────────────────────── */}
      {verdict ? (
        <VerdictBanner verdict={verdict} score={dealScore} label={verdictLabel} />
      ) : (
        <div className="flex flex-col items-center gap-1 py-4">
          <DealScore score={dealScore} />
        </div>
      )}

      {/* ── Development-specific feasibility panel ─────────────────── */}
      {data.investmentType === "development" && (
        <DevelopmentResults data={data} results={results} />
      )}

      {/* ── Key Metrics Grid ────────────────────────────────────────── */}
      {/* Skip the yield/cashflow grid for development — those are all zero
          for a build-to-sell scheme; DevelopmentResults panel above shows
          the relevant metrics. */}
      {data.investmentType !== "development" && (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <MetricCard
          label="Gross Yield"
          value={formatPercent(results.grossYield)}
          icon={Percent}
          positive={results.grossYield >= 6}
        />
        <MetricCard
          label="Net Yield"
          value={formatPercent(results.netYield)}
          icon={Percent}
          positive={results.netYield >= 4}
        />
        <MetricCard
          label="Monthly Cash Flow"
          value={formatCurrency(results.monthlyCashFlow)}
          icon={results.monthlyCashFlow >= 0 ? TrendingUp : TrendingDown}
          positive={results.monthlyCashFlow >= 0}
        />
        <MetricCard
          label="Cash-on-Cash ROI"
          value={formatPercent(results.cashOnCashReturn)}
          icon={PoundSterling}
          positive={results.cashOnCashReturn >= 5}
        />
        <MetricCard
          label="Total Capital Required"
          value={formatCurrency(results.totalCapitalRequired)}
          icon={Wallet}
        />
        <MetricCard
          label="SDLT"
          value={formatCurrency(results.sdltAmount)}
          sub={
            data.buyerType === "additional"
              ? "Incl. 5% surcharge"
              : "First-time buyer rate"
          }
          icon={Home}
        />
      </div>
      )}

      {/* ── Location & Council ──────────────────────────────────────── */}
      {hasLocation && <LocationCard location={backendData?.location} />}

      {/* ── House Valuation ─────────────────────────────────────────── */}
      {hasValuation && (
        <HouseValuationCard
          valuation={backendData?.house_valuation}
          purchasePrice={data.purchasePrice}
        />
      )}

      {/* ── Charts ──────────────────────────────────────────────────── */}
      <Tabs defaultValue="cashflow" className="w-full">
        <TabsList
          className={`w-full grid ${
            hasSoldComparables || hasRentComparables ? "grid-cols-4" : "grid-cols-3"
          }`}
        >
          <TabsTrigger value="cashflow">Cash Flow</TabsTrigger>
          <TabsTrigger value="costs">Costs</TabsTrigger>
          <TabsTrigger value="projection">5-Year</TabsTrigger>
          {(hasSoldComparables || hasRentComparables) && (
            <TabsTrigger value="comparables">Comparables</TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="cashflow" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Monthly Cash Flow Breakdown</CardTitle>
              <CardDescription>Income vs expenses each month</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={cashFlowData} barGap={8}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="oklch(0.25 0.02 260)"
                    />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: "oklch(0.6 0.01 260)", fontSize: 12 }}
                    />
                    <YAxis
                      tick={{ fill: "oklch(0.6 0.01 260)", fontSize: 12 }}
                      tickFormatter={(v) => `£${v}`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "oklch(0.16 0.015 260)",
                        border: "1px solid oklch(0.25 0.02 260)",
                        borderRadius: "8px",
                        color: "oklch(0.95 0.005 260)",
                      }}
                      formatter={(value: number) => [`£${value}`, undefined]}
                    />
                    <Legend
                      wrapperStyle={{ color: "oklch(0.6 0.01 260)", fontSize: 12 }}
                    />
                    <Bar
                      dataKey="Income"
                      fill={CHART_COLORS[0]}
                      radius={[4, 4, 0, 0]}
                    />
                    <Bar
                      dataKey="Mortgage"
                      fill={CHART_COLORS[2]}
                      radius={[4, 4, 0, 0]}
                    />
                    <Bar
                      dataKey="Running Costs"
                      fill={CHART_COLORS[4]}
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="costs" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Capital Cost Breakdown</CardTitle>
              <CardDescription>
                Total capital: {formatCurrency(results.totalCapitalRequired)}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={costBreakdown}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={90}
                      paddingAngle={3}
                      dataKey="value"
                      label={({ name, value }) =>
                        `${name}: £${value.toLocaleString()}`
                      }
                    >
                      {costBreakdown.map((_, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={CHART_COLORS[index % CHART_COLORS.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "oklch(0.16 0.015 260)",
                        border: "1px solid oklch(0.25 0.02 260)",
                        borderRadius: "8px",
                        color: "oklch(0.95 0.005 260)",
                      }}
                      formatter={(value: number) => [
                        `£${value.toLocaleString()}`,
                        undefined,
                      ]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="projection" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">5-Year Projection</CardTitle>
              <CardDescription>
                Assuming {data.capitalGrowthRate ?? 4}% capital growth and{" "}
                {data.annualRentIncrease}% rent increase
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={projectionData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="oklch(0.25 0.02 260)"
                    />
                    <XAxis
                      dataKey="name"
                      tick={{ fill: "oklch(0.6 0.01 260)", fontSize: 12 }}
                    />
                    <YAxis
                      tick={{ fill: "oklch(0.6 0.01 260)", fontSize: 12 }}
                      tickFormatter={(v) => `£${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "oklch(0.16 0.015 260)",
                        border: "1px solid oklch(0.25 0.02 260)",
                        borderRadius: "8px",
                        color: "oklch(0.95 0.005 260)",
                      }}
                      formatter={(value: number) => [
                        `£${value.toLocaleString()}`,
                        undefined,
                      ]}
                    />
                    <Legend
                      wrapperStyle={{ color: "oklch(0.6 0.01 260)", fontSize: 12 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="Equity"
                      stroke={CHART_COLORS[0]}
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="Cumulative Cash Flow"
                      stroke={CHART_COLORS[1]}
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="Total Return"
                      stroke={CHART_COLORS[2]}
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {(hasSoldComparables || hasRentComparables) && (
          <TabsContent value="comparables" className="mt-4">
            <PropertyComparables
              postcode={data.postcode}
              bedrooms={data.bedrooms}
              currentPrice={data.purchasePrice}
            />
          </TabsContent>
        )}
      </Tabs>

      {/* ── Full Financial Breakdown ─────────────────────────────────── */}
      {data.investmentType !== "r2sa" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Full Financial Breakdown</CardTitle>
            <CardDescription>Complete breakdown of all costs, income and returns</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">

            {/* ── Acquisition Costs ──────────────────────────────────── */}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Acquisition Costs</p>
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Purchase Price</span>
                  <span className="font-semibold text-foreground">{formatCurrency(data.purchasePrice)}</span>
                </div>

                {/* SDLT with band detail */}
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    SDLT{data.buyerType === "first-time" ? " (first-time buyer)" : " (incl. 5% surcharge)"}
                  </span>
                  <span className="font-medium text-foreground">{formatCurrency(results.sdltAmount)}</span>
                </div>
                {results.sdltBreakdown.length > 0 && (
                  <div className="ml-4 flex flex-col gap-1 rounded-md bg-muted/30 px-3 py-2">
                    {results.sdltBreakdown.map((band) => (
                      <div key={band.band} className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Band: {band.band}</span>
                        <span className="text-foreground">{formatCurrency(band.tax)}</span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Legal Fees</span>
                  <span className="font-medium text-foreground">{formatCurrency(data.legalFees)}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Survey Costs</span>
                  <span className="font-medium text-foreground">{formatCurrency(data.surveyCosts)}</span>
                </div>
                {data.refurbishmentBudget > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Refurbishment Budget</span>
                    <span className="font-medium text-foreground">{formatCurrency(data.refurbishmentBudget)}</span>
                  </div>
                )}
                <Separator className="my-1" />
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Total Purchase Cost</span>
                  <span className="font-semibold text-foreground">{formatCurrency(results.totalPurchaseCost)}</span>
                </div>
              </div>
            </div>

            {/* ── Financing ──────────────────────────────────────────── */}
            {data.purchaseType !== "cash" && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Financing</p>
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Deposit ({data.depositPercentage}%)</span>
                    <span className="font-medium text-foreground">{formatCurrency(results.depositAmount)}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">
                      {data.purchaseType === "bridging-loan" ? "Bridging Loan" : "Mortgage Amount"}
                    </span>
                    <span className="font-medium text-foreground">{formatCurrency(results.mortgageAmount)}</span>
                  </div>
                  {data.purchaseType === "bridging-loan" && results.bridgingLoanDetails ? (
                    <>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Monthly Interest ({data.bridgingMonthlyRate ?? 0.75}%/mo)</span>
                        <span className="font-medium text-foreground">{formatCurrency(results.bridgingLoanDetails.monthlyInterest)}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Total Interest ({results.bridgingLoanDetails.termMonths} months)</span>
                        <span className="font-medium text-foreground">{formatCurrency(results.bridgingLoanDetails.totalInterest)}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Arrangement Fee</span>
                        <span className="font-medium text-foreground">{formatCurrency(results.bridgingLoanDetails.arrangementFee)}</span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Exit Fee</span>
                        <span className="font-medium text-foreground">{formatCurrency(results.bridgingLoanDetails.exitFee)}</span>
                      </div>
                      <Separator className="my-1" />
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Total Bridging Cost</span>
                        <span className="font-semibold text-foreground">{formatCurrency(results.bridgingLoanDetails.totalCost)}</span>
                      </div>
                    </>
                  ) : (
                    results.monthlyMortgagePayment > 0 && (
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">Monthly Mortgage ({data.interestRate}% {data.mortgageType})</span>
                        <span className="font-medium text-foreground">{formatCurrency(results.monthlyMortgagePayment)}</span>
                      </div>
                    )
                  )}
                </div>
              </div>
            )}

            {/* ── Total Capital Required ─────────────────────────────── */}
            <div className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-foreground">Total Capital Required</span>
                <span className="text-lg font-bold text-primary">{formatCurrency(results.totalCapitalRequired)}</span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Deposit + SDLT + legal + survey{data.refurbishmentBudget > 0 ? " + refurb" : ""}
              </p>
            </div>

            {/* ── Monthly Income & Expenses ───────────────────────────── */}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Monthly Income & Expenses</p>
              <div className="flex flex-col gap-1.5">
                {/* Income */}
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Gross Monthly Rent</span>
                  <span className="font-medium text-success">+{formatCurrency(data.monthlyRent)}</span>
                </div>
                {data.voidWeeks > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Void Allowance ({data.voidWeeks} weeks/yr)</span>
                    <span className="font-medium text-destructive">-{formatCurrency(Math.round((data.monthlyRent * data.voidWeeks) / 52))}</span>
                  </div>
                )}
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Effective Monthly Income</span>
                  <span className="font-semibold text-foreground">{formatCurrency(results.monthlyIncome)}</span>
                </div>

                <Separator className="my-1" />

                {/* Expenses */}
                {results.monthlyMortgagePayment > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Mortgage Payment</span>
                    <span className="font-medium text-destructive">-{formatCurrency(results.monthlyMortgagePayment)}</span>
                  </div>
                )}
                {data.managementFeePercent > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Management Fee ({data.managementFeePercent}%)</span>
                    <span className="font-medium text-destructive">-{formatCurrency(Math.round(data.monthlyRent * (data.managementFeePercent / 100)))}</span>
                  </div>
                )}
                {data.insurance > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Insurance</span>
                    <span className="font-medium text-destructive">-{formatCurrency(Math.round(data.insurance / 12))}</span>
                  </div>
                )}
                {data.maintenance > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Maintenance</span>
                    <span className="font-medium text-destructive">-{formatCurrency(Math.round(data.maintenance / 12))}</span>
                  </div>
                )}
                {data.groundRent > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Ground Rent</span>
                    <span className="font-medium text-destructive">-{formatCurrency(Math.round(data.groundRent / 12))}</span>
                  </div>
                )}
                {data.bills > 0 && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Bills</span>
                    <span className="font-medium text-destructive">-{formatCurrency(Math.round(data.bills / 12))}</span>
                  </div>
                )}

                <Separator className="my-1" />
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Total Monthly Expenses</span>
                  <span className="font-semibold text-destructive">-{formatCurrency(results.monthlyExpenses)}</span>
                </div>

                <Separator className="my-1" />

                {/* Cash Flow */}
                <div className="flex items-center justify-between text-sm">
                  <span className="font-semibold text-foreground">Monthly Cash Flow</span>
                  <span className={`text-base font-bold ${results.monthlyCashFlow >= 0 ? "text-success" : "text-destructive"}`}>
                    {results.monthlyCashFlow >= 0 ? "+" : ""}{formatCurrency(results.monthlyCashFlow)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="font-semibold text-foreground">Annual Cash Flow</span>
                  <span className={`font-bold ${results.annualCashFlow >= 0 ? "text-success" : "text-destructive"}`}>
                    {results.annualCashFlow >= 0 ? "+" : ""}{formatCurrency(results.annualCashFlow)}
                  </span>
                </div>
              </div>
            </div>

            {/* ── Returns ─────────────────────────────────────────────── */}
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Returns</p>
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Gross Yield</span>
                  <span className={`font-semibold ${results.grossYield >= 6 ? "text-success" : "text-foreground"}`}>{formatPercent(results.grossYield)}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Net Yield</span>
                  <span className={`font-semibold ${results.netYield >= 4 ? "text-success" : "text-foreground"}`}>{formatPercent(results.netYield)}</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Cash-on-Cash ROI</span>
                  <span className={`font-semibold ${results.cashOnCashReturn >= 5 ? "text-success" : "text-foreground"}`}>{formatPercent(results.cashOnCashReturn)}</span>
                </div>
              </div>
            </div>

          </CardContent>
        </Card>
      )}

      {/* ── Article 4 & Planning ────────────────────────────────────── */}
      {/* Always rendered — the card checks the Metalyzi Article 4 database
          itself using data.postcode, so it works even if the Flask backend
          didn't return article_4 (legacy field passed as fallback advice). */}
      <Article4Card
        postcode={data.postcode}
        legacy={backendData?.article_4}
        investmentType={data.investmentType}
        devConstructionType={data.devConstructionType}
      />
      {hasArticle4 ? null : null}

      {/* ── Strategy Suitability ────────────────────────────────────── */}
      {hasStrategies && (
        <StrategySuitability strategies={backendData?.strategy_recommendations} />
      )}

      {/* ── Sold & Rent Comparables ─────────────────────────────────── */}
      {hasSoldComparables && (
        <SoldComparablesTable comparables={backendData?.sold_comparables} />
      )}
      {hasRentComparables && (
        <RentComparablesTable comparables={backendData?.rent_comparables} />
      )}

      {/* ── HMO Rental Comparables & Area Analysis ─────────────────── */}
      {data.investmentType === "hmo" && data.postcode && (
        <HmoComparables postcode={data.postcode} />
      )}

      {/* ── Refurbishment Estimates ─────────────────────────────────── */}
      {hasRefurb && <RefurbEstimatesCard estimates={backendData?.refurb_estimates} />}

      {/* ── Risk Flags ──────────────────────────────────────────────── */}
      {hasRiskFlags && <RiskFlagsPanel flags={backendData?.risk_flags} />}

      {/* ── Regional Benchmarks ─────────────────────────────────────── */}
      {hasBenchmark && <RegionalBenchmarkPanel benchmark={backendData?.regional_benchmark} />}

      {/* ── Sensitivity Analysis ────────────────────────────────────── */}
      <SensitivityAnalysisPanel baseFormData={data} baseResults={results} />

      {/* ── AI Insights (Strengths / Risks / Area / Next Steps) ─────── */}
      {hasAIInsights ? (
        <AIInsightsCard
          strengths={backendData?.ai_strengths}
          risks={backendData?.ai_risks}
          area={backendData?.ai_area}
          nextSteps={backendData?.ai_next_steps}
        />
      ) : (
        /* Fallback: raw AI text when no structured insights available */
        <Card className="border-primary/20">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Sparkles className="size-4 text-primary" />
              <CardTitle className="text-base">AI Investment Analysis</CardTitle>
            </div>
            <CardDescription>
              Powered by AI — reviewing your deal against market benchmarks
            </CardDescription>
          </CardHeader>
          <CardContent>
            {aiLoading && !aiText ? (
              <div className="flex items-center gap-3 py-8 text-muted-foreground">
                <Loader2 className="size-5 animate-spin text-primary" />
                <span className="text-sm">Analysing your deal...</span>
              </div>
            ) : (
              <div className="prose prose-sm prose-invert max-w-none">
                {parsedAI.sections.length > 0 ? (
                  parsedAI.sections.map((section, i) => (
                    <div key={i} className="mb-4">
                      <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
                        {section.heading.toLowerCase().includes("strength") ? (
                          <CheckCircle2 className="size-4 text-success" />
                        ) : section.heading.toLowerCase().includes("risk") ? (
                          <AlertTriangle className="size-4 text-warning" />
                        ) : null}
                        {section.heading}
                      </h4>
                      <div className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                        {section.content}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                    {aiText}
                    {aiLoading && (
                      <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-primary" />
                    )}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

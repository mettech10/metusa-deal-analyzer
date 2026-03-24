"use client"

import { useState, useRef, useCallback, useEffect } from "react"
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
import { Slider } from "@/components/ui/slider"
import { DealScore } from "./deal-score"
import { PropertyComparables } from "./property-comparables"
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
  Info,
  SlidersHorizontal,
  Activity,
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
function Article4Card({ article4 }: { article4?: BackendResults["article_4"] }) {
  if (!article4) return null

  const isArticle4 = article4.is_article_4
  const isUnknown = article4.known === false
  const status = isArticle4 ? "restricted" : isUnknown ? "unknown" : "clear"

  const cfg = {
    restricted: {
      bg: "bg-destructive/10 border-destructive/30",
      badgeCls: "bg-destructive/20 text-destructive border-destructive/40",
      icon: <ShieldAlert className="size-4 text-destructive" />,
      label: "Article 4 in Force",
      titleCls: "text-destructive",
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

  return (
    <Card className={`border ${cfg.bg}`}>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          {cfg.icon}
          <CardTitle className={`text-sm ${cfg.titleCls}`}>Article 4 & Planning</CardTitle>
          <span className={`ml-auto rounded-full border px-2 py-0.5 text-xs font-medium ${cfg.badgeCls}`}>
            {cfg.label}
          </span>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {article4.note && <p className="text-muted-foreground">{article4.note}</p>}
        {article4.advice && <p className="text-foreground">{article4.advice}</p>}
        {article4.hmo_guidance && (
          <div className="rounded-lg bg-card p-3">
            <p className="mb-1 text-xs font-semibold text-foreground">HMO Guidance</p>
            <p className="text-muted-foreground">{article4.hmo_guidance}</p>
          </div>
        )}
        {article4.social_housing_suggestion && (
          <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
            <p className="mb-1 text-xs font-semibold text-primary">
              Alternative: Social / Supported Housing (C3→C3b)
            </p>
            <p className="text-muted-foreground">{article4.social_housing_suggestion}</p>
          </div>
        )}
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

  const rents = comparables.slice(0, 8)
  const avgRent = rents.length > 0
    ? Math.round(rents.reduce((s, r) => s + r.monthly_rent, 0) / rents.length)
    : 0

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Users className="size-4 text-primary" />
          <CardTitle className="text-sm">Comparable Rental Prices</CardTitle>
          <Badge variant="outline" className="ml-auto text-xs">
            {rents.length} listings
          </Badge>
        </div>
        <CardDescription className="text-xs">
          Similar properties currently let or recently listed in this area
          {avgRent > 0 && (
            <span className="ml-1 font-medium text-foreground">· Avg: {formatCurrency(avgRent)}/mo</span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 text-left">
                <th className="pb-2 pr-4 text-xs font-medium text-muted-foreground">Address</th>
                <th className="pb-2 pr-4 text-right text-xs font-medium text-muted-foreground">Rent/mo</th>
                <th className="pb-2 pr-4 text-xs font-medium text-muted-foreground">Beds</th>
                <th className="pb-2 pr-4 text-xs font-medium text-muted-foreground">Type</th>
                <th className="pb-2 pr-4 text-xs font-medium text-muted-foreground">Tenure</th>
                <th className="pb-2 text-xs font-medium text-muted-foreground">Source</th>
              </tr>
            </thead>
            <tbody>
              {rents.map((rent, i) => (
                <tr key={i} className="border-b border-border/20 last:border-0">
                  <td className="py-2 pr-4 text-foreground">
                    <span className="line-clamp-1 block max-w-[160px]">{rent.address}</span>
                  </td>
                  <td className="py-2 pr-4 text-right font-medium text-foreground">
                    {formatCurrency(rent.monthly_rent)}/mo
                  </td>
                  <td className="py-2 pr-4 text-muted-foreground">{rent.bedrooms ?? "—"}</td>
                  <td className="py-2 pr-4 text-muted-foreground capitalize">{rent.type || "—"}</td>
                  <td className="py-2 pr-4 text-muted-foreground capitalize">{rent.tenure || "—"}</td>
                  <td className="py-2 text-xs text-muted-foreground">{rent.source || "—"}</td>
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

// ── Risk Flags ─────────────────────────────────────────────────────────────
function LTVTooltip() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [open])

  return (
    <span ref={ref} className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="ml-1 inline-flex size-4 items-center justify-center rounded-full border border-muted-foreground/40 text-muted-foreground hover:border-primary hover:text-primary transition-colors"
        aria-label="What is LTV?"
      >
        <Info className="size-2.5" />
      </button>
      {open && (
        <div className="absolute bottom-6 left-1/2 z-50 w-64 -translate-x-1/2 rounded-lg border border-border bg-popover px-3 py-2.5 text-xs text-popover-foreground shadow-lg">
          <p className="font-semibold mb-1">What is LTV?</p>
          <p className="leading-relaxed text-muted-foreground">
            <strong>Loan-to-Value (LTV)</strong> is the mortgage amount as a percentage of the property value. A 75% LTV means you borrow 75% and put in 25% as a deposit. Higher LTV = more leverage but also more risk if property values fall.
          </p>
        </div>
      )}
    </span>
  )
}

function RiskFlagsCard({ flags }: { flags?: BackendResults["risk_flags"] }) {
  if (!flags || flags.length === 0) return null

  const severityConfig = {
    HIGH: {
      border: "border-destructive/40",
      bg: "bg-destructive/5",
      badge: "bg-destructive/15 text-destructive border-destructive/30",
      dot: "bg-destructive",
    },
    MEDIUM: {
      border: "border-warning/40",
      bg: "bg-warning/5",
      badge: "bg-warning/15 text-warning border-warning/30",
      dot: "bg-warning",
    },
    LOW: {
      border: "border-success/40",
      bg: "bg-success/5",
      badge: "bg-success/15 text-success border-success/30",
      dot: "bg-success",
    },
  }

  const highCount = flags.filter((f) => f.severity === "HIGH").length
  const medCount = flags.filter((f) => f.severity === "MEDIUM").length

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <ShieldAlert className="size-4 text-primary" />
          <CardTitle className="text-sm">Risk Flags</CardTitle>
          <div className="ml-auto flex gap-1.5">
            {highCount > 0 && (
              <span className="rounded-full border border-destructive/30 bg-destructive/15 px-2 py-0.5 text-xs font-medium text-destructive">
                {highCount} HIGH
              </span>
            )}
            {medCount > 0 && (
              <span className="rounded-full border border-warning/30 bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning">
                {medCount} MEDIUM
              </span>
            )}
          </div>
        </div>
        <CardDescription className="text-xs">
          Automatically detected risks based on your deal metrics
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {flags.map((flag) => {
          const cfg = severityConfig[flag.severity] ?? severityConfig.LOW
          const isLTV = flag.description.toLowerCase().includes("ltv") || flag.name.toLowerCase().includes("leverage")
          return (
            <div key={flag.id} className={`rounded-lg border p-3 ${cfg.border} ${cfg.bg}`}>
              <div className="mb-1.5 flex items-center gap-2">
                <span className={`size-2 shrink-0 rounded-full ${cfg.dot}`} />
                <span className="text-sm font-semibold text-foreground flex items-center gap-0.5">
                  {flag.name}
                  {isLTV && <LTVTooltip />}
                </span>
                <span className={`ml-auto rounded-full border px-1.5 py-0.5 text-[10px] font-bold ${cfg.badge}`}>
                  {flag.severity}
                </span>
              </div>
              <p className="mb-2 text-xs leading-relaxed text-muted-foreground">{flag.description}</p>
              <div className="rounded bg-background/60 px-2 py-1.5">
                <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Mitigation</p>
                <p className="text-xs text-foreground">{flag.mitigation}</p>
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

// ── Regional Benchmark ──────────────────────────────────────────────────────
function RegionalBenchmarkCard({ benchmark }: { benchmark?: BackendResults["regional_benchmark"] }) {
  if (!benchmark || !benchmark.region_name) return null

  const yieldDiff = benchmark.yield_difference ?? 0
  const cashDiff = benchmark.cashflow_difference ?? 0

  function DiffBadge({ diff, unit }: { diff: number; unit: "%" | "£" }) {
    const isPos = diff > 0
    const isFlat = Math.abs(diff) < (unit === "%" ? 0.05 : 5)
    if (isFlat) return <span className="text-xs text-muted-foreground">In line with market</span>
    return (
      <span className={`text-xs font-semibold ${isPos ? "text-success" : "text-destructive"}`}>
        {isPos ? "+" : ""}{unit === "£" ? `£${Math.abs(diff).toLocaleString("en-GB")}` : `${Math.abs(diff).toFixed(2)}%`} {isPos ? "above" : "below"} regional {unit === "%" ? "median" : "average"}
      </span>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Activity className="size-4 text-primary" />
          <CardTitle className="text-sm">Regional Benchmark</CardTitle>
          <Badge variant="outline" className="ml-auto text-xs">
            {benchmark.region_name}
          </Badge>
        </div>
        <CardDescription className="text-xs">
          How this deal compares to the {benchmark.postcode_area} area median
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {benchmark.summary && (
          <p className="rounded-lg bg-muted/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
            {benchmark.summary}
          </p>
        )}

        <div className="grid grid-cols-2 gap-3">
          {/* Yield comparison */}
          <div className="flex flex-col gap-1 rounded-lg border border-border/50 bg-muted/20 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Gross Yield</p>
            <p className="text-lg font-bold text-foreground">{benchmark.your_yield?.toFixed(2)}%</p>
            <DiffBadge diff={yieldDiff} unit="%" />
            <p className="mt-1 text-[10px] text-muted-foreground">
              Regional median: {benchmark.regional_median_yield?.toFixed(2)}%
            </p>
            {benchmark.yield_percentile != null && (
              <div className="mt-1">
                <div className="mb-0.5 flex justify-between text-[10px] text-muted-foreground">
                  <span>Percentile</span>
                  <span className="font-medium text-foreground">{benchmark.yield_percentile}th</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-muted">
                  <div
                    className={`h-1.5 rounded-full ${yieldDiff >= 0 ? "bg-success" : "bg-destructive"}`}
                    style={{ width: `${Math.min(100, benchmark.yield_percentile)}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Cashflow comparison */}
          <div className="flex flex-col gap-1 rounded-lg border border-border/50 bg-muted/20 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Monthly Cashflow</p>
            <p className={`text-lg font-bold ${(benchmark.your_cashflow ?? 0) >= 0 ? "text-success" : "text-destructive"}`}>
              {formatCurrency(benchmark.your_cashflow ?? 0)}/mo
            </p>
            <DiffBadge diff={cashDiff} unit="£" />
            <p className="mt-1 text-[10px] text-muted-foreground">
              Regional avg: {formatCurrency(benchmark.regional_avg_cashflow ?? 0)}/mo
            </p>
            {benchmark.cashflow_percentile != null && (
              <div className="mt-1">
                <div className="mb-0.5 flex justify-between text-[10px] text-muted-foreground">
                  <span>Percentile</span>
                  <span className="font-medium text-foreground">{benchmark.cashflow_percentile}th</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-muted">
                  <div
                    className={`h-1.5 rounded-full ${cashDiff >= 0 ? "bg-success" : "bg-destructive"}`}
                    style={{ width: `${Math.min(100, benchmark.cashflow_percentile)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {benchmark.data_source && (
          <p className="text-[10px] text-muted-foreground">Source: {benchmark.data_source}</p>
        )}
      </CardContent>
    </Card>
  )
}

// ── Sensitivity Analysis ────────────────────────────────────────────────────
interface SensitivityMetrics {
  deal_score: number
  deal_score_label: string
  monthly_cashflow: number
  gross_yield: number
  net_yield: number
  cash_on_cash: number
  verdict: string
  risk_level: string
  monthly_mortgage: number
  annual_cashflow: number
}

function SensitivityAnalysisPanel({
  formData,
}: {
  formData: PropertyFormData
}) {
  const [mortgageRate, setMortgageRate] = useState(formData.interestRate)
  const [monthlyRent, setMonthlyRent] = useState(formData.monthlyRent)
  const [vacancyRate, setVacancyRate] = useState(4.2)
  const [purchasePrice, setPurchasePrice] = useState(formData.purchasePrice)
  const [metrics, setMetrics] = useState<SensitivityMetrics | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const runScenario = useCallback(
    async (rate: number, rent: number, vacancy: number, price: number) => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch("/api/sensitivity-analysis", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            purchasePrice: price,
            dealType: (formData.investmentType || "btl").toUpperCase(),
            monthlyRent: rent,
            interestRate: rate,
            address: formData.address,
            postcode: formData.postcode,
            deposit: Math.round(price * (formData.depositPercentage / 100)),
            override_mortgage_rate: rate,
            override_monthly_rent: rent,
            override_vacancy_rate: vacancy,
            override_purchase_price: price,
          }),
        })
        const data = await res.json()
        if (data.success && data.metrics) {
          setMetrics(data.metrics)
        } else {
          setError(data.message || "Scenario calculation failed")
        }
      } catch {
        setError("Failed to reach analysis server")
      } finally {
        setLoading(false)
      }
    },
    [formData]
  )

  const debouncedRun = useCallback(
    (rate: number, rent: number, vacancy: number, price: number) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => runScenario(rate, rent, vacancy, price), 600)
    },
    [runScenario]
  )

  const verdictConfig: Record<string, { text: string; cls: string }> = {
    PROCEED: { text: "PROCEED", cls: "text-success" },
    REVIEW:  { text: "REVIEW",  cls: "text-warning" },
    AVOID:   { text: "AVOID",   cls: "text-destructive" },
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="size-4 text-primary" />
          <CardTitle className="text-sm">What-If Sensitivity Analysis</CardTitle>
          {loading && <Loader2 className="ml-auto size-3.5 animate-spin text-muted-foreground" />}
        </div>
        <CardDescription className="text-xs">
          Adjust the sliders to instantly see how changes affect this deal
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {/* Sliders */}
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Mortgage Rate */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-foreground">Mortgage Rate</span>
              <span className="font-bold text-primary">{mortgageRate.toFixed(2)}%</span>
            </div>
            <Slider
              min={1} max={12} step={0.25}
              value={[mortgageRate]}
              onValueChange={([v]) => {
                setMortgageRate(v)
                debouncedRun(v, monthlyRent, vacancyRate, purchasePrice)
              }}
            />
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>1%</span><span>Current: {formData.interestRate}%</span><span>12%</span>
            </div>
          </div>

          {/* Monthly Rent */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-foreground">Monthly Rent</span>
              <span className="font-bold text-primary">£{monthlyRent.toLocaleString("en-GB")}</span>
            </div>
            <Slider
              min={300} max={Math.max(5000, formData.monthlyRent * 2)} step={25}
              value={[monthlyRent]}
              onValueChange={([v]) => {
                setMonthlyRent(v)
                debouncedRun(mortgageRate, v, vacancyRate, purchasePrice)
              }}
            />
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>£300</span><span>Current: £{formData.monthlyRent.toLocaleString()}</span><span>£{Math.max(5000, formData.monthlyRent * 2).toLocaleString()}</span>
            </div>
          </div>

          {/* Vacancy Rate */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-foreground">Vacancy Rate</span>
              <span className="font-bold text-primary">{vacancyRate.toFixed(1)}%</span>
            </div>
            <Slider
              min={0} max={20} step={0.5}
              value={[vacancyRate]}
              onValueChange={([v]) => {
                setVacancyRate(v)
                debouncedRun(mortgageRate, monthlyRent, v, purchasePrice)
              }}
            />
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>0% (fully let)</span><span>20% (~10 wks void)</span>
            </div>
          </div>

          {/* Purchase Price Negotiation */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-foreground">Purchase Price</span>
              <span className="font-bold text-primary">£{purchasePrice.toLocaleString("en-GB")}</span>
            </div>
            <Slider
              min={Math.round(formData.purchasePrice * 0.75)}
              max={Math.round(formData.purchasePrice * 1.1)}
              step={1000}
              value={[purchasePrice]}
              onValueChange={([v]) => {
                setPurchasePrice(v)
                debouncedRun(mortgageRate, monthlyRent, vacancyRate, v)
              }}
            />
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>-25% (neg.)</span>
              <span>Listed: £{formData.purchasePrice.toLocaleString()}</span>
              <span>+10%</span>
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <p className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>
        )}

        {/* Scenario Results */}
        {metrics && (
          <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Scenario Outcome</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted-foreground">Verdict</span>
                <span className={`text-sm font-bold ${verdictConfig[metrics.verdict]?.cls ?? "text-foreground"}`}>
                  {metrics.verdict}
                </span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted-foreground">Deal Score</span>
                <span className="text-sm font-bold text-foreground">{metrics.deal_score}/100</span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted-foreground">Monthly CF</span>
                <span className={`text-sm font-bold ${metrics.monthly_cashflow >= 0 ? "text-success" : "text-destructive"}`}>
                  {metrics.monthly_cashflow >= 0 ? "+" : ""}{formatCurrency(metrics.monthly_cashflow)}/mo
                </span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted-foreground">Gross Yield</span>
                <span className="text-sm font-bold text-foreground">{Number(metrics.gross_yield).toFixed(2)}%</span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted-foreground">Net Yield</span>
                <span className="text-sm font-bold text-foreground">{Number(metrics.net_yield).toFixed(2)}%</span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted-foreground">Cash-on-Cash</span>
                <span className="text-sm font-bold text-foreground">{Number(metrics.cash_on_cash).toFixed(2)}%</span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted-foreground">Annual CF</span>
                <span className={`text-sm font-bold ${metrics.annual_cashflow >= 0 ? "text-success" : "text-destructive"}`}>
                  {formatCurrency(metrics.annual_cashflow)}/yr
                </span>
              </div>
              <div className="flex flex-col gap-0.5">
                <span className="text-[10px] text-muted-foreground">Monthly Mortgage</span>
                <span className="text-sm font-bold text-foreground">{formatCurrency(metrics.monthly_mortgage)}/mo</span>
              </div>
            </div>
          </div>
        )}

        {!metrics && !loading && (
          <p className="text-center text-xs text-muted-foreground">
            Move any slider above to instantly calculate a scenario outcome
          </p>
        )}
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
  benchmark,
  riskFlags,
}: {
  strengths?: string[]
  risks?: string[]
  nextSteps?: string[]
  area?: string
  benchmark?: BackendResults["regional_benchmark"]
  riskFlags?: BackendResults["risk_flags"]
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

      {(area || benchmark || riskFlags?.length) && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <MapPin className="size-4 text-primary" />
              <CardTitle className="text-sm">Area Analysis</CardTitle>
              {benchmark?.region_name && (
                <Badge variant="outline" className="ml-auto text-xs">{benchmark.region_name}</Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {area && (
              <p className="text-sm leading-relaxed text-muted-foreground">{area}</p>
            )}
            {/* Live benchmark summary inline */}
            {benchmark?.summary && (
              <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-primary">Live Market Benchmark</p>
                <p className="text-xs leading-relaxed text-muted-foreground">{benchmark.summary}</p>
                {benchmark.yield_vs_median_label && (
                  <p className="mt-1 text-xs font-medium text-foreground">Yield: {benchmark.yield_vs_median_label}</p>
                )}
                {benchmark.cashflow_vs_avg_label && (
                  <p className="text-xs font-medium text-foreground">Cashflow: {benchmark.cashflow_vs_avg_label}</p>
                )}
              </div>
            )}
            {/* Risk flag summary */}
            {riskFlags && riskFlags.length > 0 && (
              <div className="rounded-lg border border-warning/20 bg-warning/5 px-3 py-2">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-warning">Risk Summary</p>
                <div className="flex flex-wrap gap-1.5">
                  {riskFlags.map((f) => (
                    <span
                      key={f.id}
                      className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                        f.severity === "HIGH"
                          ? "border-destructive/30 bg-destructive/10 text-destructive"
                          : f.severity === "MEDIUM"
                          ? "border-warning/30 bg-warning/10 text-warning"
                          : "border-success/30 bg-success/10 text-success"
                      }`}
                    >
                      {f.name}
                    </span>
                  ))}
                </div>
              </div>
            )}
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
  const hasRiskFlags = (backendData?.risk_flags?.length ?? 0) > 0
  const hasBenchmark = !!backendData?.regional_benchmark?.region_name
  const hasAIInsights = !!(
    backendData?.ai_strengths?.length ||
    backendData?.ai_risks?.length ||
    backendData?.ai_next_steps?.length ||
    backendData?.ai_area ||
    hasBenchmark ||
    hasRiskFlags
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

      {/* ── Key Metrics Grid ────────────────────────────────────────── */}
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
      {hasArticle4 && <Article4Card article4={backendData?.article_4} />}

      {/* ── Strategy Suitability ────────────────────────────────────── */}
      {hasStrategies && (
        <StrategySuitability strategies={backendData?.strategy_recommendations} />
      )}

      {/* ── Risk Flags ──────────────────────────────────────────────── */}
      {hasRiskFlags && <RiskFlagsCard flags={backendData?.risk_flags} />}

      {/* ── Regional Benchmark ──────────────────────────────────────── */}
      {hasBenchmark && <RegionalBenchmarkCard benchmark={backendData?.regional_benchmark} />}

      {/* ── Sensitivity Analysis ────────────────────────────────────── */}
      <SensitivityAnalysisPanel formData={data} />

      {/* ── Sold & Rent Comparables ─────────────────────────────────── */}
      {hasSoldComparables && (
        <SoldComparablesTable comparables={backendData?.sold_comparables} />
      )}
      {hasRentComparables && (
        <RentComparablesTable comparables={backendData?.rent_comparables} />
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
          benchmark={backendData?.regional_benchmark}
          riskFlags={backendData?.risk_flags}
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

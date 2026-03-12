"use client"

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
import type { PropertyFormData, CalculationResults, BackendResults } from "@/lib/types"
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

      {/* ── SDLT Breakdown ──────────────────────────────────────────── */}
      {results.sdltBreakdown.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">SDLT Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-2">
              {results.sdltBreakdown.map((band) => (
                <div
                  key={band.band}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="text-muted-foreground">{band.band}</span>
                  <span className="font-medium text-foreground">
                    {formatCurrency(band.tax)}
                  </span>
                </div>
              ))}
              <Separator className="my-1" />
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium text-foreground">Total SDLT</span>
                <span className="font-bold text-foreground">
                  {formatCurrency(results.sdltAmount)}
                </span>
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

      {/* ── Sold & Rent Comparables ─────────────────────────────────── */}
      {hasSoldComparables && (
        <SoldComparablesTable comparables={backendData?.sold_comparables} />
      )}
      {hasRentComparables && (
        <RentComparablesTable comparables={backendData?.rent_comparables} />
      )}

      {/* ── Refurbishment Estimates ─────────────────────────────────── */}
      {hasRefurb && <RefurbEstimatesCard estimates={backendData?.refurb_estimates} />}

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

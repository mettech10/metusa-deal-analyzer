"use client"

/**
 * Development-specific results panel — rendered from analysis-results.tsx
 * when investmentType === "development". Mirrors the brrrr-results /
 * flip-results pattern but shows feasibility-appraisal displays:
 *
 *   1. Viability Dashboard (score + label + flags + verdict chip)
 *   2. Key Metrics tiles (profit on cost / GDV, LTGDV, IRR, equity, ...)
 *   3. GDV Summary (per-unit-type table with totals)
 *   4. Cost Stack (ordered £ + % of TDC with inline stacked bar)
 *   5. Finance Summary (facility, day-1, interest, fees, rolled-up badge)
 *   6. RLV Analysis (current purchase vs residual @ 20% profit-on-cost)
 *   7. Timeline (acquisition → build term → marketing → profit)
 *   8. Sensitivity sliders (GDV ± 10%, build cost ± 10%, rate ± 2%)
 *
 * The calculation engine is lib/developmentCalculations.ts. For
 * sensitivity recompute we call calculateAll with a shallow-overridden
 * form payload and read back .development — the engine is cheap enough
 * to re-run on every slider tick.
 */

import { useMemo, useState } from "react"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import type { PropertyFormData, CalculationResults } from "@/lib/types"
import type { DevelopmentResult } from "@/lib/developmentCalculations"
import { formatCurrency, calculateAll } from "@/lib/calculations"
import {
  AlertTriangle,
  Banknote,
  Building2,
  Calendar,
  CheckCircle2,
  Download,
  Info,
  Layers,
  PoundSterling,
  Receipt,
  Scale,
  SlidersHorizontal,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
  XCircle,
} from "lucide-react"

interface DevelopmentResultsProps {
  data: PropertyFormData
  results: CalculationResults
}

/** Tailwind colour per cost-stack line (kept explicit for print). */
const STACK_COLORS: Record<string, string> = {
  Acquisition: "bg-blue-500",
  Construction: "bg-emerald-500",
  "Professional Fees": "bg-violet-500",
  "Planning Obligations": "bg-amber-500",
  Finance: "bg-rose-500",
  "Exit / Sales": "bg-slate-500",
}

function severityIcon(sev: "info" | "warn" | "danger") {
  if (sev === "danger") return <XCircle className="size-4 text-red-500" />
  if (sev === "warn")
    return <AlertTriangle className="size-4 text-amber-500" />
  return <Info className="size-4 text-blue-500" />
}

function verdictFromScore(score: number): {
  label: string
  verdict: "PROCEED" | "REVIEW" | "AVOID"
  tone: string
} {
  if (score >= 70)
    return {
      label: "Proceed",
      verdict: "PROCEED",
      tone: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    }
  if (score >= 50)
    return {
      label: "Review",
      verdict: "REVIEW",
      tone: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/30",
    }
  return {
    label: "Avoid",
    verdict: "AVOID",
    tone: "bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/30",
  }
}

export function DevelopmentResults({
  data,
  results,
}: DevelopmentResultsProps) {
  const dev: DevelopmentResult | undefined = results.development
  // If engine didn't run (shouldn't happen — calculateAll always populates
  // for investmentType === "development"), render a soft fallback.
  if (!dev) {
    return (
      <Card>
        <CardContent className="p-6">
          <p className="text-sm text-muted-foreground">
            Development appraisal unavailable — add unit mix + construction
            inputs to see the full feasibility breakdown.
          </p>
        </CardContent>
      </Card>
    )
  }

  // ── Sensitivity sliders ────────────────────────────────────
  const [gdvDeltaPct, setGdvDeltaPct] = useState(0) // -10 .. +10
  const [buildDeltaPct, setBuildDeltaPct] = useState(0) // -10 .. +10
  const [rateDelta, setRateDelta] = useState(0) // -2 .. +2 (%)

  const sensitivityDev: DevelopmentResult | null = useMemo(() => {
    if (gdvDeltaPct === 0 && buildDeltaPct === 0 && rateDelta === 0)
      return null
    // Shallow-override the form payload and re-run calculateAll.
    // Unit-mix sale prices and build cost per m² get nudged by the deltas.
    const nudged: PropertyFormData = {
      ...data,
      devUnitMix: (data.devUnitMix ?? []).map((u) => ({
        ...u,
        salePricePerUnit: Math.max(
          0,
          (Number(u.salePricePerUnit) || 0) * (1 + gdvDeltaPct / 100),
        ),
      })),
      devBuildCostPerM2: Math.max(
        0,
        (Number(data.devBuildCostPerM2) || 0) * (1 + buildDeltaPct / 100),
      ),
      devFinanceRate: Math.max(
        0,
        (Number(data.devFinanceRate) || 0) + rateDelta,
      ),
    }
    return calculateAll(nudged).development ?? null
  }, [data, gdvDeltaPct, buildDeltaPct, rateDelta])

  const verdict = verdictFromScore(dev.dealScore)
  const buildMonths = dev.financeTermMonths || 0

  // ── Print → browser save-as-PDF ─────────────────────────────────
  // Toggles body.print-development so globals.css can isolate the
  // print-development-root subtree and force light colours. Cleanup
  // listener removes the class as soon as the print dialog closes,
  // leaving normal page styling untouched.
  const handlePrintReport = () => {
    if (typeof document === "undefined") return
    document.body.classList.add("print-development")
    const cleanup = () => {
      document.body.classList.remove("print-development")
      window.removeEventListener("afterprint", cleanup)
    }
    window.addEventListener("afterprint", cleanup)
    setTimeout(() => window.print(), 50)
  }

  const reportDate = new Date().toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  })

  return (
    <div className="flex flex-col gap-6 print-development-root">
      {/* ── Download report button (hidden in print) ───────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 no-print">
        <div>
          <h2 className="text-lg font-semibold text-foreground">
            Development Feasibility Report
          </h2>
          <p className="text-xs text-muted-foreground">
            Print or save the below as PDF — the full appraisal pack for
            lender / broker / partner submission.
          </p>
        </div>
        <Button
          onClick={handlePrintReport}
          variant="outline"
          size="sm"
          className="gap-2"
        >
          <Download className="size-4" />
          Download Report
        </Button>
      </div>

      {/* ── Print-only cover page ──────────────────────────────────── */}
      <div className="print-only">
        <div className="rounded-xl border-2 border-slate-300 p-8">
          <div className="flex flex-col gap-6">
            <div className="flex items-start justify-between border-b border-slate-200 pb-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  Development Feasibility Report
                </p>
                <h1 className="text-2xl font-bold text-slate-900">
                  {data.address || "Site Appraisal"}
                </h1>
                <p className="text-sm text-slate-600">
                  {data.postcode}
                </p>
              </div>
              <div className="text-right">
                <p className="text-[10px] uppercase tracking-wide text-slate-500">
                  Report Date
                </p>
                <p className="text-sm font-semibold text-slate-900">
                  {reportDate}
                </p>
                <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-500">
                  Verdict
                </p>
                <p className="text-sm font-bold text-slate-900">
                  {verdict.label} · {dev.dealScore}/100
                </p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <CoverStat label="GDV" value={formatCurrency(dev.totalGDV)} />
              <CoverStat
                label="Total Dev Cost"
                value={formatCurrency(dev.totalDevelopmentCost)}
              />
              <CoverStat
                label="Net Profit"
                value={formatCurrency(dev.grossProfit)}
              />
              <CoverStat
                label="Profit on Cost"
                value={`${dev.profitOnCost.toFixed(1)}%`}
              />
              <CoverStat
                label="LTGDV"
                value={`${dev.ltgdv.toFixed(1)}%`}
              />
              <CoverStat
                label="IRR"
                value={`${dev.irr.toFixed(1)}%`}
              />
              <CoverStat
                label="Equity Required"
                value={formatCurrency(dev.equityRequired)}
              />
              <CoverStat
                label="Units / GIA"
                value={`${dev.totalUnits} · ${dev.totalGIA.toLocaleString()} m²`}
              />
            </div>
            <p className="text-[10px] text-slate-500">
              This appraisal is an indicative feasibility assessment based
              on user-supplied inputs and {dev.totalUnits > 0 ? "scheme " : ""}
              comparables sourced from HM Land Registry sold-price data.
              Not a regulated valuation. Verify all figures with your QS,
              lender and planning consultant before commitment.
            </p>
          </div>
        </div>
      </div>

      {/* ── 1 · Viability Dashboard ─────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Target className="size-5 text-primary" />
                Development Viability Dashboard
              </CardTitle>
              <CardDescription>
                RICS blue-book appraisal · {dev.totalUnits} unit
                {dev.totalUnits === 1 ? "" : "s"} ·{" "}
                {dev.totalGIA.toLocaleString()} m² GIA
              </CardDescription>
            </div>
            <div
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${verdict.tone}`}
            >
              {verdict.verdict === "PROCEED" ? (
                <CheckCircle2 className="size-3.5" />
              ) : verdict.verdict === "AVOID" ? (
                <XCircle className="size-3.5" />
              ) : (
                <AlertTriangle className="size-3.5" />
              )}
              {verdict.label}
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {/* Score + label */}
          <div className="flex items-end gap-3">
            <div className="text-4xl font-bold text-foreground">
              {dev.dealScore}
            </div>
            <div className="flex flex-col pb-1">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Deal Score / 100
              </span>
              <span className="text-sm font-semibold text-primary">
                {dev.dealScoreLabel}
              </span>
            </div>
          </div>
          {/* Flags */}
          {dev.flags.length > 0 && (
            <ul className="flex flex-col gap-2">
              {dev.flags.map((f, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-lg border border-border/60 bg-background/60 px-3 py-2 text-xs"
                >
                  <span className="mt-0.5">{severityIcon(f.severity)}</span>
                  <span className="text-foreground">{f.message}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* ── 2 · Key Metrics ─────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <DevMetric
          label="Net Profit"
          value={formatCurrency(dev.grossProfit)}
          icon={dev.grossProfit >= 0 ? TrendingUp : TrendingDown}
          positive={dev.grossProfit >= 0}
        />
        <DevMetric
          label="Profit on Cost"
          value={`${dev.profitOnCost.toFixed(1)}%`}
          sub="Target ≥ 20%"
          icon={PoundSterling}
          positive={dev.profitOnCost >= 20}
        />
        <DevMetric
          label="Profit on GDV"
          value={`${dev.profitOnGDV.toFixed(1)}%`}
          sub="Target ≥ 15%"
          icon={Receipt}
          positive={dev.profitOnGDV >= 15}
        />
        <DevMetric
          label="LTGDV"
          value={`${dev.ltgdv.toFixed(1)}%`}
          sub="Lender cap ~70%"
          icon={Scale}
          positive={dev.ltgdv < 70 && dev.ltgdv > 0}
        />
        <DevMetric
          label="IRR (annualised)"
          value={`${dev.irr.toFixed(1)}%`}
          icon={TrendingUp}
          positive={dev.irr >= 20}
        />
        <DevMetric
          label="Return on Equity"
          value={`${dev.roe.toFixed(1)}%`}
          sub={`${dev.annualisedROI.toFixed(1)}% annualised`}
          icon={PoundSterling}
          positive={dev.roe >= 25}
        />
        <DevMetric
          label="Equity Required"
          value={formatCurrency(dev.equityRequired)}
          sub="Your cash in"
          icon={Wallet}
        />
        <DevMetric
          label="Total Dev Cost"
          value={formatCurrency(dev.totalDevelopmentCost)}
          sub={`GDV ${formatCurrency(dev.totalGDV)}`}
          icon={Layers}
        />
      </div>

      {/* ── 3 · GDV Summary ─────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Building2 className="size-5 text-primary" /> GDV Summary
          </CardTitle>
          <CardDescription>
            Gross Development Value by unit type · avg £
            {dev.avgGDVPerM2.toLocaleString()} /m²
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground">
                  <th className="pb-2 text-left font-medium">Unit Type</th>
                  <th className="pb-2 text-right font-medium">Qty</th>
                  <th className="pb-2 text-right font-medium">Size m²</th>
                  <th className="pb-2 text-right font-medium">£/unit</th>
                  <th className="pb-2 text-right font-medium">GDV</th>
                </tr>
              </thead>
              <tbody>
                {dev.unitLines.map((u, i) => (
                  <tr key={i} className="border-t border-border/40">
                    <td className="py-2 text-foreground">{u.unitType}</td>
                    <td className="py-2 text-right text-foreground">
                      {u.numberOfUnits}
                    </td>
                    <td className="py-2 text-right text-muted-foreground">
                      {u.avgSizeM2}
                    </td>
                    <td className="py-2 text-right text-muted-foreground">
                      {formatCurrency(u.salePricePerUnit)}
                    </td>
                    <td className="py-2 text-right font-semibold text-foreground">
                      {formatCurrency(u.gdv)}
                    </td>
                  </tr>
                ))}
                <tr className="border-t-2 border-primary/30 bg-primary/5">
                  <td className="py-2 text-sm font-semibold text-foreground">
                    Total
                  </td>
                  <td className="py-2 text-right text-sm font-semibold text-foreground">
                    {dev.totalUnits}
                  </td>
                  <td className="py-2 text-right text-sm font-semibold text-foreground">
                    {dev.totalGIA.toLocaleString()}
                  </td>
                  <td className="py-2 text-right text-sm font-semibold text-foreground">
                    {formatCurrency(dev.avgGDVPerUnit)}
                  </td>
                  <td className="py-2 text-right text-base font-bold text-primary">
                    {formatCurrency(dev.totalGDV)}
                  </td>
                </tr>
              </tbody>
            </table>
            {dev.affordableHousingDiscount > 0 && (
              <p className="mt-2 text-[11px] text-amber-700 dark:text-amber-400">
                Affordable housing revenue discount:{" "}
                {formatCurrency(dev.affordableHousingDiscount)} — netted off
                downstream profit.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── 4 · Cost Stack ──────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Layers className="size-5 text-primary" /> Cost Stack
          </CardTitle>
          <CardDescription>
            Every pound in the scheme, ordered by category. TDC ={" "}
            {formatCurrency(dev.totalDevelopmentCost)}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {/* Stacked bar */}
          <div className="flex h-4 w-full overflow-hidden rounded-full border border-border/50">
            {dev.costStack.map((line, i) => {
              const color = STACK_COLORS[line.label] ?? "bg-slate-400"
              return line.percentOfTDC > 0 ? (
                <div
                  key={i}
                  className={color}
                  style={{ width: `${line.percentOfTDC}%` }}
                  title={`${line.label}: ${formatCurrency(line.amount)} (${line.percentOfTDC.toFixed(1)}%)`}
                />
              ) : null
            })}
          </div>
          {/* Table */}
          <div className="grid grid-cols-1 gap-2">
            {dev.costStack.map((line, i) => {
              const color = STACK_COLORS[line.label] ?? "bg-slate-400"
              return (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg border border-border/50 bg-background/60 px-3 py-2 text-sm"
                >
                  <div className="flex items-center gap-2">
                    <span className={`size-3 rounded-full ${color}`} />
                    <span className="text-foreground">{line.label}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="text-muted-foreground">
                      {line.percentOfTDC.toFixed(1)}%
                    </span>
                    <span className="font-semibold text-foreground">
                      {formatCurrency(line.amount)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      {/* ── 5 · Finance Summary ─────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Banknote className="size-5 text-primary" /> Development Finance
          </CardTitle>
          <CardDescription>
            {dev.financeRolledUp
              ? "Interest rolled up to exit"
              : "Interest serviced monthly"}{" "}
            · {dev.financeRateUsed.toFixed(2)}% · {dev.financeTermMonths}{" "}
            months
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <DevMetric
              label="Facility Size"
              value={formatCurrency(dev.financeFacilityLoan)}
              sub={`LTC ${dev.ltc.toFixed(1)}%`}
              icon={Scale}
            />
            <DevMetric
              label="Day-1 Advance"
              value={formatCurrency(dev.financeDay1Drawdown)}
              sub="Against land at completion"
              icon={Wallet}
            />
            <DevMetric
              label="Total Interest"
              value={formatCurrency(dev.financeInterest)}
              sub="50% avg-utilisation basis"
              icon={TrendingUp}
            />
            <DevMetric
              label="Fees + Monitoring"
              value={formatCurrency(
                dev.financeArrangementFee +
                  dev.financeExitFee +
                  dev.financeMonitoringTotal,
              )}
              sub={`Arr ${formatCurrency(dev.financeArrangementFee)} · Exit ${formatCurrency(dev.financeExitFee)}`}
              icon={Receipt}
            />
            <DevMetric
              label="Peak Funding"
              value={formatCurrency(dev.peakFunding)}
              sub="At practical completion"
              icon={TrendingUp}
            />
            <DevMetric
              label="Total Finance Cost"
              value={formatCurrency(dev.financeCostTotal)}
              icon={Banknote}
            />
            <DevMetric
              label="LTGDV"
              value={`${dev.ltgdv.toFixed(1)}%`}
              sub="Peak loan / GDV"
              icon={Scale}
              positive={dev.ltgdv < 70 && dev.ltgdv > 0}
            />
            <DevMetric
              label="Equity Required"
              value={formatCurrency(dev.equityRequired)}
              sub="Gap to plug"
              icon={Wallet}
            />
          </div>
        </CardContent>
      </Card>

      {/* ── 6 · RLV Analysis ────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Target className="size-5 text-primary" /> Residual Land Value
          </CardTitle>
          <CardDescription>
            Back-solved maximum land price at{" "}
            {dev.rlvProfitTargetPercent}% profit-on-cost (RICS blue-book
            target)
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="flex flex-col gap-1 rounded-lg border border-border/60 bg-background/60 px-3 py-2">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Your Price
              </span>
              <span className="text-lg font-bold text-foreground">
                {formatCurrency(dev.acquisitionPrice)}
              </span>
            </div>
            <div className="flex flex-col gap-1 rounded-lg border border-primary/40 bg-primary/5 px-3 py-2">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                Residual Land Value
              </span>
              <span className="text-lg font-bold text-primary">
                {formatCurrency(dev.residualLandValue)}
              </span>
            </div>
            <div
              className={`flex flex-col gap-1 rounded-lg border px-3 py-2 ${
                dev.landPremiumOverAsk >= 0
                  ? "border-emerald-500/40 bg-emerald-500/5"
                  : "border-red-500/40 bg-red-500/5"
              }`}
            >
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                {dev.landPremiumOverAsk >= 0
                  ? "Margin of Safety"
                  : "Over-paying"}
              </span>
              <span
                className={`text-lg font-bold ${
                  dev.landPremiumOverAsk >= 0
                    ? "text-emerald-700 dark:text-emerald-400"
                    : "text-red-700 dark:text-red-400"
                }`}
              >
                {dev.landPremiumOverAsk >= 0 ? "+" : ""}
                {formatCurrency(dev.landPremiumOverAsk)}
              </span>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            RLV is the maximum you could pay for the site and still hit a{" "}
            {dev.rlvProfitTargetPercent}% profit-on-cost return, holding
            every other input constant. A negative margin means you&apos;re
            paying a premium that erodes the target margin — renegotiate
            or find efficiencies.
          </p>
        </CardContent>
      </Card>

      {/* ── 7 · Timeline ────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Calendar className="size-5 text-primary" /> Project Timeline
          </CardTitle>
          <CardDescription>
            {buildMonths} months facility term · indicative phases
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col gap-2 text-sm">
            <TimelineStep
              index={1}
              label="Acquisition & completion"
              detail={`Purchase ${formatCurrency(dev.acquisitionPrice)}, SDLT ${formatCurrency(dev.acquisitionSDLT)} · day-1 draw ${formatCurrency(dev.financeDay1Drawdown)}`}
            />
            <TimelineStep
              index={2}
              label="Construction"
              detail={`${Math.max(1, buildMonths - 3)} months · ${formatCurrency(dev.constructionTotal)} drawn in tranches`}
            />
            <TimelineStep
              index={3}
              label="Practical completion & warranty sign-off"
              detail={`Peak funding ${formatCurrency(dev.peakFunding)} · LTGDV ${dev.ltgdv.toFixed(1)}%`}
            />
            <TimelineStep
              index={4}
              label="Marketing & sales"
              detail={`~3 months · sales costs ${formatCurrency(dev.exitCostsTotal)} · redemption of facility`}
            />
            <TimelineStep
              index={5}
              label="Profit realised"
              detail={`Net profit ${formatCurrency(dev.grossProfit)} · ROE ${dev.roe.toFixed(1)}% · IRR ${dev.irr.toFixed(1)}%`}
              terminal
            />
          </ol>
        </CardContent>
      </Card>

      {/* ── 8 · Sensitivity ─────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <SlidersHorizontal className="size-5 text-primary" /> Sensitivity
          </CardTitle>
          <CardDescription>
            Stress-test the scheme — nudge GDV, build cost, or interest
            rate and watch profit-on-cost move live.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <SensitivitySlider
            label="GDV"
            value={gdvDeltaPct}
            onChange={setGdvDeltaPct}
            unit="%"
            min={-10}
            max={10}
            step={1}
          />
          <SensitivitySlider
            label="Build cost £/m²"
            value={buildDeltaPct}
            onChange={setBuildDeltaPct}
            unit="%"
            min={-10}
            max={10}
            step={1}
          />
          <SensitivitySlider
            label="Finance rate"
            value={rateDelta}
            onChange={setRateDelta}
            unit=" pp"
            min={-2}
            max={2}
            step={0.25}
          />

          {sensitivityDev && (
            <div className="grid grid-cols-1 gap-3 rounded-xl border border-primary/30 bg-primary/5 p-3 sm:grid-cols-4">
              <DevMiniStat
                label="Net Profit"
                base={formatCurrency(dev.grossProfit)}
                next={formatCurrency(sensitivityDev.grossProfit)}
                positive={
                  sensitivityDev.grossProfit >= dev.grossProfit
                }
              />
              <DevMiniStat
                label="Profit on Cost"
                base={`${dev.profitOnCost.toFixed(1)}%`}
                next={`${sensitivityDev.profitOnCost.toFixed(1)}%`}
                positive={
                  sensitivityDev.profitOnCost >= dev.profitOnCost
                }
              />
              <DevMiniStat
                label="LTGDV"
                base={`${dev.ltgdv.toFixed(1)}%`}
                next={`${sensitivityDev.ltgdv.toFixed(1)}%`}
                positive={sensitivityDev.ltgdv <= dev.ltgdv}
              />
              <DevMiniStat
                label="Deal Score"
                base={String(dev.dealScore)}
                next={String(sensitivityDev.dealScore)}
                positive={sensitivityDev.dealScore >= dev.dealScore}
              />
            </div>
          )}
          {!sensitivityDev && (
            <p className="text-[11px] text-muted-foreground">
              Move a slider to see stressed vs baseline metrics.
            </p>
          )}
        </CardContent>
      </Card>

      {/* ── 9 · Strategy Comparison chip ────────────────────── */}
      <Card className="border-dashed">
        <CardContent className="flex flex-wrap items-center gap-3 p-4 text-sm">
          <Badge variant="secondary" className="text-[11px]">
            Strategy
          </Badge>
          <span className="text-foreground">
            <strong>Build to Sell</strong>{" "}
            <span className="text-muted-foreground">
              · net profit {formatCurrency(dev.grossProfit)} in{" "}
              {buildMonths} months
            </span>
          </span>
          <span className="text-muted-foreground">vs</span>
          <span className="text-foreground">
            <strong>Build to Rent</strong>{" "}
            <span className="text-muted-foreground">
              · would require a refinance model (switch exit strategy in
              the form to model)
            </span>
          </span>
        </CardContent>
      </Card>

      {/* ── Print-only flag log + footer ───────────────────────────── */}
      <div className="print-only">
        <div className="rounded-xl border-2 border-slate-300 p-6">
          <h2 className="mb-3 text-base font-bold text-slate-900">
            Appraisal Notes & Flags
          </h2>
          {dev.flags.length === 0 ? (
            <p className="text-xs text-slate-600">
              No viability flags — scheme passes all base checks.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5 text-xs">
              {dev.flags.map((f, i) => (
                <li key={i} className="text-slate-800">
                  <strong className="uppercase">[{f.severity}]</strong>{" "}
                  {f.message}
                </li>
              ))}
            </ul>
          )}
          <div className="mt-6 grid grid-cols-2 gap-4 border-t border-slate-200 pt-4 text-[10px] text-slate-500">
            <div>
              <p className="font-semibold uppercase tracking-wide">
                Methodology
              </p>
              <p className="mt-1 leading-snug">
                Cost stack: BCIS 2024/25 build benchmarks. Finance:
                50% avg-utilisation interest approximation on
                construction tranche. RLV back-solved at{" "}
                {dev.rlvProfitTargetPercent}% profit-on-cost (RICS).
              </p>
            </div>
            <div>
              <p className="font-semibold uppercase tracking-wide">
                Disclaimer
              </p>
              <p className="mt-1 leading-snug">
                Indicative only. Not a regulated valuation. Confirm all
                inputs with QS, planning consultant, and finance broker
                before commitment.
              </p>
            </div>
          </div>
          <p className="mt-4 text-center text-[10px] text-slate-400">
            Generated by Metalyzi · {reportDate}
          </p>
        </div>
      </div>
    </div>
  )
}

/** Cover-page stat tile (print-only). */
function CoverStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="text-[9px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-1 text-base font-bold text-slate-900">{value}</p>
    </div>
  )
}

/* ── Local helpers ──────────────────────────────────────────── */

interface DevMetricProps {
  label: string
  value: string
  sub?: string
  icon?: React.ComponentType<{ className?: string }>
  positive?: boolean
}
function DevMetric({
  label,
  value,
  sub,
  icon: Icon,
  positive,
}: DevMetricProps) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-border/60 bg-background/60 p-4">
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
        {Icon ? <Icon className="size-3.5" /> : null}
        {label}
      </div>
      <div
        className={`text-lg font-bold ${
          positive === true
            ? "text-emerald-700 dark:text-emerald-400"
            : positive === false
              ? "text-red-700 dark:text-red-400"
              : "text-foreground"
        }`}
      >
        {value}
      </div>
      {sub && (
        <div className="text-[10px] text-muted-foreground">{sub}</div>
      )}
    </div>
  )
}

function TimelineStep({
  index,
  label,
  detail,
  terminal,
}: {
  index: number
  label: string
  detail: string
  terminal?: boolean
}) {
  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center">
        <div
          className={`flex size-7 items-center justify-center rounded-full border text-xs font-semibold ${
            terminal
              ? "border-primary bg-primary text-primary-foreground"
              : "border-primary/40 bg-primary/10 text-primary"
          }`}
        >
          {index}
        </div>
        {!terminal && <div className="h-full w-px bg-border/60" />}
      </div>
      <div className="flex flex-col pb-3">
        <span className="text-sm font-semibold text-foreground">
          {label}
        </span>
        <span className="text-[11px] text-muted-foreground">{detail}</span>
      </div>
    </li>
  )
}

function SensitivitySlider({
  label,
  value,
  onChange,
  unit,
  min,
  max,
  step,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  unit: string
  min: number
  max: number
  step: number
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-semibold text-foreground">
          {value > 0 ? "+" : ""}
          {value}
          {unit}
        </span>
      </div>
      <Slider
        value={[value]}
        onValueChange={(v) => onChange(v[0] ?? 0)}
        min={min}
        max={max}
        step={step}
      />
    </div>
  )
}

function DevMiniStat({
  label,
  base,
  next,
  positive,
}: {
  label: string
  base: string
  next: string
  positive: boolean
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span
        className={`text-base font-bold ${
          positive
            ? "text-emerald-700 dark:text-emerald-400"
            : "text-red-700 dark:text-red-400"
        }`}
      >
        {next}
      </span>
      <span className="text-[10px] text-muted-foreground">
        baseline {base}
      </span>
    </div>
  )
}

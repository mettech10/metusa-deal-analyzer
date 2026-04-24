"use client"

/**
 * Auto-GDV estimator — Property Development strategy.
 *
 * Given postcode + the current unit mix + construction type, hits
 * /api/gdv/calculate and lets the user one-click-apply Conservative,
 * Mid, or Optimistic per-unit sale prices back onto the unit-mix rows.
 * Pre-selects Mid on successful load.
 *
 * Fails gracefully: if the service returns an error envelope (no comps
 * available etc.), we surface the message as a hint — the manual
 * Sale £/unit inputs continue to work unchanged. We never block the form.
 */

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Calculator,
  ChevronDown,
  ChevronUp,
  Loader2,
  Sparkles,
} from "lucide-react"
import { formatCurrency } from "@/lib/calculations"

interface GdvComparable {
  address: string
  saleDate: string
  salePrice: number
  floorAreaM2: number
  pricePerM2: number
  source: string
  floorAreaEstimated: boolean
}

export interface GdvPerUnit {
  unitType: string
  numberOfUnits: number
  avgSizeM2: number
  conservativePerUnit: number
  midPerUnit: number
  optimisticPerUnit: number
  conservativeTotal: number
  midTotal: number
  optimisticTotal: number
}

export interface GdvEstimate {
  conservativeGDV: number
  midGDV: number
  optimisticGDV: number
  avgPricePerM2: number
  lowerPricePerM2: number
  upperPricePerM2: number
  perUnit: GdvPerUnit[]
  comparables: GdvComparable[]
  comparablesUsed: number
  methodology: string
  dataSource: string
  quantileUsed: string
  epcDataUsed: boolean
  wideningLabel?: string
  relaxation?: string
  constructionType: string
  newBuildUplift: number
}

export interface AutoGdvUnitInput {
  unitType: string
  numberOfUnits: number
  avgSizeM2: number
}

interface AutoGdvButtonProps {
  postcode: string
  units: AutoGdvUnitInput[]
  constructionType?: string
  /** Apply the chosen scenario's per-unit prices back onto the unit mix.
   *  Receives an ordered array matching the input `units` order. */
  onApplyScenario: (
    scenario: "conservative" | "mid" | "optimistic",
    perUnit: GdvPerUnit[],
  ) => void
  onEstimate?: (estimate: GdvEstimate | null) => void
}

export function AutoGdvButton({
  postcode,
  units,
  constructionType,
  onApplyScenario,
  onEstimate,
}: AutoGdvButtonProps) {
  const [loading, setLoading] = useState(false)
  const [estimate, setEstimate] = useState<GdvEstimate | null>(null)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [selected, setSelected] = useState<
    "conservative" | "mid" | "optimistic" | null
  >(null)
  const [compsOpen, setCompsOpen] = useState(false)

  const validUnits = units.filter(
    (u) => (u?.numberOfUnits || 0) > 0 && (u?.avgSizeM2 || 0) > 0,
  )
  const canFetch =
    typeof postcode === "string" &&
    postcode.trim().length >= 2 &&
    validUnits.length > 0

  async function fetchGdv() {
    setLoading(true)
    setErrorMsg(null)
    try {
      const resp = await fetch("/api/gdv/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          postcode: postcode.trim().toUpperCase(),
          units: validUnits,
          constructionType: constructionType || "new-build-traditional",
        }),
      })
      const data = await resp.json()
      if (data && typeof data.midGDV === "number") {
        setEstimate(data as GdvEstimate)
        setErrorMsg(null)
        setSelected("mid")
        onApplyScenario("mid", (data as GdvEstimate).perUnit)
        onEstimate?.(data as GdvEstimate)
      } else {
        setEstimate(null)
        setErrorMsg(
          data?.message ||
            data?.error ||
            "Could not compute GDV — enter sale prices manually",
        )
        onEstimate?.(null)
      }
    } catch (e) {
      console.error("[auto-gdv]", e)
      setEstimate(null)
      setErrorMsg("Auto-GDV request failed — enter sale prices manually")
      onEstimate?.(null)
    } finally {
      setLoading(false)
    }
  }

  function pick(scenario: "conservative" | "mid" | "optimistic") {
    if (!estimate) return
    setSelected(scenario)
    onApplyScenario(scenario, estimate.perUnit)
  }

  const scenarios: Array<{
    id: "conservative" | "mid" | "optimistic"
    label: string
    total: number
    hint: string
  }> = estimate
    ? [
        {
          id: "conservative",
          label: "Conservative",
          total: estimate.conservativeGDV,
          hint: "Lower £/m² — cautious sale assumption",
        },
        {
          id: "mid",
          label: "Mid",
          total: estimate.midGDV,
          hint: "Weighted-avg £/m² of top comps",
        },
        {
          id: "optimistic",
          label: "Optimistic",
          total: estimate.optimisticGDV,
          hint: "Upper £/m² — premium / strong market",
        },
      ]
    : []

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-primary/30 bg-primary/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles className="size-4 text-primary" />
          <span className="text-sm font-semibold text-foreground">
            Auto-Calculate GDV
          </span>
          {estimate?.comparablesUsed ? (
            <Badge variant="secondary" className="text-[10px]">
              {estimate.comparablesUsed} comps
            </Badge>
          ) : null}
        </div>
        <Button
          type="button"
          size="sm"
          onClick={fetchGdv}
          disabled={!canFetch || loading}
          className="gap-1.5"
        >
          {loading ? (
            <>
              <Loader2 className="size-3.5 animate-spin" />
              Fetching comps…
            </>
          ) : (
            <>
              <Calculator className="size-3.5" />
              {estimate ? "Recalculate" : "Calculate GDV"}
            </>
          )}
        </Button>
      </div>

      {!canFetch && (
        <p className="text-[11px] text-muted-foreground">
          Enter a postcode and add at least one unit (with units &gt; 0 and
          size &gt; 0 m²) to enable Auto-GDV.
        </p>
      )}

      {errorMsg && (
        <p className="text-[11px] text-amber-700 dark:text-amber-400">
          {errorMsg}
        </p>
      )}

      {estimate && (
        <>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {scenarios.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => pick(s.id)}
                className={`flex flex-col gap-0.5 rounded-lg border px-3 py-2.5 text-left transition-all ${
                  selected === s.id
                    ? "border-primary bg-primary/15 ring-1 ring-primary/40"
                    : "border-border/50 bg-background hover:border-border"
                }`}
              >
                <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {s.label}
                </span>
                <span className="text-base font-bold text-foreground">
                  {formatCurrency(s.total)}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {s.hint}
                </span>
              </button>
            ))}
          </div>

          <div className="rounded-lg border border-border/60 bg-background/60 p-2">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted-foreground">
                  <th className="pb-1 text-left font-medium">Unit</th>
                  <th className="pb-1 text-right font-medium">Cons.</th>
                  <th className="pb-1 text-right font-medium">Mid</th>
                  <th className="pb-1 text-right font-medium">Opt.</th>
                </tr>
              </thead>
              <tbody>
                {estimate.perUnit.map((row, idx) => (
                  <tr key={idx} className="border-t border-border/40">
                    <td className="py-1 text-foreground">
                      {row.numberOfUnits}× {row.unitType}{" "}
                      <span className="text-muted-foreground">
                        ({row.avgSizeM2} m²)
                      </span>
                    </td>
                    <td className="py-1 text-right text-muted-foreground">
                      {formatCurrency(row.conservativePerUnit)}
                    </td>
                    <td className="py-1 text-right font-semibold text-foreground">
                      {formatCurrency(row.midPerUnit)}
                    </td>
                    <td className="py-1 text-right text-muted-foreground">
                      {formatCurrency(row.optimisticPerUnit)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-[11px] text-muted-foreground">
            {estimate.methodology}
          </p>
          <p className="text-[10px] text-muted-foreground">
            Source: {estimate.dataSource}
            {estimate.wideningLabel ? ` · ${estimate.wideningLabel}` : ""}
            {estimate.relaxation ? ` · ${estimate.relaxation}` : ""}
          </p>

          {estimate.comparables?.length ? (
            <button
              type="button"
              onClick={() => setCompsOpen((o) => !o)}
              className="inline-flex items-center gap-1 self-start text-[11px] text-primary hover:underline"
            >
              {compsOpen ? (
                <>
                  <ChevronUp className="size-3" /> Hide comparable sales
                </>
              ) : (
                <>
                  <ChevronDown className="size-3" /> Show{" "}
                  {estimate.comparables.length} comparable sale
                  {estimate.comparables.length === 1 ? "" : "s"}
                </>
              )}
            </button>
          ) : null}

          {compsOpen && (
            <div className="rounded-lg border border-border/60 bg-background/60 p-2">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-muted-foreground">
                    <th className="pb-1 text-left font-medium">Address</th>
                    <th className="pb-1 text-right font-medium">Sold</th>
                    <th className="pb-1 text-right font-medium">Price</th>
                    <th className="pb-1 text-right font-medium">m²</th>
                    <th className="pb-1 text-right font-medium">£/m²</th>
                  </tr>
                </thead>
                <tbody>
                  {estimate.comparables.map((c, i) => (
                    <tr key={i} className="border-t border-border/40">
                      <td className="py-1 text-foreground">{c.address}</td>
                      <td className="py-1 text-right text-muted-foreground">
                        {c.saleDate}
                      </td>
                      <td className="py-1 text-right text-muted-foreground">
                        {formatCurrency(c.salePrice)}
                      </td>
                      <td className="py-1 text-right text-muted-foreground">
                        {c.floorAreaM2}
                        {c.floorAreaEstimated ? "*" : ""}
                      </td>
                      <td className="py-1 text-right text-muted-foreground">
                        £{c.pricePerM2.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1 text-[10px] text-muted-foreground">
                * floor area estimated from postcode EPC median
              </p>
            </div>
          )}
        </>
      )}
    </div>
  )
}

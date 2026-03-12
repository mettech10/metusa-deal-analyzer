"use client"

import { useEffect, useState, useCallback } from "react"
import { MoreVertical, Trash2, TrendingUp, Calendar, MapPin, ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { PropertyFormData, CalculationResults } from "@/lib/types"

interface SavedAnalysis {
  id: string
  created_at: string
  address: string
  postcode: string | null
  investment_type: string
  purchase_price: number
  deal_score: number | null
  monthly_cashflow: number | null
  annual_cashflow: number | null
  gross_yield: number | null
}

interface RecentDealsProps {
  onLoad?: (formData: PropertyFormData, results: CalculationResults, aiText: string) => void
}

const strategyLabel: Record<string, string> = {
  btl: "BTL",
  brr: "BRR",
  hmo: "HMO",
  flip: "Flip",
  r2sa: "R2SA",
  development: "Dev",
}

const strategyColor: Record<string, string> = {
  btl: "bg-blue-100 text-blue-700",
  brr: "bg-purple-100 text-purple-700",
  hmo: "bg-orange-100 text-orange-700",
  flip: "bg-red-100 text-red-700",
  r2sa: "bg-green-100 text-green-700",
  development: "bg-yellow-100 text-yellow-700",
}

function scoreColor(score: number | null) {
  if (score === null) return "text-muted-foreground"
  if (score >= 75) return "text-green-600"
  if (score >= 50) return "text-blue-600"
  if (score >= 25) return "text-amber-600"
  return "text-red-600"
}

function formatCurrency(n: number | null) {
  if (n === null || n === undefined) return "—"
  return `£${Math.round(n).toLocaleString("en-GB")}`
}

export function RecentDeals({ onLoad }: RecentDealsProps) {
  const [analyses, setAnalyses] = useState<SavedAnalysis[]>([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [loadingId, setLoadingId] = useState<string | null>(null)

  const fetchAnalyses = useCallback(async () => {
    try {
      const res = await fetch("/api/analyses")
      if (!res.ok) {
        setAnalyses([])
        return
      }
      const data = await res.json()
      setAnalyses(data.analyses || [])
    } catch {
      setAnalyses([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAnalyses()
  }, [fetchAnalyses])

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    setDeletingId(id)
    try {
      const res = await fetch(`/api/analyses/${id}`, { method: "DELETE" })
      if (res.ok || res.status === 204) {
        setAnalyses((prev) => prev.filter((a) => a.id !== id))
      }
    } finally {
      setDeletingId(null)
    }
  }

  const handleLoad = async (id: string) => {
    if (!onLoad) return
    setLoadingId(id)
    try {
      const res = await fetch(`/api/analyses/${id}`)
      if (!res.ok) return
      const data = await res.json()
      if (data.form_data && data.results) {
        onLoad(data.form_data as PropertyFormData, data.results as CalculationResults, data.ai_text || "")
      }
    } catch {
      // silently skip
    } finally {
      setLoadingId(null)
    }
  }

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="h-4 w-32 rounded bg-muted animate-pulse" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-32 rounded-xl border border-border/50 bg-muted/30 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (analyses.length === 0) return null

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <TrendingUp className="size-4 text-primary" />
        <h2 className="text-sm font-semibold text-foreground">Recent Deals</h2>
        <span className="ml-auto text-xs text-muted-foreground">{analyses.length} saved</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {analyses.map((deal) => (
          <div
            key={deal.id}
            onClick={() => handleLoad(deal.id)}
            className={`group relative rounded-xl border border-border/50 bg-card p-4 shadow-sm transition-all hover:shadow-md hover:border-primary/30 ${onLoad ? "cursor-pointer" : ""} ${loadingId === deal.id ? "opacity-60" : ""}`}
          >
            {/* Top row: strategy badge + three-dot menu */}
            <div className="mb-2 flex items-start justify-between gap-2">
              <span
                className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${
                  strategyColor[deal.investment_type] || "bg-muted text-muted-foreground"
                }`}
              >
                {strategyLabel[deal.investment_type] || deal.investment_type.toUpperCase()}
              </span>

              <div className="flex items-center gap-1">
                {onLoad && (
                  <ExternalLink className="size-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                )}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-6 opacity-0 group-hover:opacity-100 transition-opacity"
                      disabled={deletingId === deal.id}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreVertical className="size-3.5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      className="text-destructive focus:text-destructive"
                      onClick={(e) => handleDelete(e, deal.id)}
                    >
                      <Trash2 className="mr-2 size-3.5" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>

            {/* Address */}
            <div className="mb-3">
              <div className="flex items-start gap-1.5">
                <MapPin className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
                <p className="line-clamp-2 text-xs font-medium text-foreground leading-snug">
                  {deal.address}
                  {deal.postcode ? `, ${deal.postcode}` : ""}
                </p>
              </div>
            </div>

            {/* Metrics row */}
            <div className="grid grid-cols-3 gap-1 mb-3">
              <div className="text-center">
                <p className={`text-sm font-bold tabular-nums ${scoreColor(deal.deal_score)}`}>
                  {deal.deal_score !== null ? `${deal.deal_score}` : "—"}
                </p>
                <p className="text-[10px] text-muted-foreground">Score</p>
              </div>
              <div className="text-center">
                <p className={`text-sm font-bold tabular-nums ${
                  (deal.monthly_cashflow ?? 0) >= 0 ? "text-green-600" : "text-red-600"
                }`}>
                  {formatCurrency(deal.monthly_cashflow)}<span className="text-[9px] font-normal">/mo</span>
                </p>
                <p className="text-[10px] text-muted-foreground">Cash Flow</p>
              </div>
              <div className="text-center">
                <p className="text-sm font-bold tabular-nums text-foreground">
                  {deal.gross_yield !== null ? `${deal.gross_yield.toFixed(1)}%` : "—"}
                </p>
                <p className="text-[10px] text-muted-foreground">Yield</p>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-border/40 pt-2">
              <p className="text-[10px] text-muted-foreground">
                {formatCurrency(deal.purchase_price)}
              </p>
              <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
                <Calendar className="size-2.5" />
                {new Date(deal.created_at).toLocaleDateString("en-GB", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

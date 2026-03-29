"use client"

import { useState, useEffect } from "react"
import { ExternalLink, Loader2, TrendingUp, TrendingDown, Minus } from "lucide-react"

interface SpareRoomListing {
  title: string
  address: string
  postcode: string
  monthly_rent: number | null
  bills_included: string
  num_rooms: number | null
  room_type: string
  available_from: string
  listing_url: string
}

interface HmoAnalysis {
  demand: "strong" | "moderate" | "weak"
  rentRange: string
  roomTypes: string
  patterns: string
  verdict: string
}

interface HmoComparablesProps {
  postcode: string
}

const DEMAND_CONFIG = {
  strong: { label: "Strong HMO Demand", icon: TrendingUp, color: "text-emerald-600", bg: "bg-emerald-50 border-emerald-200" },
  moderate: { label: "Moderate HMO Demand", icon: Minus, color: "text-amber-600", bg: "bg-amber-50 border-amber-200" },
  weak: { label: "Weak HMO Demand", icon: TrendingDown, color: "text-red-600", bg: "bg-red-50 border-red-200" },
}

function DemandBadge({ demand }: { demand: "strong" | "moderate" | "weak" }) {
  const cfg = DEMAND_CONFIG[demand] || DEMAND_CONFIG.moderate
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium ${cfg.color} ${cfg.bg}`}>
      <Icon className="size-4" />
      {cfg.label}
    </span>
  )
}

export function HmoComparables({ postcode }: HmoComparablesProps) {
  const [listings, setListings] = useState<SpareRoomListing[]>([])
  const [analysis, setAnalysis] = useState<HmoAnalysis | null>(null)
  const [loadingListings, setLoadingListings] = useState(true)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function fetchData() {
      setLoadingListings(true)
      setError(null)

      try {
        const res = await fetch("/api/comparables/spareroom", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ postcode, maxResults: 12 }),
        })
        const data = await res.json()
        if (cancelled) return

        if (!data.success) {
          setError(data.message || "Failed to fetch SpareRoom listings")
          setLoadingListings(false)
          return
        }

        const fetchedListings: SpareRoomListing[] = data.listings || []
        setListings(fetchedListings)
        setLoadingListings(false)

        if (fetchedListings.length === 0) return

        // Run HMO area analysis
        setLoadingAnalysis(true)
        const aiRes = await fetch("/api/comparables/hmo-analysis", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ postcode, listings: fetchedListings }),
        })
        const aiData = await aiRes.json()
        if (cancelled) return

        if (aiData.success && aiData.analysis) {
          setAnalysis(aiData.analysis)
        }
      } catch {
        if (!cancelled) setError("Failed to load HMO data")
      } finally {
        if (!cancelled) {
          setLoadingListings(false)
          setLoadingAnalysis(false)
        }
      }
    }

    fetchData()
    return () => { cancelled = true }
  }, [postcode])

  if (loadingListings) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center gap-3 py-8">
          <Loader2 className="size-5 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Fetching live SpareRoom listings near {postcode}…</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        {error}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* ── Rental Comparables ─────────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h3 className="text-base font-semibold text-foreground">
            Rental Comparables — {postcode}
          </h3>
          <span className="text-xs text-muted-foreground">
            Live listings from SpareRoom · {listings.length} found
          </span>
        </div>

        {listings.length === 0 ? (
          <p className="text-sm text-muted-foreground py-2">
            No SpareRoom listings found near {postcode}. Try a broader postcode (e.g. just the outward code).
          </p>
        ) : (
          <div className="flex flex-col divide-y divide-border/50 rounded-xl border border-border/50 overflow-hidden">
            {listings.map((lst, i) => (
              <div key={i} className="flex items-start gap-3 px-4 py-3 bg-card hover:bg-muted/30 transition-colors">
                <div className="flex-1 min-w-0 flex flex-col gap-0.5">
                  <p className="text-sm font-medium text-foreground truncate">{lst.title}</p>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                    <span>{lst.postcode || lst.address}</span>
                    {lst.room_type && lst.room_type !== "Unknown" && <span>· {lst.room_type}</span>}
                    {lst.bills_included === "Yes" && <span>· Bills included</span>}
                    {lst.available_from && lst.available_from !== "Now" && (
                      <span>· Available {lst.available_from}</span>
                    )}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  {lst.monthly_rent ? (
                    <span className="text-sm font-semibold text-foreground">£{lst.monthly_rent.toLocaleString()} pcm</span>
                  ) : (
                    <span className="text-sm text-muted-foreground">POA</span>
                  )}
                  {lst.listing_url && (
                    <a
                      href={lst.listing_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-primary hover:underline"
                    >
                      View <ExternalLink className="size-3" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Area HMO Analysis ──────────────────────────────────────────── */}
      {(analysis || loadingAnalysis) && (
        <div className="flex flex-col gap-4 rounded-xl border border-border/50 bg-card p-5">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="text-base font-semibold text-foreground">Area HMO Analysis</h3>
            {loadingAnalysis && !analysis && (
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Analysing…
              </span>
            )}
            {analysis && <DemandBadge demand={analysis.demand} />}
          </div>

          {analysis && (
            <div className="flex flex-col gap-3 text-sm">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-lg bg-muted/50 px-3 py-2">
                  <p className="text-xs text-muted-foreground mb-0.5">Typical Rent Range</p>
                  <p className="font-medium text-foreground">{analysis.rentRange}</p>
                </div>
                <div className="rounded-lg bg-muted/50 px-3 py-2">
                  <p className="text-xs text-muted-foreground mb-0.5">Common Room Types</p>
                  <p className="font-medium text-foreground">{analysis.roomTypes}</p>
                </div>
              </div>
              {analysis.patterns && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Notable Patterns</p>
                  <p className="text-muted-foreground leading-relaxed">{analysis.patterns}</p>
                </div>
              )}
              {analysis.verdict && (
                <div className="border-t border-border/50 pt-3">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Overall Verdict</p>
                  <p className="text-foreground leading-relaxed">{analysis.verdict}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

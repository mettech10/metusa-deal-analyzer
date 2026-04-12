"use client"

import { useState, useEffect } from "react"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { formatCurrency } from "@/lib/calculations"
import {
  Star,
  ExternalLink,
  TrendingUp,
  TrendingDown,
  Minus,
  Moon,
  BarChart3,
  AlertTriangle,
  Loader2,
  MapPin,
  Home,
  Users,
  Percent,
  CalendarDays,
} from "lucide-react"

// ── Types ────────────────────────────────────────────────────────────────

interface AirroiMarketStats {
  avg_nightly_rate?: number
  min_nightly_rate?: number
  max_nightly_rate?: number
  avg_occupancy?: number
  avg_rating?: number
  estimated_monthly_revenue?: number
  listing_count?: number
  revenue_validation?: {
    user_entered: number
    market_estimate: number
    deviation_pct: number
    direction: "above" | "below"
    flag: string
  }
}

interface AirroiNearbyListing {
  // Airroi field names vary — handle flexibly
  title?: string
  name?: string
  adr?: number
  average_daily_rate?: number
  nightly_rate?: number
  price?: number
  rate?: number
  occupancy?: number
  occupancy_rate?: number
  rating?: number
  stars?: number
  review_score?: number
  reviews?: number
  reviews_count?: number
  number_of_reviews?: number
  bedrooms?: number
  beds?: number
  property_type?: string
  room_type?: string
  type?: string
  url?: string
  listing_url?: string
  airbnb_url?: string
  thumbnail?: string
  image_url?: string
  photo?: string
  revenue?: number
  monthly_revenue?: number
  annual_revenue?: number
  latitude?: number
  longitude?: number
  id?: string
  listing_id?: string
}

interface SaComparablesProps {
  postcode: string
  backendData?: {
    airroi_market?: AirroiMarketStats
    airroi_nearby_listings?: AirroiNearbyListing[]
    airroi_market_summary?: Record<string, unknown>
    airroi_occupancy_trend?: Record<string, unknown>
    airroi_adr_trend?: Record<string, unknown>
  } | null
}

// ── Helpers ──────────────────────────────────────────────────────────────

function getNightly(item: AirroiNearbyListing): number | null {
  for (const k of ["adr", "average_daily_rate", "nightly_rate", "price", "rate"] as const) {
    const v = item[k as keyof AirroiNearbyListing]
    if (v != null && typeof v === "number" && v > 0) return v
  }
  return null
}

function getRating(item: AirroiNearbyListing): number | null {
  for (const k of ["rating", "stars", "review_score"] as const) {
    const v = item[k as keyof AirroiNearbyListing]
    if (v != null && typeof v === "number" && v > 0) return v
  }
  return null
}

function getReviews(item: AirroiNearbyListing): number {
  for (const k of ["reviews", "reviews_count", "number_of_reviews"] as const) {
    const v = item[k as keyof AirroiNearbyListing]
    if (v != null && typeof v === "number") return v
  }
  return 0
}

function getOccupancy(item: AirroiNearbyListing): number | null {
  for (const k of ["occupancy", "occupancy_rate"] as const) {
    const v = item[k as keyof AirroiNearbyListing]
    if (v != null && typeof v === "number") return v
  }
  return null
}

function getTitle(item: AirroiNearbyListing): string {
  return item.title || item.name || "Airbnb Listing"
}

function getUrl(item: AirroiNearbyListing): string {
  return item.url || item.listing_url || item.airbnb_url || ""
}

function getThumbnail(item: AirroiNearbyListing): string {
  return item.thumbnail || item.image_url || item.photo || ""
}

function getPropertyType(item: AirroiNearbyListing): string {
  return item.property_type || item.room_type || item.type || "Entire home"
}

function formatOccupancy(val: number | null | undefined): string {
  if (val == null) return "N/A"
  // Could be 0-1 or 0-100
  if (val <= 1) return `${Math.round(val * 100)}%`
  return `${Math.round(val)}%`
}

function StarRating({ rating }: { rating: number | null }) {
  if (!rating) return null
  return (
    <span className="inline-flex items-center gap-1 text-xs text-amber-400">
      <Star className="size-3 fill-amber-400" />
      {rating.toFixed(1)}
    </span>
  )
}

// ── SA Market Metrics Panel ─────────────────────────────────────────────

function SAMarketMetrics({ stats }: { stats: AirroiMarketStats }) {
  const metrics = [
    {
      label: "Avg Nightly Rate",
      value: stats.avg_nightly_rate ? `£${Math.round(stats.avg_nightly_rate)}` : "–",
      icon: Moon,
      color: "text-blue-400",
    },
    {
      label: "Rate Range",
      value:
        stats.min_nightly_rate && stats.max_nightly_rate
          ? `£${Math.round(stats.min_nightly_rate)} – £${Math.round(stats.max_nightly_rate)}`
          : "–",
      icon: BarChart3,
      color: "text-purple-400",
    },
    {
      label: "Avg Occupancy",
      value: formatOccupancy(stats.avg_occupancy),
      icon: CalendarDays,
      color: "text-emerald-400",
    },
    {
      label: "Est. Monthly Revenue",
      value: stats.estimated_monthly_revenue
        ? `£${Math.round(stats.estimated_monthly_revenue).toLocaleString()}`
        : "–",
      icon: TrendingUp,
      color: "text-teal-400",
    },
    {
      label: "Active Listings",
      value: stats.listing_count ? stats.listing_count.toString() : "–",
      icon: Home,
      color: "text-indigo-400",
    },
    {
      label: "Avg Guest Rating",
      value: stats.avg_rating ? `${stats.avg_rating.toFixed(1)}/5` : "–",
      icon: Star,
      color: "text-amber-400",
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="flex items-start gap-2 rounded-lg border border-border/50 bg-muted/30 p-3"
        >
          <m.icon className={`mt-0.5 size-4 shrink-0 ${m.color}`} />
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">{m.label}</p>
            <p className="text-sm font-semibold">{m.value}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Revenue Validation Banner ───────────────────────────────────────────

function RevenueValidationBanner({
  validation,
}: {
  validation: AirroiMarketStats["revenue_validation"]
}) {
  if (!validation) return null

  const isAbove = validation.direction === "above"
  const severity = validation.deviation_pct > 50 ? "high" : "medium"

  return (
    <div
      className={`flex items-start gap-3 rounded-lg border p-4 ${
        severity === "high"
          ? "border-red-500/30 bg-red-500/10"
          : "border-amber-500/30 bg-amber-500/10"
      }`}
    >
      <AlertTriangle
        className={`mt-0.5 size-5 shrink-0 ${
          severity === "high" ? "text-red-400" : "text-amber-400"
        }`}
      />
      <div>
        <p
          className={`text-sm font-semibold ${
            severity === "high" ? "text-red-300" : "text-amber-300"
          }`}
        >
          Revenue {isAbove ? "Above" : "Below"} Market ({validation.deviation_pct}%
          {isAbove ? " higher" : " lower"})
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Your entered SA revenue of{" "}
          <span className="font-medium text-foreground">
            £{validation.user_entered.toLocaleString()}/mo
          </span>{" "}
          is {validation.deviation_pct}% {validation.direction} the market estimate of{" "}
          <span className="font-medium text-foreground">
            £{Math.round(validation.market_estimate).toLocaleString()}/mo
          </span>
          .
          {isAbove
            ? " Consider verifying your revenue projections against actual comparable listings."
            : " Your projection may be conservative — review nearby listings for potential upside."}
        </p>
      </div>
    </div>
  )
}

// ── Nightly Rate Comparable Card ────────────────────────────────────────

function ListingCard({ item }: { item: AirroiNearbyListing }) {
  const nightly = getNightly(item)
  const rating = getRating(item)
  const reviews = getReviews(item)
  const occ = getOccupancy(item)
  const title = getTitle(item)
  const url = getUrl(item)
  const thumb = getThumbnail(item)
  const propType = getPropertyType(item)
  const beds = item.bedrooms || item.beds

  return (
    <div className="group flex gap-3 rounded-lg border border-border/50 bg-card p-3 transition-colors hover:border-border">
      {/* Thumbnail */}
      <div className="size-20 shrink-0 overflow-hidden rounded-md bg-muted">
        {thumb ? (
          <img
            src={thumb}
            alt={title}
            className="size-full object-cover"
            onError={(e) => {
              ;(e.target as HTMLImageElement).style.display = "none"
            }}
          />
        ) : (
          <div className="flex size-full items-center justify-center">
            <Home className="size-6 text-muted-foreground/40" />
          </div>
        )}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <h4 className="truncate text-sm font-medium leading-tight">{title}</h4>
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 text-muted-foreground transition-colors hover:text-primary"
            >
              <ExternalLink className="size-3.5" />
            </a>
          )}
        </div>

        <div className="mt-1 flex flex-wrap items-center gap-2">
          {nightly != null && (
            <span className="text-sm font-bold text-primary">
              £{Math.round(nightly)}/night
            </span>
          )}
          <StarRating rating={rating} />
          {reviews > 0 && (
            <span className="text-xs text-muted-foreground">({reviews} reviews)</span>
          )}
        </div>

        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
            {propType}
          </Badge>
          {beds != null && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {beds} bed{beds !== 1 ? "s" : ""}
            </Badge>
          )}
          {occ != null && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {formatOccupancy(occ)} occ.
            </Badge>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main Component ──────────────────────────────────────────────────────

export function SaComparables({ postcode, backendData }: SaComparablesProps) {
  const airroiMarket = backendData?.airroi_market as AirroiMarketStats | undefined
  const nearbyListings = (backendData?.airroi_nearby_listings ?? []) as AirroiNearbyListing[]
  const hasData = !!airroiMarket?.avg_nightly_rate || nearbyListings.length > 0
  const validation = airroiMarket?.revenue_validation

  if (!hasData) {
    // No Airroi data — show fallback with Airbnb search link
    const district = postcode.split(" ")[0] || postcode
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Moon className="size-4 text-primary" />
            <CardTitle className="text-base">Airbnb Market Comparables</CardTitle>
          </div>
          <CardDescription>
            Nightly rate data for SA/R2SA analysis near {postcode}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-lg border border-dashed border-border/60 p-6 text-center">
            <p className="text-sm text-muted-foreground">
              Airbnb market data is not available for this area.
            </p>
            <a
              href={`https://www.airbnb.co.uk/s/${district}/homes?adults=2`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
            >
              Search Airbnb manually
              <ExternalLink className="size-3.5" />
            </a>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Moon className="size-4 text-primary" />
            <CardTitle className="text-base">Airbnb Market Comparables</CardTitle>
          </div>
          <Badge variant="outline" className="text-[10px]">
            <MapPin className="mr-1 size-3" />
            {postcode}
          </Badge>
        </div>
        <CardDescription>
          Live Airbnb nightly rate data for SA/R2SA investment analysis
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-5">
        {/* Revenue Validation Flag */}
        {validation && <RevenueValidationBanner validation={validation} />}

        {/* Market Metrics Grid */}
        {airroiMarket && <SAMarketMetrics stats={airroiMarket} />}

        {/* Source attribution */}
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>
            Source: <span className="font-medium text-foreground/70">Airroi API</span>{" "}
            — live Airbnb data
          </span>
          {nearbyListings.length > 0 && (
            <span>{nearbyListings.length} nearby listings</span>
          )}
        </div>

        {/* Nearby Listings */}
        {nearbyListings.length > 0 && (
          <div>
            <h4 className="mb-3 text-sm font-semibold">Nearby Airbnb Listings</h4>
            <div className="max-h-[500px] space-y-2 overflow-y-auto pr-1">
              {nearbyListings.map((item, i) => (
                <ListingCard key={item.id || item.listing_id || i} item={item} />
              ))}
            </div>
          </div>
        )}

        {/* Airbnb search link */}
        <div className="pt-1 text-center">
          <a
            href={`https://www.airbnb.co.uk/s/${postcode.split(" ")[0]}/homes?adults=2`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary"
          >
            View all Airbnb listings near {postcode}
            <ExternalLink className="size-3" />
          </a>
        </div>
      </CardContent>
    </Card>
  )
}

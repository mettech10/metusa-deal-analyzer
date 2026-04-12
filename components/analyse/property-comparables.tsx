"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { formatCurrency } from "@/lib/calculations"
import {
  Home,
  PoundSterling,
  TrendingUp,
  MapPin,
  ExternalLink,
  BedDouble,
  Loader2,
} from "lucide-react"

// ── Interfaces ────────────────────────────────────────────────────────
interface ComparableSale {
  price: number
  date: string
  street: string
  town?: string
}

interface RentalComparable {
  price: number
  date?: string
  address?: string
  source?: string
}

interface ComparablesData {
  postcode: string
  soldPrices: {
    sales: ComparableSale[]
    average: number
    count: number
  }
  rentalEstimate?: {
    monthly: number
    confidence: string
    range?: {
      low: number
      high: number
    }
  }
  priceTrend?: {
    trend: string
    change_percent: number
  }
}

interface RoomListing {
  title: string
  address: string
  postcode: string
  monthly_rent: number | null
  bills_included: string
  room_type: string
  listing_url: string
  image_url: string
  distance_km: number | null
  source: string
}

interface RoomListingsData {
  listings: RoomListing[]
  source: string
  count: number
  summary?: {
    averageRent?: number
    minRent?: number
    maxRent?: number
  }
  searchUrl?: string
  propertyDataFallback?: {
    monthly?: number
    range?: { low: number; high: number }
  }
  timestamp?: string
}

interface PropertyComparablesProps {
  postcode: string
  bedrooms: number
  currentPrice?: number
  investmentType?: string
}

// ── Room type badge colours ───────────────────────────────────────────
const ROOM_TYPE_STYLES: Record<string, string> = {
  double: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300",
  single: "bg-slate-100 text-slate-800 dark:bg-slate-900/30 dark:text-slate-300",
  "en-suite":
    "bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-300",
  studio:
    "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
}

function RoomTypeBadge({ type }: { type: string }) {
  const label = type.charAt(0).toUpperCase() + type.slice(1)
  const style = ROOM_TYPE_STYLES[type.toLowerCase()] || ROOM_TYPE_STYLES.double
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${style}`}
    >
      {label}
    </span>
  )
}

// ── Sold Prices Card (unchanged from original) ───────────────────────
function SoldPricesCard({
  soldPrices,
  postcode,
  currentPrice,
}: {
  soldPrices: ComparablesData["soldPrices"]
  postcode: string
  currentPrice?: number
}) {
  const priceDiff =
    currentPrice && soldPrices.average
      ? ((currentPrice - soldPrices.average) / soldPrices.average) * 100
      : null

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Home className="size-4 text-primary" />
            <CardTitle className="text-base">Sold Prices</CardTitle>
          </div>
          <Badge variant="outline" className="text-xs">
            {postcode}
          </Badge>
        </div>
        <CardDescription>Recent sales from Land Registry</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {soldPrices.average > 0 && (
          <div className="rounded-lg bg-primary/5 p-3">
            <div className="text-sm text-muted-foreground">
              Average Sold Price
            </div>
            <div className="text-2xl font-bold text-foreground">
              {formatCurrency(soldPrices.average)}
            </div>
            {priceDiff !== null && (
              <div
                className={`text-sm mt-1 ${priceDiff > 0 ? "text-destructive" : "text-success"}`}
              >
                {priceDiff > 0 ? "\u2191" : "\u2193"}{" "}
                {Math.abs(priceDiff).toFixed(1)}% vs asking price
              </div>
            )}
          </div>
        )}

        {soldPrices.sales.length > 0 && (
          <div className="space-y-2">
            <div className="text-sm font-medium">
              Recent Sales ({soldPrices.count} found)
            </div>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {soldPrices.sales.slice(0, 5).map((sale, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-sm p-2 rounded bg-muted/50"
                >
                  <div className="flex flex-col">
                    <span className="font-medium">
                      {formatCurrency(sale.price)}
                    </span>
                    <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                      {sale.street}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(sale.date).toLocaleDateString("en-GB", {
                      month: "short",
                      year: "numeric",
                    })}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {soldPrices.sales.length === 0 && (
          <div className="text-sm text-muted-foreground text-center py-4">
            No recent sales found for this postcode
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Rental Estimate Card (unchanged — whole-property, for BTL etc) ───
function RentalEstimateCard({
  rentalEstimate,
  bedrooms,
  currentPrice,
}: {
  rentalEstimate: ComparablesData["rentalEstimate"]
  bedrooms: number
  currentPrice?: number
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <PoundSterling className="size-4 text-primary" />
          <CardTitle className="text-base">Rental Estimate</CardTitle>
        </div>
        <CardDescription>
          Market rent for {bedrooms} bed properties
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {rentalEstimate ? (
          <>
            <div className="rounded-lg bg-primary/5 p-3">
              <div className="text-sm text-muted-foreground">
                Estimated Monthly Rent
              </div>
              <div className="text-2xl font-bold text-foreground">
                {formatCurrency(rentalEstimate.monthly)}
                <span className="text-sm font-normal text-muted-foreground">
                  /mo
                </span>
              </div>
              <Badge
                variant={
                  rentalEstimate.confidence === "high" ? "default" : "secondary"
                }
                className="mt-2 text-xs"
              >
                {rentalEstimate.confidence} confidence
              </Badge>
            </div>

            {rentalEstimate.range && (
              <div className="text-sm">
                <span className="text-muted-foreground">Range: </span>
                <span className="font-medium">
                  {formatCurrency(rentalEstimate.range.low)} -{" "}
                  {formatCurrency(rentalEstimate.range.high)}
                </span>
              </div>
            )}

            {currentPrice && rentalEstimate.monthly > 0 && (
              <div className="rounded-lg bg-muted p-3">
                <div className="flex items-center gap-2 text-sm">
                  <TrendingUp className="size-4 text-success" />
                  <span className="text-muted-foreground">
                    Potential Gross Yield:
                  </span>
                  <span className="font-bold text-success">
                    {(
                      ((rentalEstimate.monthly * 12) / currentPrice) *
                      100
                    ).toFixed(2)}
                    %
                  </span>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="text-sm text-muted-foreground text-center py-4">
            <MapPin className="size-4 mx-auto mb-2" />
            Rental data unavailable for this area
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ── Room Listings Tab Content (HMO only — SpareRoom data) ────────────
function RoomListingsTab({ postcode }: { postcode: string }) {
  const [data, setData] = useState<RoomListingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function fetchRoomListings() {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch("/api/comparables/spareroom", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ postcode, maxResults: 12 }),
        })
        const json = await res.json()
        if (cancelled) return

        if (!json.success) {
          setError(json.message || "Failed to fetch room listings")
          return
        }

        setData(json)
      } catch {
        if (!cancelled) setError("Failed to load room listings")
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchRoomListings()
    return () => {
      cancelled = true
    }
  }, [postcode])

  if (loading) {
    return (
      <div className="flex items-center gap-3 py-8 justify-center">
        <Loader2 className="size-5 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">
          Fetching live room listings near {postcode}...
        </p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-sm text-muted-foreground text-center py-6">
        {error}
      </div>
    )
  }

  if (!data) return null

  const { listings, source, summary, searchUrl, propertyDataFallback, timestamp } =
    data

  // ── PropertyData fallback view ─────────────────────────────────────
  if (source === "propertydata" && propertyDataFallback) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg bg-primary/5 p-4">
          <div className="text-sm text-muted-foreground">
            Average Room Rent (estimated)
          </div>
          <div className="text-2xl font-bold text-foreground">
            {propertyDataFallback.monthly
              ? formatCurrency(propertyDataFallback.monthly)
              : "N/A"}
            <span className="text-sm font-normal text-muted-foreground">
              /mo
            </span>
          </div>
          {propertyDataFallback.range && (
            <div className="text-sm mt-1 text-muted-foreground">
              Range: {formatCurrency(propertyDataFallback.range.low)} &ndash;{" "}
              {formatCurrency(propertyDataFallback.range.high)}
            </div>
          )}
        </div>

        {/* Source label */}
        <div className="text-xs text-muted-foreground">
          Market averages from PropertyData &middot; No live listings available
          for this postcode
        </div>

        {/* SpareRoom search link */}
        {searchUrl && (
          <a
            href={searchUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
          >
            Browse live rooms on SpareRoom
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>
    )
  }

  // ── No results at all ──────────────────────────────────────────────
  if (listings.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-6 text-center">
        <BedDouble className="size-6 text-muted-foreground/40" />
        <p className="text-sm text-muted-foreground">
          No rental comparables available for {postcode}
        </p>
        {searchUrl && (
          <a
            href={searchUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
          >
            Browse live rooms on SpareRoom
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>
    )
  }

  // ── SpareRoom / OpenRent / Rightmove listing cards ─────────────────
  const rents = listings
    .map((l) => l.monthly_rent)
    .filter((r): r is number => r != null && r > 0)
  const avgRent = rents.length > 0 ? Math.round(rents.reduce((a, b) => a + b, 0) / rents.length) : 0
  const minRent = rents.length > 0 ? Math.min(...rents) : 0
  const maxRent = rents.length > 0 ? Math.max(...rents) : 0

  const sourceLabel =
    source === "spareroom"
      ? "SpareRoom"
      : source === "openrent"
        ? "OpenRent"
        : source === "rightmove"
          ? "Rightmove"
          : "Live listings"

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="rounded-lg bg-primary/5 p-3">
        <div className="text-sm font-medium text-foreground">
          {listings.length} live room listing{listings.length !== 1 ? "s" : ""}
          {avgRent > 0 && (
            <>
              {" "}
              &middot; Average:{" "}
              <span className="font-bold">{formatCurrency(avgRent)} pcm</span>
            </>
          )}
          {minRent > 0 && maxRent > 0 && minRent !== maxRent && (
            <>
              {" "}
              &middot; Range: {formatCurrency(minRent)}&ndash;
              {formatCurrency(maxRent)} pcm
            </>
          )}
        </div>
      </div>

      {/* Source label */}
      <div className="text-xs text-muted-foreground">
        Live listings from {sourceLabel}
        {source === "spareroom" && " via Bright Data"}
        {timestamp && (
          <>
            {" "}
            &middot; Updated:{" "}
            {new Date(timestamp).toLocaleString("en-GB", {
              day: "numeric",
              month: "short",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </>
        )}
      </div>

      {/* Listing cards */}
      <div className="space-y-2 max-h-[420px] overflow-y-auto">
        {listings.map((lst, i) => (
          <div
            key={i}
            className="flex items-start gap-3 rounded-lg border border-border/50 bg-card p-3 hover:bg-muted/30 transition-colors"
          >
            {/* Thumbnail */}
            {lst.image_url ? (
              <img
                src={lst.image_url}
                alt=""
                className="size-14 rounded-md object-cover shrink-0 bg-muted"
                loading="lazy"
              />
            ) : (
              <div className="size-14 rounded-md bg-muted flex items-center justify-center shrink-0">
                <BedDouble className="size-5 text-muted-foreground/40" />
              </div>
            )}

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {lst.title}
                  </p>
                  <p className="text-xs text-muted-foreground truncate mt-0.5">
                    {lst.address || lst.postcode}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  {lst.monthly_rent ? (
                    <span className="text-sm font-bold text-foreground">
                      {formatCurrency(lst.monthly_rent)}
                      <span className="text-xs font-normal text-muted-foreground">
                        {" "}
                        pcm
                      </span>
                    </span>
                  ) : (
                    <span className="text-sm text-muted-foreground">POA</span>
                  )}
                  {lst.distance_km != null && (
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {lst.distance_km.toFixed(1)}km
                    </p>
                  )}
                </div>
              </div>

              {/* Badges + link */}
              <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                <RoomTypeBadge type={lst.room_type} />
                {lst.bills_included === "Yes" && (
                  <span className="inline-flex items-center rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 px-2 py-0.5 text-xs font-medium">
                    Bills Inc.
                  </span>
                )}
                {lst.listing_url && (
                  <a
                    href={lst.listing_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-auto flex items-center gap-1 text-xs text-primary hover:underline"
                  >
                    View on {sourceLabel}
                    <ExternalLink className="size-3" />
                  </a>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────
export function PropertyComparables({
  postcode,
  bedrooms,
  currentPrice,
  investmentType,
}: PropertyComparablesProps) {
  const [data, setData] = useState<ComparablesData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const isHmo = investmentType === "hmo"

  useEffect(() => {
    async function fetchComparables() {
      if (!postcode) return

      setLoading(true)
      setError(null)

      try {
        // Fetch sold prices from Land Registry
        const soldResponse = await fetch("/api/comparables/sold", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ postcode }),
        })

        // Fetch rental estimates (whole-property — shown for non-HMO)
        const rentalResponse = await fetch("/api/comparables/rental", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ postcode, bedrooms }),
        })

        const soldData = await soldResponse.json()
        const rentalData = await rentalResponse.json()

        if (soldData.success || rentalData.success) {
          setData({
            postcode,
            soldPrices: soldData.success
              ? soldData.data
              : { sales: [], average: 0, count: 0 },
            rentalEstimate: rentalData.success ? rentalData.data : undefined,
          })
        } else {
          setError("Could not fetch comparables for this postcode")
        }
      } catch {
        setError("Failed to load comparables")
      } finally {
        setLoading(false)
      }
    }

    fetchComparables()
  }, [postcode, bedrooms])

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Market Comparables</CardTitle>
          <CardDescription>
            Loading sold prices and rental data...
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (error || !data) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Sold Comparables placeholder */}
        <Card className="border-dashed">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Home className="size-4 text-primary" />
              <CardTitle className="text-base">Sold Comparables</CardTitle>
            </div>
            <CardDescription>Recent sales from Land Registry</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <div className="flex size-10 items-center justify-center rounded-full bg-primary/10">
                <Home className="size-5 text-primary/60" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">
                  Coming Soon
                </p>
                <p className="text-xs text-muted-foreground max-w-[220px]">
                  Sold price data from Land Registry will appear here once the
                  market data API is connected.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Rental Comparables placeholder */}
        <Card className="border-dashed">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <PoundSterling className="size-4 text-primary" />
              <CardTitle className="text-base">Rental Comparables</CardTitle>
            </div>
            <CardDescription>
              Market rent for {bedrooms} bed properties
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <div className="flex size-10 items-center justify-center rounded-full bg-primary/10">
                <PoundSterling className="size-5 text-primary/60" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">
                  Coming Soon
                </p>
                <p className="text-xs text-muted-foreground max-w-[220px]">
                  Live rental estimates for {postcode} will appear here once the
                  rental data API is connected.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const { soldPrices, rentalEstimate } = data

  // ── HMO: tabbed layout with Sold Prices + Room Listings ────────────
  if (isHmo) {
    return (
      <Tabs defaultValue="rooms" className="w-full">
        <TabsList className="w-full grid grid-cols-2">
          <TabsTrigger value="sold" className="gap-1.5">
            <Home className="size-3.5" />
            Sold Prices
          </TabsTrigger>
          <TabsTrigger value="rooms" className="gap-1.5">
            <PoundSterling className="size-3.5" />
            Room Listings
          </TabsTrigger>
        </TabsList>

        <TabsContent value="sold" className="mt-4">
          <SoldPricesCard
            soldPrices={soldPrices}
            postcode={postcode}
            currentPrice={currentPrice}
          />
        </TabsContent>

        <TabsContent value="rooms" className="mt-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <BedDouble className="size-4 text-primary" />
                  <CardTitle className="text-base">Room Listings</CardTitle>
                </div>
                <Badge variant="outline" className="text-xs">
                  {postcode}
                </Badge>
              </div>
              <CardDescription>
                Live room-level listings for HMO analysis
              </CardDescription>
            </CardHeader>
            <CardContent>
              <RoomListingsTab postcode={postcode} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    )
  }

  // ── Non-HMO: original side-by-side layout ──────────────────────────
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <SoldPricesCard
        soldPrices={soldPrices}
        postcode={postcode}
        currentPrice={currentPrice}
      />
      <RentalEstimateCard
        rentalEstimate={rentalEstimate}
        bedrooms={bedrooms}
        currentPrice={currentPrice}
      />
    </div>
  )
}

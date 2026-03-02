"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { formatCurrency } from "@/lib/calculations"
import { Home, PoundSterling, TrendingUp, MapPin, AlertCircle } from "lucide-react"

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

interface PropertyComparablesProps {
  postcode: string
  bedrooms: number
  currentPrice?: number
}

export function PropertyComparables({ postcode, bedrooms, currentPrice }: PropertyComparablesProps) {
  const [data, setData] = useState<ComparablesData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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
          body: JSON.stringify({ postcode })
        })
        
        // Fetch rental estimates
        const rentalResponse = await fetch("/api/comparables/rental", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ postcode, bedrooms })
        })
        
        const soldData = await soldResponse.json()
        const rentalData = await rentalResponse.json()
        
        if (soldData.success || rentalData.success) {
          setData({
            postcode,
            soldPrices: soldData.success ? soldData.data : { sales: [], average: 0, count: 0 },
            rentalEstimate: rentalData.success ? rentalData.data : undefined
          })
        } else {
          setError("Could not fetch comparables for this postcode")
        }
      } catch (err) {
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
          <CardDescription>Loading sold prices and rental data...</CardDescription>
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
                <p className="text-sm font-medium text-foreground">Coming Soon</p>
                <p className="text-xs text-muted-foreground max-w-[220px]">
                  Sold price data from Land Registry will appear here once the market data API is connected.
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
            <CardDescription>Market rent for {bedrooms} bed properties</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <div className="flex size-10 items-center justify-center rounded-full bg-primary/10">
                <PoundSterling className="size-5 text-primary/60" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium text-foreground">Coming Soon</p>
                <p className="text-xs text-muted-foreground max-w-[220px]">
                  Live rental estimates for {postcode} will appear here once the rental data API is connected.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const { soldPrices, rentalEstimate } = data
  
  // Calculate price vs market average
  const priceDiff = currentPrice && soldPrices.average 
    ? ((currentPrice - soldPrices.average) / soldPrices.average) * 100 
    : null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Sold Prices Section */}
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
          <CardDescription>
            Recent sales from Land Registry
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Average Price */}
          {soldPrices.average > 0 && (
            <div className="rounded-lg bg-primary/5 p-3">
              <div className="text-sm text-muted-foreground">Average Sold Price</div>
              <div className="text-2xl font-bold text-foreground">
                {formatCurrency(soldPrices.average)}
              </div>
              {priceDiff !== null && (
                <div className={`text-sm mt-1 ${priceDiff > 0 ? 'text-destructive' : 'text-success'}`}>
                  {priceDiff > 0 ? '↑' : '↓'} {Math.abs(priceDiff).toFixed(1)}% vs asking price
                </div>
              )}
            </div>
          )}
          
          {/* Recent Sales List */}
          {soldPrices.sales.length > 0 && (
            <div className="space-y-2">
              <div className="text-sm font-medium">Recent Sales ({soldPrices.count} found)</div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {soldPrices.sales.slice(0, 5).map((sale, i) => (
                  <div 
                    key={i} 
                    className="flex items-center justify-between text-sm p-2 rounded bg-muted/50"
                  >
                    <div className="flex flex-col">
                      <span className="font-medium">{formatCurrency(sale.price)}</span>
                      <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                        {sale.street}
                      </span>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {new Date(sale.date).toLocaleDateString('en-GB', { 
                        month: 'short', 
                        year: 'numeric' 
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

      {/* Rental Section */}
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
                <div className="text-sm text-muted-foreground">Estimated Monthly Rent</div>
                <div className="text-2xl font-bold text-foreground">
                  {formatCurrency(rentalEstimate.monthly)}
                  <span className="text-sm font-normal text-muted-foreground">/mo</span>
                </div>
                <Badge 
                  variant={rentalEstimate.confidence === 'high' ? 'default' : 'secondary'}
                  className="mt-2 text-xs"
                >
                  {rentalEstimate.confidence} confidence
                </Badge>
              </div>
              
              {rentalEstimate.range && (
                <div className="text-sm">
                  <span className="text-muted-foreground">Range: </span>
                  <span className="font-medium">
                    {formatCurrency(rentalEstimate.range.low)} - {formatCurrency(rentalEstimate.range.high)}
                  </span>
                </div>
              )}
              
              {/* Yield Calculation */}
              {currentPrice && rentalEstimate.monthly > 0 && (
                <div className="rounded-lg bg-muted p-3">
                  <div className="flex items-center gap-2 text-sm">
                    <TrendingUp className="size-4 text-success" />
                    <span className="text-muted-foreground">Potential Gross Yield:</span>
                    <span className="font-bold text-success">
                      {((rentalEstimate.monthly * 12) / currentPrice * 100).toFixed(2)}%
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
    </div>
  )
}

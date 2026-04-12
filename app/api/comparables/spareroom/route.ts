import { NextResponse } from "next/server"

/**
 * POST /api/comparables/spareroom
 *
 * Proxies to the Flask backend /api/comparables endpoint which runs the
 * SpareRoom Bright Data scraper as its primary source (with OpenRent and
 * Rightmove as automatic fallbacks).
 *
 * If the scraper returns fewer than 3 listings, we also fetch PropertyData
 * aggregated rental data as a supplementary fallback so the frontend always
 * has something to show.
 *
 * Response shape matches what HmoComparables component expects:
 *   { success, listings: SpareRoomListing[], source, count, summary, ... }
 */

const FLASK_URL =
  process.env.BACKEND_API_URL || "https://metusa-deal-analyzer.onrender.com"

// ── Field mapping: Flask → HmoComparables interface ───────────────────
interface FlaskListing {
  title?: string
  rentPcm?: number | null
  roomType?: string
  billsIncluded?: boolean | null
  area?: string
  distanceKm?: number | null
  listingUrl?: string
  imageUrl?: string
  source?: string
}

interface FrontendListing {
  title: string
  address: string
  postcode: string
  monthly_rent: number | null
  bills_included: string
  num_rooms: number | null
  room_type: string
  available_from: string
  listing_url: string
  image_url: string
  distance_km: number | null
  source: string
}

function mapListing(raw: FlaskListing, searchPostcode: string): FrontendListing {
  const area = raw.area || searchPostcode
  return {
    title: raw.title || "Room to rent",
    address: area,
    postcode: area,
    monthly_rent: raw.rentPcm ?? null,
    bills_included:
      raw.billsIncluded === true
        ? "Yes"
        : raw.billsIncluded === false
          ? "No"
          : "Unknown",
    num_rooms: null,
    room_type: raw.roomType || "double",
    available_from: "Now",
    listing_url: raw.listingUrl || "",
    image_url: raw.imageUrl || "",
    distance_km: raw.distanceKm ?? null,
    source: raw.source || "spareroom",
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const { postcode, maxResults = 12 } = body

    if (!postcode) {
      return NextResponse.json(
        { success: false, message: "postcode is required" },
        { status: 400 }
      )
    }

    const pc = postcode.toUpperCase().trim()

    // ── Step 1: Call Flask /api/comparables (SpareRoom → OpenRent → Rightmove) ──
    let listings: FrontendListing[] = []
    let source = "none"
    let summary: Record<string, number> = {}
    let searchUrl = ""
    let scraperTimedOut = false

    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 65_000) // 65s — Flask scraper has 60s internal timeout + retry

      const res = await fetch(`${FLASK_URL}/api/comparables`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ postcode: pc, maxResults }),
        signal: controller.signal,
      })
      clearTimeout(timeout)

      const data = await res.json()

      if (data.success && Array.isArray(data.listings) && data.listings.length > 0) {
        listings = data.listings.map((l: FlaskListing) => mapListing(l, pc))
        source = data.source || "spareroom"
        summary = data.summary || {}
        searchUrl = data.searchUrl || ""

        console.log(
          `[HMO COMPARABLES] ${source} returned ${listings.length} listings for ${pc}`
        )
      } else {
        console.log(
          `[HMO COMPARABLES] Flask /api/comparables returned 0 listings for ${pc}`
        )
        searchUrl = data.searchUrl || ""
      }
    } catch (err: unknown) {
      const isAbort =
        err instanceof Error && (err.name === "AbortError" || err.message.includes("aborted"))
      if (isAbort) {
        console.log(
          `[HMO COMPARABLES] SpareRoom scraper timed out for ${pc}, falling back to PropertyData`
        )
        scraperTimedOut = true
      } else {
        console.error("[HMO COMPARABLES] Flask /api/comparables error:", err)
      }
    }

    // ── Step 2: If fewer than 3 listings, try PropertyData as fallback ──
    let propertyDataFallback: {
      monthly?: number
      range?: { low: number; high: number }
    } | null = null

    if (listings.length < 3) {
      try {
        const pdRes = await fetch(`${FLASK_URL}/api/propertydata/rental-valuation`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ postcode: pc, bedrooms: 1 }), // 1-bed as room proxy
        })
        const pdData = await pdRes.json()

        if (pdData.success && pdData.data?.estimate?.monthly) {
          propertyDataFallback = {
            monthly: pdData.data.estimate.monthly,
            range: pdData.data.range
              ? {
                  low: Math.round(pdData.data.range.low_weekly * 4.33),
                  high: Math.round(pdData.data.range.high_weekly * 4.33),
                }
              : undefined,
          }

          // If we had zero scraper results, set source to propertydata
          if (listings.length === 0) {
            source = "propertydata"
            console.log(
              `[HMO COMPARABLES] SpareRoom insufficient (${listings.length} results), ` +
                `falling back to PropertyData`
            )
          }
        }
      } catch (pdErr) {
        console.error("[HMO COMPARABLES] PropertyData fallback error:", pdErr)
      }
    }

    // ── Step 3: Build response ──────────────────────────────────────────
    if (listings.length === 0 && !propertyDataFallback) {
      return NextResponse.json({
        success: true,
        listings: [],
        source: "none",
        count: 0,
        summary: {},
        searchUrl,
        message: `No rental comparables available for ${pc}`,
        scraperTimedOut,
      })
    }

    return NextResponse.json({
      success: true,
      listings,
      source,
      count: listings.length,
      summary,
      searchUrl,
      propertyDataFallback,
      scraperTimedOut,
      timestamp: new Date().toISOString(),
    })
  } catch (error) {
    console.error("[API] SpareRoom comparables error:", error)
    return NextResponse.json(
      { success: false, message: "Failed to fetch HMO rental comparables" },
      { status: 500 }
    )
  }
}

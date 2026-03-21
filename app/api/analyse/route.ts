import { NextResponse } from "next/server"

const BACKEND_URL = (
  process.env.BACKEND_API_URL || "http://localhost:5000"
).replace(/\/$/, "")

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { mode, url, propertyData, calculationResults, userEmail } = body

    // ── Scrape-only mode: extract property data from a listing URL ──────────
    if (mode === "scrape-only") {
      if (!url) {
        return NextResponse.json(
          { error: "URL is required" },
          { status: 400 }
        )
      }

      const flaskRes = await fetch(`${BACKEND_URL}/extract-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
        signal: AbortSignal.timeout(30_000),
      })

      if (!flaskRes.ok) {
        const errData = await flaskRes.json().catch(() => null)
        return NextResponse.json(
          { error: errData?.message || "Failed to scrape the listing." },
          { status: flaskRes.status }
        )
      }

      const flaskData = await flaskRes.json()
      const d = flaskData.data || {}

      // Convert sqm → sqft (1 sqm ≈ 10.764 sqft)
      const sqft = d.sqm ? Math.round(d.sqm * 10.764) : undefined

      return NextResponse.json({
        success: true,
        propertyData: {
          address: d.address || "",
          postcode: d.postcode || "",
          purchasePrice: d.price || 0,
          propertyType: d.property_type || "house",
          bedrooms: d.bedrooms || 3,
          ...(sqft ? { sqft } : {}),
        },
      })
    }

    // ── Manual mode: run AI analysis on user-entered property data ──────────
    if (mode === "manual") {
      if (!propertyData) {
        return NextResponse.json(
          { error: "propertyData is required" },
          { status: 400 }
        )
      }

      const flaskRes = await fetch(`${BACKEND_URL}/ai-analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(userEmail ? { "X-User-Email": userEmail } : {}),
        },
        body: JSON.stringify({ ...propertyData, calculationResults }),
        signal: AbortSignal.timeout(60_000),
      })

      const flaskData = await flaskRes.json().catch(() => null)

      if (!flaskRes.ok) {
        if (flaskData?.code === "subscription_required") {
          return NextResponse.json(
            { error: flaskData.message, code: "subscription_required" },
            { status: 403 }
          )
        }
        return NextResponse.json(
          { error: flaskData?.message || "Analysis failed." },
          { status: flaskRes.status }
        )
      }

      return NextResponse.json({
        success: true,
        structured: flaskData.results || null,
      })
    }

    return NextResponse.json({ error: "Invalid mode" }, { status: 400 })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Unexpected error"
    console.error("[api/analyse]", msg)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

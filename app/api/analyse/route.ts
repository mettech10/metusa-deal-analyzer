import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"

const BACKEND_API_URL = process.env.BACKEND_API_URL || "https://metusa-deal-analyzer.onrender.com"

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const { mode } = body

    // ── Scrape-only mode: extract property data from a listing URL ──────────
    if (mode === "scrape-only") {
      const { url } = body
      if (!url) {
        return NextResponse.json({ error: "URL is required" }, { status: 400 })
      }

      const response = await fetch(`${BACKEND_API_URL}/extract-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      })

      const data = await response.json()

      if (!response.ok || !data.success) {
        return NextResponse.json(
          { error: data.message || "Failed to scrape listing" },
          { status: response.ok ? 400 : response.status }
        )
      }

      // Scrapers return snake_case fields; remap to the camelCase shape
      // that page.tsx expects under `propertyData`.
      const raw = data.data || {}
      return NextResponse.json({
        success: true,
        propertyData: {
          address: raw.address || "",
          postcode: raw.postcode || "",
          purchasePrice: Number(raw.price || raw.purchasePrice) || 0,
          propertyType: raw.propertyType || raw.property_type || "house",
          bedrooms: Number(raw.bedrooms) || 3,
          ...(raw.sqft ? { sqft: Number(raw.sqft) } : {}),
        },
      })
    }

    // ── Manual mode: run AI analysis on submitted property data ─────────────
    if (mode === "manual") {
      const { propertyData, calculationResults } = body

      if (!propertyData?.purchasePrice) {
        return NextResponse.json(
          { error: "purchasePrice is required" },
          { status: 400 }
        )
      }

      // Get the authenticated user's email for the subscription gate
      const supabase = await createClient()
      const {
        data: { user },
      } = await supabase.auth.getUser()
      const userEmail = user?.email || ""

      // Flask /ai-analyze expects flat camelCase property fields directly in
      // the request body, not nested under propertyData.
      const response = await fetch(`${BACKEND_API_URL}/ai-analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // Passed as header so Flask can gate without touching the body
          "X-User-Email": userEmail,
        },
        body: JSON.stringify({
          ...propertyData,
          userEmail,
          // FLIP-specific rich metrics from the Next.js engine. Flask AI
          // prompt reads these to replace its 5-line £0 placeholder with
          // the full UK 2024/25 Flip context (SDLT, bridging, CGT/CT,
          // 70% rule, deal score, post-tax ROI).
          flipComputed:
            propertyData?.investmentType === "flip" && calculationResults
              ? {
                  preTaxProfit:         calculationResults.flipPreTaxProfit,
                  postTaxProfit:        calculationResults.flipPostTaxProfit,
                  postTaxROI:           calculationResults.flipPostTaxROI,
                  taxType:              calculationResults.flipTaxType,
                  taxableGain:          calculationResults.flipTaxableGain,
                  taxLiability:         calculationResults.flipTaxLiability,
                  taxRateUsed:          calculationResults.flipTaxRateUsed,
                  dealScore:            calculationResults.flipDealScore,
                  dealScoreLabel:       calculationResults.flipDealScoreLabel,
                  passesSimple70:       calculationResults.flipPassesSimple70,
                  passesStrict70:       calculationResults.flipPassesStrict70,
                  simpleMAO:            calculationResults.flipSimpleMAO,
                  strictMAO:            calculationResults.flipStrictMAO,
                  percentOfARV:         calculationResults.flipPercentOfARV,
                  totalCapitalInvested: calculationResults.flipTotalCapitalInvested,
                  holdingCostsTotal:    calculationResults.flipHoldingCostsTotal,
                  exitCostsTotal:       calculationResults.flipExitCostsTotal,
                  financeTotal:         calculationResults.flipFinanceTotal,
                  refurbTotal:          calculationResults.flipRefurbTotal,
                  refurbContingency:    calculationResults.flipRefurbContingency,
                  holdingMonths:        calculationResults.flipHoldingMonths,
                  acquisitionCost:      calculationResults.flipAcquisitionCost,
                  arv:                  propertyData?.arv,
                }
              : undefined,
        }),
      })

      const data = await response.json()

      if (!response.ok) {
        // Preserve the subscription_required code so page.tsx can show the
        // correct upgrade prompt.
        if (data.code === "subscription_required") {
          return NextResponse.json(data, { status: 403 })
        }
        return NextResponse.json(
          { error: data.message || "Analysis failed" },
          { status: response.status }
        )
      }

      if (!data.success) {
        return NextResponse.json(
          { error: data.message || "Analysis failed" },
          { status: 400 }
        )
      }

      // Flask returns { success: true, results: { ...metrics, ai_verdict, ... } }
      // page.tsx expects { structured: { ... } } and calls formatAnalysisResults()
      // on the structured object to render the text view.
      return NextResponse.json({ structured: data.results })
    }

    return NextResponse.json({ error: "Invalid mode" }, { status: 400 })
  } catch (error) {
    console.error("[API] /api/analyse error:", error)
    return NextResponse.json({ error: "Internal server error" }, { status: 500 })
  }
}

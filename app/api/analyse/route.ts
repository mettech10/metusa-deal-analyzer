import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"
import { createAdminClient } from "@/lib/supabase/admin"
import { checkArticle4 } from "@/lib/article4-service"

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

      // Article 4 engine lookup — runs server-side against Supabase so the
      // Flask AI prompt gets the same 3-state view the result card shows.
      // Fail-soft: if the table is missing or the postcode is unparseable
      // we forward undefined, never block analysis.
      let article4Engine:
        | {
            isArticle4: boolean
            status: "active" | "proposed" | "none" | "unknown"
            warningLevel: "red" | "amber" | "none"
            summary: string
            district: string | null
            sector: string | null
            areas: Array<{
              councilName: string
              directionType: string | null
              effectiveDate: string | null
              consultationEndDate: string | null
              impactDescription: string | null
              councilPlanningUrl: string | null
              dataSource: string | null
              status: string
            }>
          }
        | undefined
      try {
        if (propertyData?.postcode) {
          const admin = createAdminClient()
          const a4 = await checkArticle4(admin, propertyData.postcode)
          article4Engine = {
            isArticle4: a4.isArticle4,
            status: a4.status,
            warningLevel: a4.warningLevel,
            summary: a4.summary,
            district: a4.district,
            sector: a4.sector,
            areas: a4.areas.map((a) => ({
              councilName: a.councilName,
              directionType: a.directionType,
              effectiveDate: a.effectiveDate,
              consultationEndDate: a.consultationEndDate,
              impactDescription: a.impactDescription,
              councilPlanningUrl: a.councilPlanningUrl,
              dataSource: a.dataSource,
              status: a.status,
            })),
          }
        }
      } catch (err) {
        console.warn("[api/analyse] article4 engine lookup failed:", err)
      }

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
          // Article 4 engine snapshot — threaded into the Flask AI prompt
          // so HMO analyses reference the Metalyzi Supabase dataset
          // (council, direction type, effective date, impact, source) and
          // not just the Flask-side hardcoded fallback.
          _article4Engine: article4Engine,
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
          // Property Development feasibility appraisal — threaded into the
          // Flask AI prompt so DEV analyses get full GDV / TDC / cost-stack /
          // RLV / leverage / IRR context, plus the engine's viability flags
          // and deal score, instead of generic BTL commentary.
          _devContext:
            propertyData?.investmentType === "development" &&
            calculationResults?.development
              ? calculationResults.development
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

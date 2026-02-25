"use client"

import { useState, useCallback } from "react"

// Helper to format analysis results from backend
function formatAnalysisResults(r: Record<string, any>): string {
  const verdict = r.verdict || 'N/A'
  const score = r.deal_score || 0
  const label = r.deal_score_label || 'N/A'
  
  let emoji = '🟡'
  if (verdict === 'PROCEED') emoji = '🟢'
  if (verdict === 'AVOID') emoji = '🔴'
  
  let formatted = ''
  
  // HEADER WITH SCORE CIRCLE
  formatted += `╔═══════════════════════════════════════════════════════╗\n`
  formatted += `║  ${emoji} VERDICT: ${verdict.padEnd(43)}║\n`
  formatted += `║  ⭐ SCORE: ${score.toString().padStart(3)}/100 ${label.padEnd(29)}║\n`
  
  // Location info
  const country = r.location?.country || 'England'
  const region = r.location?.region || 'Unknown Region'
  formatted += `║  🏴󠁧󠁢󠁥󠁮󠁧󠁿 ${country} - ${region.padEnd(38)}║\n`
  formatted += `╚═══════════════════════════════════════════════════════╝\n\n`
  
  // Property details
  formatted += `📍 PROPERTY\n`
  formatted += `─`.repeat(55) + `\n`
  formatted += `  Address: ${r.address || 'N/A'}\n`
  formatted += `  Postcode: ${r.postcode || 'N/A'}\n`
  formatted += `  Council: ${r.location?.council || 'Unknown'}\n`
  formatted += `  Purchase Price: £${r.purchase_price || 'N/A'}\n\n`
  
  // KEY METRICS
  formatted += `📊 KEY METRICS\n`
  formatted += `─`.repeat(55) + `\n`
  formatted += `  • Gross Yield: ${r.gross_yield || 'N/A'}%\n`
  formatted += `  • Net Yield: ${r.net_yield || 'N/A'}%\n`
  formatted += `  • Monthly Cashflow: £${r.monthly_cashflow || 'N/A'}\n`
  formatted += `  • Cash-on-Cash: ${r.cash_on_cash || 'N/A'}%\n\n`
  
  // PURCHASE COSTS
  formatted += `💰 PURCHASE COSTS\n`
  formatted += `─`.repeat(55) + `\n`
  formatted += `  • Stamp Duty: £${r.stamp_duty || 'N/A'}\n`
  formatted += `  • Deposit (25%): £${r.deposit_amount || 'N/A'}\n`
  formatted += `  • Loan Amount: £${r.loan_amount || 'N/A'}\n`
  formatted += `  • Monthly Mortgage: £${r.monthly_mortgage || 'N/A'} @ ${r.interest_rate || 'N/A'}%\n\n`
  
  // ARTICLE 4 SECTION
  if (r.article_4) {
    formatted += `⚖️  ARTICLE 4\n`
    formatted += `─`.repeat(55) + `\n`
    if (r.article_4.is_article_4) {
      formatted += `  🔴 THIS AREA IS UNDER ARTICLE 4\n`
      formatted += `  ${r.article_4.note || ''}\n`
      formatted += `  ${r.article_4.advice || ''}\n`
    } else {
      formatted += `  🟢 THIS AREA IS NOT UNDER ARTICLE 4\n`
      formatted += `  ${r.article_4.advice || 'No restrictions - permitted development applies'}\n`
    }
    formatted += `\n`
  }
  
  // STRATEGY RECOMMENDATIONS
  if (r.strategy_recommendations) {
    formatted += `🎯 STRATEGY SUITABILITY\n`
    formatted += `─`.repeat(55) + `\n`
    const strategies = r.strategy_recommendations
    
    if (strategies.BTL) {
      const status = strategies.BTL.suitable ? '✅' : '⚠️'
      formatted += `  ${status} BTL: ${strategies.BTL.note || 'N/A'}\n`
    }
    if (strategies.HMO) {
      const status = strategies.HMO.suitable ? '✅' : '⚠️'
      formatted += `  ${status} HMO: ${strategies.HMO.note || 'N/A'}\n`
    }
    if (strategies.BRR) {
      const status = strategies.BRR.suitable ? '✅' : '⚠️'
      formatted += `  ${status} BRR: ${strategies.BRR.note || 'N/A'}\n`
    }
    if (strategies.FLIP) {
      const status = strategies.FLIP.suitable ? '✅' : '⚠️'
      formatted += `  ${status} FLIP: ${strategies.FLIP.note || 'N/A'}\n`
    }
    if (strategies.SOCIAL_HOUSING?.suitable) {
      formatted += `  ✅ SOCIAL HOUSING (C3-C3b): ${strategies.SOCIAL_HOUSING.note || 'N/A'}\n`
    }
    formatted += `\n`
  }
  
  // REFURB ESTIMATES
  if (r.refurb_estimates) {
    formatted += `🔨 REFURBISHMENT COSTS (per sq meter)\n`
    formatted += `─`.repeat(55) + `\n`
    const ref = r.refurb_estimates
    if (ref.light) formatted += `  • Light (cosmetic): £${ref.light.total} (£${ref.light.per_sqm}/sqm)\n`
    if (ref.medium) formatted += `  • Medium (kitchen/bath): £${ref.medium.total} (£${ref.medium.per_sqm}/sqm)\n`
    if (ref.heavy) formatted += `  • Heavy (full refurb): £${ref.heavy.total} (£${ref.heavy.per_sqm}/sqm)\n`
    if (ref.structural) formatted += `  • Structural: £${ref.structural.total} (£${ref.structural.per_sqm}/sqm)\n`
    formatted += `\n`
  }
  
  // COMPARABLE SOLD PRICES TABLE
  if (r.comparable_sales && r.comparable_sales.length > 0) {
    formatted += `📈 COMPARABLE SOLD PRICES\n`
    formatted += `─`.repeat(75) + `\n`
    formatted += `  ${'Address'.padEnd(25)} ${'Price'.padStart(12)} ${'Type'.padEnd(15)} ${'Date'.padStart(12)}\n`
    formatted += `  ${'─'.repeat(75)}\n`
    r.comparable_sales.slice(0, 5).forEach((sale: any) => {
      const addr = (sale.address || 'N/A').substring(0, 22).padEnd(25)
      const price = `£${(sale.price || 0).toLocaleString()}`.padStart(12)
      const type = (sale.type || 'N/A').padEnd(15)
      const date = (sale.date || 'N/A').padStart(12)
      formatted += `  ${addr} ${price} ${type} ${date}\n`
    })
    formatted += `\n`
  }
  
  // COMPARABLE RENT PRICES TABLE
  if (r.comparable_rents && r.comparable_rents.length > 0) {
    formatted += `🏠 COMPARABLE RENTAL PRICES\n`
    formatted += `─`.repeat(75) + `\n`
    formatted += `  ${'Address'.padEnd(25)} ${'Rent'.padStart(12)} ${'Type'.padEnd(15)} ${'Beds'.padStart(6)}\n`
    formatted += `  ${'─'.repeat(75)}\n`
    r.comparable_rents.slice(0, 5).forEach((rent: any) => {
      const addr = (rent.address || 'N/A').substring(0, 22).padEnd(25)
      const price = `£${(rent.rent || 0).toLocaleString()}/mo`.padStart(12)
      const type = (rent.type || 'N/A').padEnd(15)
      const beds = (rent.bedrooms || 'N/A').toString().padStart(6)
      formatted += `  ${addr} ${price} ${type} ${beds}\n`
    })
    formatted += `\n`
  }
  
  // STRENGTHS
  if (r.ai_strengths) {
    formatted += `✅ STRENGTHS\n`
    formatted += `─`.repeat(55) + `\n`
    const strengths = r.ai_strengths.split('<br>').filter((s: string) => s.trim())
    strengths.slice(0, 3).forEach((s: string) => {
      formatted += `  • ${s.trim().substring(0, 60)}\n`
    })
    formatted += `\n`
  }
  
  // RISKS
  if (r.ai_risks) {
    formatted += `⚠️  RISKS\n`
    formatted += `─`.repeat(55) + `\n`
    const risks = r.ai_risks.split('<br>').filter((s: string) => s.trim())
    risks.slice(0, 3).forEach((s: string) => {
      formatted += `  • ${s.trim().substring(0, 60)}\n`
    })
    formatted += `\n`
  }
  
  // NEXT STEPS
  if (r.next_steps && r.next_steps.length > 0) {
    formatted += `📋 NEXT STEPS\n`
    formatted += `─`.repeat(55) + `\n`
    r.next_steps.slice(0, 5).forEach((step: string) => {
      formatted += `  → ${step}\n`
    })
  }
  
  return formatted
}
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PropertyForm } from "@/components/analyse/property-form"
import { AnalysisResults } from "@/components/analyse/analysis-results"
import { calculateAll } from "@/lib/calculations"
import type { PropertyFormData, CalculationResults } from "@/lib/types"
import {
  BarChart3,
  ArrowLeft,
  Link2,
  ClipboardEdit,
  Loader2,
  ExternalLink,
} from "lucide-react"

type InputMode = "url" | "manual"

export default function AnalysePage() {
  const [inputMode, setInputMode] = useState<InputMode>("url")
  const [formData, setFormData] = useState<PropertyFormData | null>(null)
  const [results, setResults] = useState<CalculationResults | null>(null)
  const [listingUrl, setListingUrl] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [aiText, setAiText] = useState("")
  const [aiLoading, setAiLoading] = useState(false)
  const [prefillData, setPrefillData] = useState<Partial<PropertyFormData> | null>(null)
  const [scrapedFromUrl, setScrapedFromUrl] = useState(false)

  // Call the Flask backend API and handle the response
  const callAnalysisAPI = useCallback(
    async (body: Record<string, unknown>) => {
      setAiText("")
      setAiLoading(true)

      try {
        const res = await fetch("/api/analyse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        })

        if (!res.ok) {
          const errData = await res.json().catch(() => null)
          throw new Error(
            errData?.error || "Analysis failed. Please try again."
          )
        }

        const contentType = res.headers.get("content-type") || ""

        // Handle streaming text response
        if (
          contentType.includes("text/event-stream") ||
          contentType.includes("text/plain")
        ) {
          const reader = res.body?.getReader()
          const decoder = new TextDecoder()
          if (reader) {
            let accumulated = ""
            while (true) {
              const { done, value } = await reader.read()
              if (done) break
              accumulated += decoder.decode(value, { stream: true })
              setAiText(accumulated)
            }
          }
          return
        }

        // Handle JSON response
        const data = await res.json()

        // Extract AI analysis text -- our API returns { aiAnalysis: "..." }
        let analysis = data.aiAnalysis || ""
        let parsedResults = null

        // Try to parse JSON response
        if (analysis && typeof analysis === 'string') {
          try {
            const parsed = JSON.parse(analysis)
            if (parsed.results) {
              parsedResults = parsed.results
              // Format for text display
              analysis = formatAnalysisResults(parsed.results)
            } else if (parsed.success && parsed.message) {
              analysis = parsed.message
            }
          } catch (e) {
            // Not JSON, use as-is
          }
        }

        // If backend returns structured property data, use it for charts
        if (data.data) {
          setFormData(data.data)
          if (data.calculationResults) {
            setResults(data.calculationResults)
          } else {
            setResults(calculateAll(data.data))
          }
        } else if (parsedResults) {
          // URL mode: Build formData from parsed AI results, then use calculateAll
          const propertyData: PropertyFormData = {
            address: parsedResults.address || 'Unknown',
            postcode: parsedResults.postcode || '',
            propertyType: parsedResults.property_type || 'Terrace',
            bedrooms: parseInt(parsedResults.bedrooms) || 3,
            bathrooms: 1,
            condition: 'good',
            purchasePrice: parseFloat(parsedResults.purchase_price?.toString().replace(/[^0-9.]/g, '')) || 0,
            monthlyRent: parseFloat(parsedResults.monthly_rent?.toString().replace(/[^0-9.]/g, '')) || 0,
            depositPercentage: parseFloat(parsedResults.deposit_pct) || 25,
            interestRate: parseFloat(parsedResults.interest_rate) || 3.75,
            isAdditionalProperty: true,
            purchaseMethod: 'mortgage',
            mortgageType: 'interest-only',
            mortgageTerm: 25,
            annualRentIncrease: 3,
            voidWeeks: 2,
            managementFeePercent: 10,
            insurance: 480,
            maintenance: 8,
            groundRent: 0,
            serviceCharge: 0,
            refurbishmentBudget: 0,
            legalFees: 1500,
            surveyCosts: 500
          }
          setFormData(propertyData)
          
          // Use calculateAll to generate proper CalculationResults
          const calcResults = calculateAll(propertyData)
          setResults(calcResults)
        }

        if (analysis) {
          setAiText(analysis)
        } else {
          setAiText("Analysis complete but no text was returned. Please try again.")
        }
      } finally {
        setAiLoading(false)
      }
    },
    []
  )

  // Manual form submission -- runs local calculations then sends to backend
  const handleManualSubmit = useCallback(
    async (data: PropertyFormData) => {
      setError(null)
      setIsLoading(true)

      const calcResults = calculateAll(data)
      setFormData(data)
      setResults(calcResults)

      try {
        await callAnalysisAPI({
          mode: "manual",
          propertyData: data,
          calculationResults: calcResults,
        })
      } catch (err) {
        // Calculations still show, only AI commentary failed
        setError(
          err instanceof Error
            ? err.message
            : "AI analysis failed, but your numbers are ready below."
        )
      } finally {
        setIsLoading(false)
      }
    },
    [callAnalysisAPI]
  )

  // URL-based submission -- scrapes data then transitions to manual form with pre-filled fields
  const handleUrlSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault()
      setError(null)

      if (!listingUrl.trim()) {
        setError("Please enter a property listing URL")
        return
      }

      try {
        new URL(listingUrl)
      } catch {
        setError(
          "Please enter a valid URL (e.g. https://www.rightmove.co.uk/...)"
        )
        return
      }

      setIsLoading(true)

      try {
        const res = await fetch("/api/analyse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: "scrape-only", url: listingUrl }),
        })

        if (!res.ok) {
          const errData = await res.json().catch(() => null)
          throw new Error(
            errData?.error || "Failed to scrape the listing. Please try again."
          )
        }

        const data = await res.json()

        if (!data.success || !data.data) {
          throw new Error("No property data was returned from the listing.")
        }

        // Map scraped data to form fields for pre-filling
        const scraped = data.data
        const mapped: Partial<PropertyFormData> = {
          address: scraped.address || "",
          postcode: scraped.postcode || "",
          purchasePrice: Number(scraped.purchasePrice) || 0,
          propertyType: scraped.propertyType || "house",
          bedrooms: Number(scraped.bedrooms) || 3,
        }

        // Transition to manual form with pre-filled data
        setPrefillData(mapped)
        setScrapedFromUrl(true)
        setInputMode("manual")
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Something went wrong. Please try again."
        )
      } finally {
        setIsLoading(false)
      }
    },
    [listingUrl]
  )

  const hasResults = (results && formData) || aiText
  const isProcessing = isLoading || aiLoading

  const resetAll = () => {
    setResults(null)
    setFormData(null)
    setListingUrl("")
    setError(null)
    setAiText("")
    setPrefillData(null)
    setScrapedFromUrl(false)
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top Bar */}
      <header className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex size-7 items-center justify-center rounded-lg bg-primary">
              <BarChart3 className="size-3.5 text-primary-foreground" />
            </div>
            <span className="text-sm font-semibold text-foreground">
              DealCheck UK
            </span>
          </Link>
          <Button asChild variant="ghost" size="sm">
            <Link href="/">
              <ArrowLeft className="size-3.5" />
              Back
            </Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-8">
        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold tracking-tight text-foreground md:text-3xl">
            Property Deal Analyser
          </h1>
          <p className="mt-1 text-muted-foreground">
            Paste a listing URL for instant analysis, or enter property details
            manually.
          </p>
        </div>

        {/* Input Mode Selector -- hidden once we have results */}
        {!hasResults && (
          <div className="mb-8 flex max-w-lg rounded-lg border border-border/50 bg-card p-1">
            <button
              type="button"
              onClick={() => setInputMode("url")}
              className={`flex flex-1 items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm font-medium transition-all ${
                inputMode === "url"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Link2 className="size-4" />
              Paste Listing URL
            </button>
            <button
              type="button"
              onClick={() => setInputMode("manual")}
              className={`flex flex-1 items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm font-medium transition-all ${
                inputMode === "manual"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <ClipboardEdit className="size-4" />
              Enter Details Manually
            </button>
          </div>
        )}

        {/* URL Input Mode */}
        {inputMode === "url" && !hasResults && (
          <div className="mb-8 max-w-3xl">
            <form onSubmit={handleUrlSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <label
                  htmlFor="listing-url"
                  className="text-sm font-medium text-foreground"
                >
                  Property Listing URL
                </label>
                <div className="flex gap-3">
                  <div className="relative flex-1">
                    <div className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2">
                      <ExternalLink className="size-4 text-muted-foreground" />
                    </div>
                    <Input
                      id="listing-url"
                      type="url"
                      placeholder="https://www.rightmove.co.uk/properties/..."
                      value={listingUrl}
                      onChange={(e) => {
                        setListingUrl(e.target.value)
                        setError(null)
                      }}
                      className="h-12 pl-10 text-base"
                      disabled={isProcessing}
                    />
                  </div>
                  <Button
                    type="submit"
                    size="xl"
                    disabled={isProcessing}
                    className="shrink-0"
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="size-4 animate-spin" />
                        Analysing...
                      </>
                    ) : (
                      "Analyse Listing"
                    )}
                  </Button>
                </div>
                {error && (
                  <p className="text-sm text-destructive">{error}</p>
                )}
              </div>

              {/* Supported sites hint */}
              <div className="rounded-lg border border-border/30 bg-card/50 px-4 py-3">
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">
                    Supported sites:
                  </span>{" "}
                  Rightmove, Zoopla, OnTheMarket, and most UK property listing
                  portals. Paste the full URL to a property listing page.
                </p>
              </div>
            </form>
          </div>
        )}

        {/* Manual Input Mode */}
        {inputMode === "manual" && !hasResults && (
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
            {/* Form Panel */}
            <div className="rounded-xl border border-border/50 bg-card p-6">
              <PropertyForm
                key={scrapedFromUrl ? "prefilled" : "manual"}
                onSubmit={handleManualSubmit}
                isLoading={isProcessing}
                defaultValues={prefillData || undefined}
                prefilled={scrapedFromUrl}
              />
            </div>

            {/* Empty state */}
            <div className="flex h-full min-h-[400px] flex-col items-center justify-center rounded-xl border border-dashed border-border/50 bg-card/30 p-12 text-center">
              <div className="mb-4 flex size-16 items-center justify-center rounded-2xl bg-primary/10">
                <BarChart3 className="size-7 text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">
                {scrapedFromUrl ? "Almost There" : "No Analysis Yet"}
              </h3>
              <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
                {scrapedFromUrl
                  ? "We've imported property details from the listing. Fill in the remaining fields (rent, financing, running costs) and hit \"Analyse This Deal\" for a full breakdown."
                  : "Fill in the property details on the left and hit \"Analyse This Deal\" to see a full financial breakdown and AI-powered insights."}
              </p>
            </div>
          </div>
        )}

        {/* Loading state (URL scraping) */}
        {isProcessing && inputMode === "url" && !hasResults && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Loader2 className="mb-4 size-10 animate-spin text-primary" />
            <h3 className="text-lg font-semibold text-foreground">
              Scraping Listing Details...
            </h3>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              Extracting property details from the listing page. This may take a
              moment if the backend is warming up.
            </p>
          </div>
        )}

        {/* Results view */}
        {hasResults && (
          <div className="flex flex-col gap-6">
            {/* New analysis button */}
            <div className="flex items-center gap-3">
              <Button variant="outline" size="sm" onClick={resetAll}>
                <ArrowLeft className="size-3.5" />
                New Analysis
              </Button>
              {formData?.address && (
                <span className="text-sm text-muted-foreground">
                  Showing results for{" "}
                  <span className="font-medium text-foreground">
                    {formData.address}
                  </span>
                </span>
              )}
            </div>

            {results && formData ? (
              <AnalysisResults
                data={formData}
                results={results}
                aiText={aiText}
                aiLoading={aiLoading}
              />
            ) : (
              /* URL mode -- AI text only (no structured data from backend) */
              <div className="rounded-xl border border-primary/20 bg-card p-6">
                <div className="mb-4 flex items-center gap-2">
                  <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10">
                    <BarChart3 className="size-4 text-primary" />
                  </div>
                  <h3 className="text-base font-semibold text-foreground">
                    AI Investment Analysis
                  </h3>
                </div>
                <div className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                  {aiText}
                  {aiLoading && (
                    <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-primary" />
                  )}
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

"use client"

import { useState, useCallback, useEffect, useRef } from "react"
import Link from "next/link"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { PropertyForm } from "@/components/analyse/property-form"
import { AnalysisResults } from "@/components/analyse/analysis-results"
import { RecentDeals } from "@/components/analyse/recent-deals"
import { calculateAll, calculateDealScore } from "@/lib/calculations"
import type { PropertyFormData, CalculationResults, BackendResults } from "@/lib/types"
import {
  BarChart3,
  ArrowLeft,
  Link2,
  ClipboardEdit,
  Loader2,
  ExternalLink,
  FileDown,
} from "lucide-react"

// Helper to format analysis results from backend
// overridePostcode: use the user's actual form postcode instead of any AI-hallucinated one
function formatAnalysisResults(r: Record<string, any>, overridePostcode?: string): string {
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
  formatted += `  Postcode: ${overridePostcode || r.postcode || 'N/A'}\n`
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
    formatted += `⚖️  ARTICLE 4 & PLANNING\n`
    formatted += `─`.repeat(55) + `\n`
    if (r.article_4.is_article_4) {
      formatted += `  🔴 ARTICLE 4 DIRECTION IN FORCE\n`
      formatted += `  ${r.article_4.note || ''}\n`
      formatted += `  ${r.article_4.advice || 'Planning permission required for HMO conversion.'}\n`
    } else if (r.article_4.known === false) {
      formatted += `  🟡 ARTICLE 4 STATUS UNCONFIRMED\n`
      formatted += `  ${r.article_4.note || 'Not in our database — verify with local council.'}\n`
      formatted += `  ${r.article_4.advice || 'Check with local planning authority before any HMO conversion.'}\n`
    } else {
      formatted += `  🟢 NO ARTICLE 4 RESTRICTIONS\n`
      formatted += `  ${r.article_4.advice || 'Permitted Development applies — no planning permission needed for HMO (up to 6 people).'}\n`
    }
    // HMO licensing guidance (shown when strategy is HMO)
    if (r.article_4.hmo_guidance) {
      formatted += `\n  💡 HMO GUIDANCE:\n`
      r.article_4.hmo_guidance.split('. ').filter((s: string) => s.trim()).forEach((line: string) => {
        formatted += `    → ${line.trim()}${line.trim().endsWith('.') ? '' : '.'}\n`
      })
    }
    // Social housing alternative (shown when Article 4 and HMO strategy)
    if (r.article_4.social_housing_suggestion) {
      formatted += `\n  🏠 ALTERNATIVE — SOCIAL/SUPPORTED HOUSING (C3→C3b):\n`
      r.article_4.social_housing_suggestion.split('. ').filter((s: string) => s.trim()).forEach((line: string) => {
        formatted += `    → ${line.trim()}${line.trim().endsWith('.') ? '' : '.'}\n`
      })
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
    if (ref.light) formatted += `  • Light (cosmetic): £${ref.light.total} (£${ref.light.per_sqft_mid ?? ref.light.per_sqm}/sqft)\n`
    if (ref.medium) formatted += `  • Medium (kitchen/bath): £${ref.medium.total} (£${ref.medium.per_sqft_mid ?? ref.medium.per_sqm}/sqft)\n`
    if (ref.heavy) formatted += `  • Heavy (full refurb): £${ref.heavy.total} (£${ref.heavy.per_sqft_mid ?? ref.heavy.per_sqm}/sqft)\n`
    if (ref.structural) formatted += `  • Structural: £${ref.structural.total} (£${ref.structural.per_sqft_mid ?? ref.structural.per_sqm}/sqft)\n`
    formatted += `\n`
  }
  
  // COMPARABLE SOLD PRICES TABLE
  if ((r.sold_comparables || r.comparable_sales)?.length > 0) {
    const sales = r.sold_comparables || r.comparable_sales
    formatted += `📈 COMPARABLE SOLD PRICES\n`
    formatted += `─`.repeat(75) + `\n`
    formatted += `  ${'Address'.padEnd(25)} ${'Price'.padStart(12)} ${'Type'.padEnd(15)} ${'Date'.padStart(12)}\n`
    formatted += `  ${'─'.repeat(75)}\n`
    sales.slice(0, 5).forEach((sale: any) => {
      const addr = (sale.address || 'N/A').substring(0, 22).padEnd(25)
      const price = `£${(sale.price || 0).toLocaleString()}`.padStart(12)
      const type = (sale.type || 'N/A').padEnd(15)
      const date = (sale.date || 'N/A').padStart(12)
      formatted += `  ${addr} ${price} ${type} ${date}\n`
    })
    formatted += `\n`
  }

  // COMPARABLE RENT PRICES TABLE
  if ((r.rent_comparables || r.comparable_rents)?.length > 0) {
    const rents = r.rent_comparables || r.comparable_rents
    formatted += `🏠 COMPARABLE RENTAL PRICES\n`
    formatted += `─`.repeat(75) + `\n`
    formatted += `  ${'Address'.padEnd(25)} ${'Rent'.padStart(12)} ${'Type'.padEnd(15)} ${'Beds'.padStart(6)}\n`
    formatted += `  ${'─'.repeat(75)}\n`
    rents.slice(0, 5).forEach((rent: any) => {
      const addr = (rent.address || 'N/A').substring(0, 22).padEnd(25)
      const price = `£${(rent.monthly_rent || rent.rent || 0).toLocaleString()}/mo`.padStart(12)
      const type = (rent.type || 'N/A').padEnd(15)
      const beds = (rent.bedrooms || 'N/A').toString().padStart(6)
      formatted += `  ${addr} ${price} ${type} ${beds}\n`
    })
    formatted += `\n`
  }
  
  // STRENGTHS — handle both new string[] arrays and legacy '<br>' strings
  if (r.ai_strengths) {
    formatted += `✅ STRENGTHS\n`
    formatted += `─`.repeat(55) + `\n`
    const strengths: string[] = Array.isArray(r.ai_strengths)
      ? r.ai_strengths
      : String(r.ai_strengths).split('<br>').filter((s: string) => s.trim())
    strengths.slice(0, 4).forEach((s: string) => {
      formatted += `  • ${s.replace(/^[•\-]\s*/, '').trim().substring(0, 80)}\n`
    })
    formatted += `\n`
  }

  // RISKS — handle both new string[] arrays and legacy '<br>' strings
  if (r.ai_risks) {
    formatted += `⚠️  RISKS\n`
    formatted += `─`.repeat(55) + `\n`
    const risks: string[] = Array.isArray(r.ai_risks)
      ? r.ai_risks
      : String(r.ai_risks).split('<br>').filter((s: string) => s.trim())
    risks.slice(0, 4).forEach((s: string) => {
      formatted += `  • ${s.replace(/^[•\-]\s*/, '').trim().substring(0, 80)}\n`
    })
    formatted += `\n`
  }

  // AREA ANALYSIS
  if (r.ai_area) {
    formatted += `🗺️  AREA ANALYSIS\n`
    formatted += `─`.repeat(55) + `\n`
    formatted += `  ${r.ai_area.trim().substring(0, 400)}\n\n`
  }

  // NEXT STEPS — ai_next_steps is now an array; also check legacy next_steps
  const nextSteps: string[] = Array.isArray(r.ai_next_steps)
    ? r.ai_next_steps
    : Array.isArray(r.next_steps)
      ? r.next_steps
      : []
  if (nextSteps.length > 0) {
    formatted += `📋 NEXT STEPS\n`
    formatted += `─`.repeat(55) + `\n`
    nextSteps.slice(0, 5).forEach((step: string) => {
      formatted += `  → ${step}\n`
    })
  }
  
  return formatted
}

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
  const [backendData, setBackendData] = useState<BackendResults | null>(null)
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
          if (errData?.code === "subscription_required") {
            throw new Error(
              "🔒 An active subscription is required to run analyses. Please upgrade your plan."
            )
          }
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

        // Extract AI analysis text -- our API returns { aiAnalysis: "...", structured: {...} }
        let analysis = data.aiAnalysis || ""
        let parsedResults = null

        // Store structured backend data if returned directly
        if (data.structured) {
          setBackendData(data.structured as BackendResults)
          parsedResults = data.structured
          const userPostcode = (body.propertyData as Record<string, any>)?.postcode as string | undefined
          analysis = formatAnalysisResults(data.structured, userPostcode)
        } else if (analysis && typeof analysis === 'string') {
          // Fallback: parse JSON-stringified response from older API format
          try {
            const parsed = JSON.parse(analysis)
            if (parsed.results) {
              parsedResults = parsed.results
              setBackendData(parsed.results as BackendResults)
              // Format for text display; pass user's postcode so AI can't override it
              const userPostcode = (body.propertyData as Record<string, any>)?.postcode as string | undefined
              analysis = formatAnalysisResults(parsed.results, userPostcode)
            } else if (parsed.success && parsed.message) {
              analysis = parsed.message
            }
          } catch (e) {
            // Not JSON, use as-is
          }
        }

        // If backend returns structured property data, use it for charts
        if (data.propertyData) {
          setFormData(data.propertyData)
          if (data.calculationResults) {
            setResults(data.calculationResults)
          } else {
            setResults(calculateAll(data.propertyData))
          }
        } else if (parsedResults) {
          if (body.propertyData) {
            // Manual mode: the user submitted the form with specific inputs (incl. refurb budget).
            // Use the original propertyData and calculationResults so that refurb cost and all
            // other user-entered values are preserved after AI analysis completes.
            const originalData = body.propertyData as PropertyFormData
            setFormData(originalData)
            setResults(
              body.calculationResults
                ? (body.calculationResults as CalculationResults)
                : calculateAll(originalData)
            )
          } else {
            // URL mode: no original propertyData — reconstruct from AI-parsed results
            const propertyData: PropertyFormData = {
              address: parsedResults.address || 'Unknown',
              postcode: parsedResults.postcode || '',
              propertyType: parsedResults.property_type || 'house',
              investmentType: 'btl',
              bedrooms: parseInt(parsedResults.bedrooms) || 3,
              condition: 'good',
              purchasePrice: parseFloat(parsedResults.purchase_price?.toString().replace(/[^0-9.]/g, '')) || 0,
              monthlyRent: parseFloat(parsedResults.monthly_rent?.toString().replace(/[^0-9.]/g, '')) || 0,
              depositPercentage: parseFloat(parsedResults.deposit_pct) || 25,
              interestRate: parseFloat(parsedResults.interest_rate) || 3.75,
              buyerType: 'additional',
              purchaseType: 'mortgage',
              mortgageType: 'interest-only',
              mortgageTerm: 25,
              annualRentIncrease: 3,
              voidWeeks: 2,
              managementFeePercent: 10,
              insurance: 480,
              maintenance: 8,
              groundRent: 0,
              bills: 0,
              refurbishmentBudget: 0,
              legalFees: 1500,
              surveyCosts: 500
            }
            setFormData(propertyData)
            setResults(calculateAll(propertyData))
          }
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

        if (!data.success || !data.propertyData) {
          throw new Error("No property data was returned from the listing.")
        }

        // Map scraped data to form fields for pre-filling
        const scraped = data.propertyData
        const mapped: Partial<PropertyFormData> = {
          address: scraped.address || "",
          postcode: scraped.postcode || "",
          purchasePrice: Number(scraped.purchasePrice) || 0,
          propertyType: scraped.propertyType || "house",
          bedrooms: Number(scraped.bedrooms) || 3,
          ...(scraped.sqft ? { sqft: Number(scraped.sqft) } : {}),
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

  // Track last-saved analysis so we don't double-save on re-renders
  const savedKeyRef = useRef<string | null>(null)
  // Ref to always have the latest aiText synchronously in effects
  const aiTextRef = useRef("")
  useEffect(() => { aiTextRef.current = aiText }, [aiText])

  // Auto-save to Supabase after AI analysis finishes (aiLoading → false with content)
  const [recentDealsVersion, setRecentDealsVersion] = useState(0)
  useEffect(() => {
    // Only fire when AI loading just completed and we have data
    if (aiLoading || !aiText || !formData) return

    // Build a unique key for this analysis to prevent double-saves
    const key = `${formData.address}|${formData.purchasePrice}|${aiText.length}`
    if (savedKeyRef.current === key) return
    savedKeyRef.current = key

    // Extract score from AI text
    const scoreMatch = aiText.match(/SCORE:\s*(\d+)/i) || aiText.match(/⭐ SCORE:\s*(\d+)/i)
    const dealScore = scoreMatch ? parseInt(scoreMatch[1]) : null

    fetch("/api/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        address: formData.address || "Unknown",
        postcode: formData.postcode || null,
        investment_type: formData.investmentType || "btl",
        purchase_price: formData.purchasePrice || 0,
        deal_score: dealScore,
        monthly_cashflow: results?.monthlyCashFlow ?? null,
        annual_cashflow: results?.annualCashFlow ?? null,
        gross_yield: results?.grossYield ?? null,
        form_data: formData,
        results: results,
        ai_text: aiText,
        backend_data: backendData || null,
      }),
    })
      .then((r) => {
        if (r.ok) setRecentDealsVersion((v) => v + 1)
      })
      .catch(() => {
        // Not logged in or DB error — silently skip, saving is best-effort
      })
  }, [aiLoading]) // eslint-disable-line react-hooks/exhaustive-deps

  const hasResults = (results && formData) || aiText
  const isProcessing = isLoading || aiLoading

  // Restore a saved analysis from the Recent Deals panel
  const handleLoadSavedDeal = useCallback(
    (savedFormData: PropertyFormData, savedResults: CalculationResults | null, savedAiText: string, savedBackendData: BackendResults | null) => {
      setFormData(savedFormData)
      // If results weren't persisted, recalculate from the saved form data
      setResults(savedResults ?? calculateAll(savedFormData))
      setAiText(savedAiText)
      setBackendData(savedBackendData)
      setError(null)
      setInputMode("manual")
      savedKeyRef.current = null // allow re-save if user triggers a new analysis
      // Scroll to top so the user sees the loaded analysis results
      window.scrollTo({ top: 0, behavior: "smooth" })
    },
    []
  )

  const resetAll = () => {
    setResults(null)
    setFormData(null)
    setListingUrl("")
    setError(null)
    setAiText("")
    setBackendData(null)
    setPrefillData(null)
    setScrapedFromUrl(false)
    savedKeyRef.current = null
  }

  const handleSavePDF = () => {
    if (!aiText && !formData) return

    const fd = formData
    const res = results
    const address = fd?.address || "Unknown Address"
    const postcode = fd?.postcode || ""
    const date = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })

    // Helper formatters
    const gbp = (n: number) => `£${Math.round(n).toLocaleString("en-GB")}`
    const pct = (n: number) => `${n.toFixed(2)}%`
    const na = (v: unknown) => (v !== undefined && v !== null && v !== 0 && v !== "" ? String(v) : "—")

    // Strategy label
    const strategyLabels: Record<string, string> = {
      btl: "Buy-to-Let (BTL)", brr: "Buy Refurbish Refinance (BRR)",
      hmo: "HMO", flip: "Flip", r2sa: "Rent-to-SA (R2SA)", development: "Development",
    }
    const conditionLabels: Record<string, string> = {
      excellent: "Excellent", good: "Good", fair: "Fair", "needs-work": "Needs Work",
    }
    const strategy = strategyLabels[fd?.investmentType || "btl"] || "BTL"
    const condition = conditionLabels[fd?.condition || "good"] || "Good"
    const propType = (fd?.propertyType || "house").charAt(0).toUpperCase() + (fd?.propertyType || "house").slice(1)

    // ROI-based deal score (matches the on-screen scoring formula)
    const score = calculateDealScore(results?.cashOnCashReturn ?? 0)
    const scoreColor = score >= 75 ? "#16a34a" : score >= 50 ? "#0ea5e9" : score >= 25 ? "#f59e0b" : "#dc2626"
    const scoreLabel = score >= 100 ? "Excellent Deal" : score >= 75 ? "Good Deal" : score >= 50 ? "Fair Deal" : score >= 25 ? "Below Average" : "Poor Deal"

    // Extract AI text sections for summary/strengths/risks
    const extractSection = (label: string) => {
      const rx = new RegExp(`${label}[:\\s]+([\\s\\S]*?)(?=\\n[\\n✅⚠️📋🔨📈🏠🎯]|$)`, "i")
      const m = aiText.match(rx)
      return m ? m[1].trim().replace(/^\s*[-•→]\s*/gm, "• ").substring(0, 600) : ""
    }
    const aiSummary = extractSection("SUMMARY|DEAL SUMMARY|OVERVIEW")
    const aiStrengths = extractSection("STRENGTH")
    const aiRisks = extractSection("RISK")
    const aiNextSteps = extractSection("NEXT STEP")

    // Backend data helpers for PDF
    const bd = backendData
    const riskFlags = bd?.risk_flags || []
    const benchmark = bd?.regional_benchmark
    const rentComps = bd?.rent_comparables || []
    const soldComps = bd?.sold_comparables || []

    // Risk flag HTML
    const riskFlagColor = (color: string) => {
      if (color === "red") return { bg: "#fff1f2", border: "#fca5a5", badge: "#dc2626", label: "#991b1b" }
      if (color === "amber") return { bg: "#fffbeb", border: "#fcd34d", badge: "#d97706", label: "#92400e" }
      return { bg: "#f0fdf4", border: "#86efac", badge: "#16a34a", label: "#14532d" }
    }

    const riskFlagsHtml = riskFlags.length > 0 ? `
      <div class="sec-title">Risk Flags</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px">
        ${riskFlags.map((flag) => {
          const c = riskFlagColor(flag.color)
          return `<div style="background:${c.bg};border:1px solid ${c.border};border-radius:6px;padding:10px">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
              <span style="background:${c.badge};color:#fff;font-size:7px;font-weight:700;padding:1px 5px;border-radius:3px;text-transform:uppercase">${flag.severity}</span>
              <span style="font-size:10px;font-weight:700;color:${c.label}">${flag.name}</span>
            </div>
            <div style="font-size:9px;color:#444;margin-bottom:4px">${flag.description}</div>
            <div style="font-size:8px;color:#666;font-style:italic">${flag.mitigation}</div>
          </div>`
        }).join("")}
      </div>` : ""

    // Regional benchmark HTML
    const benchmarkHtml = benchmark ? `
      <div class="sec-title">Regional Benchmark</div>
      <div style="background:#f8f8fc;border:1px solid #e8e8f0;border-radius:6px;padding:12px;margin-bottom:14px">
        ${benchmark.region_name ? `<div style="font-size:10px;font-weight:700;color:#1a1a2e;margin-bottom:8px">${benchmark.region_name}${benchmark.postcode_area ? " · " + benchmark.postcode_area : ""}</div>` : ""}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
          <div>
            <div style="font-size:8px;text-transform:uppercase;color:#888;margin-bottom:3px">Gross Yield</div>
            <div style="font-size:14px;font-weight:700;color:#4f46e5">${benchmark.your_yield != null ? benchmark.your_yield.toFixed(2) + "%" : "—"}</div>
            ${benchmark.regional_median_yield != null ? `<div style="font-size:8px;color:#666">Region median: ${benchmark.regional_median_yield.toFixed(2)}%</div>` : ""}
            ${benchmark.yield_vs_median_label ? `<div style="font-size:8px;font-weight:600;color:${(benchmark.yield_difference || 0) >= 0 ? "#16a34a" : "#dc2626"}">${benchmark.yield_vs_median_label}</div>` : ""}
          </div>
          <div>
            <div style="font-size:8px;text-transform:uppercase;color:#888;margin-bottom:3px">Monthly Cash Flow</div>
            <div style="font-size:14px;font-weight:700;color:${(benchmark.your_cashflow || 0) >= 0 ? "#16a34a" : "#dc2626"}">${benchmark.your_cashflow != null ? "£" + Math.round(benchmark.your_cashflow).toLocaleString("en-GB") : "—"}</div>
            ${benchmark.regional_avg_cashflow != null ? `<div style="font-size:8px;color:#666">Region avg: £${Math.round(benchmark.regional_avg_cashflow).toLocaleString("en-GB")}</div>` : ""}
            ${benchmark.cashflow_vs_avg_label ? `<div style="font-size:8px;font-weight:600;color:${(benchmark.cashflow_difference || 0) >= 0 ? "#16a34a" : "#dc2626"}">${benchmark.cashflow_vs_avg_label}</div>` : ""}
          </div>
        </div>
        ${benchmark.summary ? `<div style="margin-top:8px;font-size:9px;color:#555;border-top:1px solid #e8e8f0;padding-top:8px">${benchmark.summary}</div>` : ""}
      </div>` : ""

    // Rental comparables HTML
    const rentCompsHtml = rentComps.length > 0 ? `
      <div class="sec-title">Rental Comparables</div>
      <table>
        <tr>
          <th>Address</th>
          <th style="text-align:right">Monthly Rent</th>
          <th>Beds</th>
          <th>Type</th>
          <th>Tenure</th>
          <th>Source</th>
        </tr>
        ${rentComps.slice(0, 8).map(c => `<tr>
          <td>${c.address || "—"}</td>
          <td class="td-right" style="color:#16a34a;font-weight:700">£${Math.round(c.monthly_rent).toLocaleString("en-GB")}</td>
          <td>${c.bedrooms != null ? c.bedrooms + " bed" : "—"}</td>
          <td>${c.type || "—"}</td>
          <td>${(c as {tenure?: string}).tenure || "—"}</td>
          <td style="font-size:8px;color:#888">${c.source || "—"}</td>
        </tr>`).join("")}
      </table>` : ""

    // Sold comparables HTML
    const soldCompsHtml = soldComps.length > 0 ? `
      <div class="sec-title">Sold Comparables</div>
      <table>
        <tr>
          <th>Address</th>
          <th style="text-align:right">Price</th>
          <th>Beds</th>
          <th>Type</th>
          <th>Date</th>
        </tr>
        ${soldComps.slice(0, 8).map(c => `<tr>
          <td>${c.address || "—"}</td>
          <td class="td-right" style="color:#4f46e5;font-weight:700">£${Math.round(c.price).toLocaleString("en-GB")}</td>
          <td>${c.bedrooms != null ? c.bedrooms + " bed" : "—"}</td>
          <td>${c.type || "—"}</td>
          <td style="font-size:8px">${c.date || "—"}</td>
        </tr>`).join("")}
      </table>` : ""

    // Area analysis enriched HTML
    const aiVerdictHtml = bd?.ai_verdict ? `
      <div style="background:#f0f4ff;border:1px solid #c7d2fe;border-radius:6px;padding:10px;margin-bottom:10px">
        <div style="font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:#4f46e5;font-weight:700;margin-bottom:4px">AI Area Verdict</div>
        <div style="font-size:10px;color:#1a1a2e;line-height:1.5">${bd.ai_verdict}</div>
      </div>` : ""

    const aiAreaHtml = bd?.ai_area ? `
      <div style="background:#f8f8fc;border:1px solid #e8e8f0;border-radius:6px;padding:10px;margin-bottom:10px">
        <div style="font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:#888;font-weight:700;margin-bottom:4px">Area Analysis</div>
        <div style="font-size:10px;color:#333;line-height:1.6;white-space:pre-wrap">${bd.ai_area}</div>
      </div>` : ""

    const strategyRecsHtml = bd?.strategy_recommendations ? (() => {
      const recs = bd.strategy_recommendations
      const entries = Object.entries(recs).filter(([, v]) => v)
      if (!entries.length) return ""
      return `<div class="sec-title">Strategy Recommendations</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:14px">
          ${entries.map(([key, val]) => {
            const v = val as { suitable: boolean; note: string }
            return `<div style="background:${v.suitable ? "#f0fdf4" : "#fff1f2"};border:1px solid ${v.suitable ? "#86efac" : "#fca5a5"};border-radius:4px;padding:7px">
              <div style="display:flex;align-items:center;gap:4px;margin-bottom:3px">
                <span style="font-size:10px">${v.suitable ? "✅" : "❌"}</span>
                <span style="font-size:9px;font-weight:700;color:${v.suitable ? "#15803d" : "#dc2626"}">${key}</span>
              </div>
              <div style="font-size:8px;color:#555;line-height:1.4">${v.note}</div>
            </div>`
          }).join("")}
        </div>`
    })() : ""

    // Refurb estimates from aiText
    const lightMatch = aiText.match(/Light[^:]*:\s*£([\d,]+)/)
    const mediumMatch = aiText.match(/Medium[^:]*:\s*£([\d,]+)/)
    const heavyMatch = aiText.match(/Heavy[^:]*:\s*£([\d,]+)/)

    // 5-year projection table rows
    const projRows = res?.fiveYearProjection?.map(y =>
      `<tr>
        <td>Year ${y.year}</td>
        <td>${gbp(y.propertyValue)}</td>
        <td>${gbp(y.equity)}</td>
        <td>${gbp(y.annualCashFlow)}</td>
        <td>${gbp(y.cumulativeCashFlow)}</td>
        <td>${gbp(y.totalReturn)}</td>
      </tr>`
    ).join("") || ""

    // SDLT breakdown rows
    const sdltRows = res?.sdltBreakdown?.map(b =>
      `<tr><td>${b.band}</td><td>${gbp(b.tax)}</td></tr>`
    ).join("") || ""

    // Score ring SVG (inline)
    const scoreRingSvg = score !== null ? `
      <div style="position:relative;width:110px;height:110px;margin:0 auto 8px;">
        <svg width="110" height="110" style="transform:rotate(-90deg)">
          <circle cx="55" cy="55" r="46" fill="none" stroke="#e5e7eb" stroke-width="10"/>
          <circle cx="55" cy="55" r="46" fill="none" stroke="${scoreColor}" stroke-width="10"
            stroke-linecap="round"
            stroke-dasharray="${(score / 100) * 2 * Math.PI * 46} ${2 * Math.PI * 46}"/>
        </svg>
        <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.1;">
          <span style="font-size:22px;font-weight:700;color:${scoreColor}">${score}%</span>
          <span style="font-size:9px;color:#999">/100</span>
        </div>
      </div>
      <div style="text-align:center;font-size:11px;font-weight:600;color:${scoreColor};margin-bottom:4px">${scoreLabel}</div>
    ` : ""

    const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>Deal Report — ${address}</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#1a1a2e;background:#fff}
  .page{padding:28px 32px;page-break-after:always;break-after:page}
  .page:last-child{page-break-after:auto;break-after:auto}
  /* ── HEADER ── */
  .rpt-header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:3px solid #1a1a2e;padding-bottom:12px;margin-bottom:18px}
  .rpt-title{font-size:20px;font-weight:700;letter-spacing:.3px}
  .rpt-sub{font-size:10px;color:#555;margin-top:3px}
  .rpt-badge{background:#1a1a2e;color:#fff;font-size:8px;letter-spacing:1px;padding:2px 8px;border-radius:2px;text-transform:uppercase;margin-top:6px;display:inline-block}
  /* ── SECTION TITLES ── */
  .sec-title{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#1a1a2e;border-left:4px solid #4f46e5;padding-left:8px;margin:18px 0 10px}
  /* ── PROPERTY DETAIL GRID ── */
  .detail-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:14px}
  .detail-item{background:#f8f8fc;border:1px solid #e8e8f0;border-radius:4px;padding:8px 10px}
  .detail-label{font-size:9px;text-transform:uppercase;color:#888;letter-spacing:.5px;margin-bottom:2px}
  .detail-value{font-size:13px;font-weight:700;color:#1a1a2e}
  /* ── HEADLINE FIGURES ── */
  .figures-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:14px}
  .fig-card{border:1px solid #e8e8f0;border-radius:6px;padding:10px;text-align:center;background:#fff}
  .fig-card.accent{background:#4f46e5;color:#fff;border-color:#4f46e5}
  .fig-card.green{background:#16a34a;color:#fff;border-color:#16a34a}
  .fig-card.amber{background:#f59e0b;color:#fff;border-color:#f59e0b}
  .fig-label{font-size:8px;text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px;opacity:.75}
  .fig-value{font-size:16px;font-weight:700}
  .fig-card.accent .fig-label,.fig-card.green .fig-label,.fig-card.amber .fig-label{opacity:.85}
  /* ── TABLE ── */
  table{width:100%;border-collapse:collapse;font-size:10px;margin-bottom:12px}
  th{background:#1a1a2e;color:#fff;padding:5px 8px;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.4px}
  td{padding:5px 8px;border-bottom:1px solid #f0f0f0}
  tr:nth-child(even) td{background:#f9f9fb}
  .td-right{text-align:right;font-weight:600}
  /* ── TWO-COL LAYOUT ── */
  .two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  /* ── AI TEXT ── */
  .ai-block{background:#f8f8fc;border:1px solid #e8e8f0;border-radius:6px;padding:12px;margin-bottom:12px}
  .ai-block-title{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:#4f46e5;font-weight:700;margin-bottom:6px}
  .ai-text{font-size:10px;line-height:1.6;color:#333;white-space:pre-wrap}
  /* ── SCORE SECTION ── */
  .score-banner{display:flex;align-items:center;gap:20px;background:#f8f8fc;border:1px solid #e8e8f0;border-radius:8px;padding:14px 16px;margin-bottom:14px}
  /* ── FOOTER ── */
  .rpt-footer{margin-top:20px;padding-top:8px;border-top:1px solid #ddd;font-size:8px;color:#aaa;text-align:center}
  @media print{.page{padding:16px 20px;page-break-after:always;break-after:page}.page:last-child{page-break-after:auto;break-after:auto}}
</style>
</head>
<body>

<!-- ════════════════════════════════════════════════════════
     PAGE 1 · DEAL SUMMARY
     ════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="rpt-header">
    <div>
      <div class="rpt-title">Property Investment Report</div>
      <div class="rpt-sub">${address}${postcode ? " · " + postcode : ""}</div>
      <div class="rpt-sub">Generated: ${date}</div>
      <span class="rpt-badge">Metalyzi · AI Deal Analyser</span>
    </div>
    <div style="text-align:right">
      <div style="font-size:9px;color:#888;margin-bottom:4px">Strategy</div>
      <div style="font-size:13px;font-weight:700;color:#4f46e5">${strategy}</div>
    </div>
  </div>

  <!-- Score banner -->
  ${score !== null ? `
  <div class="score-banner">
    ${scoreRingSvg}
    <div>
      <div style="font-size:16px;font-weight:700;color:${scoreColor}">${scoreLabel}</div>
      <div style="font-size:10px;color:#555;margin-top:4px">AI Deal Score: ${score}/100</div>
      ${aiSummary ? `<div style="font-size:10px;color:#333;margin-top:8px;max-width:480px;line-height:1.5">${aiSummary.substring(0, 280)}</div>` : ""}
    </div>
  </div>` : ""}

  <!-- Property details -->
  <div class="sec-title">Headline Details</div>
  <div class="detail-grid">
    <div class="detail-item"><div class="detail-label">Property Type</div><div class="detail-value">${propType}</div></div>
    <div class="detail-item"><div class="detail-label">Bedrooms</div><div class="detail-value">${na(fd?.bedrooms)} bed</div></div>
    <div class="detail-item"><div class="detail-label">Internal Area</div><div class="detail-value">${fd?.sqft ? fd.sqft + " sqft" : "—"}</div></div>
    <div class="detail-item"><div class="detail-label">Condition</div><div class="detail-value">${condition}</div></div>
    <div class="detail-item"><div class="detail-label">Strategy</div><div class="detail-value">${strategy}</div></div>
    <div class="detail-item"><div class="detail-label">Purchase Type</div><div class="detail-value">${(fd?.purchaseType || "mortgage").replace("-", " ").replace(/\b\w/g, c => c.toUpperCase())}</div></div>
  </div>

  <!-- Headline figures -->
  <div class="sec-title">Headline Deal Figures</div>
  <div class="figures-grid">
    <div class="fig-card accent"><div class="fig-label">Purchase Price</div><div class="fig-value">${gbp(fd?.purchasePrice || 0)}</div></div>
    <div class="fig-card"><div class="fig-label">Stamp Duty</div><div class="fig-value">${gbp(res?.sdltAmount || 0)}</div></div>
    <div class="fig-card"><div class="fig-label">Legal &amp; Survey</div><div class="fig-value">${gbp((fd?.legalFees || 0) + (fd?.surveyCosts || 0))}</div></div>
    <div class="fig-card"><div class="fig-label">Refurb Budget</div><div class="fig-value">${gbp(fd?.refurbishmentBudget || 0)}</div></div>
    <div class="fig-card accent"><div class="fig-label">Total Money In</div><div class="fig-value">${gbp(res?.totalCapitalRequired || 0)}</div></div>
    <div class="fig-card ${(res?.monthlyCashFlow || 0) >= 0 ? "green" : ""}"><div class="fig-label">Monthly Cashflow</div><div class="fig-value">${gbp(res?.monthlyCashFlow || 0)}</div></div>
    <div class="fig-card green"><div class="fig-label">Annual Cashflow</div><div class="fig-value">${gbp(res?.annualCashFlow || 0)}</div></div>
    <div class="fig-card ${(res?.grossYield || 0) >= 6 ? "green" : "amber"}"><div class="fig-label">Gross Yield</div><div class="fig-value">${pct(res?.grossYield || 0)}</div></div>
    <div class="fig-card"><div class="fig-label">Net Yield</div><div class="fig-value">${pct(res?.netYield || 0)}</div></div>
    <div class="fig-card ${(res?.cashOnCashReturn || 0) >= 10 ? "green" : ""}"><div class="fig-label">Cash-on-Cash ROI</div><div class="fig-value">${pct(res?.cashOnCashReturn || 0)}</div></div>
    <div class="fig-card"><div class="fig-label">Monthly Income</div><div class="fig-value">${gbp(res?.monthlyIncome || 0)}</div></div>
    <div class="fig-card"><div class="fig-label">Monthly Expenses</div><div class="fig-value">${gbp(res?.monthlyExpenses || 0)}</div></div>
  </div>

  <div class="rpt-footer">Metalyzi · AI Property Deal Analyser · metalyzi.com · For informational purposes only. Always seek professional financial and legal advice.</div>
</div>

<!-- ════════════════════════════════════════════════════════
     PAGE 2 · DEAL ANALYSER — FINANCIAL BREAKDOWN
     ════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="rpt-header">
    <div>
      <div class="rpt-title">Deal Analyser · Financial Breakdown</div>
      <div class="rpt-sub">${address} · ${strategy}</div>
    </div>
    <span class="rpt-badge">Metalyzi</span>
  </div>

  <div class="two-col">
    <!-- Purchase Costs -->
    <div>
      <div class="sec-title" style="margin-top:0">Purchase Costs</div>
      <table>
        <tr><th>Item</th><th style="text-align:right">Amount</th></tr>
        <tr><td>Purchase Price</td><td class="td-right">${gbp(fd?.purchasePrice || 0)}</td></tr>
        <tr><td>Deposit (${fd?.depositPercentage || 25}%)</td><td class="td-right">${gbp(res?.depositAmount || 0)}</td></tr>
        <tr><td>Mortgage Amount</td><td class="td-right">${gbp(res?.mortgageAmount || 0)}</td></tr>
        <tr><td>Stamp Duty (SDLT)</td><td class="td-right">${gbp(res?.sdltAmount || 0)}</td></tr>
        <tr><td>Legal Fees</td><td class="td-right">${gbp(fd?.legalFees || 0)}</td></tr>
        <tr><td>Survey Costs</td><td class="td-right">${gbp(fd?.surveyCosts || 0)}</td></tr>
        ${fd?.refurbishmentBudget ? `<tr><td>Refurbishment</td><td class="td-right">${gbp(fd.refurbishmentBudget)}</td></tr>` : ""}
        ${fd?.investmentType === "brr" && fd?.arv ? `<tr><td>After Repair Value (ARV)</td><td class="td-right">${gbp(fd.arv)}</td></tr>` : ""}
        <tr style="font-weight:700"><td><strong>Total Capital Required</strong></td><td class="td-right"><strong>${gbp(res?.totalCapitalRequired || 0)}</strong></td></tr>
      </table>

      ${fd?.investmentType === "brr" && fd?.arv ? `
      <div class="sec-title">BRR — Money Left In</div>
      <table>
        <tr><th>Item</th><th style="text-align:right">Amount</th></tr>
        <tr><td>After Repair Value (ARV)</td><td class="td-right">${gbp(fd.arv)}</td></tr>
        <tr><td>New Mortgage (75% ARV)</td><td class="td-right">${gbp(fd.arv * 0.75)}</td></tr>
        <tr><td>Total Money In</td><td class="td-right">${gbp(res?.totalCapitalRequired || 0)}</td></tr>
        <tr><td>Money Pulled Out</td><td class="td-right">${gbp(Math.max(0, fd.arv * 0.75 - (res?.totalCapitalRequired || 0)))}</td></tr>
        <tr style="font-weight:700"><td><strong>Money Left In</strong></td><td class="td-right"><strong>${gbp(Math.max(0, (res?.totalCapitalRequired || 0) - fd.arv * 0.75))}</strong></td></tr>
        <tr><td>Equity Created</td><td class="td-right">${gbp(Math.max(0, fd.arv - (res?.totalCapitalRequired || 0)))}</td></tr>
      </table>` : ""}

      ${fd?.investmentType === "hmo" && fd?.roomCount && fd?.avgRoomRate ? `
      <div class="sec-title">HMO Room Details</div>
      <table>
        <tr><th>Item</th><th style="text-align:right">Amount</th></tr>
        <tr><td>Number of Rooms</td><td class="td-right">${fd.roomCount}</td></tr>
        <tr><td>Avg Room Rate</td><td class="td-right">${gbp(fd.avgRoomRate)}/month</td></tr>
        <tr><td>Total HMO Income</td><td class="td-right">${gbp(fd.roomCount * fd.avgRoomRate)}/month</td></tr>
        <tr><td>Annual HMO Income</td><td class="td-right">${gbp(fd.roomCount * fd.avgRoomRate * 12)}/year</td></tr>
      </table>` : ""}
    </div>

    <!-- Monthly P&L -->
    <div>
      <div class="sec-title" style="margin-top:0">Monthly P&amp;L</div>
      <table>
        <tr><th>Item</th><th style="text-align:right">Amount</th></tr>
        <tr><td>Rental Income</td><td class="td-right">${gbp(res?.monthlyIncome || 0)}</td></tr>
        ${fd?.voidWeeks ? `<tr><td>Void Allowance (${fd.voidWeeks} wks)</td><td class="td-right" style="color:#dc2626">-${gbp(((fd.monthlyRent || 0) * fd.voidWeeks) / 52)}</td></tr>` : ""}
        <tr><td style="border-top:1px solid #ddd">Mortgage Payment</td><td class="td-right" style="border-top:1px solid #ddd">-${gbp(res?.monthlyMortgagePayment || 0)}</td></tr>
        ${fd?.managementFeePercent ? `<tr><td>Management (${fd.managementFeePercent}%)</td><td class="td-right">-${gbp((res?.monthlyIncome || 0) * (fd.managementFeePercent / 100))}</td></tr>` : ""}
        ${fd?.insurance ? `<tr><td>Insurance</td><td class="td-right">-${gbp(fd.insurance / 12)}/mo</td></tr>` : ""}
        ${fd?.maintenance ? `<tr><td>Maintenance</td><td class="td-right">-${gbp(fd.maintenance / 12)}/mo</td></tr>` : ""}
        ${fd?.groundRent ? `<tr><td>Ground Rent</td><td class="td-right">-${gbp(fd.groundRent / 12)}/mo</td></tr>` : ""}
        ${fd?.bills ? `<tr><td>Bills</td><td class="td-right">-${gbp(fd.bills / 12)}/mo</td></tr>` : ""}
        <tr><td><strong>Total Expenses</strong></td><td class="td-right"><strong>-${gbp(res?.monthlyExpenses || 0)}</strong></td></tr>
        <tr style="font-size:13px;font-weight:700;color:${(res?.monthlyCashFlow || 0) >= 0 ? "#16a34a" : "#dc2626"}">
          <td><strong>Net Monthly Cashflow</strong></td>
          <td class="td-right"><strong>${gbp(res?.monthlyCashFlow || 0)}</strong></td>
        </tr>
        <tr style="font-weight:700"><td>Annual Cashflow</td><td class="td-right">${gbp(res?.annualCashFlow || 0)}</td></tr>
      </table>

      <div class="sec-title">Returns</div>
      <table>
        <tr><th>Metric</th><th style="text-align:right">Value</th></tr>
        <tr><td>Gross Yield</td><td class="td-right">${pct(res?.grossYield || 0)}</td></tr>
        <tr><td>Net Yield</td><td class="td-right">${pct(res?.netYield || 0)}</td></tr>
        <tr><td>Cash-on-Cash ROI</td><td class="td-right">${pct(res?.cashOnCashReturn || 0)}</td></tr>
        <tr><td>Interest Rate</td><td class="td-right">${pct(fd?.interestRate || 0)}</td></tr>
        ${fd?.mortgageTerm ? `<tr><td>Mortgage Term</td><td class="td-right">${fd.mortgageTerm} years</td></tr>` : ""}
      </table>

      ${sdltRows ? `
      <div class="sec-title">SDLT Breakdown</div>
      <table>
        <tr><th>Band</th><th style="text-align:right">Tax</th></tr>
        ${sdltRows}
        <tr style="font-weight:700"><td>Total SDLT</td><td class="td-right">${gbp(res?.sdltAmount || 0)}</td></tr>
      </table>` : ""}
    </div>
  </div>

  <div class="rpt-footer">Metalyzi · AI Property Deal Analyser · For informational purposes only.</div>
</div>

<!-- ════════════════════════════════════════════════════════
     PAGE 3 · PROPERTY DETAILS, REFURB & 5-YEAR PROJECTION
     ════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="rpt-header">
    <div>
      <div class="rpt-title">Property Details &amp; Refurb</div>
      <div class="rpt-sub">${address}</div>
    </div>
    <span class="rpt-badge">Metalyzi</span>
  </div>

  <div class="sec-title" style="margin-top:0">Property Information</div>
  <table style="margin-bottom:18px">
    <tr><th>Field</th><th>Detail</th></tr>
    <tr><td>Full Address</td><td>${address}</td></tr>
    <tr><td>Postcode</td><td>${postcode || "—"}</td></tr>
    <tr><td>Property Type</td><td>${propType}</td></tr>
    <tr><td>Bedrooms</td><td>${na(fd?.bedrooms)}</td></tr>
    <tr><td>Internal Area</td><td>${fd?.sqft ? fd.sqft + " sqft" : "—"}</td></tr>
    <tr><td>Condition</td><td>${condition}</td></tr>
    <tr><td>Investment Strategy</td><td>${strategy}</td></tr>
    <tr><td>Purchase Type</td><td>${(fd?.purchaseType || "mortgage").replace("-", " ").replace(/\b\w/g, c => c.toUpperCase())}</td></tr>
    ${fd?.investmentType !== "r2sa" ? `<tr><td>Buyer Type</td><td>${fd?.buyerType === "first-time" ? "First-Time Buyer" : "Second Home / Investment (5% surcharge)"}</td></tr>` : ""}
  </table>

  <!-- Refurb estimates -->
  <div class="sec-title">Refurb &amp; Furnishing Estimate</div>
  <table style="margin-bottom:18px">
    <tr><th>Refurb Level</th><th style="text-align:right">Estimated Cost</th><th>Description</th></tr>
    <tr>
      <td><strong>Light (Cosmetic)</strong></td>
      <td class="td-right">${lightMatch ? `£${lightMatch[1]}` : fd?.sqft ? gbp(fd.sqft * 18) : "—"}</td>
      <td style="color:#555;font-size:9px">Redecorate, carpets, minor fixtures</td>
    </tr>
    <tr>
      <td><strong>Medium (Standard)</strong></td>
      <td class="td-right">${mediumMatch ? `£${mediumMatch[1]}` : fd?.sqft ? gbp(fd.sqft * 35) : "—"}</td>
      <td style="color:#555;font-size:9px">New kitchen, bathroom, replastering</td>
    </tr>
    <tr>
      <td><strong>Heavy (Full Refurb)</strong></td>
      <td class="td-right">${heavyMatch ? `£${heavyMatch[1]}` : fd?.sqft ? gbp(fd.sqft * 60) : "—"}</td>
      <td style="color:#555;font-size:9px">Rewire, new heating, full internal strip-out</td>
    </tr>
    <tr>
      <td><strong>Budgeted Refurb</strong></td>
      <td class="td-right" style="color:#4f46e5;font-weight:700">${gbp(fd?.refurbishmentBudget || 0)}</td>
      <td style="color:#555;font-size:9px">As entered in deal analysis</td>
    </tr>
  </table>

  <!-- 5-year projection -->
  ${projRows ? `
  <div class="sec-title">5-Year Investment Projection</div>
  <div style="font-size:9px;color:#888;margin-bottom:6px">Assumes 3% annual capital growth &amp; ${fd?.annualRentIncrease || 2}% rent increase per year</div>
  <table>
    <tr>
      <th>Year</th>
      <th style="text-align:right">Property Value</th>
      <th style="text-align:right">Equity</th>
      <th style="text-align:right">Annual CF</th>
      <th style="text-align:right">Cumulative CF</th>
      <th style="text-align:right">Total Return</th>
    </tr>
    ${projRows}
  </table>` : ""}

  <div class="rpt-footer">Metalyzi · AI Property Deal Analyser · For informational purposes only. Projections are estimates only and not guaranteed.</div>
</div>

<!-- ════════════════════════════════════════════════════════
     PAGE 4 · AI ANALYSIS & RISK FLAGS
     ════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="rpt-header">
    <div>
      <div class="rpt-title">AI Investment Analysis</div>
      <div class="rpt-sub">${address} · Powered by Metalyzi AI</div>
    </div>
    <span class="rpt-badge">Metalyzi</span>
  </div>

  ${aiStrengths ? `
  <div class="ai-block">
    <div class="ai-block-title">✅ Strengths</div>
    <div class="ai-text">${aiStrengths}</div>
  </div>` : ""}

  ${aiRisks ? `
  <div class="ai-block">
    <div class="ai-block-title">⚠️ Risks &amp; Concerns</div>
    <div class="ai-text">${aiRisks}</div>
  </div>` : ""}

  ${aiNextSteps ? `
  <div class="ai-block">
    <div class="ai-block-title">📋 Recommended Next Steps</div>
    <div class="ai-text">${aiNextSteps}</div>
  </div>` : ""}

  ${riskFlagsHtml}
  ${benchmarkHtml}
  ${strategyRecsHtml}

  <div class="rpt-footer">Continued on next page →</div>
</div>

<!-- ════════════════════════════════════════════════════════
     PAGE 5 · MARKET DATA & COMPARABLES
     ════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="rpt-header">
    <div>
      <div class="rpt-title">Market Data &amp; Comparables</div>
      <div class="rpt-sub">${address} · Powered by Metalyzi AI</div>
    </div>
    <span class="rpt-badge">Metalyzi</span>
  </div>

  ${aiVerdictHtml}
  ${aiAreaHtml}
  ${rentCompsHtml}
  ${soldCompsHtml}

  <div class="rpt-footer">This report was generated by Metalyzi (metalyzi.com) on ${date}. It is for informational purposes only. Always seek independent financial and legal advice before making any property investment decision. Past performance is not a reliable indicator of future results.</div>
</div>

</body>
</html>`

    const win = window.open("", "_blank", "width=1000,height=800")
    if (!win) {
      alert("Please allow pop-ups for this site to download the PDF.")
      return
    }
    win.document.write(html)
    win.document.close()
    win.onload = () => { win.print() }
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      {/* Top Bar */}
      <header className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <Image
              src="/logo.png"
              alt="Metalyzi Logo"
              width={28}
              height={28}
              className="rounded-lg object-contain"
            />
            <span className="text-sm font-semibold text-foreground">
              Metalyzi
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

        {/* Recent Deals — shown only when not viewing a current analysis */}
        {!hasResults && !isProcessing && (
          <div className="mb-8">
            <RecentDeals key={recentDealsVersion} onLoad={handleLoadSavedDeal} />
          </div>
        )}

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
          <div className="max-w-4xl">
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
            {/* Results toolbar */}
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" size="sm" onClick={resetAll}>
                <ArrowLeft className="size-3.5" />
                New Analysis
              </Button>

              {/* Save as PDF — available once analysis text is ready */}
              {aiText && !aiLoading && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSavePDF}
                  className="gap-1.5 border-primary/40 text-primary hover:bg-primary/10"
                >
                  <FileDown className="size-3.5" />
                  Save as PDF
                </Button>
              )}

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
                backendData={backendData}
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

"use client"

import { useState, useCallback } from "react"
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

  // Call the OpenClaw proxy API and handle the response
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

        // Handle streaming text response from OpenClaw
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

        // If OpenClaw returns structured property data, use it for charts
        if (data.propertyData) {
          setFormData(data.propertyData)
          if (data.calculationResults) {
            setResults(data.calculationResults)
          } else {
            setResults(calculateAll(data.propertyData))
          }
        }

        // Extract AI analysis text -- our API returns { aiAnalysis: "..." }
        const analysis = data.aiAnalysis || ""

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

  // Manual form submission -- runs local calculations then sends to OpenClaw
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

  // URL-based submission -- sends URL to OpenClaw for scraping + analysis
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
        await callAnalysisAPI({ mode: "url", url: listingUrl })
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
    [listingUrl, callAnalysisAPI]
  )

  const hasResults = (results && formData) || aiText
  const isProcessing = isLoading || aiLoading

  const resetAll = () => {
    setResults(null)
    setFormData(null)
    setListingUrl("")
    setError(null)
    setAiText("")
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
                onSubmit={handleManualSubmit}
                isLoading={isProcessing}
              />
            </div>

            {/* Empty state */}
            <div className="flex h-full min-h-[400px] flex-col items-center justify-center rounded-xl border border-dashed border-border/50 bg-card/30 p-12 text-center">
              <div className="mb-4 flex size-16 items-center justify-center rounded-2xl bg-primary/10">
                <BarChart3 className="size-7 text-primary" />
              </div>
              <h3 className="text-lg font-semibold text-foreground">
                No Analysis Yet
              </h3>
              <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
                Fill in the property details on the left and hit
                &quot;Analyse This Deal&quot; to see a full financial breakdown
                and AI-powered insights.
              </p>
            </div>
          </div>
        )}

        {/* Loading state (URL mode) */}
        {isProcessing && inputMode === "url" && !hasResults && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Loader2 className="mb-4 size-10 animate-spin text-primary" />
            <h3 className="text-lg font-semibold text-foreground">
              Analysing Property...
            </h3>
            <p className="mt-2 max-w-sm text-sm text-muted-foreground">
              Your AI agent is scraping the listing and running a full
              investment analysis. This may take a moment.
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
              /* URL mode -- AI text only (no structured data from OpenClaw) */
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

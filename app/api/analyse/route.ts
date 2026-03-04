// Flask Backend Proxy - connects to Render-deployed Flask API
// Endpoints: /extract-url (scraping) and /ai-analyze (AI analysis)
// Last updated: force cache bust v2

const RENDER_URL = "https://metusa-deal-analyzer.onrender.com"

async function sendToFlask(
  endpoint: string,
  payload: Record<string, unknown>
): Promise<Response> {
  const url = `${RENDER_URL}${endpoint}`
  console.log("[v0] FLASK PROXY: Sending to", url)
  console.log("[v0] FLASK PROXY: Payload keys:", Object.keys(payload))

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 120000)

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    clearTimeout(timeout)

    console.log("[v0] FLASK PROXY: Response status:", res.status)
    console.log("[v0] FLASK PROXY: Response content-type:", res.headers.get("content-type"))

    if (!res.ok) {
      const errText = await res.text().catch(() => "Unknown error")
      console.error("[v0] FLASK PROXY: Error response body:", errText)
      // Parse structured errors from Flask (e.g. subscription gate)
      let errJson: Record<string, string> | null = null
      try { errJson = JSON.parse(errText) } catch { /* ignore */ }
      const code    = errJson?.code    || null
      const message = errJson?.message || `Backend error (${res.status})`
      return Response.json({ error: message, code }, { status: res.status })
    }

    return res
  } catch (err) {
    clearTimeout(timeout)
    console.error("[v0] FLASK PROXY: Fetch exception:", err)

    if (err instanceof Error && err.name === "AbortError") {
      return Response.json(
        { error: "Request timed out after 120s. Your Render service may be starting up (cold start). Please try again in 30 seconds." },
        { status: 504 }
      )
    }

    return Response.json(
      { error: err instanceof Error ? `Connection failed: ${err.message}` : "Connection failed" },
      { status: 502 }
    )
  }
}

export async function POST(req: Request) {
  console.log("[v0] ========== FLASK PROXY ROUTE HIT ==========")

  const body = await req.json()
  const { mode } = body

  console.log("[v0] FLASK PROXY: mode =", mode)
  console.log("[v0] FLASK PROXY: Using Render URL:", RENDER_URL)

  // ── Scrape-Only Mode ──────────────────────────────────────────────
  // Returns scraped property data mapped to PropertyFormData field names.
  // Used by the two-step URL flow: scrape first, then user fills remaining fields.
  if (mode === "scrape-only") {
    const { url } = body

    if (!url || typeof url !== "string") {
      return Response.json({ error: "A property listing URL is required." }, { status: 400 })
    }

    console.log("[v0] FLASK PROXY: Scrape-only mode - calling /extract-url")
    const scrapeRes = await sendToFlask("/extract-url", { url })

    if (!scrapeRes.ok) {
      return scrapeRes
    }

    let scrapedData: Record<string, unknown>
    try {
      scrapedData = await scrapeRes.json()
      console.log("[v0] FLASK PROXY: Scraped data keys:", Object.keys(scrapedData))
    } catch {
      return Response.json(
        { error: "Failed to parse scraped data from backend." },
        { status: 502 }
      )
    }

    // The /extract-url response has { data: {...}, success: true }
    const raw = (scrapedData.data || scrapedData) as Record<string, unknown>
    console.log("[v0] FLASK PROXY: Raw scraped fields:", raw)

    // Map property_type from scraper (e.g. "Terraced", "Detached", "Flat") to our enum
    const rawType = String(raw.property_type || "").toLowerCase()
    let propertyType: string = "house"
    if (rawType.includes("flat") || rawType.includes("apartment") || rawType.includes("maisonette")) {
      propertyType = "flat"
    } else if (rawType.includes("hmo")) {
      propertyType = "hmo"
    } else if (rawType.includes("commercial")) {
      propertyType = "commercial"
    }

    // Map scraped fields to our PropertyFormData field names
    const rawSqft = Number(raw.sqft) || 0
    const mappedData = {
      address: raw.address || "",
      postcode: raw.postcode || "",
      purchasePrice: Number(raw.price) || Number(raw.purchasePrice) || 0,
      propertyType,
      bedrooms: Number(raw.bedrooms) || 3,
      description: raw.description || "",
      sqft: rawSqft > 0 ? rawSqft : undefined,
      sqftEstimated: Boolean(raw.sqft_estimated),
    }

    console.log("[v0] FLASK PROXY: Mapped scrape data:", mappedData)
    return Response.json({ success: true, propertyData: mappedData })
  }

  // ── URL Mode (legacy - kept for backwards compatibility) ─────────
  if (mode === "url") {
    const { url } = body

    if (!url || typeof url !== "string") {
      return Response.json({ error: "A property listing URL is required." }, { status: 400 })
    }

    // Step 1: Scrape the listing URL
    console.log("[v0] FLASK PROXY: Step 1 - Scraping URL via /extract-url")
    const scrapeRes = await sendToFlask("/extract-url", { url })

    if (!scrapeRes.ok) {
      return scrapeRes
    }

    let scrapedData: Record<string, unknown>
    try {
      scrapedData = await scrapeRes.json()
      console.log("[v0] FLASK PROXY: Scraped data keys:", Object.keys(scrapedData))
    } catch {
      return Response.json(
        { error: "Failed to parse scraped data from backend." },
        { status: 502 }
      )
    }

    // Step 2: Send scraped data to AI analysis
    const propertyPayload = (scrapedData.data || scrapedData) as Record<string, unknown>
    console.log("[v0] FLASK PROXY: Step 2 - AI analysis via /ai-analyze")
    const aiPayload = { 
      address: propertyPayload.address || 'Unknown Address',
      postcode: propertyPayload.postcode || 'N/A',
      purchasePrice: propertyPayload.price || propertyPayload.purchasePrice || 0,
      bedrooms: propertyPayload.bedrooms || 3,
      property_type: propertyPayload.property_type || 'Terrace',
      description: propertyPayload.description || '',
      url,
      dealType: 'BTL',
      deposit: 25,
      interestRate: 3.75
    }
    const aiRes = await sendToFlask("/ai-analyze", aiPayload)

    if (!aiRes.ok) {
      return aiRes
    }

    try {
      const aiData = await aiRes.json()
      return Response.json({ aiAnalysis: aiData.analysis || aiData.text || aiData.response || aiData.result || JSON.stringify(aiData) })
    } catch {
      const text = await aiRes.text()
      return Response.json({ aiAnalysis: text })
    }
  }

  // ── Manual Mode ──────────────────────────────────────────────────
  if (mode === "manual") {
    const { propertyData, calculationResults } = body

    if (!propertyData || !calculationResults) {
      return Response.json(
        { error: "Property data and calculation results are required." },
        { status: 400 }
      )
    }

    console.log("[v0] FLASK PROXY: Manual mode - flattening data for /ai-analyze")
    // Flatten the nested structure - backend expects flat fields
    // investmentType (lowercase e.g. "btl") → dealType (uppercase e.g. "BTL")
    const rawInvestmentType = propertyData.investmentType || 'btl'
    const aiPayload = {
      address: propertyData.address || 'Unknown Address',
      postcode: propertyData.postcode || 'N/A',
      dealType: String(rawInvestmentType).toUpperCase(),
      purchaseType: propertyData.purchaseType || 'mortgage',
      purchasePrice: Number(propertyData.purchasePrice) || 0,
      bedrooms: Number(propertyData.bedrooms) || 3,
      monthlyRent: Number(propertyData.monthlyRent) || 0,
      deposit: Number(propertyData.depositPercentage) || 25,
      interestRate: Number(propertyData.interestRate) || 5.5,
      propertyType: propertyData.propertyType || 'house',
      description: propertyData.description || '',
      // BRR / Flip
      refurbCosts: Number(propertyData.refurbishmentBudget) || 0,
      arv: Number(propertyData.arv) || 0,
      // Bridging loan
      bridgingMonthlyRate: Number(propertyData.bridgingMonthlyRate) || 0.75,
      bridgingTermMonths: Number(propertyData.bridgingTermMonths) || 12,
      bridgingArrangementFee: Number(propertyData.bridgingArrangementFee) || 1.0,
      bridgingExitFee: Number(propertyData.bridgingExitFee) || 0.5,
      // HMO
      roomCount: Number(propertyData.roomCount) || 0,
      avgRoomRate: Number(propertyData.avgRoomRate) || 0,
      // R2SA
      saMonthlySARevenue: Number(propertyData.saMonthlySARevenue) || 0,
      saSetupCosts: Number(propertyData.saSetupCosts) || 5000,
      // Projection assumption
      capitalGrowthRate: Number(propertyData.capitalGrowthRate) || 4,
    }
    console.log("[v0] FLASK PROXY: Sending flattened payload:", aiPayload)
    const aiRes = await sendToFlask("/ai-analyze", aiPayload)

    if (!aiRes.ok) {
      return aiRes
    }

    try {
      const aiData = await aiRes.json()
      console.log("[v0] FLASK PROXY: AI response keys:", Object.keys(aiData))
      return Response.json({ aiAnalysis: aiData.analysis || aiData.text || aiData.response || aiData.result || JSON.stringify(aiData) })
    } catch {
      const text = await aiRes.text()
      return Response.json({ aiAnalysis: text })
    }
  }

  return Response.json({ error: "Invalid mode. Use 'scrape-only', 'url', or 'manual'." }, { status: 400 })
}

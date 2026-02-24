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
      return Response.json(
        { error: `Backend error (${res.status}): ${errText}` },
        { status: res.status }
      )
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

  // ── URL Mode ─────────────────────────────────────────────────────
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
    // Note: scrapedData has {data: {...}, success: true} structure from /extract-url
    const propertyPayload = scrapedData.data || scrapedData
    console.log("[v0] FLASK PROXY: Step 2 - AI analysis via /ai-analyze")
    console.log("[v0] FLASK PROXY: Sending property data:", propertyPayload)
    // Add default dealType if not present (scraping doesn't know the strategy)
    const aiPayload = { 
      ...propertyPayload, 
      url,
      dealType: propertyPayload.dealType || 'BTL'  // Default to BTL if not specified
    }
    const aiRes = await sendToFlask("/ai-analyze", aiPayload)

    if (!aiRes.ok) {
      return aiRes
    }

    try {
      const aiData = await aiRes.json()
      console.log("[v0] FLASK PROXY: AI response keys:", Object.keys(aiData))
      return Response.json({ aiAnalysis: aiData.analysis || aiData.text || aiData.response || aiData.result || JSON.stringify(aiData) })
    } catch {
      // Maybe it's plain text
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
    const aiPayload = {
      address: propertyData.address || 'Unknown Address',
      postcode: propertyData.postcode || 'N/A',
      dealType: calculationResults.dealType || propertyData.dealType || 'BTL',
      purchasePrice: Number(propertyData.purchasePrice) || Number(calculationResults.purchasePrice) || 0,
      bedrooms: Number(propertyData.bedrooms) || 3,
      monthlyRent: Number(propertyData.monthlyRent) || Number(calculationResults.monthlyRent) || 0,
      deposit: Number(propertyData.deposit) || Number(calculationResults.deposit) || 25,
      interestRate: Number(propertyData.interestRate) || Number(calculationResults.interestRate) || 3.75,
      propertyType: propertyData.propertyType || 'Terrace',
      description: propertyData.description || '',
      refurbCost: Number(propertyData.refurbCost) || 0,
      arv: Number(propertyData.arv) || 0
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

  return Response.json({ error: "Invalid mode. Use 'url' or 'manual'." }, { status: 400 })
}

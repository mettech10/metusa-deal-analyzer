// DealCheck UK - Flask Backend Proxy (Render deployment)
// Endpoints: /extract-url (scrape), /ai-analyze (AI analysis)
// Updated: 2026-02-23

const FLASK_BASE =
  process.env.FLASK_API_URL?.replace(/\/+$/, "") ||
  "https://metusa-deal-analyzer.onrender.com"

export async function POST(req: Request) {
  const body = await req.json()
  const { mode } = body

  console.log("[v0] === NEW Flask API Route ===")
  console.log("[v0] FLASK_BASE:", FLASK_BASE)
  console.log("[v0] FLASK_API_URL env:", process.env.FLASK_API_URL)
  console.log("[v0] Mode:", mode)

  if (mode === "url") {
    return handleUrlMode(body)
  }

  if (mode === "manual") {
    return handleManualMode(body)
  }

  return Response.json(
    { error: "Invalid mode. Use 'url' or 'manual'." },
    { status: 400 }
  )
}

// ── URL Mode: scrape via /extract-url then analyse via /ai-analyze ──
async function handleUrlMode(body: { url?: string }) {
  const { url } = body

  if (!url || typeof url !== "string") {
    return Response.json(
      { error: "A valid property listing URL is required." },
      { status: 400 }
    )
  }

  // Step 1: Scrape the listing
  const extractUrl = `${FLASK_BASE}/extract-url`
  console.log("[v0] Step 1 - Scraping:", extractUrl)

  const scrapeRes = await safeFetch(extractUrl, { url })
  if (scrapeRes.error) {
    return Response.json({ error: scrapeRes.error }, { status: scrapeRes.status })
  }

  console.log("[v0] Scrape response keys:", Object.keys(scrapeRes.data))

  // Step 2: Send scraped data to AI analysis
  const analyzeUrl = `${FLASK_BASE}/ai-analyze`
  console.log("[v0] Step 2 - Analysing:", analyzeUrl)

  const analyzeRes = await safeFetch(analyzeUrl, {
    ...scrapeRes.data,
    url,
  })
  if (analyzeRes.error) {
    return Response.json({ error: analyzeRes.error }, { status: analyzeRes.status })
  }

  console.log("[v0] Analyze response keys:", Object.keys(analyzeRes.data))
  return Response.json(normalizeResponse(analyzeRes.data))
}

// ── Manual Mode: send property data directly to /ai-analyze ─────────
async function handleManualMode(body: {
  propertyData?: unknown
  calculationResults?: unknown
}) {
  const { propertyData, calculationResults } = body

  if (!propertyData || !calculationResults) {
    return Response.json(
      { error: "Property data and calculation results are required." },
      { status: 400 }
    )
  }

  const analyzeUrl = `${FLASK_BASE}/ai-analyze`
  console.log("[v0] Manual mode - Analysing:", analyzeUrl)

  const analyzeRes = await safeFetch(analyzeUrl, {
    propertyData,
    calculationResults,
  })
  if (analyzeRes.error) {
    return Response.json({ error: analyzeRes.error }, { status: analyzeRes.status })
  }

  console.log("[v0] Manual analyze response keys:", Object.keys(analyzeRes.data))
  return Response.json(normalizeResponse(analyzeRes.data))
}

// ── Safe fetch wrapper with timeout + error handling ────────────────
async function safeFetch(
  url: string,
  payload: Record<string, unknown>
): Promise<
  | { data: Record<string, unknown>; error?: never; status?: never }
  | { error: string; status: number; data?: never }
> {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 120_000)

    console.log("[v0] Fetching:", url)

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    clearTimeout(timeout)

    console.log("[v0] Response status:", res.status)

    if (!res.ok) {
      const errText = await res.text().catch(() => "Unknown error")
      console.error("[v0] Error body:", errText)
      return { error: `Backend error (${res.status}): ${errText}`, status: res.status }
    }

    const data = await res.json()
    return { data }
  } catch (err) {
    console.error("[v0] Fetch failed:", err)

    if (err instanceof Error && err.name === "AbortError") {
      return {
        error:
          "Request timed out (120s). Your Render service may be waking up from sleep. Please try again in 30 seconds.",
        status: 504,
      }
    }

    return {
      error:
        err instanceof Error
          ? `Connection failed: ${err.message}`
          : "Failed to connect to backend.",
      status: 502,
    }
  }
}

// ── Normalize Flask response into { aiAnalysis: string } shape ──────
function normalizeResponse(data: Record<string, unknown>) {
  const text =
    data.aiAnalysis ||
    data.analysis ||
    data.result ||
    data.response ||
    data.text ||
    data.content ||
    data.message ||
    data.output ||
    ""

  const result: Record<string, unknown> = {
    aiAnalysis:
      typeof text === "string" ? text : JSON.stringify(text, null, 2),
  }

  if (data.propertyData) result.propertyData = data.propertyData
  if (data.calculationResults) result.calculationResults = data.calculationResults

  return result
}

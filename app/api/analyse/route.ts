export async function POST(req: Request) {
  const body = await req.json()
  const { mode } = body

  const flaskUrl = process.env.FLASK_API_URL

  console.log("[v0] Flask API URL:", flaskUrl)
  console.log("[v0] Request mode:", mode)

  if (!flaskUrl) {
    return Response.json(
      {
        error:
          "Flask API URL is not configured. Please set FLASK_API_URL in environment variables.",
      },
      { status: 500 }
    )
  }

  // Build the full endpoint URLs for each Flask route
  const baseUrl = flaskUrl.replace(/\/+$/, "")
  const extractUrlEndpoint = `${baseUrl}/extract-url`
  const aiAnalyzeEndpoint = `${baseUrl}/ai-analyze`

  console.log("[v0] Flask base URL:", baseUrl)
  console.log("[v0] Extract URL endpoint:", extractUrlEndpoint)
  console.log("[v0] AI Analyze endpoint:", aiAnalyzeEndpoint)

  // ── URL Mode: First scrape the URL, then run AI analysis ─────────
  if (mode === "url") {
    const { url } = body

    if (!url || typeof url !== "string") {
      return Response.json(
        { error: "A valid property listing URL is required." },
        { status: 400 }
      )
    }

    // Step 1: Scrape the property listing URL
    console.log("[v0] Step 1: Scraping URL via /extract-url")
    const scrapeResult = await callFlaskAPI(extractUrlEndpoint, { url })

    if (scrapeResult.status !== 200) {
      return scrapeResult
    }

    // Step 2: Send scraped data to AI analysis
    const scrapedData = await scrapeResult.json()
    console.log("[v0] Scraped data keys:", Object.keys(scrapedData))

    console.log("[v0] Step 2: Sending to /ai-analyze")
    return await callFlaskAPI(aiAnalyzeEndpoint, {
      ...scrapedData,
      url,
    })
  }

  // ── Manual Mode: Send property data directly to AI analysis ──────
  if (mode === "manual") {
    const { propertyData, calculationResults } = body

    if (!propertyData || !calculationResults) {
      return Response.json(
        { error: "Property data and calculation results are required." },
        { status: 400 }
      )
    }

    return await callFlaskAPI(aiAnalyzeEndpoint, {
      propertyData,
      calculationResults,
    })
  }

  return Response.json(
    { error: "Invalid mode. Use 'url' or 'manual'." },
    { status: 400 }
  )
}

// ── Shared function to call your Flask backend on Render ───────────
async function callFlaskAPI(
  url: string,
  payload: Record<string, unknown>
) {
  try {
    const controller = new AbortController()
    // Render free tier can be slow to wake up -- give it 120 seconds
    const timeout = setTimeout(() => controller.abort(), 120000)

    console.log("[v0] Sending to Flask:", url)
    console.log("[v0] Payload keys:", Object.keys(payload))

    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    clearTimeout(timeout)

    console.log("[v0] Flask response status:", res.status)
    console.log(
      "[v0] Flask response content-type:",
      res.headers.get("content-type")
    )

    if (!res.ok) {
      const errText = await res.text().catch(() => "Unknown error")
      console.error("[v0] Flask error body:", errText)
      return Response.json(
        {
          error: `Backend returned ${res.status}: ${errText}`,
        },
        { status: res.status }
      )
    }

    const contentType = res.headers.get("content-type") || ""

    // If Flask streams text, pass it through
    if (
      contentType.includes("text/event-stream") ||
      contentType.includes("text/plain")
    ) {
      return new Response(res.body, {
        headers: {
          "Content-Type": contentType,
          "Cache-Control": "no-cache",
        },
      })
    }

    // JSON response from Flask
    const data = await res.json()
    console.log("[v0] Flask response keys:", Object.keys(data))

    // Extract analysis text from whatever shape Flask returns
    const analysisText =
      data.aiAnalysis ||
      data.analysis ||
      data.result ||
      data.response ||
      data.text ||
      data.content ||
      data.message ||
      data.output ||
      (typeof data === "string" ? data : "")

    // If Flask returns property data too, forward it
    const responsePayload: Record<string, unknown> = {
      aiAnalysis:
        typeof analysisText === "string"
          ? analysisText
          : JSON.stringify(analysisText, null, 2),
    }

    if (data.propertyData) {
      responsePayload.propertyData = data.propertyData
    }
    if (data.calculationResults) {
      responsePayload.calculationResults = data.calculationResults
    }

    return Response.json(responsePayload)
  } catch (err) {
    console.error("[v0] Flask fetch error:", err)

    const message =
      err instanceof Error && err.name === "AbortError"
        ? "Request timed out after 120 seconds. Your Render service may be starting up (free tier cold start). Please try again in a moment."
        : err instanceof Error
          ? `Failed to connect to backend: ${err.message}`
          : "Failed to connect to backend. Please check your API configuration."

    return Response.json({ error: message }, { status: 502 })
  }
}

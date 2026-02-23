export async function POST(req: Request) {
  const body = await req.json()
  const { mode } = body

  const openclawUrl = process.env.OPENCLAW_API_URL
  const openclawKey = process.env.OPENCLAW_API_KEY

  console.log("[v0] OpenClaw URL:", openclawUrl)
  console.log("[v0] OpenClaw Key present:", !!openclawKey)
  console.log("[v0] Request mode:", mode)

  if (!openclawUrl) {
    return Response.json(
      { error: "OpenClaw API URL is not configured. Set OPENCLAW_API_URL in environment variables." },
      { status: 500 }
    )
  }

  // Build the OpenResponses API URL
  // The user may have set the base URL (e.g. https://gateway.openclaw.ai)
  // or the full endpoint (e.g. https://gateway.openclaw.ai/v1/responses)
  let apiUrl: string
  try {
    const parsed = new URL(openclawUrl)
    // If the path doesn't already include /v1/responses, append it
    if (parsed.pathname.endsWith("/v1/responses")) {
      apiUrl = openclawUrl
    } else {
      // Strip trailing slash and append the endpoint
      apiUrl = openclawUrl.replace(/\/+$/, "") + "/v1/responses"
    }
  } catch {
    return Response.json(
      { error: `OPENCLAW_API_URL is not a valid URL: "${openclawUrl}". Check your environment variables.` },
      { status: 500 }
    )
  }

  console.log("[v0] Resolved OpenClaw API URL:", apiUrl)

  // ── URL Mode: Ask OpenClaw to analyse a listing URL ──────────────
  if (mode === "url") {
    const { url } = body

    if (!url || typeof url !== "string") {
      return Response.json(
        { error: "A valid property listing URL is required." },
        { status: 400 }
      )
    }

    const inputMessage = `Analyse this UK property listing: ${url}

Please scrape the listing and extract all property details (address, price, bedrooms, property type, etc.).
Then provide a full investment analysis including:
1. Deal Score (0-100)
2. Summary of the property and area
3. Strengths of this deal
4. Risks & Concerns
5. Recommendation (buy / avoid / negotiate)

Also calculate or estimate: SDLT (stamp duty), mortgage costs, rental yield, monthly cash flow, and ROI where possible.`

    return await callOpenClaw(apiUrl, openclawKey, inputMessage)
  }

  // ── Manual Mode: Forward property data + calculations ────────────
  if (mode === "manual") {
    const { propertyData, calculationResults } = body

    if (!propertyData || !calculationResults) {
      return Response.json(
        { error: "Property data and calculation results are required." },
        { status: 400 }
      )
    }

    const inputMessage = `Analyse this UK property investment deal:

**Property Details:**
- Address: ${propertyData.address || "Not specified"}
- Type: ${propertyData.propertyType || "Unknown"}
- Bedrooms: ${propertyData.bedrooms || "Unknown"}
- Condition: ${propertyData.condition || "Unknown"}
- Purchase Price: £${Number(propertyData.purchasePrice).toLocaleString()}

**Financing:**
- Method: ${propertyData.purchaseMethod}
${
  propertyData.purchaseMethod === "mortgage"
    ? `- Deposit: ${propertyData.depositPercentage}% (£${Number(calculationResults.depositAmount).toLocaleString()})
- Mortgage Amount: £${Number(calculationResults.mortgageAmount).toLocaleString()}
- Interest Rate: ${propertyData.interestRate}%
- Term: ${propertyData.mortgageTerm} years
- Type: ${propertyData.mortgageType}
- Monthly Mortgage: £${Number(calculationResults.monthlyMortgagePayment).toLocaleString()}`
    : "- Cash purchase"
}

**Calculated Metrics:**
- SDLT: £${Number(calculationResults.sdltAmount).toLocaleString()} ${propertyData.isAdditionalProperty ? "(includes 5% surcharge)" : ""}
- Total Capital Required: £${Number(calculationResults.totalCapitalRequired).toLocaleString()}
- Monthly Rent: £${Number(propertyData.monthlyRent).toLocaleString()}
- Monthly Cash Flow: £${Number(calculationResults.monthlyCashFlow).toLocaleString()}
- Annual Cash Flow: £${Number(calculationResults.annualCashFlow).toLocaleString()}
- Gross Yield: ${calculationResults.grossYield}%
- Net Yield: ${calculationResults.netYield}%
- Cash-on-Cash ROI: ${calculationResults.cashOnCashReturn}%
- Void Period: ${propertyData.voidWeeks} weeks/year
- Management Fee: ${propertyData.managementFeePercent}%
- Annual Running Costs: £${Number(calculationResults.annualRunningCosts).toLocaleString()}
${Number(propertyData.refurbishmentBudget) > 0 ? `- Refurbishment Budget: £${Number(propertyData.refurbishmentBudget).toLocaleString()}` : ""}

**5-Year Projection (Year 5):**
- Projected Property Value: £${Number(calculationResults.fiveYearProjection?.[4]?.propertyValue ?? 0).toLocaleString()}
- Projected Equity: £${Number(calculationResults.fiveYearProjection?.[4]?.equity ?? 0).toLocaleString()}
- Cumulative Cash Flow: £${Number(calculationResults.fiveYearProjection?.[4]?.cumulativeCashFlow ?? 0).toLocaleString()}
- Total Return: £${Number(calculationResults.fiveYearProjection?.[4]?.totalReturn ?? 0).toLocaleString()}

Provide your analysis with:
1. Deal Score: X (0-100)
2. ## Summary
3. ## Strengths
4. ## Risks & Concerns
5. ## Recommendation`

    return await callOpenClaw(apiUrl, openclawKey, inputMessage)
  }

  return Response.json({ error: "Invalid mode. Use 'url' or 'manual'." }, { status: 400 })
}

// ── Shared function to call OpenClaw's OpenResponses API ───────────
async function callOpenClaw(
  apiUrl: string,
  apiKey: string | undefined,
  input: string
) {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 90000)

    console.log("[v0] Sending to OpenClaw:", apiUrl)

    const openclawRes = await fetch(apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
      },
      body: JSON.stringify({
        model: "openclaw",
        input,
        stream: false,
        instructions:
          "You are a UK property investment analyst. Provide detailed, data-driven investment analysis with clear deal scores, strengths, risks, and actionable recommendations.",
      }),
      signal: controller.signal,
    })

    clearTimeout(timeout)

    console.log("[v0] OpenClaw response status:", openclawRes.status)
    console.log("[v0] OpenClaw response content-type:", openclawRes.headers.get("content-type"))

    if (!openclawRes.ok) {
      const errText = await openclawRes.text().catch(() => "Unknown error")
      console.error("[v0] OpenClaw error body:", errText)
      return Response.json(
        { error: `OpenClaw returned ${openclawRes.status}: ${errText}` },
        { status: openclawRes.status }
      )
    }

    const contentType = openclawRes.headers.get("content-type") || ""

    // Stream SSE responses through to client
    if (contentType.includes("text/event-stream")) {
      return new Response(openclawRes.body, {
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache",
        },
      })
    }

    // JSON response -- extract the text output
    const data = await openclawRes.json()
    console.log("[v0] OpenClaw response keys:", Object.keys(data))

    // OpenResponses format: data.output is an array of output items
    let analysisText = ""
    if (data.output && Array.isArray(data.output)) {
      for (const item of data.output) {
        if (item.type === "message" && item.content) {
          for (const part of item.content) {
            if (part.type === "output_text") {
              analysisText += part.text
            }
          }
        }
      }
    }

    // Fallback: try common response shapes
    if (!analysisText) {
      analysisText =
        data.text ||
        data.response ||
        data.content ||
        data.message ||
        data.aiAnalysis ||
        data.analysis ||
        (typeof data === "string" ? data : "")
    }

    // Last resort: return the whole thing
    if (!analysisText) {
      analysisText = JSON.stringify(data, null, 2)
    }

    return Response.json({
      aiAnalysis: analysisText,
      raw: data,
    })
  } catch (err) {
    console.error("[v0] OpenClaw fetch error:", err)
    const message =
      err instanceof Error && err.name === "AbortError"
        ? "Request to OpenClaw timed out after 90 seconds. The service may be busy -- please try again."
        : err instanceof Error
          ? `Failed to connect to OpenClaw: ${err.message}`
          : "Failed to connect to OpenClaw. Please check your API configuration."
    return Response.json({ error: message }, { status: 502 })
  }
}

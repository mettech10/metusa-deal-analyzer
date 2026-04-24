/**
 * POST /api/gdv/calculate
 *
 * Proxies to Flask /api/gdv/calculate. Used by the Property Development
 * strategy's "Auto-Calculate GDV" button to derive per-unit +
 * scheme-level conservative/mid/optimistic sale prices from sold
 * comparables.
 *
 * Body: {
 *   postcode,
 *   units: [{ unitType, numberOfUnits, avgSizeM2 }, ...],
 *   constructionType?
 * }
 *
 * The Flask endpoint never 500s — it returns structured { error,
 * message, comparablesUsed } envelopes on failure, so the UI can show
 * "enter manually" without blocking analysis.
 */
import { NextResponse } from "next/server"

const FLASK_URL =
  process.env.BACKEND_API_URL || "https://metusa-deal-analyzer.onrender.com"

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const { postcode, units } = body || {}

    if (!postcode) {
      return NextResponse.json(
        {
          error: "postcode is required",
          message: "Enter a postcode or set sale prices manually",
          comparablesUsed: 0,
        },
        { status: 400 },
      )
    }
    if (!Array.isArray(units) || units.length === 0) {
      return NextResponse.json(
        {
          error: "units array is required",
          message: "Add at least one unit type before calculating GDV",
          comparablesUsed: 0,
        },
        { status: 400 },
      )
    }

    const resp = await fetch(`${FLASK_URL}/api/gdv/calculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      // Same budget as ARV — Land Registry + postcode widening can be slow.
      signal: AbortSignal.timeout(45_000),
    })

    const data = await resp.json().catch(() => ({
      error: "Invalid JSON from GDV service",
      message: "Auto-GDV unavailable — enter sale prices manually",
      comparablesUsed: 0,
    }))
    return NextResponse.json(data, { status: resp.ok ? 200 : resp.status })
  } catch (error) {
    console.error("[GDV] proxy error:", error)
    return NextResponse.json(
      {
        error: String(error),
        message: "Auto-GDV failed — please enter sale prices manually",
        comparablesUsed: 0,
      },
      { status: 200 },
    )
  }
}

import { NextResponse } from "next/server"

const BACKEND_API_URL = process.env.BACKEND_API_URL || "https://metusa-deal-analyzer.onrender.com"

export async function POST(req: Request) {
  try {
    const body = await req.json()

    const response = await fetch(`${BACKEND_API_URL}/api/sensitivity-analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    })

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(
        { success: false, message: data.message || "Sensitivity analysis failed" },
        { status: response.status }
      )
    }

    return NextResponse.json(data)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Unexpected error"
    console.error("[api/sensitivity-analysis]", msg)
    return NextResponse.json(
      { success: false, message: msg },
      { status: 500 }
    )
  }
}

import { NextResponse } from "next/server"

const BACKEND_URL = (
  process.env.BACKEND_API_URL || "http://localhost:5000"
).replace(/\/$/, "")

export async function POST(request: Request) {
  try {
    const body = await request.json()

    const backendRes = await fetch(`${BACKEND_URL}/api/sensitivity-analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30_000),
    })

    const data = await backendRes.json().catch(() => null)

    if (!backendRes.ok) {
      return NextResponse.json(
        { success: false, message: data?.message || "Sensitivity analysis failed" },
        { status: backendRes.status }
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

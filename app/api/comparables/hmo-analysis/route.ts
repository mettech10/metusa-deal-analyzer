import { NextResponse } from "next/server"

const BACKEND_API_URL = process.env.BACKEND_API_URL || "https://metusa-deal-analyzer.onrender.com"

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const { postcode, listings } = body

    if (!postcode) {
      return NextResponse.json({ success: false, message: "postcode is required" }, { status: 400 })
    }
    if (!listings || !Array.isArray(listings) || listings.length === 0) {
      return NextResponse.json({ success: false, message: "listings array is required" }, { status: 400 })
    }

    const response = await fetch(`${BACKEND_API_URL}/api/hmo-analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ postcode, listings }),
    })

    const data = await response.json()

    if (!response.ok || !data.success) {
      return NextResponse.json(
        { success: false, message: data.message || "HMO analysis failed" },
        { status: response.ok ? 400 : response.status }
      )
    }

    return NextResponse.json({ success: true, analysis: data.analysis })
  } catch {
    return NextResponse.json({ success: false, message: "Error running HMO analysis" }, { status: 500 })
  }
}

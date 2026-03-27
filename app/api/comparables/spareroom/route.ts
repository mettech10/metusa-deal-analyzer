import { NextResponse } from "next/server"

const BACKEND_API_URL = process.env.BACKEND_API_URL || "https://metusa-deal-analyzer.onrender.com"

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const { postcode, maxResults } = body

    if (!postcode) {
      return NextResponse.json(
        { success: false, message: "postcode is required" },
        { status: 400 }
      )
    }

    const response = await fetch(`${BACKEND_API_URL}/api/comparables`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ postcode, maxResults: maxResults || 10 }),
    })

    const data = await response.json()

    if (!response.ok || !data.success) {
      return NextResponse.json(
        { success: false, message: data.message || "Failed to fetch SpareRoom comparables" },
        { status: response.ok ? 400 : response.status }
      )
    }

    return NextResponse.json({
      success: true,
      postcode: data.postcode,
      listings: data.listings || [],
      count: data.count || 0,
    })
  } catch (e) {
    return NextResponse.json(
      { success: false, message: "Error fetching SpareRoom comparables" },
      { status: 500 }
    )
  }
}

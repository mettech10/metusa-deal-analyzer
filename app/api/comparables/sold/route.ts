import { NextResponse } from "next/server"

const FLASK_URL = process.env.FLASK_API_URL || "http://127.0.0.1:5000"

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const { postcode } = body

    if (!postcode) {
      return NextResponse.json(
        { success: false, message: "Postcode is required" },
        { status: 400 }
      )
    }

    // Call Flask backend
    const response = await fetch(`${FLASK_URL}/api/sold-prices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ postcode: postcode.toUpperCase() })
    })

    const data = await response.json()
    
    return NextResponse.json(data)

  } catch (error) {
    console.error("[API] Sold comparables error:", error)
    return NextResponse.json(
      { success: false, message: "Failed to fetch sold prices" },
      { status: 500 }
    )
  }
}

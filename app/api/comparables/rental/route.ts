import { NextResponse } from "next/server"

const FLASK_URL = process.env.BACKEND_API_URL || "https://metusa-deal-analyzer.onrender.com"

export async function POST(req: Request) {
  try {
    const body = await req.json()
    const { postcode, bedrooms } = body

    if (!postcode) {
      return NextResponse.json(
        { success: false, message: "Postcode is required" },
        { status: 400 }
      )
    }

    // Call Flask backend for rental valuation
    const response = await fetch(`${FLASK_URL}/api/propertydata/rental-valuation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        postcode: postcode.toUpperCase(),
        bedrooms: bedrooms || 3
      })
    })

    const data = await response.json()
    
    // Format the response for frontend
    if (data.success && data.data) {
      const estimate = data.data.estimate
      return NextResponse.json({
        success: true,
        data: {
          monthly: estimate?.monthly || 0,
          confidence: data.data.confidence || 'medium',
          range: data.data.range ? {
            low: Math.round(data.data.range.low_weekly * 4.33),
            high: Math.round(data.data.range.high_weekly * 4.33)
          } : undefined
        }
      })
    }
    
    // If PropertyData not configured, return mock/estimated data
    return NextResponse.json({
      success: false,
      message: "Rental data not available - PropertyData API not configured"
    })

  } catch (error) {
    console.error("[API] Rental comparables error:", error)
    return NextResponse.json(
      { success: false, message: "Failed to fetch rental estimates" },
      { status: 500 }
    )
  }
}

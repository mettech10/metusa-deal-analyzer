import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"

// GET /api/portfolio - Get user's portfolio
export async function GET(request: Request) {
  try {
    const supabase = await createClient()
    
    // Get current user
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    
    if (authError || !user) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      )
    }
    
    // Get portfolio properties
    const { data: properties, error } = await supabase
      .from("portfolio_properties")
      .select("*")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
    
    if (error) {
      console.error("Portfolio fetch error:", error)
      return NextResponse.json(
        { error: "Failed to fetch portfolio" },
        { status: 500 }
      )
    }
    
    // Calculate portfolio stats
    const stats = {
      total_properties: properties?.length || 0,
      total_value: properties?.reduce((sum, p) => sum + (p.current_value || 0), 0) || 0,
      total_equity: properties?.reduce((sum, p) => sum + ((p.current_value || 0) - (p.mortgage_balance || 0)), 0) || 0,
      total_monthly_rent: properties?.reduce((sum, p) => sum + (p.monthly_rent || 0), 0) || 0,
      avg_yield: properties?.length 
        ? (properties.reduce((sum, p) => sum + (p.gross_yield || 0), 0) / properties.length)
        : 0,
    }
    
    return NextResponse.json({
      properties: properties || [],
      stats,
    })
    
  } catch (error) {
    console.error("Portfolio API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

// POST /api/portfolio - Add new property
export async function POST(request: Request) {
  try {
    const supabase = await createClient()
    const body = await request.json()
    
    // Get current user
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    
    if (authError || !user) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      )
    }
    
    // Validate required fields
    const required = ["address", "purchase_price", "current_value", "monthly_rent"]
    for (const field of required) {
      if (!body[field]) {
        return NextResponse.json(
          { error: `${field} is required` },
          { status: 400 }
        )
      }
    }
    
    // Calculate derived fields
    const purchasePrice = Number(body.purchase_price)
    const currentValue = Number(body.current_value)
    const monthlyRent = Number(body.monthly_rent)
    const mortgageBalance = Number(body.mortgage_balance || 0)
    
    const grossYield = (monthlyRent * 12) / currentValue * 100
    const equity = currentValue - mortgageBalance
    const equityGain = currentValue - purchasePrice
    const equityGainPercent = ((currentValue - purchasePrice) / purchasePrice) * 100
    
    // Insert property
    const { data: property, error } = await supabase
      .from("portfolio_properties")
      .insert({
        user_id: user.id,
        address: body.address,
        postcode: body.postcode || "",
        property_type: body.property_type || "residential",
        bedrooms: body.bedrooms || null,
        purchase_price: purchasePrice,
        purchase_date: body.purchase_date || null,
        current_value: currentValue,
        monthly_rent: monthlyRent,
        mortgage_balance: mortgageBalance,
        gross_yield: grossYield,
        equity: equity,
        equity_gain: equityGain,
        equity_gain_percent: equityGainPercent,
        notes: body.notes || "",
        status: body.status || "active",
      })
      .select()
      .single()
    
    if (error) {
      console.error("Portfolio insert error:", error)
      return NextResponse.json(
        { error: "Failed to add property" },
        { status: 500 }
      )
    }
    
    return NextResponse.json(
      { property, message: "Property added successfully" },
      { status: 201 }
    )
    
  } catch (error) {
    console.error("Portfolio API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

// PATCH /api/portfolio - Update property
export async function PATCH(request: Request) {
  try {
    const supabase = await createClient()
    const body = await request.json()
    const { id, ...updates } = body
    
    if (!id) {
      return NextResponse.json(
        { error: "Property ID is required" },
        { status: 400 }
      )
    }
    
    // Get current user
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    
    if (authError || !user) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      )
    }
    
    // Recalculate derived fields if values changed
    if (updates.current_value || updates.monthly_rent || updates.mortgage_balance || updates.purchase_price) {
      const { data: existing } = await supabase
        .from("portfolio_properties")
        .select("purchase_price, current_value, monthly_rent, mortgage_balance")
        .eq("id", id)
        .single()
      
      const purchasePrice = Number(updates.purchase_price || existing?.purchase_price || 0)
      const currentValue = Number(updates.current_value || existing?.current_value || 0)
      const monthlyRent = Number(updates.monthly_rent || existing?.monthly_rent || 0)
      const mortgageBalance = Number(updates.mortgage_balance || existing?.mortgage_balance || 0)
      
      updates.gross_yield = (monthlyRent * 12) / currentValue * 100
      updates.equity = currentValue - mortgageBalance
      updates.equity_gain = currentValue - purchasePrice
      updates.equity_gain_percent = ((currentValue - purchasePrice) / purchasePrice) * 100
    }
    
    // Update property
    const { data: property, error } = await supabase
      .from("portfolio_properties")
      .update(updates)
      .eq("id", id)
      .eq("user_id", user.id) // Ensure user owns this property
      .select()
      .single()
    
    if (error) {
      console.error("Portfolio update error:", error)
      return NextResponse.json(
        { error: "Failed to update property" },
        { status: 500 }
      )
    }
    
    return NextResponse.json(
      { property, message: "Property updated successfully" },
      { status: 200 }
    )
    
  } catch (error) {
    console.error("Portfolio API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

// DELETE /api/portfolio - Remove property
export async function DELETE(request: Request) {
  try {
    const supabase = await createClient()
    const { searchParams } = new URL(request.url)
    const id = searchParams.get("id")
    
    if (!id) {
      return NextResponse.json(
        { error: "Property ID is required" },
        { status: 400 }
      )
    }
    
    // Get current user
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    
    if (authError || !user) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      )
    }
    
    // Delete property (only if owned by user)
    const { error } = await supabase
      .from("portfolio_properties")
      .delete()
      .eq("id", id)
      .eq("user_id", user.id)
    
    if (error) {
      console.error("Portfolio delete error:", error)
      return NextResponse.json(
        { error: "Failed to delete property" },
        { status: 500 }
      )
    }
    
    return NextResponse.json(
      { message: "Property deleted successfully" },
      { status: 200 }
    )
    
  } catch (error) {
    console.error("Portfolio API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}
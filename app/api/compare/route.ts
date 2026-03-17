import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"

// POST /api/compare - Compare multiple deals
export async function POST(request: Request) {
  try {
    const supabase = await createClient()
    const body = await request.json()
    const { deals, name } = body
    
    if (!deals || !Array.isArray(deals) || deals.length < 2) {
      return NextResponse.json(
        { error: "At least 2 deals required for comparison" },
        { status: 400 }
      )
    }
    
    if (deals.length > 5) {
      return NextResponse.json(
        { error: "Maximum 5 deals can be compared" },
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
    
    // Calculate comparison metrics
    const comparison = calculateComparison(deals)
    
    // Save comparison if name provided
    if (name) {
      await supabase
        .from("saved_comparisons")
        .insert({
          user_id: user.id,
          name,
          deals,
        })
    }
    
    return NextResponse.json({
      comparison,
      deals,
    })
    
  } catch (error) {
    console.error("Comparison API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

// GET /api/compare - Get saved comparisons
export async function GET(request: Request) {
  try {
    const supabase = await createClient()
    
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    
    if (authError || !user) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      )
    }
    
    const { data: comparisons, error } = await supabase
      .from("saved_comparisons")
      .select("*")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
    
    if (error) {
      console.error("Comparison fetch error:", error)
      return NextResponse.json(
        { error: "Failed to fetch comparisons" },
        { status: 500 }
      )
    }
    
    return NextResponse.json({ comparisons: comparisons || [] })
    
  } catch (error) {
    console.error("Comparison API error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}

// Helper function to calculate comparison metrics
function calculateComparison(deals: any[]) {
  const metrics = {
    best: {
      yield: { deal: null, value: 0 },
      cashflow: { deal: null, value: -Infinity },
      roi: { deal: null, value: 0 },
      score: { deal: null, value: 0 },
      lowest_price: { deal: null, value: Infinity },
    },
    averages: {
      yield: 0,
      cashflow: 0,
      roi: 0,
      score: 0,
      price: 0,
    },
    rankings: [] as any[],
  }
  
  // Calculate bests and averages
  let totalYield = 0
  let totalCashflow = 0
  let totalRoi = 0
  let totalScore = 0
  let totalPrice = 0
  
  for (const deal of deals) {
    const yield_val = deal.gross_yield || 0
    const cashflow = deal.monthly_cashflow || 0
    const roi = deal.roi || 0
    const score = deal.deal_score || 0
    const price = deal.purchase_price || deal.price || 0
    
    // Track bests
    if (yield_val > metrics.best.yield.value) {
      metrics.best.yield = { deal: deal.address || deal.title, value: yield_val }
    }
    if (cashflow > metrics.best.cashflow.value) {
      metrics.best.cashflow = { deal: deal.address || deal.title, value: cashflow }
    }
    if (roi > metrics.best.roi.value) {
      metrics.best.roi = { deal: deal.address || deal.title, value: roi }
    }
    if (score > metrics.best.score.value) {
      metrics.best.score = { deal: deal.address || deal.title, value: score }
    }
    if (price < metrics.best.lowest_price.value && price > 0) {
      metrics.best.lowest_price = { deal: deal.address || deal.title, value: price }
    }
    
    // Accumulate for averages
    totalYield += yield_val
    totalCashflow += cashflow
    totalRoi += roi
    totalScore += score
    totalPrice += price
  }
  
  // Calculate averages
  const count = deals.length
  metrics.averages = {
    yield: Number((totalYield / count).toFixed(2)),
    cashflow: Number((totalCashflow / count).toFixed(2)),
    roi: Number((totalRoi / count).toFixed(2)),
    score: Number((totalScore / count).toFixed(1)),
    price: Number((totalPrice / count).toFixed(0)),
  }
  
  // Create rankings
  metrics.rankings = deals.map(deal => ({
    address: deal.address || deal.title,
    score: deal.deal_score || 0,
    yield: deal.gross_yield || 0,
    cashflow: deal.monthly_cashflow || 0,
    roi: deal.roi || 0,
    price: deal.purchase_price || deal.price || 0,
    verdict: deal.verdict || deal.ai_verdict || 'N/A',
  })).sort((a, b) => b.score - a.score)
  
  return metrics
}
import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"

/**
 * GET /api/stats/deal-count
 * Returns total number of analyses (authenticated users only)
 */
export async function GET(request: Request) {
  try {
    const supabase = await createClient()
    
    // Check if user is authenticated
    const { data: { user }, error: authError } = await supabase.auth.getUser()
    
    if (authError || !user) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      )
    }
    
    // Get count of analyses
    const { count, error } = await supabase
      .from("analyses")
      .select("*", { count: "exact", head: true })
    
    if (error) {
      console.error("[Stats] Database error:", error)
      return NextResponse.json(
        { error: "Failed to fetch stats" },
        { status: 500 }
      )
    }
    
    return NextResponse.json({ 
      total_analyses: count || 0,
      timestamp: new Date().toISOString()
    })
    
  } catch (error) {
    console.error("[Stats] Unexpected error:", error)
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    )
  }
}
import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"

// GET /api/stats/deal-count — public endpoint, no auth required
export async function GET() {
  const supabase = await createClient()

  const { data, error } = await supabase
    .from("global_stats")
    .select("deal_count")
    .eq("id", 1)
    .single()

  if (error || !data) {
    // Fallback so the UI always has something to show
    return NextResponse.json({ count: 10 })
  }

  return NextResponse.json({ count: data.deal_count })
}

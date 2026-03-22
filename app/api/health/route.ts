import { NextResponse } from "next/server"

/**
 * GET /api/health
 * Public health check endpoint - returns minimal status only
 */
export async function GET() {
  // Return minimal public info only
  return NextResponse.json({
    status: "ok",
    timestamp: new Date().toISOString(),
  })
}
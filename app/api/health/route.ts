import { NextResponse } from "next/server"

// Public endpoint for uptime monitoring — returns minimal info only.
export async function GET() {
  return NextResponse.json({ status: "ok" })
}

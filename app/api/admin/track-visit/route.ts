import { NextResponse } from 'next/server'

// Simple in-memory storage (use Redis/DB in production)
let visits: any[] = []
let errors: any[] = []

export async function POST(req: Request) {
  try {
    const data = await req.json()
    
    // Add visit
    visits.push({
      id: Date.now(),
      ...data,
    })
    
    // Keep only last 1000 visits
    if (visits.length > 1000) {
      visits = visits.slice(-1000)
    }
    
    return NextResponse.json({ success: true })
  } catch (error) {
    return NextResponse.json({ error: 'Failed to track' }, { status: 500 })
  }
}

export async function GET() {
  // Calculate stats
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000)
  
  const todayVisits = visits.filter(v => new Date(v.timestamp) >= today).length
  const weekVisits = visits.filter(v => new Date(v.timestamp) >= weekAgo).length
  const totalVisits = visits.length
  
  // Top pages
  const pageCounts: Record<string, number> = {}
  visits.forEach(v => {
    pageCounts[v.page] = (pageCounts[v.page] || 0) + 1
  })
  const topPages = Object.entries(pageCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([page, visits]) => ({ page, visits }))
  
  // Recent activity
  const recentActivity = visits
    .slice(-20)
    .reverse()
    .map(v => ({
      page: v.page,
      time: new Date(v.timestamp).toLocaleTimeString(),
    }))
  
  return NextResponse.json({
    totalVisits,
    todayVisits,
    weekVisits,
    topPages,
    recentActivity,
  })
}
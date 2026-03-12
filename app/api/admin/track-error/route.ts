import { NextResponse } from 'next/server'

// In-memory error storage
let errors: any[] = []

export async function POST(req: Request) {
  try {
    const data = await req.json()
    
    errors.push({
      id: Date.now(),
      ...data,
      resolved: false,
    })
    
    // Keep only last 500 errors
    if (errors.length > 500) {
      errors = errors.slice(-500)
    }
    
    return NextResponse.json({ success: true })
  } catch (error) {
    return NextResponse.json({ error: 'Failed to track' }, { status: 500 })
  }
}

export async function GET() {
  const unresolved = errors.filter(e => !e.resolved).length
  const recentErrors = errors
    .slice(-10)
    .reverse()
    .map(e => ({
      id: e.id,
      message: e.message,
      page: e.page,
      time: new Date(e.timestamp).toLocaleString(),
      resolved: e.resolved,
    }))
  
  return NextResponse.json({
    totalErrors: errors.length,
    unresolvedErrors: unresolved,
    recentErrors,
  })
}
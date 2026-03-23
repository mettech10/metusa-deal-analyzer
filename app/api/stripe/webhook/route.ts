// Stripe webhook temporarily disabled - install 'stripe' package to enable
export async function POST(req: Request) {
  return Response.json({ error: 'Stripe not configured' }, { status: 501 })
}
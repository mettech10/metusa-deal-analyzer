import { createClient } from "@/lib/supabase/server"
import { NextResponse } from "next/server"

// GET /api/analyses/[id] — fetch full saved analysis data for re-loading
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const supabase = await createClient()

  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser()

  if (authError || !user) {
    return NextResponse.json({ error: "Unauthorised" }, { status: 401 })
  }

  const { data, error } = await supabase
    .from("saved_analyses")
    .select("id, address, form_data, results, ai_text, backend_data")
    .eq("id", id)
    .eq("user_id", user.id)
    .single()

  if (error || !data) {
    return NextResponse.json({ error: error?.message || "Not found" }, { status: 404 })
  }

  return NextResponse.json(data)
}

// DELETE /api/analyses/[id] — delete a saved analysis owned by the logged-in user
export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params
  const supabase = await createClient()

  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser()

  if (authError || !user) {
    return NextResponse.json({ error: "Unauthorised" }, { status: 401 })
  }

  const { error } = await supabase
    .from("saved_analyses")
    .delete()
    .eq("id", id)
    .eq("user_id", user.id) // RLS double-check — only delete own records

  if (error) {
    console.error("[DELETE /api/analyses]", error)
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  return new Response(null, { status: 204 })
}

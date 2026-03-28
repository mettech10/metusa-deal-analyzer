import { createClient } from "@supabase/supabase-js"

/**
 * Supabase Admin client — uses the service role key, server-side only.
 * Never import this in client components or expose SUPABASE_SERVICE_ROLE_KEY
 * to the browser.
 *
 * Required env var:
 *   SUPABASE_SERVICE_ROLE_KEY  — from Supabase Dashboard → Settings → API → service_role key
 */
export function createAdminClient() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY

  if (!supabaseUrl) {
    throw new Error("[Supabase Admin] NEXT_PUBLIC_SUPABASE_URL is not set")
  }
  if (!serviceRoleKey) {
    throw new Error("[Supabase Admin] SUPABASE_SERVICE_ROLE_KEY is not set")
  }

  return createClient(supabaseUrl, serviceRoleKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  })
}

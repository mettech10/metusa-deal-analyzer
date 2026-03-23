import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"
import { updateSession } from "@/lib/supabase/proxy"

// Secret key for developer access
const DEV_SECRET = "metalyzi2026"

/** Apply security hardening headers to every outgoing response. */
function addSecurityHeaders(response: NextResponse): NextResponse {
  response.headers.set("X-Content-Type-Options", "nosniff")
  response.headers.set("X-Frame-Options", "DENY")
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin")
  return response
}

export async function proxy(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl

  // Check for dev access key in URL
  const hasDevKey = searchParams.get("dev") === DEV_SECRET

  // If dev key is present, set a cookie and allow access
  if (hasDevKey) {
    const response = await updateSession(request)
    response.cookies.set("dev_access", DEV_SECRET, {
      maxAge: 60 * 60 * 24 * 7, // 7 days
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
    })
    return addSecurityHeaders(response)
  }

  // Check if dev cookie is present
  const devCookie = request.cookies.get("dev_access")?.value
  const hasDevCookie = devCookie === DEV_SECRET

  // Allow list - these paths are always accessible
  const allowedPaths = [
    "/waitlist",
    "/coming-soon",
    "/api/waitlist",
    "/api/auth",
    "/_next",
    "/favicon.ico",
    "/logo.png",
    "/icon.svg",
  ]

  // Check if the current path is allowed
  const isAllowed = allowedPaths.some(
    (path) => pathname === path || pathname.startsWith(path + "/")
  )

  // Allow static files and API routes — but still run updateSession to keep auth fresh
  if (
    pathname.startsWith("/_next/") ||
    pathname.startsWith("/api/") ||
    pathname.startsWith("/static/") ||
    pathname.match(/\.(png|jpg|jpeg|gif|svg|ico|css|js)$/)
  ) {
    return addSecurityHeaders(await updateSession(request))
  }

  // If has dev cookie, allow access to everything (but refresh session)
  if (hasDevCookie) {
    return addSecurityHeaders(await updateSession(request))
  }

  // Redirect to coming-soon if not allowed
  if (!isAllowed) {
    return addSecurityHeaders(
      NextResponse.redirect(new URL("/coming-soon", request.url))
    )
  }

  return addSecurityHeaders(await updateSession(request))
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
}
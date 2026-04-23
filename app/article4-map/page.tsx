"use client"

/**
 * /article4-map — public Article 4 Direction map.
 *
 * The map component pulls from Supabase client-side (anon key + RLS),
 * so no server data-fetching is needed here. We render a small hero +
 * the Leaflet map via dynamic import (ssr:false) because Leaflet relies
 * on `window`.
 */

import dynamic from "next/dynamic"
import Link from "next/link"
import { ArrowLeft, AlertTriangle } from "lucide-react"

const Article4Map = dynamic(
  () => import("@/components/article4/Article4Map"),
  {
    ssr: false,
    loading: () => (
      <div
        style={{
          width: "100%",
          height: 600,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f3f4f6",
          borderRadius: 8,
          color: "#6b7280",
        }}
      >
        Loading map…
      </div>
    ),
  }
)

export default function Article4MapPage() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <Link
          href="/analyse"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to analyse
        </Link>

        <h1 className="text-3xl font-bold tracking-tight">
          UK Article 4 Direction Map
        </h1>
        <p className="mt-2 text-muted-foreground max-w-3xl">
          Article 4 directions remove permitted development rights — most
          commonly, the right to convert a single dwelling (C3) to a small
          HMO (C4) without full planning permission. Check this map before
          buying any HMO conversion project.
        </p>

        <div className="mt-6">
          <Article4Map height={600} />
        </div>

        <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 flex gap-3">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div>
            <strong>Important:</strong> This map is a guide, not a
            substitute for professional planning advice. Coverage is
            approximate (council-level centres, not exact boundaries) and
            directions change. Always verify with the local planning
            authority before making any investment decision.
          </div>
        </div>

        <div className="mt-4 text-xs text-muted-foreground">
          Data sourced from council planning documents. Map tiles &copy;{" "}
          <a
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
          >
            OpenStreetMap
          </a>{" "}
          contributors.
        </div>
      </div>
    </div>
  )
}

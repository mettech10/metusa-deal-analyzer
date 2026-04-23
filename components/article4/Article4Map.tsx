"use client"

/**
 * Article 4 Direction Map
 *
 * Live Leaflet map showing every Article 4 direction in the UK. Pulls
 * data from Supabase via the anon key (RLS allows SELECT). Renders:
 *   - Subject-property marker (optional, blue)
 *   - Council markers coloured by status (red = active, amber = proposed/
 *     consultation, green = none — but we don't render "none")
 *   - Popups with council name, direction type, impact, and planning link
 *   - A collapsible legend + disclaimer
 *   - A postcode search that flies the map to a district's approximate
 *     centre (derived from the first matching area)
 *
 * ⚠ Never imported from a server component. `app/article4-map/page.tsx`
 * loads this via `dynamic(() => …, { ssr: false })` because Leaflet
 * touches `window` at module import time.
 */

import { useEffect, useMemo, useRef, useState } from "react"
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import { createClient } from "@/lib/supabase/client"
import {
  getAllArticle4Areas,
  parsePostcode,
  type Article4Area,
} from "@/lib/article4-service"

// ── Centre of Great Britain, roughly ──────────────────────────────────────
const UK_CENTRE: [number, number] = [53.0, -2.0]
const DEFAULT_ZOOM = 6

// ── Marker icon factory ───────────────────────────────────────────────────
// react-leaflet + default Leaflet icons don't bundle correctly with
// webpack, so we use divIcons (CSS-only) coloured per-status.
function makeIcon(color: string): L.DivIcon {
  return L.divIcon({
    className: "article4-marker",
    html: `<div style="
      width: 22px; height: 22px; border-radius: 50%;
      background: ${color};
      border: 2px solid white;
      box-shadow: 0 1px 4px rgba(0,0,0,0.4);
    "></div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  })
}
const ICONS = {
  active: makeIcon("#dc2626"), // red
  proposed: makeIcon("#f59e0b"), // amber
  consultation: makeIcon("#f59e0b"),
  revoked: makeIcon("#9ca3af"), // grey
  subject: makeIcon("#2563eb"), // blue
}

// ── Helper: fly map when a target changes ─────────────────────────────────
function FlyTo({ target, zoom }: { target: [number, number] | null; zoom: number }) {
  const map = useMap()
  useEffect(() => {
    if (target) {
      map.flyTo(target, zoom, { duration: 1.2 })
    }
  }, [target, zoom, map])
  return null
}

// ── Subject property marker ───────────────────────────────────────────────
export interface SubjectProperty {
  lat: number
  lng: number
  label?: string
}

export interface Article4MapProps {
  subject?: SubjectProperty | null
  height?: number | string
  /** When true, the legend and postcode search are hidden (for small embedded cards). */
  compact?: boolean
}

export default function Article4Map({
  subject = null,
  height = 600,
  compact = false,
}: Article4MapProps) {
  const [areas, setAreas] = useState<Article4Area[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [searchInput, setSearchInput] = useState("")
  const [searchError, setSearchError] = useState<string | null>(null)
  const [flyTarget, setFlyTarget] = useState<[number, number] | null>(
    subject ? [subject.lat, subject.lng] : null
  )
  const [flyZoom, setFlyZoom] = useState<number>(subject ? 13 : DEFAULT_ZOOM)
  const didInit = useRef(false)

  // Fetch all areas on mount.
  useEffect(() => {
    if (didInit.current) return
    didInit.current = true
    let cancelled = false
    ;(async () => {
      try {
        const supabase = createClient()
        const rows = await getAllArticle4Areas(supabase)
        if (!cancelled) setAreas(rows)
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Failed to load")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // If subject changes, fly to it.
  useEffect(() => {
    if (subject) {
      setFlyTarget([subject.lat, subject.lng])
      setFlyZoom(13)
    }
  }, [subject])

  // Postcode search handler.
  const onSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearchError(null)
    const parsed = parsePostcode(searchInput)
    if (!parsed) {
      setSearchError("Enter a valid UK postcode or district (e.g. M14, LS6, OX1).")
      return
    }
    const match = areas.find(
      (a) =>
        (a.postcodeDistricts ?? []).includes(parsed.district) ||
        (parsed.sector &&
          (a.postcodeSectors ?? []).includes(parsed.sector))
    )
    if (!match || match.approximateCenterLat == null || match.approximateCenterLng == null) {
      setSearchError(
        `No Article 4 area found for ${parsed.district}. C3→C4 may be permitted development here — always verify with the council.`
      )
      return
    }
    setFlyTarget([match.approximateCenterLat, match.approximateCenterLng])
    setFlyZoom(12)
  }

  // Filter out areas without coordinates (can't render them).
  const rendered = useMemo(
    () =>
      areas.filter(
        (a) =>
          a.approximateCenterLat != null &&
          a.approximateCenterLng != null &&
          a.status !== "revoked"
      ),
    [areas]
  )

  return (
    <div style={{ position: "relative", width: "100%", height }}>
      {!compact && (
        <div
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            zIndex: 1000,
            background: "white",
            padding: "10px 12px",
            borderRadius: 8,
            boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
            fontSize: 13,
            maxWidth: 280,
          }}
        >
          <form onSubmit={onSearch} style={{ display: "flex", gap: 6 }}>
            <input
              type="text"
              placeholder="Postcode (e.g. M14 5AA)"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              style={{
                flex: 1,
                padding: "6px 8px",
                border: "1px solid #d1d5db",
                borderRadius: 6,
                fontSize: 13,
                outline: "none",
              }}
              aria-label="Postcode"
            />
            <button
              type="submit"
              style={{
                padding: "6px 10px",
                background: "#2563eb",
                color: "white",
                border: "none",
                borderRadius: 6,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Search
            </button>
          </form>
          {searchError && (
            <div style={{ marginTop: 6, color: "#b91c1c", fontSize: 12 }}>
              {searchError}
            </div>
          )}
          <div style={{ marginTop: 10, color: "#6b7280", fontSize: 11, lineHeight: 1.4 }}>
            Markers show approximate council centres — not exact boundary
            geometry. Always verify with the local planning authority.
          </div>
        </div>
      )}

      {!compact && (
        <div
          style={{
            position: "absolute",
            bottom: 24,
            right: 12,
            zIndex: 1000,
            background: "white",
            padding: "10px 12px",
            borderRadius: 8,
            boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
            fontSize: 12,
            minWidth: 170,
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Article 4 status</div>
          <LegendRow color="#dc2626" label="Active (HMO restricted)" />
          <LegendRow color="#f59e0b" label="Proposed / consultation" />
          {subject && <LegendRow color="#2563eb" label="Subject property" />}
          <div style={{ marginTop: 6, color: "#6b7280", fontSize: 11 }}>
            {loading
              ? "Loading areas…"
              : loadError
              ? `Error: ${loadError}`
              : `${rendered.length} areas shown`}
          </div>
        </div>
      )}

      <MapContainer
        center={subject ? [subject.lat, subject.lng] : UK_CENTRE}
        zoom={subject ? 13 : DEFAULT_ZOOM}
        style={{ width: "100%", height: "100%", borderRadius: 8 }}
        scrollWheelZoom={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FlyTo target={flyTarget} zoom={flyZoom} />

        {subject && (
          <Marker
            position={[subject.lat, subject.lng]}
            icon={ICONS.subject}
          >
            <Popup>
              <strong>Subject property</strong>
              {subject.label && (
                <>
                  <br />
                  {subject.label}
                </>
              )}
            </Popup>
          </Marker>
        )}

        {rendered.map((a) => (
          <Marker
            key={a.id}
            position={[a.approximateCenterLat!, a.approximateCenterLng!]}
            icon={ICONS[a.status] ?? ICONS.active}
          >
            <Popup maxWidth={320}>
              <div style={{ fontSize: 13 }}>
                <div style={{ fontWeight: 700, fontSize: 14 }}>
                  {a.councilName}
                </div>
                <div
                  style={{
                    display: "inline-block",
                    marginTop: 4,
                    padding: "2px 8px",
                    borderRadius: 999,
                    fontSize: 11,
                    fontWeight: 600,
                    color: "white",
                    background:
                      a.status === "active"
                        ? "#dc2626"
                        : a.status === "proposed" || a.status === "consultation"
                        ? "#f59e0b"
                        : "#9ca3af",
                  }}
                >
                  {a.status.toUpperCase()}
                </div>
                {a.directionType && (
                  <div style={{ marginTop: 6 }}>
                    <strong>Type:</strong> {a.directionType}
                  </div>
                )}
                {a.impactDescription && (
                  <div style={{ marginTop: 4, color: "#374151" }}>
                    {a.impactDescription}
                  </div>
                )}
                {a.effectiveDate && a.status === "active" && (
                  <div style={{ marginTop: 4, color: "#6b7280", fontSize: 12 }}>
                    Effective: {a.effectiveDate}
                  </div>
                )}
                {a.consultationEndDate &&
                  (a.status === "proposed" || a.status === "consultation") && (
                    <div style={{ marginTop: 4, color: "#6b7280", fontSize: 12 }}>
                      Consultation ends: {a.consultationEndDate}
                    </div>
                  )}
                {(a.postcodeDistricts?.length ?? 0) > 0 && (
                  <div style={{ marginTop: 6, fontSize: 11, color: "#6b7280" }}>
                    Districts: {(a.postcodeDistricts ?? []).join(", ")}
                  </div>
                )}
                {a.councilPlanningUrl && (
                  <div style={{ marginTop: 8 }}>
                    <a
                      href={a.councilPlanningUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: "#2563eb", fontWeight: 600 }}
                    >
                      View council planning page ↗
                    </a>
                  </div>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}

function LegendRow({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
      <span
        style={{
          width: 14,
          height: 14,
          borderRadius: "50%",
          background: color,
          display: "inline-block",
          border: "1.5px solid white",
          boxShadow: "0 1px 2px rgba(0,0,0,0.3)",
        }}
      />
      <span>{label}</span>
    </div>
  )
}

/**
 * Article 4 Direction Lookup Service
 *
 * Queries the article4_areas table for a given postcode (or the full
 * dataset for the Leaflet map) and returns a normalised shape the
 * result card + AI prompt + map component can all consume.
 *
 * Reads go through whichever Supabase client the caller supplies:
 *   - server routes / API routes → createAdminClient()
 *   - client components (the map) → createClient() (browser)
 * Both have SELECT access via the RLS policy defined in
 * supabase/migrations/20260423_article4_areas.sql.
 *
 * All functions fail soft — if the table is missing, the query errors,
 * or the postcode is malformed, the service returns status 'unknown'
 * rather than throwing. The main analysis pipeline must never be
 * blocked by an Article 4 lookup (General Rules).
 */

import type { SupabaseClient } from "@supabase/supabase-js"

// ── Types ─────────────────────────────────────────────────────────────────

export type Article4Status =
  | "active"
  | "proposed"
  | "consultation"
  | "revoked"

export type Article4WarningLevel = "red" | "amber" | "none"

export type Article4CheckStatus =
  | "active"
  | "proposed"
  | "none"
  | "unknown"

/** A single row from article4_areas — camelCase for the frontend. */
export interface Article4Area {
  id: string
  councilName: string
  councilCode: string | null
  region: string | null
  country: string | null
  directionType: string | null
  propertyTypesAffected: string[] | null
  boundaryGeojson: unknown | null
  postcodeDistricts: string[] | null
  postcodeSectors: string[] | null
  approximateCenterLat: number | null
  approximateCenterLng: number | null
  status: Article4Status
  confirmedDate: string | null
  proposedDate: string | null
  consultationEndDate: string | null
  effectiveDate: string | null
  impactDescription: string | null
  planningPortalUrl: string | null
  councilPlanningUrl: string | null
  sourceDocumentUrl: string | null
  verified: boolean
  dataSource: string | null
  lastVerifiedAt: string | null
}

export interface Article4CheckResult {
  isArticle4: boolean
  status: Article4CheckStatus
  areas: Article4Area[]
  warningLevel: Article4WarningLevel
  summary: string
  /** The postcode district we derived from the input (e.g. "M14"). */
  district: string | null
  /** The postcode sector we derived from the input (e.g. "M14 5"). */
  sector: string | null
}

// ── Raw row type (snake_case, direct from Postgres) ───────────────────────

interface Article4Row {
  id: string
  council_name: string
  council_code: string | null
  region: string | null
  country: string | null
  direction_type: string | null
  property_types_affected: string[] | null
  boundary_geojson: unknown | null
  postcode_districts: string[] | null
  postcode_sectors: string[] | null
  approximate_center_lat: number | null
  approximate_center_lng: number | null
  status: string
  confirmed_date: string | null
  proposed_date: string | null
  consultation_end_date: string | null
  effective_date: string | null
  impact_description: string | null
  planning_portal_url: string | null
  council_planning_url: string | null
  source_document_url: string | null
  verified: boolean | null
  data_source: string | null
  last_verified_at: string | null
}

// ── Helpers ───────────────────────────────────────────────────────────────

const ALL_COLUMNS =
  "id,council_name,council_code,region,country,direction_type," +
  "property_types_affected,boundary_geojson,postcode_districts," +
  "postcode_sectors,approximate_center_lat,approximate_center_lng," +
  "status,confirmed_date,proposed_date,consultation_end_date," +
  "effective_date,impact_description,planning_portal_url," +
  "council_planning_url,source_document_url,verified,data_source," +
  "last_verified_at"

function normaliseStatus(s: string): Article4Status {
  const lower = s.toLowerCase()
  if (lower === "active" || lower === "proposed" || lower === "consultation" || lower === "revoked") {
    return lower
  }
  return "active"
}

function toArea(row: Article4Row): Article4Area {
  return {
    id: row.id,
    councilName: row.council_name,
    councilCode: row.council_code,
    region: row.region,
    country: row.country,
    directionType: row.direction_type,
    propertyTypesAffected: row.property_types_affected,
    boundaryGeojson: row.boundary_geojson,
    postcodeDistricts: row.postcode_districts,
    postcodeSectors: row.postcode_sectors,
    approximateCenterLat: row.approximate_center_lat,
    approximateCenterLng: row.approximate_center_lng,
    status: normaliseStatus(row.status),
    confirmedDate: row.confirmed_date,
    proposedDate: row.proposed_date,
    consultationEndDate: row.consultation_end_date,
    effectiveDate: row.effective_date,
    impactDescription: row.impact_description,
    planningPortalUrl: row.planning_portal_url,
    councilPlanningUrl: row.council_planning_url,
    sourceDocumentUrl: row.source_document_url,
    verified: row.verified === true,
    dataSource: row.data_source,
    lastVerifiedAt: row.last_verified_at,
  }
}

/**
 * Extract the outward code (district) and sector from a UK postcode.
 * Accepts loose input like "m14 5aa", "M14  5AA", "M145AA", "M14".
 * Returns { district, sector } with sector possibly null if the input
 * was too short to resolve one.
 */
export function parsePostcode(
  raw: string
): { district: string; sector: string | null } | null {
  if (!raw) return null
  const cleaned = raw.trim().toUpperCase().replace(/\s+/g, "")
  if (!cleaned) return null

  // Outward code regex: 1–2 letters, 1–2 digits, optional trailing letter
  // (handles EC1A, WC2N, M1, M14, SW1A, B3, etc.)
  const match = cleaned.match(/^([A-Z]{1,2}\d[A-Z\d]?)([\d][A-Z]{2})?$/)
  if (!match) return null

  const district = match[1]
  // Sector = district + first digit of the inward code
  const inward = match[2]
  const sector = inward ? `${district} ${inward.charAt(0)}` : null

  return { district, sector }
}

// ── Public API ────────────────────────────────────────────────────────────

/**
 * Check whether a postcode falls within any known Article 4 direction.
 *
 * Match priority (best-match wins):
 *   1. Exact sector match (e.g. "LS6 1")
 *   2. District match (e.g. "LS6")
 *
 * Status precedence when multiple areas match the same postcode:
 *   active > consultation > proposed > revoked
 * So a district that is 'active' takes precedence over a 'proposed'
 * neighbour with the same coverage.
 */
export async function checkArticle4(
  supabase: SupabaseClient,
  postcode: string
): Promise<Article4CheckResult> {
  const parsed = parsePostcode(postcode)
  if (!parsed) {
    return {
      isArticle4: false,
      status: "unknown",
      areas: [],
      warningLevel: "none",
      summary:
        "Article 4 status unknown — postcode could not be parsed. Verify with the local planning authority.",
      district: null,
      sector: null,
    }
  }

  const { district, sector } = parsed

  try {
    // One query covers both district and sector overlap via PostgREST's
    // array `cs` (contains) operator. We prefer an OR so we get rows that
    // match either the sector OR the district.
    const filters: string[] = [`postcode_districts.cs.{${district}}`]
    if (sector) {
      // PostgREST array literal — quote the sector because it contains a space
      filters.push(`postcode_sectors.cs.{"${sector}"}`)
    }
    const { data, error } = await supabase
      .from("article4_areas")
      .select(ALL_COLUMNS)
      .or(filters.join(","))
      .neq("status", "revoked")

    if (error) {
      // Table missing, RLS denied, network — fall through to 'unknown'.
      // Never throw; the caller is the main analysis pipeline.
      console.warn("[article4] lookup failed:", error.message)
      return buildUnknownResult(district, sector)
    }

    const rows = (data ?? []) as unknown as Article4Row[]
    const areas = rows.map(toArea)

    if (areas.length === 0) {
      return {
        isArticle4: false,
        status: "none",
        areas: [],
        warningLevel: "none",
        summary: `No Article 4 direction found for ${district}. C3→C4 HMO conversion may be permitted development — always verify with the local planning authority.`,
        district,
        sector,
      }
    }

    // Pick the "strongest" status across matching areas.
    const hasActive = areas.some((a) => a.status === "active")
    const hasProposed = areas.some(
      (a) => a.status === "proposed" || a.status === "consultation"
    )

    if (hasActive) {
      const primary = areas.find((a) => a.status === "active")!
      return {
        isArticle4: true,
        status: "active",
        areas,
        warningLevel: "red",
        summary: `ARTICLE 4 IN FORCE: ${primary.councilName}${
          primary.directionType ? ` — ${primary.directionType}` : ""
        } — HMO conversion requires full planning permission.`,
        district,
        sector,
      }
    }

    if (hasProposed) {
      const primary = areas.find(
        (a) => a.status === "proposed" || a.status === "consultation"
      )!
      return {
        isArticle4: false,
        status: "proposed",
        areas,
        warningLevel: "amber",
        summary: `ARTICLE 4 PROPOSED: ${primary.councilName} is consulting on a direction that may affect ${district}. Monitor closely — if confirmed, HMO conversion will require planning permission.`,
        district,
        sector,
      }
    }

    // All remaining matches are revoked (filtered above) — treat as none.
    return {
      isArticle4: false,
      status: "none",
      areas,
      warningLevel: "none",
      summary: `No active Article 4 direction for ${district}.`,
      district,
      sector,
    }
  } catch (err) {
    console.warn("[article4] unexpected error:", err)
    return buildUnknownResult(district, sector)
  }
}

function buildUnknownResult(
  district: string,
  sector: string | null
): Article4CheckResult {
  return {
    isArticle4: false,
    status: "unknown",
    areas: [],
    warningLevel: "none",
    summary: `Article 4 status unknown for ${district} — verify with the local planning authority.`,
    district,
    sector,
  }
}

/**
 * Return every Article 4 area for the Leaflet map. Excludes 'revoked'
 * by default (the map is about *current* restrictions). Caller can pass
 * { includeRevoked: true } to see historical directions.
 */
export async function getAllArticle4Areas(
  supabase: SupabaseClient,
  opts: { includeRevoked?: boolean } = {}
): Promise<Article4Area[]> {
  try {
    let query = supabase.from("article4_areas").select(ALL_COLUMNS)
    if (!opts.includeRevoked) {
      query = query.neq("status", "revoked")
    }
    const { data, error } = await query.order("status", { ascending: true })

    if (error) {
      console.warn("[article4] getAll failed:", error.message)
      return []
    }
    return ((data ?? []) as unknown as Article4Row[]).map(toArea)
  } catch (err) {
    console.warn("[article4] getAll unexpected error:", err)
    return []
  }
}

/**
 * All Article 4 directions for a specific council (useful for admin
 * tooling and the detail page). Match is case-insensitive contains.
 */
export async function getArticle4ByCouncil(
  supabase: SupabaseClient,
  councilName: string
): Promise<Article4Area[]> {
  if (!councilName) return []
  try {
    const { data, error } = await supabase
      .from("article4_areas")
      .select(ALL_COLUMNS)
      .ilike("council_name", `%${councilName}%`)
      .order("status", { ascending: true })

    if (error) {
      console.warn("[article4] getByCouncil failed:", error.message)
      return []
    }
    return ((data ?? []) as unknown as Article4Row[]).map(toArea)
  } catch (err) {
    console.warn("[article4] getByCouncil unexpected error:", err)
    return []
  }
}

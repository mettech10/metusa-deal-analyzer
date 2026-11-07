-- Clear the Supabase security advisor warnings from 7 Nov 2026 for Metalyzi.
--
-- 1. SECURITY DEFINER functions that signed-out visitors (anon) could call
--    through /rest/v1/rpc/...: take EXECUTE away from everyone who doesn't
--    need it. The owner (postgres) and service_role keep it.
-- 2. find_sold_comps, find_land_registry_comps and mtd_forbid_pack_mutation:
--    pin search_path to '' and schema-qualify every name in the body.
--
-- Callers checked on 7 Nov 2026 in ~/dealcheck-uk and ~/metusa-deal-analyzer:
--   cleanup_old_scrape_logs, cleanup_propertydata_cache,
--   cleanup_stale_spareroom_listings  -> no callers (no pg_cron, no Edge Functions)
--   increment_deal_count()            -> trigger on saved_analyses only.
--                                        Triggers fire without EXECUTE.
--   increment_deal_count_rpc()        -> /api/stats/increment, signed-in user
--                                        session. Keeps authenticated.
--   mtd_is_org_member(uuid)           -> RLS policies on mtd_* tables (role
--                                        authenticated). Keeps authenticated.
--   mtd_read_share(text)              -> no callers. Public share links go
--                                        through Flask /share/<token> with
--                                        the service key.
--   find_sold_comps                   -> lib/discovery/comps.ts, admin client
--                                        (service role). Grants unchanged.
--   find_land_registry_comps          -> no callers. Grants unchanged.
--
-- Left on purpose (the advisor will still list these):
--   increment_deal_count_rpc and mtd_is_org_member stay callable by
--   signed-in users, as above.
--   spatial_ref_sys RLS, postgis in public and st_estimatedextent belong to
--   the PostGIS extension and can't be changed here.
--   studio_* belongs to Metusa Studio and is not touched.

-- ── 1. EXECUTE grants ────────────────────────────────────────────────────

revoke execute on function public.cleanup_old_scrape_logs() from public, anon, authenticated;
revoke execute on function public.cleanup_propertydata_cache() from public, anon, authenticated;
revoke execute on function public.cleanup_stale_spareroom_listings() from public, anon, authenticated;
grant execute on function public.cleanup_old_scrape_logs() to service_role;
grant execute on function public.cleanup_propertydata_cache() to service_role;
grant execute on function public.cleanup_stale_spareroom_listings() to service_role;

revoke execute on function public.increment_deal_count() from public, anon, authenticated;
grant execute on function public.increment_deal_count() to service_role;

revoke execute on function public.increment_deal_count_rpc() from public, anon;
grant execute on function public.increment_deal_count_rpc() to authenticated, service_role;

revoke execute on function public.mtd_is_org_member(uuid) from public, anon;
grant execute on function public.mtd_is_org_member(uuid) to authenticated, service_role;

revoke execute on function public.mtd_read_share(text) from public, anon, authenticated;
grant execute on function public.mtd_read_share(text) to service_role;

-- ── 2. Fixed search_path ─────────────────────────────────────────────────
-- Same signatures and return types, so CREATE OR REPLACE keeps the existing
-- grants (postgres + service_role only for the two comps functions).
-- PostGIS lives in public, so its functions and types are public.-qualified.

create or replace function public.find_sold_comps(
  p_lat double precision,
  p_lng double precision,
  p_radius_m integer default 1600,
  p_min_beds integer default null::integer,
  p_max_beds integer default null::integer,
  p_property_type text default null::text,
  p_months integer default 24,
  p_limit integer default 30
)
returns table(
  sale_id uuid,
  property_id uuid,
  canonical_address text,
  postcode character varying,
  distance_m double precision,
  sold_price numeric,
  sold_date date,
  bedrooms integer,
  property_type character varying,
  floor_area_sqft numeric,
  source character varying
)
language sql
stable
set search_path = ''
as $function$
  SELECT
    s.id,
    p.id,
    p.canonical_address,
    p.postcode,
    public.ST_Distance(p.geog, public.ST_SetSRID(public.ST_MakePoint(p_lng, p_lat), 4326)::public.geography) AS distance_m,
    s.sold_price,
    s.sold_date,
    s.bedrooms,
    s.property_type,
    s.floor_area_sqft,
    s.source
  FROM public.property_sales s
  JOIN public.properties p ON p.id = s.property_id
  WHERE p.geog IS NOT NULL
    AND public.ST_DWithin(p.geog, public.ST_SetSRID(public.ST_MakePoint(p_lng, p_lat), 4326)::public.geography, p_radius_m)
    AND s.sold_date >= (CURRENT_DATE - (p_months || ' months')::interval)
    AND (p_min_beds IS NULL OR s.bedrooms IS NULL OR s.bedrooms >= p_min_beds)
    AND (p_max_beds IS NULL OR s.bedrooms IS NULL OR s.bedrooms <= p_max_beds)
    AND (
      p_property_type IS NULL
      OR s.property_type IS NULL
      OR lower(s.property_type) LIKE '%' || lower(p_property_type) || '%'
    )
    AND s.sold_price > 0
  ORDER BY distance_m ASC, s.sold_date DESC
  LIMIT p_limit;
$function$;

create or replace function public.find_land_registry_comps(
  p_lat double precision,
  p_lng double precision,
  p_radius_m integer default 1600,
  p_property_type text default null::text,
  p_months integer default 24,
  p_limit integer default 40
)
returns table(
  sale_id uuid,
  canonical_address text,
  postcode character varying,
  distance_m double precision,
  sold_price numeric,
  sold_date date,
  property_type character,
  source text
)
language sql
stable
set search_path = ''
as $function$
  SELECT
    s.id,
    NULLIF(TRIM(CONCAT_WS(' ', s.saon, s.paon, s.street)), '') AS canonical_address,
    s.postcode,
    public.ST_Distance(g.geog, public.ST_SetSRID(public.ST_MakePoint(p_lng, p_lat), 4326)::public.geography) AS distance_m,
    s.price,
    s.sold_date,
    s.property_type,
    'land_registry'::text
  FROM public.land_registry_sales s
  JOIN public.postcode_geo g ON g.postcode = s.postcode
  WHERE g.geog IS NOT NULL
    AND public.ST_DWithin(g.geog, public.ST_SetSRID(public.ST_MakePoint(p_lng, p_lat), 4326)::public.geography, p_radius_m)
    AND s.sold_date >= (CURRENT_DATE - (p_months || ' months')::interval)
    AND (p_property_type IS NULL OR s.property_type = p_property_type)
    AND s.price > 0
    AND (s.ppd_category IS NULL OR s.ppd_category = 'A')
  ORDER BY distance_m ASC, s.sold_date DESC
  LIMIT p_limit;
$function$;

-- Body only raises an exception and names no objects.
alter function public.mtd_forbid_pack_mutation() set search_path = '';

notify pgrst, 'reload schema';

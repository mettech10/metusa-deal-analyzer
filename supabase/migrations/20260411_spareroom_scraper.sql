-- ──────────────────────────────────────────────────────────────────────────────
-- Migration: SpareRoom scraper tables (Bright Data Browser API)
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run
--
-- Replaces the Apify memo23/spareroom-scraper actor. Two tables:
--   spareroom_listings — canonical room-listing cache, upserted on listing_id
--   scrape_logs        — per-run audit log used for the 13-day skip check
--
-- Both tables are written to exclusively by the service-role key from the
-- Python Flask backend (metusa-deal-analyzer). RLS is enabled but there are
-- no public-read policies — data is only exposed via the Flask endpoints.
-- ──────────────────────────────────────────────────────────────────────────────

-- ── spareroom_listings ───────────────────────────────────────────────────────
create table if not exists public.spareroom_listings (
  id                bigserial primary key,
  listing_id        text not null,
  location          text not null,
  title             text,
  rent_pcm          integer,
  room_type         text,        -- 'single' | 'double' | 'en-suite' | 'studio'
  bills_included    boolean,
  area              text,
  available_from    text,
  number_of_rooms   integer,
  listing_url       text,
  image_url         text,
  scraped_at        timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  constraint spareroom_listings_listing_id_unique unique (listing_id)
);

-- Lookups by location for the /api/comparables endpoint and cache reads
create index if not exists spareroom_listings_location_idx
  on public.spareroom_listings (location);

-- Recency queries for the bulk skip check and health dashboards
create index if not exists spareroom_listings_scraped_at_idx
  on public.spareroom_listings (scraped_at desc);

-- Sanity constraint: rent must be positive if set
alter table public.spareroom_listings
  drop constraint if exists spareroom_listings_rent_positive;
alter table public.spareroom_listings
  add constraint spareroom_listings_rent_positive
  check (rent_pcm is null or rent_pcm > 0);

-- ── scrape_logs ──────────────────────────────────────────────────────────────
create table if not exists public.scrape_logs (
  id              bigserial primary key,
  run_id          text not null,            -- timestamp-based run identifier
  location        text not null,
  status          text not null,            -- 'ok' | 'error' | 'skipped'
  listings_found  integer not null default 0,
  error_message   text,
  scraped_at      timestamptz not null default now()
);

-- The bulk scraper queries scrape_logs by (location, status, scraped_at) for
-- the 13-day skip check. This composite index covers that path directly.
create index if not exists scrape_logs_location_status_time_idx
  on public.scrape_logs (location, status, scraped_at desc);

-- Per-run reporting
create index if not exists scrape_logs_run_id_idx
  on public.scrape_logs (run_id);

-- ── Row Level Security ───────────────────────────────────────────────────────
alter table public.spareroom_listings enable row level security;
alter table public.scrape_logs        enable row level security;

-- Service role bypasses RLS automatically; we add an explicit policy for
-- clarity and to document intent. No anon/authenticated policies — the
-- Flask backend is the only reader/writer.
drop policy if exists "Service role full access to spareroom_listings"
  on public.spareroom_listings;
create policy "Service role full access to spareroom_listings"
  on public.spareroom_listings
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists "Service role full access to scrape_logs"
  on public.scrape_logs;
create policy "Service role full access to scrape_logs"
  on public.scrape_logs
  for all
  to service_role
  using (true)
  with check (true);

-- ── Cleanup helper (optional, call from cron) ────────────────────────────────
-- Removes stale listings older than 30 days. Keeps the cache fresh without
-- requiring a DELETE on every bulk run.
create or replace function public.cleanup_stale_spareroom_listings()
  returns integer
  language plpgsql
  security definer
as $$
declare
  deleted_count integer;
begin
  delete from public.spareroom_listings
  where scraped_at < now() - interval '30 days';
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

-- Trim scrape_logs to the last 90 days so it doesn't grow unbounded
create or replace function public.cleanup_old_scrape_logs()
  returns integer
  language plpgsql
  security definer
as $$
declare
  deleted_count integer;
begin
  delete from public.scrape_logs
  where scraped_at < now() - interval '90 days';
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

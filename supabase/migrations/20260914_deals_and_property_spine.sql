-- Screener → Analyser handoff + shared property spine.
--
-- Sibling features (MTD, compliance, ltd co, licensing) should key off
-- properties.id. This migration is additive and safe to run against a
-- database that already has the Discovery `properties` table
-- (dealcheck-uk/supabase/migrations/20260817_discovery_pipeline_layers.sql):
-- CREATE TABLE IF NOT EXISTS is a no-op when that table is present.
--
-- Intentionally no PostGIS / geog column here — Discovery already owns that
-- enrichment. Fresh backends get a minimal identity table.

CREATE TABLE IF NOT EXISTS public.properties (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  property_key TEXT NOT NULL UNIQUE,
  canonical_address TEXT NOT NULL,
  postcode VARCHAR(10),
  postcode_district VARCHAR(10),
  property_type VARCHAR(50),
  bedrooms INTEGER,
  bathrooms INTEGER,
  tenure VARCHAR(30),
  first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_properties_postcode
  ON public.properties (postcode, status);

CREATE INDEX IF NOT EXISTS idx_properties_district
  ON public.properties (postcode_district, status);

-- User-scoped screener (and future) deals. One row per handoff; idempotent
-- retries reuse the same id via (user_id, idempotency_key).
CREATE TABLE IF NOT EXISTS public.deals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  property_id UUID REFERENCES public.properties(id) ON DELETE SET NULL,

  source TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1,
  strategy TEXT,
  rent_pcm_gbp NUMERIC(12,2),
  listing JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'created',

  idempotency_key TEXT,
  source_listing_id TEXT,
  listing_source TEXT,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT deals_source_check CHECK (source IN ('screener')),
  CONSTRAINT deals_strategy_check CHECK (
    strategy IS NULL OR strategy IN ('btl', 'hmo', 'brrrr', 'flip', 'sa', 'development')
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS deals_user_idempotency_idx
  ON public.deals (user_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS deals_property_id_idx
  ON public.deals (property_id);

CREATE INDEX IF NOT EXISTS deals_user_created_idx
  ON public.deals (user_id, created_at DESC);

ALTER TABLE public.properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.deals ENABLE ROW LEVEL SECURITY;

-- Canonical properties are a shared spine; user-facing reads go through deals.
-- Flask uses the service role key and bypasses RLS.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'deals' AND policyname = 'Users can view own deals'
  ) THEN
    CREATE POLICY "Users can view own deals"
      ON public.deals FOR SELECT
      USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'deals' AND policyname = 'Users can insert own deals'
  ) THEN
    CREATE POLICY "Users can insert own deals"
      ON public.deals FOR INSERT
      WITH CHECK (auth.uid() = user_id);
  END IF;
END $$;

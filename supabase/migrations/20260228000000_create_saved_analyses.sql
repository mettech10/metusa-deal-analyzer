-- ──────────────────────────────────────────────────────────────────────────────
-- Migration: create saved_analyses table
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run
-- ──────────────────────────────────────────────────────────────────────────────

create table if not exists public.saved_analyses (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  created_at      timestamptz not null default now(),

  -- Summary columns (shown on the Recent Deals cards)
  address         text not null,
  postcode        text,
  investment_type text not null default 'btl',
  purchase_price  numeric(12,2),
  deal_score      integer,
  monthly_cashflow  numeric(10,2),
  annual_cashflow   numeric(10,2),
  gross_yield       numeric(6,2),

  -- Full data for future "reload this deal" feature
  form_data       jsonb,
  results         jsonb,
  ai_text         text
);

-- Index for fast user-scoped lookups ordered by recency
create index if not exists saved_analyses_user_id_created_at_idx
  on public.saved_analyses (user_id, created_at desc);

-- ── Row Level Security ───────────────────────────────────────────────────────
alter table public.saved_analyses enable row level security;

-- Users can only read their own analyses
create policy "Users can view own analyses"
  on public.saved_analyses
  for select
  using (auth.uid() = user_id);

-- Users can only insert analyses linked to themselves
create policy "Users can insert own analyses"
  on public.saved_analyses
  for insert
  with check (auth.uid() = user_id);

-- Users can only delete their own analyses
create policy "Users can delete own analyses"
  on public.saved_analyses
  for delete
  using (auth.uid() = user_id);

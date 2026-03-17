-- ──────────────────────────────────────────────────────────────────────────────
-- Migration: create global_stats table for real-time deal counter
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run
-- ──────────────────────────────────────────────────────────────────────────────

-- Global stats table (single row, id always = 1)
create table if not exists public.global_stats (
  id          integer primary key default 1,
  deal_count  integer not null default 10,
  updated_at  timestamptz not null default now()
);

-- Ensure only one row can ever exist
alter table public.global_stats
  add constraint single_row check (id = 1);

-- Seed with initial count of 10
insert into public.global_stats (id, deal_count)
  values (1, 10)
  on conflict (id) do nothing;

-- ── Row Level Security ────────────────────────────────────────────────────────
alter table public.global_stats enable row level security;

-- Anyone (including unauthenticated visitors) can read the counter
create policy "Public read global stats"
  on public.global_stats
  for select
  using (true);

-- ── Auto-increment trigger ────────────────────────────────────────────────────
-- Fires after each new analysis is saved and bumps the counter
create or replace function public.increment_deal_count()
  returns trigger
  language plpgsql
  security definer
as $$
begin
  insert into public.global_stats (id, deal_count, updated_at)
    values (1, 1, now())
    on conflict (id) do update
      set deal_count = global_stats.deal_count + 1,
          updated_at = now();
  return new;
end;
$$;

create trigger on_analysis_saved
  after insert on public.saved_analyses
  for each row
  execute function public.increment_deal_count();

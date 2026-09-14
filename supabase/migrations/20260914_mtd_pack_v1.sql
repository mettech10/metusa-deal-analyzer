-- Metalyzi MTD Pack v1
-- Org-scoped property-business records, SA105-aligned ledger, immutable
-- quarter packs, expiring share links. No HMRC submit. No Open Banking.

create table if not exists public.mtd_organisations (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_by  uuid not null references auth.users(id) on delete restrict,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.mtd_org_members (
  org_id      uuid not null references public.mtd_organisations(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  role        text not null check (role in ('owner', 'admin', 'member')),
  email       text,
  created_at  timestamptz not null default now(),
  primary key (org_id, user_id)
);

create index if not exists mtd_org_members_user_id_idx on public.mtd_org_members (user_id);

create table if not exists public.mtd_property_businesses (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references public.mtd_organisations(id) on delete cascade,
  name            text not null,
  tax_year_start  date not null default '2026-04-06',
  basis           text not null default 'standard' check (basis in ('standard', 'calendar')),
  country         text not null default 'uk',
  status          text not null default 'active' check (status in ('active', 'archived')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists mtd_property_businesses_org_idx
  on public.mtd_property_businesses (org_id, created_at desc);

create table if not exists public.mtd_properties (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references public.mtd_organisations(id) on delete cascade,
  business_id     uuid not null references public.mtd_property_businesses(id) on delete cascade,
  property_id     uuid references public.portfolio_properties(id) on delete set null,
  label           text not null,
  address         text,
  postcode        text,
  occupancy_type  text not null default 'residential'
                    check (occupancy_type in ('residential', 'non_residential', 'mixed')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists mtd_properties_business_idx
  on public.mtd_properties (org_id, business_id);

create table if not exists public.mtd_categories (
  code                    text primary key,
  name                    text not null,
  kind                    text not null check (kind in (
                            'income', 'expense', 'residential_finance',
                            'income_adjustment', 'adjustment'
                          )),
  sa105_box               text,
  hmrc_field              text,
  is_residential_finance  boolean not null default false,
  aliases                 text[] not null default '{}',
  sort_order              integer not null default 0
);

create table if not exists public.mtd_ledger_entries (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references public.mtd_organisations(id) on delete cascade,
  business_id     uuid not null references public.mtd_property_businesses(id) on delete cascade,
  property_id     uuid references public.mtd_properties(id) on delete set null,
  entry_date      date not null,
  amount_pence    integer not null,
  category_code   text not null references public.mtd_categories(code),
  description     text,
  counterparty    text,
  source          text not null check (source in ('manual', 'csv')),
  source_ref      text,
  fingerprint     text not null,
  created_by      uuid not null references auth.users(id),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  voided_at       timestamptz
);

create unique index if not exists mtd_ledger_entries_fingerprint_uidx
  on public.mtd_ledger_entries (org_id, fingerprint)
  where voided_at is null;

create index if not exists mtd_ledger_entries_business_date_idx
  on public.mtd_ledger_entries (org_id, business_id, entry_date);

create table if not exists public.mtd_csv_imports (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references public.mtd_organisations(id) on delete cascade,
  business_id      uuid not null references public.mtd_property_businesses(id) on delete cascade,
  filename         text not null,
  content_sha256   text not null,
  status           text not null check (status in ('preview', 'committed')),
  row_count        integer not null default 0,
  created_count    integer not null default 0,
  skipped_count    integer not null default 0,
  created_by       uuid not null references auth.users(id),
  created_at       timestamptz not null default now(),
  committed_at     timestamptz
);

create unique index if not exists mtd_csv_imports_hash_committed_uidx
  on public.mtd_csv_imports (org_id, business_id, content_sha256)
  where status = 'committed';

create table if not exists public.mtd_quarter_packs (
  id              uuid primary key default gen_random_uuid(),
  org_id          uuid not null references public.mtd_organisations(id) on delete cascade,
  business_id     uuid not null references public.mtd_property_businesses(id) on delete cascade,
  tax_year        text not null,
  quarter         integer not null check (quarter between 1 and 4),
  basis           text not null check (basis in ('standard', 'calendar')),
  period_start    date not null,
  period_end      date not null,
  snapshot        jsonb not null,
  created_by      uuid not null references auth.users(id),
  created_at      timestamptz not null default now(),
  unique (org_id, business_id, tax_year, quarter, basis)
);

create table if not exists public.mtd_share_links (
  id           uuid primary key default gen_random_uuid(),
  org_id       uuid not null references public.mtd_organisations(id) on delete cascade,
  pack_id      uuid not null references public.mtd_quarter_packs(id) on delete cascade,
  token_hash   text not null unique,
  expires_at   timestamptz not null,
  created_by   uuid not null references auth.users(id),
  created_at   timestamptz not null default now(),
  revoked_at   timestamptz
);

create index if not exists mtd_share_links_token_idx on public.mtd_share_links (token_hash);

-- ── Category seed (SA105-aligned; residential finance kept separate) ─
insert into public.mtd_categories
  (code, name, kind, sa105_box, hmrc_field, is_residential_finance, aliases, sort_order)
values
  ('uk_rent_income', 'Rents and other income from UK property', 'income', '20', 'income.periodAmount', false, array['rent','rents','rental income','box 20'], 10),
  ('tax_taken_off', 'Tax taken off any income', 'income_adjustment', '21', 'income.taxDeducted', false, array['tax deducted','box 21'], 20),
  ('lease_premiums', 'Premiums for the grant of a lease', 'income', '22', 'income.premiumsOfLeaseGrant', false, array['lease premium','box 22'], 30),
  ('reverse_premiums', 'Reverse premiums and inducements', 'income', '23', 'income.reversePremiums', false, array['reverse premium','box 23'], 40),
  ('other_property_income', 'Other property income', 'income', '20', 'income.otherIncome', false, array['other income'], 50),
  ('rent_a_room', 'Rent a Room receipts', 'income', '38', 'income.rentARoom.rentsReceived', false, array['rent a room'], 60),
  ('premises_running_costs', 'Rent, rates, insurance and ground rents', 'expense', '24', 'expenses.premisesRunningCosts', false, array['insurance','ground rent','rates','box 24'], 70),
  ('repairs_and_maintenance', 'Property repairs and maintenance', 'expense', '25', 'expenses.repairsAndMaintenance', false, array['repairs','maintenance','box 25'], 80),
  ('non_residential_finance_costs', 'Loan interest and other financial costs (non-residential)', 'expense', '26', 'expenses.financialCosts', false, array['commercial finance','box 26'], 90),
  ('professional_fees', 'Legal, management and other professional fees', 'expense', '27', 'expenses.professionalFees', false, array['legal','management fees','box 27'], 100),
  ('cost_of_services', 'Costs of services provided, including wages', 'expense', '28', 'expenses.costOfServices', false, array['wages','services','box 28'], 110),
  ('travel_costs', 'Travel costs', 'expense', '29', 'expenses.travelCosts', false, array['travel','mileage'], 120),
  ('other_allowable_expenses', 'Other allowable property expenses', 'expense', '29', 'expenses.other', false, array['other','box 29'], 130),
  ('replacing_domestic_items', 'Costs of replacing domestic items', 'expense', '37', 'expenses.other', false, array['domestic items','box 37'], 140),
  ('residential_finance_costs', 'Residential finance costs', 'residential_finance', '44', 'expenses.residentialFinancialCost', true, array['mortgage interest','residential finance','box 44'], 150),
  ('residential_finance_costs_bf', 'Unused residential finance costs brought forward', 'residential_finance', '45', 'expenses.residentialFinancialCostsCarriedForward', true, array['finance brought forward','box 45'], 160),
  ('private_use_adjustment', 'Private use adjustment', 'adjustment', '30', null, false, array['private use','box 30'], 170)
on conflict (code) do update set
  name = excluded.name,
  kind = excluded.kind,
  sa105_box = excluded.sa105_box,
  hmrc_field = excluded.hmrc_field,
  is_residential_finance = excluded.is_residential_finance,
  aliases = excluded.aliases,
  sort_order = excluded.sort_order;

-- ── Membership helper ────────────────────────────────────────────────
create or replace function public.mtd_is_org_member(p_org_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.mtd_org_members m
    where m.org_id = p_org_id
      and m.user_id = auth.uid()
  );
$$;

revoke all on function public.mtd_is_org_member(uuid) from public;
grant execute on function public.mtd_is_org_member(uuid) to authenticated;

-- Readonly share access (token hash, not raw token)
create or replace function public.mtd_read_share(p_token_hash text)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  rec record;
begin
  select s.id, s.pack_id, s.expires_at, s.revoked_at, p.snapshot, p.tax_year, p.quarter, p.basis,
         p.period_start, p.period_end, p.business_id, p.org_id, p.created_at as pack_created_at
    into rec
  from public.mtd_share_links s
  join public.mtd_quarter_packs p on p.id = s.pack_id
  where s.token_hash = p_token_hash;

  if rec.id is null then
    return null;
  end if;
  if rec.revoked_at is not null then
    return null;
  end if;
  if rec.expires_at <= now() then
    raise exception 'share link has expired' using errcode = 'P0001';
  end if;

  return jsonb_build_object(
    'readonly', true,
    'immutable', true,
    'hmrcSubmit', false,
    'packId', rec.pack_id,
    'taxYear', rec.tax_year,
    'quarter', rec.quarter,
    'basis', rec.basis,
    'periodStart', rec.period_start,
    'periodEnd', rec.period_end,
    'snapshot', rec.snapshot
  );
end;
$$;

revoke all on function public.mtd_read_share(text) from public;
grant execute on function public.mtd_read_share(text) to anon, authenticated;

-- Forbid mutating immutable quarter packs
create or replace function public.mtd_forbid_pack_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'mtd_quarter_packs are immutable';
end;
$$;

drop trigger if exists mtd_quarter_packs_immutable on public.mtd_quarter_packs;
create trigger mtd_quarter_packs_immutable
  before update or delete on public.mtd_quarter_packs
  for each row execute procedure public.mtd_forbid_pack_mutation();

-- ── RLS ──────────────────────────────────────────────────────────────
alter table public.mtd_organisations enable row level security;
alter table public.mtd_org_members enable row level security;
alter table public.mtd_property_businesses enable row level security;
alter table public.mtd_properties enable row level security;
alter table public.mtd_categories enable row level security;
alter table public.mtd_ledger_entries enable row level security;
alter table public.mtd_csv_imports enable row level security;
alter table public.mtd_quarter_packs enable row level security;
alter table public.mtd_share_links enable row level security;

create policy "mtd_categories_read"
  on public.mtd_categories for select
  to authenticated
  using (true);

create policy "mtd_orgs_select"
  on public.mtd_organisations for select
  to authenticated
  using (public.mtd_is_org_member(id));

create policy "mtd_orgs_insert"
  on public.mtd_organisations for insert
  to authenticated
  with check (created_by = auth.uid());

create policy "mtd_orgs_update"
  on public.mtd_organisations for update
  to authenticated
  using (public.mtd_is_org_member(id));

create policy "mtd_members_select"
  on public.mtd_org_members for select
  to authenticated
  using (user_id = auth.uid() or public.mtd_is_org_member(org_id));

create policy "mtd_members_insert"
  on public.mtd_org_members for insert
  to authenticated
  with check (
    user_id = auth.uid()
    or public.mtd_is_org_member(org_id)
  );

create policy "mtd_biz_all"
  on public.mtd_property_businesses for all
  to authenticated
  using (public.mtd_is_org_member(org_id))
  with check (public.mtd_is_org_member(org_id));

create policy "mtd_props_all"
  on public.mtd_properties for all
  to authenticated
  using (public.mtd_is_org_member(org_id))
  with check (public.mtd_is_org_member(org_id));

create policy "mtd_ledger_all"
  on public.mtd_ledger_entries for all
  to authenticated
  using (public.mtd_is_org_member(org_id))
  with check (public.mtd_is_org_member(org_id));

create policy "mtd_imports_all"
  on public.mtd_csv_imports for all
  to authenticated
  using (public.mtd_is_org_member(org_id))
  with check (public.mtd_is_org_member(org_id));

create policy "mtd_packs_select"
  on public.mtd_quarter_packs for select
  to authenticated
  using (public.mtd_is_org_member(org_id));

create policy "mtd_packs_insert"
  on public.mtd_quarter_packs for insert
  to authenticated
  with check (public.mtd_is_org_member(org_id));

create policy "mtd_shares_all"
  on public.mtd_share_links for all
  to authenticated
  using (public.mtd_is_org_member(org_id))
  with check (public.mtd_is_org_member(org_id));

comment on table public.mtd_quarter_packs is
  'Immutable MTD quarter snapshots. Not an HMRC submission.';
comment on column public.mtd_ledger_entries.amount_pence is
  'Integer pence. Never store pounds as float.';
comment on column public.mtd_ledger_entries.source is
  'manual or csv. Open Banking is out of scope for v1.';
comment on column public.mtd_properties.property_id is
  'Optional link to portfolio_properties.id';

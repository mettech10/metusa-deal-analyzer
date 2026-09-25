-- Persist applicability on compliance obligation instances.
-- Run order (after the table exists; safe to re-run):
--   1. supabase/migrations/20260914_compliance_cockpit.sql
--   2. supabase/migrations/20260921_compliance_cockpit_grants.sql
--   3. this file
--
-- Stored values: required | not_applicable | unknown.
-- The API alias "applicable" is persisted as "required". Existing rows
-- default to required, so they stay applicable. Do not default the column
-- to the literal 'applicable' — the check constraint rejects it.
-- GAS not_applicable still requires a reason in Flask.
--
-- Live-DB safety:
--   * ADD COLUMN IF NOT EXISTS ... NOT NULL DEFAULT <constant> is metadata-only
--     on PostgreSQL 11+ (Supabase is 15). No table rewrite. Existing rows
--     read the default from pg_attribute. One ALTER takes a brief
--     ACCESS EXCLUSIVE lock (catalog update only).
--   * The CHECK is added only when missing, scoped to this table. Every
--     existing row is already 'required' via the default, so validation
--     is a short scan of a small MVP table.
--   * RLS policies are row predicates (auth.uid() = user_id), not column
--     lists. Table GRANTs from 20260921 already cover new columns. This
--     file does not recreate policies or re-issue grants.
--   * NOTIFY reloads the PostgREST schema cache. Until this migration
--     runs, writes that send applicability return HTTP 503
--     compliance_store_unavailable (not 500). Reads keep working.

alter table public.compliance_obligations
  add column if not exists applicability text not null default 'required',
  add column if not exists applicability_reason text not null default '';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'compliance_obligations_applicability_check'
      and conrelid = 'public.compliance_obligations'::regclass
  ) then
    alter table public.compliance_obligations
      add constraint compliance_obligations_applicability_check
      check (applicability in ('required', 'not_applicable', 'unknown'));
  end if;
end $$;

comment on column public.compliance_obligations.applicability is
  'required | not_applicable | unknown. API alias applicable is stored as required. unknown = check with the council (licences).';
comment on column public.compliance_obligations.applicability_reason is
  'Required when GAS is not_applicable (e.g. no gas supply).';

notify pgrst, 'reload schema';

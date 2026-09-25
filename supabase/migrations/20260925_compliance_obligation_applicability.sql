-- Persist applicability on compliance obligation instances.
-- required | not_applicable | unknown. GAS N/A is enforced in Flask
-- (reason required). Reminders must not fire for not_applicable rows.

alter table public.compliance_obligations
  add column if not exists applicability text not null default 'required';

alter table public.compliance_obligations
  add column if not exists applicability_reason text not null default '';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'compliance_obligations_applicability_check'
  ) then
    alter table public.compliance_obligations
      add constraint compliance_obligations_applicability_check
      check (applicability in ('required', 'not_applicable', 'unknown'));
  end if;
end $$;

comment on column public.compliance_obligations.applicability is
  'required | not_applicable | unknown. unknown = check with the council (licences).';
comment on column public.compliance_obligations.applicability_reason is
  'Required when GAS is not_applicable (e.g. no gas supply).';

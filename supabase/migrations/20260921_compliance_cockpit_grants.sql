-- Repair grants + PostgREST schema cache for Compliance Cockpit tables.
-- Requires 20260914_compliance_cockpit.sql (tables) to already exist.
-- Flask uses the service role; authenticated is for user-JWT PostgREST.

grant select, insert, update, delete on table public.compliance_obligations to authenticated, service_role;
grant select, insert, update, delete on table public.compliance_reminders to authenticated, service_role;
grant select, insert, update, delete on table public.compliance_evidence to authenticated, service_role;

notify pgrst, 'reload schema';

-- Compliance Cockpit catalogue 2026: Renters' Rights Act and other gaps.
-- Adds smoke/CO alarms, Right to Rent, written statement of terms, the RRA
-- Information Sheet, EPC C by 2030 and PRS Database registration.
-- HTR stays for records of tenancies that began before 1 May 2026.
alter table public.compliance_obligations
  drop constraint if exists compliance_obligations_code_check;

alter table public.compliance_obligations
  add constraint compliance_obligations_code_check check (code in (
    'GAS', 'EICR', 'EPC', 'DEP', 'HTR', 'LIC_HMO', 'LIC_SEL',
    'SMOKE_CO', 'RTR', 'TERMS', 'RRA_INFO', 'EPC_2030', 'PRS_DB'
  ));

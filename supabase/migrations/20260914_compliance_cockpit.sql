-- Metalyzi Compliance Cockpit MVP
-- ObligationInstance + reminder stubs + evidence metadata.
-- property_id is a free-form UUID so it can point at portfolio_properties.id
-- (or any other property record) without a hard FK.
-- Licensing geo / Screener / MTD / Ltd Co are intentionally not modelled.

create table if not exists public.compliance_obligations (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  property_id   uuid not null,
  code          text not null check (code in ('GAS','EICR','EPC','DEP','HTR','LIC_HMO','LIC_SEL')),
  issued_on     date,
  expires_on    date,
  notes         text default '',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists compliance_obligations_user_id_idx
  on public.compliance_obligations (user_id, created_at desc);

create index if not exists compliance_obligations_property_idx
  on public.compliance_obligations (user_id, property_id);

create table if not exists public.compliance_reminders (
  id             uuid primary key default gen_random_uuid(),
  obligation_id  uuid not null references public.compliance_obligations(id) on delete cascade,
  user_id        uuid not null references auth.users(id) on delete cascade,
  offset_code    text not null,
  offset_days    integer not null,
  scheduled_for  date not null,
  status         text not null default 'pending'
                   check (status in ('pending','sent','skipped','failed')),
  channel        text not null default 'email',
  sent_at        timestamptz,
  last_error     text,
  created_at     timestamptz not null default now()
);

create index if not exists compliance_reminders_due_idx
  on public.compliance_reminders (status, scheduled_for);

create index if not exists compliance_reminders_obligation_idx
  on public.compliance_reminders (obligation_id);

create table if not exists public.compliance_evidence (
  id             uuid primary key default gen_random_uuid(),
  obligation_id  uuid not null references public.compliance_obligations(id) on delete cascade,
  user_id        uuid not null references auth.users(id) on delete cascade,
  filename       text not null,
  content_type   text not null,
  size_bytes     integer,
  storage_key    text not null,
  url            text,
  created_at     timestamptz not null default now()
);

create index if not exists compliance_evidence_obligation_idx
  on public.compliance_evidence (obligation_id);

alter table public.compliance_obligations enable row level security;
alter table public.compliance_reminders enable row level security;
alter table public.compliance_evidence enable row level security;

create policy "Users can view own compliance obligations"
  on public.compliance_obligations for select
  using (auth.uid() = user_id);

create policy "Users can insert own compliance obligations"
  on public.compliance_obligations for insert
  with check (auth.uid() = user_id);

create policy "Users can update own compliance obligations"
  on public.compliance_obligations for update
  using (auth.uid() = user_id);

create policy "Users can delete own compliance obligations"
  on public.compliance_obligations for delete
  using (auth.uid() = user_id);

create policy "Users can view own compliance reminders"
  on public.compliance_reminders for select
  using (auth.uid() = user_id);

create policy "Users can insert own compliance reminders"
  on public.compliance_reminders for insert
  with check (auth.uid() = user_id);

create policy "Users can update own compliance reminders"
  on public.compliance_reminders for update
  using (auth.uid() = user_id);

create policy "Users can delete own compliance reminders"
  on public.compliance_reminders for delete
  using (auth.uid() = user_id);

create policy "Users can view own compliance evidence"
  on public.compliance_evidence for select
  using (auth.uid() = user_id);

create policy "Users can insert own compliance evidence"
  on public.compliance_evidence for insert
  with check (auth.uid() = user_id);

create policy "Users can delete own compliance evidence"
  on public.compliance_evidence for delete
  using (auth.uid() = user_id);

-- Private evidence bucket. Flask uses the service role so it bypasses RLS;
-- authenticated users can read/write only their own prefix.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'compliance-evidence',
  'compliance-evidence',
  false,
  10485760,
  array['application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/jpg']
)
on conflict (id) do nothing;

create policy "Users can read own compliance evidence objects"
  on storage.objects for select
  using (
    bucket_id = 'compliance-evidence'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

create policy "Users can upload own compliance evidence objects"
  on storage.objects for insert
  with check (
    bucket_id = 'compliance-evidence'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

create policy "Users can update own compliance evidence objects"
  on storage.objects for update
  using (
    bucket_id = 'compliance-evidence'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

create policy "Users can delete own compliance evidence objects"
  on storage.objects for delete
  using (
    bucket_id = 'compliance-evidence'
    and auth.uid()::text = (storage.foldername(name))[1]
  );

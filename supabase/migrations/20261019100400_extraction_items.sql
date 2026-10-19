-- DB stage 1 / migration 4 of 8 - extraction store (Rulebook E9) with manager approval.
-- Source: scripts/db_mapping_2026-10-17.md section 5, stage 2. Not applied yet.

create table public.extraction_items (
  id               bigint generated always as identity primary key,
  company_id       bigint   not null references public.companies(id) on delete restrict,
  item_key         text     not null,   -- dictionary key, or a multi-row key such as loan:<line>, bsa_<class>__<slug>
  period           text     not null,   -- fiscal year as text, or a quarter / FY label
  value            numeric,
  value_state      text     not null default 'value',
  unit             text,
  document_ref     text     not null,   -- accession, document name, filing date
  section          text,
  exact_quote      text,
  quote_verified   boolean  not null default false,  -- automatic check of the value against the quote
  basis            text,                -- group / company_share / ACL / CAL / SCR ... (RE21)
  note             text,
  approval_status  text     not null default 'pending',
  approved_by      uuid     references auth.users(id) on delete set null,
  approved_at      timestamptz,
  extractor_version text,
  created_at       timestamptz not null default now(),
  constraint extraction_items_unique unique (company_id, item_key, period, document_ref),
  constraint extraction_items_value_state_check check (value_state in ('value','NA','MISSING','not_disclosed')),
  constraint extraction_items_value_check check (value_state <> 'value' or value is not null),
  constraint extraction_items_approval_status_check check (approval_status in ('pending','approved','rejected')),
  constraint extraction_items_approved_check check (approval_status <> 'approved' or approved_at is not null)
);
create index idx_extraction_items_pending on public.extraction_items (company_id) where approval_status = 'pending';

alter table public.financial_facts
  add constraint financial_facts_extraction_id_fkey
  foreign key (extraction_id) references public.extraction_items(id) on delete set null;
create index idx_financial_facts_extraction_id on public.financial_facts (extraction_id) where extraction_id is not null;

-- users see approved rows only; pending / rejected stay internal (service_role bypasses RLS)
alter table public.extraction_items enable row level security;
revoke all on public.extraction_items from anon, authenticated;
grant select on public.extraction_items to authenticated;
create policy "extraction_items_select_authenticated" on public.extraction_items
  for select to authenticated using (approval_status = 'approved');


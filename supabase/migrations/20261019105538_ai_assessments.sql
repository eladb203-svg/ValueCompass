-- DB stage 1 / migration 5 of 8 - AI quality-question answers.
-- Re-run only for a new annual report or a changed question (new prompt_version) => a new row, history kept.

create table public.ai_assessments (
  id              bigint generated always as identity primary key,
  company_id      bigint   not null references public.companies(id) on delete restrict,
  fiscal_year     smallint not null,     -- fiscal year of the annual report assessed
  question_id     text     not null,     -- e.g. B3.1-Q1
  answer          smallint,              -- 0 / 1 / 2
  state           text     not null default 'answered',
  evidence        jsonb    not null default '{}'::jsonb,   -- quotes and source
  model           text     not null,
  prompt_version  text     not null,
  created_at      timestamptz not null default now(),
  approval_status text     not null default 'pending',
  constraint ai_assessments_unique unique (company_id, fiscal_year, question_id, prompt_version),
  constraint ai_assessments_fiscal_year_check check (fiscal_year >= 1900 and fiscal_year <= 2100),
  constraint ai_assessments_answer_check check (answer is null or answer in (0,1,2)),
  constraint ai_assessments_state_check check (state in ('answered','insufficient_evidence')),
  constraint ai_assessments_answer_state_check check (
    (state = 'answered' and answer is not null) or (state = 'insufficient_evidence' and answer is null)),
  constraint ai_assessments_approval_status_check check (approval_status in ('pending','approved','rejected'))
);

alter table public.ai_assessments enable row level security;
revoke all on public.ai_assessments from anon, authenticated;
grant select on public.ai_assessments to authenticated;
create policy "ai_assessments_select_authenticated" on public.ai_assessments
  for select to authenticated using (approval_status = 'approved');


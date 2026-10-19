-- DB stage 1 / migration 6 of 8 - score runs, score_details extension, valuations, summary extension.
-- Source: scripts/db_mapping_2026-10-17.md section 4-5 (stage 3). Not applied yet.

create table public.score_runs (
  id                  bigint generated always as identity primary key,
  company_id          bigint   not null references public.companies(id) on delete cascade,
  run_at              timestamptz not null default now(),
  profile             text     not null,
  rulebook_version    text     not null,
  calculation_version text     not null,
  price               numeric(18,4),
  price_date          date,
  flags               jsonb    not null default '{}'::jsonb,
  constraint score_runs_profile_check check (profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE')),
  constraint score_runs_flags_check check (jsonb_typeof(flags) in ('object','array'))
);
create index idx_score_runs_company_run on public.score_runs (company_id, run_at desc);

-- ---- score_details: link to a run + metric value, inputs, coverage, range
-- The table must be empty (0 rows when mapped on 2026-10-17); the unique key changes to include run_id.
do $$
begin
  if exists (select 1 from public.score_details) then
    raise exception 'score_details is not empty: run_id would have to be backfilled first';
  end if;
end $$;

alter table public.score_details
  add column run_id          bigint not null references public.score_runs(id) on delete cascade,
  add column metric_value    numeric,
  add column inputs          jsonb,            -- source years / items of the metric
  add column coverage        numeric(6,4),
  add column observed_points smallint,
  add column range_min       numeric(8,2),
  add column range_max       numeric(8,2);

alter table public.score_details drop constraint score_details_unique_current;
alter table public.score_details add constraint score_details_unique_per_run
  unique (run_id, model, score_type, criterion_key, detail_level, sub_criterion_key);

alter table public.score_details drop constraint score_details_status_check;
alter table public.score_details add constraint score_details_status_check
  check (score_status in ('calculated','partial','missing_data','not_calculated','not_applicable','error',
                          'ai_pending','insufficient_evidence'));
alter table public.score_details
  add constraint score_details_coverage_check check (coverage is null or (coverage >= 0 and coverage <= 1)),
  add constraint score_details_range_check check (range_min is null or range_max is null or range_min <= range_max);

-- ---- valuations
create table public.valuations (
  id               bigint generated always as identity primary key,
  run_id           bigint not null references public.score_runs(id) on delete cascade,
  model            text   not null,
  method           text   not null,
  fair_value       numeric(24,4),
  price_score      numeric(5,2),
  price_state      text   not null,
  margin_of_safety numeric(9,4),
  buy_price        numeric(18,4),
  buy_price_state  text   not null,
  details          jsonb  not null default '{}'::jsonb,
  constraint valuations_unique unique (run_id, model, method),
  constraint valuations_model_check check (model in ('buffett','graham')),
  constraint valuations_price_score_check check (price_score is null or (price_score >= 0 and price_score <= 10)),
  constraint valuations_price_state_check
    check (price_state in ('scored','cannot_be_valued','cannot_be_priced','blocked','stale','not_applicable')),
  constraint valuations_buy_price_state_check
    check (buy_price_state in ('allowed','not_suitable','coverage_below_80','not_applicable')),
  constraint valuations_score_state_check check (price_score is null or price_state = 'scored'),
  constraint valuations_buy_price_allowed_check check (buy_price is null or buy_price_state = 'allowed')
);

-- ---- company_score_summary extension
alter table public.company_score_summary
  add column profile                  text,
  add column rulebook_version         text,
  add column buffett_quality_coverage numeric(6,4),
  add column graham_quality_coverage  numeric(6,4),
  add column buffett_fair_value       numeric(24,4),
  add column graham_fair_value        numeric(24,4),
  add column buffett_buy_price        numeric(18,4),
  add column graham_buy_price         numeric(18,4),
  add column latest_run_id            bigint references public.score_runs(id) on delete set null,
  add constraint company_score_summary_profile_check
    check (profile is null or profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE')),
  add constraint company_score_summary_buffett_coverage_check
    check (buffett_quality_coverage is null or (buffett_quality_coverage >= 0 and buffett_quality_coverage <= 1)),
  add constraint company_score_summary_graham_coverage_check
    check (graham_quality_coverage is null or (graham_quality_coverage >= 0 and graham_quality_coverage <= 1));
create index idx_company_score_summary_latest_run_id on public.company_score_summary (latest_run_id);

-- ---- RLS (score_details / company_score_summary already have RLS and a SELECT policy)
alter table public.score_runs enable row level security;
revoke all on public.score_runs from anon, authenticated;
grant select on public.score_runs to authenticated;
create policy "score_runs_select_authenticated" on public.score_runs
  for select to authenticated using (true);

alter table public.valuations enable row level security;
revoke all on public.valuations from anon, authenticated;
grant select on public.valuations to authenticated;
create policy "valuations_select_authenticated" on public.valuations
  for select to authenticated using (true);


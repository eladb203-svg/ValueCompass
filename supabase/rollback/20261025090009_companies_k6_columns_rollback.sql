-- K6a rollback of migration 9. Fails (by design) if a row already uses UNSUPPORTED or the new columns hold data you still need.

alter table public.score_runs drop constraint score_runs_profile_check;
alter table public.score_runs add constraint score_runs_profile_check
  check (profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE'));

alter table public.company_profile_history drop constraint company_profile_history_profile_check;
alter table public.company_profile_history add constraint company_profile_history_profile_check
  check (profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE'));

alter table public.companies drop constraint companies_profile_check;
alter table public.companies add constraint companies_profile_check
  check (profile is null or profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE'));

alter table public.companies drop constraint companies_processing_state_check;
alter table public.companies drop constraint companies_cik_key;
alter table public.companies
  drop column if exists unsupported_reason,
  drop column if exists processing_state,
  drop column if exists classification_status,
  drop column if exists classification_tier,
  drop column if exists vc_industry,
  drop column if exists sic,
  drop column if exists cik;

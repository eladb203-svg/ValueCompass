-- K6a migration 9 - companies: identifiers, industry classification and processing state (AI/K6 spec section 6, item 9); UNSUPPORTED becomes a valid profile.

alter table public.companies
  add column if not exists cik                   text,
  add column if not exists sic                   text,
  add column if not exists vc_industry           text,
  add column if not exists classification_tier   text,
  add column if not exists classification_status text,
  add column if not exists processing_state      text,
  add column if not exists unsupported_reason    text;

alter table public.companies add constraint companies_cik_key unique (cik);
alter table public.companies add constraint companies_processing_state_check
  check (processing_state is null or processing_state in ('resolved','data_loaded','scored_partial','ai_in_progress','complete','failed','unsupported'));

alter table public.companies drop constraint companies_profile_check;
alter table public.companies add constraint companies_profile_check
  check (profile is null or profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE','UNSUPPORTED'));

alter table public.company_profile_history drop constraint company_profile_history_profile_check;
alter table public.company_profile_history add constraint company_profile_history_profile_check
  check (profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE','UNSUPPORTED'));

alter table public.score_runs drop constraint score_runs_profile_check;
alter table public.score_runs add constraint score_runs_profile_check
  check (profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE','UNSUPPORTED'));

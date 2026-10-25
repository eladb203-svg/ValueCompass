-- K6a migration 8 - drop the legacy financial_yearly / financial_ratios tables and financial_overview_view (replaced by financial_facts and v_display_metrics).
-- Idempotent: on a database where they are already gone (valuecompass-test) it changes nothing. Aborts if either table still has rows. No CASCADE.
-- Pre-condition checked in code (K6a): no reference to these names remains in src/ (financial_repository.py now reads and writes financial_facts).

do $$
declare
  n_yearly  bigint := 0;
  n_ratios  bigint := 0;
begin
  if to_regclass('public.financial_yearly') is not null then
    lock table public.financial_yearly in access exclusive mode;
    execute 'select count(*) from public.financial_yearly' into n_yearly;
  end if;
  if to_regclass('public.financial_ratios') is not null then
    lock table public.financial_ratios in access exclusive mode;
    execute 'select count(*) from public.financial_ratios' into n_ratios;
  end if;
  if n_yearly > 0 or n_ratios > 0 then
    raise exception 'drop_legacy aborted: financial_yearly has % rows, financial_ratios has % rows (both must be empty)', n_yearly, n_ratios;
  end if;
end $$;

drop view  if exists public.financial_overview_view;   -- joins both tables
drop table if exists public.financial_ratios;          -- FK to financial_yearly
drop table if exists public.financial_yearly;          -- takes its updated_at trigger and checks with it

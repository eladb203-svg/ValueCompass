-- Rollback of migration 20 (K6d-1). Rows that use the new values must go first.
select cron.unschedule(jobid) from cron.job where jobname = 'flag-stale-prices';
drop function if exists public.flag_stale_prices();

delete from public.fx_rates where period_type = 'current';
alter table public.fx_rates drop constraint if exists fx_rates_period_check;
alter table public.fx_rates add constraint fx_rates_period_check check (period ~ '^[0-9]{4}$');
alter table public.fx_rates drop constraint if exists fx_rates_period_type_check;
alter table public.fx_rates add constraint fx_rates_period_type_check check (period_type in ('annual_avg','year_end'));
alter table public.fx_rates drop column if exists retrieved_at;
alter table public.fx_rates drop column if exists rate_date;

alter table public.score_runs drop column if exists changes;

update public.work_queue set priority = 3 where priority = 4;
alter table public.work_queue drop constraint if exists work_queue_priority_check;
alter table public.work_queue add constraint work_queue_priority_check check (priority between 1 and 3);
-- pg_cron is left installed (other jobs may use it); drop it by hand if nothing else does: drop extension pg_cron;

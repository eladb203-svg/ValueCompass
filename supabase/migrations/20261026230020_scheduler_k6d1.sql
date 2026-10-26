-- K6d-1 migration 20 - the scheduler: queue priority 4, the change line of a score run, current FX rates, and the price-freshness check (E1) that runs inside the database with pg_cron.
-- Test project first, production only after the owner's approval.

-- 1. work_queue.priority: 1 a user asked, 2 data completion, 3 a new annual report, 4 wide loading (K6 spec 2.8, decided 2026-10-26; before: 1 user, 2 new report, 3 backfill)
alter table public.work_queue drop constraint if exists work_queue_priority_check;
alter table public.work_queue add constraint work_queue_priority_check check (priority between 1 and 4);

-- 2. score_runs.changes: the "what changed" line against the previous run, computed by code when the run is written (only the latest run of a company is kept: K6 spec 3.3)
alter table public.score_runs add column if not exists changes jsonb;

-- 3. fx_rates: the current daily rate (USD for one unit of the currency), one row per currency, updated in place; the annual rows stay as they are
alter table public.fx_rates add column if not exists rate_date date;
alter table public.fx_rates add column if not exists retrieved_at timestamptz;
alter table public.fx_rates drop constraint if exists fx_rates_period_type_check;
alter table public.fx_rates add constraint fx_rates_period_type_check check (period_type in ('annual_avg','year_end','current'));
alter table public.fx_rates drop constraint if exists fx_rates_period_check;
alter table public.fx_rates add constraint fx_rates_period_check check ((period_type = 'current' and period = 'current') or (period_type <> 'current' and period ~ '^[0-9]{4}$'));

-- 4. E1: a price that was not updated for more than 3 trading days is flagged stale; its price scores are withdrawn (price_state 'stale', no price score) until a new price arrives.
-- Trading days here are the weekdays (the exchange holidays are not known to the database): around a holiday this can flag a stale price one day early; the next price update recomputes it.
create or replace function public.flag_stale_prices() returns integer
language plpgsql
set search_path = public, pg_temp
as $$
declare
  today_ny date := (now() at time zone 'America/New_York')::date;
  n integer := 0;
begin
  with stale as (
    update public.market_snapshot ms
       set is_stale = true, updated_at = now()
     where ms.is_stale = false
       and ms.last_price_at is not null
       and (select count(*) from generate_series((ms.last_price_at at time zone 'America/New_York')::date + 1, today_ny, interval '1 day') g(d)
             where extract(isodow from g.d) < 6) > 3
    returning ms.company_id
  ), val as (
    update public.valuations v
       set price_state = 'stale', price_score = null
      from stale s
      join public.company_score_summary cs on cs.company_id = s.company_id
     where v.run_id = cs.latest_run_id and v.price_state = 'scored'
    returning v.id
  ), summ as (
    update public.company_score_summary cs
       set buffett_price_score = null, graham_price_score = null, updated_at = now()
      from stale s
     where cs.company_id = s.company_id
    returning cs.company_id
  )
  select count(*) into n from stale;
  return n;
end;
$$;
revoke all on function public.flag_stale_prices() from public, anon, authenticated;
grant execute on function public.flag_stale_prices() to service_role;

create extension if not exists pg_cron with schema pg_catalog;
select cron.unschedule(jobid) from cron.job where jobname = 'flag-stale-prices';
select cron.schedule('flag-stale-prices', '5 * * * *', $cron$select public.flag_stale_prices()$cron$);

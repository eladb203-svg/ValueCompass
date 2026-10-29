-- K6d-2 migration 22: E1 changed (decided 2026-10-28): a price is stale when its date is before the LAST TRADING DAY (the most recent day whose NYSE session has closed), not after 3 trading days.
-- The database now knows the exchange calendar (market_calendar, 2026-2030, generated from the same rules as src/sched/nyse.py) so that holidays and half days are exact.
create table if not exists public.market_calendar (
  day  date primary key,
  kind text not null check (kind in ('closed', 'half')),
  name text
);
alter table public.market_calendar enable row level security;
revoke all on public.market_calendar from anon, authenticated;
grant all on public.market_calendar to service_role;
insert into public.market_calendar (day, kind, name) values
  ('2026-01-01', 'closed', 'New Year''s Day'),
  ('2026-01-19', 'closed', 'Martin Luther King Jr. Day'),
  ('2026-02-16', 'closed', 'Presidents'' Day'),
  ('2026-04-03', 'closed', 'Good Friday'),
  ('2026-05-25', 'closed', 'Memorial Day'),
  ('2026-06-19', 'closed', 'Juneteenth'),
  ('2026-07-03', 'closed', 'Independence Day'),
  ('2026-09-07', 'closed', 'Labor Day'),
  ('2026-11-26', 'closed', 'Thanksgiving'),
  ('2026-11-27', 'half', 'early close 13:00'),
  ('2026-12-24', 'half', 'early close 13:00'),
  ('2026-12-25', 'closed', 'Christmas'),
  ('2027-01-01', 'closed', 'New Year''s Day'),
  ('2027-01-18', 'closed', 'Martin Luther King Jr. Day'),
  ('2027-02-15', 'closed', 'Presidents'' Day'),
  ('2027-03-26', 'closed', 'Good Friday'),
  ('2027-05-31', 'closed', 'Memorial Day'),
  ('2027-06-18', 'closed', 'Juneteenth'),
  ('2027-07-05', 'closed', 'Independence Day'),
  ('2027-09-06', 'closed', 'Labor Day'),
  ('2027-11-25', 'closed', 'Thanksgiving'),
  ('2027-11-26', 'half', 'early close 13:00'),
  ('2027-12-24', 'closed', 'Christmas'),
  ('2028-01-17', 'closed', 'Martin Luther King Jr. Day'),
  ('2028-02-21', 'closed', 'Presidents'' Day'),
  ('2028-04-14', 'closed', 'Good Friday'),
  ('2028-05-29', 'closed', 'Memorial Day'),
  ('2028-06-19', 'closed', 'Juneteenth'),
  ('2028-07-03', 'half', 'early close 13:00'),
  ('2028-07-04', 'closed', 'Independence Day'),
  ('2028-09-04', 'closed', 'Labor Day'),
  ('2028-11-23', 'closed', 'Thanksgiving'),
  ('2028-11-24', 'half', 'early close 13:00'),
  ('2028-12-25', 'closed', 'Christmas'),
  ('2029-01-01', 'closed', 'New Year''s Day'),
  ('2029-01-15', 'closed', 'Martin Luther King Jr. Day'),
  ('2029-02-19', 'closed', 'Presidents'' Day'),
  ('2029-03-30', 'closed', 'Good Friday'),
  ('2029-05-28', 'closed', 'Memorial Day'),
  ('2029-06-19', 'closed', 'Juneteenth'),
  ('2029-07-03', 'half', 'early close 13:00'),
  ('2029-07-04', 'closed', 'Independence Day'),
  ('2029-09-03', 'closed', 'Labor Day'),
  ('2029-11-22', 'closed', 'Thanksgiving'),
  ('2029-11-23', 'half', 'early close 13:00'),
  ('2029-12-24', 'half', 'early close 13:00'),
  ('2029-12-25', 'closed', 'Christmas'),
  ('2030-01-01', 'closed', 'New Year''s Day'),
  ('2030-01-21', 'closed', 'Martin Luther King Jr. Day'),
  ('2030-02-18', 'closed', 'Presidents'' Day'),
  ('2030-04-19', 'closed', 'Good Friday'),
  ('2030-05-27', 'closed', 'Memorial Day'),
  ('2030-06-19', 'closed', 'Juneteenth'),
  ('2030-07-03', 'half', 'early close 13:00'),
  ('2030-07-04', 'closed', 'Independence Day'),
  ('2030-09-02', 'closed', 'Labor Day'),
  ('2030-11-28', 'closed', 'Thanksgiving'),
  ('2030-11-29', 'half', 'early close 13:00'),
  ('2030-12-24', 'half', 'early close 13:00'),
  ('2030-12-25', 'closed', 'Christmas')
on conflict (day) do update set kind = excluded.kind, name = excluded.name;

create or replace function public.last_trading_day(at_ts timestamptz default now()) returns date
language plpgsql stable
set search_path = public, pg_temp
as $$
declare
  ny timestamp := at_ts at time zone 'America/New_York';
  d date := ny::date;
  close_t time;
begin
  close_t := case when exists (select 1 from public.market_calendar c where c.day = d and c.kind = 'half') then time '13:00' else time '16:00' end;
  if extract(isodow from d) < 6 and not exists (select 1 from public.market_calendar c where c.day = d and c.kind = 'closed') and ny::time >= close_t then
    return d;
  end if;
  d := d - 1;
  while extract(isodow from d) >= 6 or exists (select 1 from public.market_calendar c where c.day = d and c.kind = 'closed') loop
    d := d - 1;
  end loop;
  return d;
end;
$$;
revoke all on function public.last_trading_day(timestamptz) from public, anon, authenticated;
grant execute on function public.last_trading_day(timestamptz) to service_role;

create or replace function public.flag_stale_prices() returns integer
language plpgsql
set search_path = public, pg_temp
as $$
declare
  last_day date := public.last_trading_day(now());
  n integer := 0;
begin
  with stale as (
    update public.market_snapshot ms
       set is_stale = true, updated_at = now()
     where ms.is_stale = false
       and ms.last_price_at is not null
       and (ms.last_price_at at time zone 'America/New_York')::date < last_day
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

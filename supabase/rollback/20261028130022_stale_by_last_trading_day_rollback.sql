-- Rollback of migration 22: back to the 3-weekday rule of migration 20.
drop function if exists public.last_trading_day(timestamptz);
drop table if exists public.market_calendar;
-- then run the flag_stale_prices() definition of 20261026230020_scheduler_k6d1.sql again

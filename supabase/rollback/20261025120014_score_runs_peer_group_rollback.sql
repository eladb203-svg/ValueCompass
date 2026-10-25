-- K6c rollback of migration 14.
alter table public.score_runs drop column if exists peer_group;

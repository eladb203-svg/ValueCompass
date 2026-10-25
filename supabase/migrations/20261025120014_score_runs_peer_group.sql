-- K6c migration 14 - score_runs.peer_group: the fixed peer group of a run (D2 compares to it) - K6 spec section 6, item 14.
alter table public.score_runs add column if not exists peer_group jsonb;

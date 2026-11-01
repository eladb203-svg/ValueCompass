-- K6d-2 fixes (2026-11-01) - work_queue: a new task state deferred_network. A task that used its five attempts on a network error waits 30 minutes there and returns to the queue (up to 6 times);
-- only a permanent error ends in failed. The open-task unique index and the pick index include the new state.

alter table public.work_queue drop constraint work_queue_state_check;
alter table public.work_queue add constraint work_queue_state_check check (state in ('queued','running','done','failed','deferred_quota','deferred_network'));

drop index public.work_queue_open_unique;
create unique index work_queue_open_unique on public.work_queue (company_id, job_type, coalesce(fiscal_year, 0), coalesce(skill, ''))
  where state in ('queued','running','deferred_quota','deferred_network');

drop index public.work_queue_pick;
create index work_queue_pick on public.work_queue (priority, next_run_at) where state in ('queued','deferred_quota','deferred_network');

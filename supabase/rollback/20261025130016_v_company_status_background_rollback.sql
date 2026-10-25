-- K6c follow-up rollback of migration 16: the view as migration 15 made it (the view is dropped and created again: the two new columns cannot be removed by create or replace).
drop view if exists public.v_company_status;
create view public.v_company_status as
select c.id as company_id, c.symbol, c.company_name, c.processing_state, c.profile, c.unsupported_reason,
       (select max(l.created_at) from public.data_update_log l where l.company_id = c.id) as last_job_at,
       (select l.status from public.data_update_log l where l.company_id = c.id order by l.created_at desc limit 1) as last_job_status,
       (select max(r.run_at) from public.score_runs r where r.company_id = c.id) as last_score_at,
       (select count(*) from public.work_queue q where q.company_id = c.id and q.job_type like 'ai\_%' and q.state = 'done')::int as ai_done,
       (select count(*) from public.work_queue q where q.company_id = c.id and q.job_type like 'ai\_%' and q.state <> 'failed')::int as ai_total
from public.companies c;
revoke all on public.v_company_status from anon;
grant select on public.v_company_status to authenticated;
grant all on public.v_company_status to service_role;

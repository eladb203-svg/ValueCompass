-- K6c follow-up, migration 16 - v_company_status: the state of the Hebrew background is shown by itself (a failed or waiting background no longer keeps a company out of `complete`), and the AI progress
-- counts only the tasks whose answers feed the score (C1, B, A). New columns at the end: background_status (approved / pending_review / failed / missing), background_human_reviewed.

create or replace view public.v_company_status as
select c.id as company_id, c.symbol, c.company_name, c.processing_state, c.profile, c.unsupported_reason,
       (select max(l.created_at) from public.data_update_log l where l.company_id = c.id) as last_job_at,
       (select l.status from public.data_update_log l where l.company_id = c.id order by l.created_at desc limit 1) as last_job_status,
       (select max(r.run_at) from public.score_runs r where r.company_id = c.id) as last_score_at,
       (select count(*) from public.work_queue q where q.company_id = c.id and q.job_type in ('ai_classify','ai_extract','ai_assess') and q.state = 'done')::int as ai_done,
       (select count(*) from public.work_queue q where q.company_id = c.id and q.job_type in ('ai_classify','ai_extract','ai_assess') and q.state <> 'failed')::int as ai_total,
       coalesce((select t.approval_status from public.ai_texts t where t.company_id = c.id and t.kind = 'background' and t.language = 'he'
                 order by t.fiscal_year desc, (t.approval_status = 'approved') desc, t.prompt_version desc limit 1), 'missing') as background_status,
       (select t.human_reviewed from public.ai_texts t where t.company_id = c.id and t.kind = 'background' and t.language = 'he'
        order by t.fiscal_year desc, (t.approval_status = 'approved') desc, t.prompt_version desc limit 1) as background_human_reviewed
from public.companies c;

-- K6d-2 fixes (2026-11-02) - companies.processing_state: a new final state insufficient_history. A company with fewer than 3 loaded annual reports (a new registrant after a merger: PNFP) is not
-- "unsupported": it gets its score when the third annual report arrives (the SEC daily index queues a new_report load). Its reason is kept in unsupported_reason, like the reason of an unsupported company.

alter table public.companies drop constraint companies_processing_state_check;
alter table public.companies add constraint companies_processing_state_check
  check (processing_state is null or processing_state in ('resolved','data_loaded','scored_partial','ai_in_progress','complete','failed','unsupported','insufficient_history'));

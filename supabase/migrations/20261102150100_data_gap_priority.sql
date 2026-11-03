-- K6d-2 fixes (2026-11-02) - data_gap_review.priority: 1 = the top priority (a core figure is missing, or a figure was held back as wrong - family suspect_data), 3 = the rest.
alter table public.data_gap_review add column priority smallint not null default 3 check (priority between 1 and 3);
create index data_gap_review_priority on public.data_gap_review (priority, state);

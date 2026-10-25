-- K6a migration 10 - extraction_items: provenance of the AI extraction (skill, versions, model, control and its result) - spec section 6, item 10,
-- plus approval_source: an approved row must say who approved it (k5b_confirmed = K5b verified the value, ai_controls = the AI controls, human_review = a person) and when.

alter table public.extraction_items
  add column if not exists skill_id        text,
  add column if not exists skill_version   text,
  add column if not exists model           text,
  add column if not exists prompt_version  text,
  add column if not exists control         jsonb,
  add column if not exists approval_source text;

-- rows that predate the column and are already approved (none on production; the test project holds only test data) are attributed to a human review.
update public.extraction_items set approval_source = 'human_review' where approval_status = 'approved' and approval_source is null;

alter table public.extraction_items add constraint extraction_items_approval_source_check
  check (approval_source is null or approval_source in ('k5b_confirmed','ai_controls','human_review'));
alter table public.extraction_items add constraint extraction_items_approved_source_check
  check (approval_status <> 'approved' or (approval_source is not null and approved_at is not null));

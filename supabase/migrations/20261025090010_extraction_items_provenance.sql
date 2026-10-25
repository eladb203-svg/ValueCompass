-- K6a migration 10 - extraction_items: provenance of the AI extraction (skill, versions, model, control and its result) - spec section 6, item 10.

alter table public.extraction_items
  add column if not exists skill_id       text,
  add column if not exists skill_version  text,
  add column if not exists model          text,
  add column if not exists prompt_version text,
  add column if not exists control        jsonb;

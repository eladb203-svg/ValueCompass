-- K6a rollback of migration 10.
alter table public.extraction_items
  drop column if exists control,
  drop column if exists prompt_version,
  drop column if exists model,
  drop column if exists skill_version,
  drop column if exists skill_id;

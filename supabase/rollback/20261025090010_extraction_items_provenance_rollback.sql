-- K6a rollback of migration 10.
alter table public.extraction_items drop constraint if exists extraction_items_approved_source_check;
alter table public.extraction_items drop constraint if exists extraction_items_approval_source_check;
alter table public.extraction_items
  drop column if exists approval_source,
  drop column if exists control,
  drop column if exists prompt_version,
  drop column if exists model,
  drop column if exists skill_version,
  drop column if exists skill_id;

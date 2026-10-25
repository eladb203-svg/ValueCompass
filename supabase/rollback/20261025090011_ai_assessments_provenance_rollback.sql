-- K6a rollback of migration 11.
alter table public.ai_assessments
  drop column if exists skill_version,
  drop column if exists accession;

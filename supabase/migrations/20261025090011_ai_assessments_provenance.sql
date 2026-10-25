-- K6a migration 11 - ai_assessments: the source document and the skill version of every answer (R18) - spec section 6, item 11.

alter table public.ai_assessments
  add column if not exists accession     text,
  add column if not exists skill_version text;

-- BP follow-up, migration 18: the profile gets display_name (the short name the report uses for the company, from BP-1 v2) and term_translations.source accepts 'azure' (the translation provider).
alter table public.company_business_profiles add column display_name jsonb not null default '{}'::jsonb;
alter table public.term_translations drop constraint term_translations_source_check;
alter table public.term_translations add constraint term_translations_source_check check (source in ('azure','google','model','human'));

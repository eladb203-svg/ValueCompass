-- rollback of migration 18 (translations from Azure are removed first: the old check does not allow them)
delete from public.term_translations where source = 'azure';
alter table public.term_translations drop constraint term_translations_source_check;
alter table public.term_translations add constraint term_translations_source_check check (source in ('google','model','human'));
alter table public.company_business_profiles drop column display_name;

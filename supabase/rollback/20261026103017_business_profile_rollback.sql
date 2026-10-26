-- BP rollback of migration 17. Texts that were 'superseded' go back to 'approved' only if you run the last statement of this file; the profile / vocab / translation tables and their rows are dropped.
update public.ai_texts set approval_status = 'approved' where approval_status = 'superseded' and template_version is null;
delete from public.ai_texts where template_version is not null;
alter table public.ai_texts drop constraint ai_texts_text_check;
alter table public.ai_texts add constraint ai_texts_text_check check (approval_status = 'failed' or text is not null);
alter table public.ai_texts drop constraint ai_texts_approval_status_check;
alter table public.ai_texts add constraint ai_texts_approval_status_check check (approval_status in ('approved','pending_review','failed'));
alter table public.ai_texts drop column profile_id;
alter table public.ai_texts drop column template_version;
drop table public.term_translations;
drop table public.business_vocab;
drop table public.company_business_profiles;

-- K6c rollback of migration 12 (drops the table and every text in it).
drop table if exists public.ai_texts;

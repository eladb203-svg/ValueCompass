alter table public.companies drop constraint companies_industry_override_reason_check;
alter table public.companies drop column industry_override_reason;
alter table public.companies drop column industry_override;

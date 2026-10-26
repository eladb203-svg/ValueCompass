-- BP round 3, migration 19: companies.industry_override - the industry (a ValueCompass industry code, e.g. internet_platforms_advertising) that the profile router must use instead of its own
-- classification, with the reason (the router refuses an override without one). It is kept on the company row, so every later load applies it.
alter table public.companies add column industry_override text;
alter table public.companies add column industry_override_reason text;
alter table public.companies add constraint companies_industry_override_reason_check check (industry_override is null or length(trim(coalesce(industry_override_reason, ''))) > 0);

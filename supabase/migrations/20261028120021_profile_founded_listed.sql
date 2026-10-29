-- K6d-2 migration 21: the business profile gets `founded` and `listed_since` (AI skills 2026-10-27_09-10, 3.1.1; BP-1 version 4).
-- founded:      {"status", "source", "items": [{"year", "kind": founded | incorporated, "quote", ...}]}
-- listed_since: {"status", "source", "items": [{"year", "source": report | price_history, "approximate": bool, "quote" | "tag", ...}]}
alter table public.company_business_profiles add column if not exists founded jsonb not null default '{}'::jsonb;
alter table public.company_business_profiles add column if not exists listed_since jsonb not null default '{}'::jsonb;

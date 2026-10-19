-- DB stage 1 / migration 3 of 8 - financial_facts: the single source for all financial data (long format).
-- No row = missing data. Row size is kept small on purpose (see scripts/db_stage1_2026-10-19.md).
-- extraction_id gets its foreign key in migration 4 (extraction_items does not exist yet).

create table public.financial_facts (
  company_id    bigint   not null references public.companies(id) on delete restrict,
  fiscal_year   smallint not null,
  item_id       smallint not null references public.dictionary_items(id),
  value         numeric,
  status        text     not null,
  source_kind   text     not null,
  tag_id        int      references public.fact_tags(id),
  flags         text[],
  basis         text,
  extraction_id bigint,
  constraint financial_facts_pkey primary key (company_id, fiscal_year, item_id),
  constraint financial_facts_fiscal_year_check check (fiscal_year >= 1900 and fiscal_year <= 2100),
  constraint financial_facts_status_check
    check (status in ('found','reported_none','assumed_zero','not_applicable')),
  constraint financial_facts_source_kind_check
    check (source_kind in ('xbrl','ixbrl','quarterly_sum','extraction','derived')),
  -- only 'not_applicable' may carry no value; 'reported_none' / 'assumed_zero' are zero by definition
  constraint financial_facts_value_check check (
    status = 'not_applicable'
    or (value is not null and (status = 'found' or value = 0)))
);
create index idx_financial_facts_item_year on public.financial_facts (item_id, fiscal_year);
create index idx_financial_facts_tag_id on public.financial_facts (tag_id);
comment on table public.financial_facts is 'One row per company x fiscal year x dictionary component. No row = missing. Derived items (source_kind = derived) are written by the engine per Rulebook D/C.';
comment on column public.financial_facts.basis is 'Reporting basis when it matters (e.g. group vs company share, per RE21 / ACL basis).';

alter table public.financial_facts enable row level security;
revoke all on public.financial_facts from anon, authenticated;
grant select on public.financial_facts to authenticated;
create policy "financial_facts_select_authenticated" on public.financial_facts
  for select to authenticated using (true);


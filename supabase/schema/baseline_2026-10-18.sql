-- תיעוד מצב בלבד — לא מיגרציה
-- =============================================================================
-- BASELINE of schema "public" - project ValueInvestConsult (zwpftrjryxyymrxsprqh)
-- Captured read-only on 2026-10-18 (DB stage 0).
--
-- !! DO NOT RUN THIS FILE AGAINST THE EXISTING DATABASE !!
-- It DESCRIBES the state that already exists in the DB (after the 7 applied
-- migrations 20260826064056 .. 20260908142258). It exists so the repo can
-- rebuild an empty database (local / branch) and as a reference point.
-- Mark it as applied (supabase migration repair --status applied <version>)
-- rather than executing it on production.
--
-- Not included by design:
--   * GRANTs: anon / authenticated / service_role hold the Supabase default
--     privileges on every table and view (ALL, incl. TRUNCATE) and EXECUTE on
--     both functions (default privileges of the supabase project).
--   * auth.users (managed by Supabase Auth; user_profiles.id references it).
--   * Row data.
-- Extensions present (installed by Supabase, schema "extensions"):
--   pg_stat_statements, uuid-ossp, pgcrypto (+ supabase_vault in "vault").
-- =============================================================================

-- ---------------------------------------------------------------- functions
create or replace function public.set_updated_at()
 returns trigger
 language plpgsql
as $function$
begin
    new.updated_at = now();
    return new;
end;
$function$;

-- ------------------------------------------------------------------- tables
create table public.companies (
  id bigint generated always as identity not null,
  symbol text not null,
  company_name text not null,
  exchange text not null,
  country text not null,
  reporting_currency text not null,
  sector text,
  industry text,
  data_source text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  public_since_date date
);

create table public.company_listings (
  id bigint generated always as identity not null,
  company_id bigint not null,
  symbol text not null,
  exchange text not null,
  mic text,
  trading_currency text,
  security_type text,
  share_class text,
  is_adr boolean,
  adr_ratio numeric(18,8),
  isin text,
  figi text,
  share_class_figi text,
  is_primary boolean not null default false,
  is_active boolean not null default true,
  data_source text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  listing_start_date date
);
comment on table public.company_listings is 'Exchange listings and tradable securities associated with a canonical company/issuer.';

create table public.financial_yearly (
  company_id bigint not null,
  fiscal_year smallint not null,
  fiscal_year_end_date date,
  filing_date date,
  revenue numeric(20,2),
  gross_profit numeric(20,2),
  operating_income numeric(20,2),
  ebit numeric(20,2),
  ebitda numeric(20,2),
  income_before_tax numeric(20,2),
  income_tax_expense numeric(20,2),
  net_income numeric(20,2),
  eps_diluted numeric(14,4),
  interest_expense numeric(20,2),
  depreciation_and_amortization numeric(20,2),
  operating_cash_flow numeric(20,2),
  capex numeric(20,2),
  free_cash_flow numeric(20,2),
  stock_based_compensation numeric(20,2),
  adjusted_free_cash_flow numeric(20,2),
  dividends_paid numeric(20,2),
  share_repurchases numeric(20,2),
  dividends_per_share numeric(14,4),
  total_assets numeric(20,2),
  total_liabilities numeric(20,2),
  total_equity numeric(20,2),
  total_debt numeric(20,2),
  long_term_debt numeric(20,2),
  cash_and_equivalents numeric(20,2),
  short_term_investments numeric(20,2),
  accounts_receivable numeric(20,2),
  current_assets numeric(20,2),
  current_liabilities numeric(20,2),
  goodwill numeric(20,2),
  intangible_assets numeric(20,2),
  shares_outstanding bigint,
  weighted_avg_shares_diluted bigint,
  source text not null default 'unknown',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  reporting_currency text
);

create table public.financial_ratios (
  company_id bigint not null,
  fiscal_year smallint not null,
  gross_margin numeric(18,6),
  operating_margin numeric(18,6),
  net_margin numeric(18,6),
  fcf_margin numeric(18,6),
  adjusted_fcf_margin numeric(18,6),
  roe numeric(18,6),
  roa numeric(18,6),
  effective_tax_rate numeric(18,6),
  nopat numeric(20,2),
  invested_capital numeric(20,2),
  roic numeric(18,6),
  fcf_to_net_income numeric(18,6),
  operating_cash_flow_to_net_income numeric(18,6),
  capex_to_revenue numeric(18,6),
  capex_to_operating_cash_flow numeric(18,6),
  adjusted_fcf_to_net_income numeric(18,6),
  working_capital numeric(20,2),
  current_ratio numeric(18,6),
  quick_ratio numeric(18,6),
  debt_to_equity numeric(18,6),
  debt_to_assets numeric(18,6),
  net_debt numeric(20,2),
  net_debt_to_ebitda numeric(18,6),
  interest_coverage numeric(18,6),
  long_term_debt_to_working_capital numeric(18,6),
  book_value_per_share numeric(18,4),
  tangible_book_value numeric(20,2),
  tangible_book_value_per_share numeric(18,4),
  ncav numeric(20,2),
  ncav_per_share numeric(18,4),
  dividend_payout_ratio numeric(18,6),
  fcf_payout_ratio numeric(18,6),
  buyback_yield numeric(18,6),
  share_dilution_1y numeric(18,6),
  share_dilution_5y numeric(18,6),
  revenue_growth_1y numeric(18,6),
  eps_growth_1y numeric(18,6),
  fcf_growth_1y numeric(18,6),
  revenue_cagr_3y numeric(18,6),
  eps_cagr_3y numeric(18,6),
  fcf_cagr_3y numeric(18,6),
  revenue_cagr_5y numeric(18,6),
  eps_cagr_5y numeric(18,6),
  fcf_cagr_5y numeric(18,6),
  calculation_version text not null default 'v1',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.market_snapshot (
  company_id bigint not null,
  snapshot_at timestamptz not null,
  market_date date,
  current_price numeric(18,4) not null,
  previous_close numeric(18,4),
  price_currency text not null,
  market_cap numeric(24,2),
  enterprise_value numeric(24,2),
  fifty_two_week_high numeric(18,4),
  fifty_two_week_low numeric(18,4),
  source text not null default 'unknown',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.company_score_summary (
  company_id bigint not null,
  as_of_fiscal_year smallint,
  years_available smallint,
  market_snapshot_at timestamptz,
  buffett_quality_score numeric(6,2),
  buffett_price_score numeric(5,2),
  graham_quality_score numeric(6,2),
  graham_price_score numeric(5,2),
  overall_status text not null default 'not_calculated',
  missing_fields text[] not null default '{}',
  calculation_version text not null default 'v1',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.score_details (
  id bigint generated always as identity not null,
  company_id bigint not null,
  model text not null,
  score_type text not null,
  criterion_key text not null,
  criterion_name text not null,
  detail_level text not null default 'criterion',
  sub_criterion_key text not null default 'main',
  sub_criterion_name text,
  criterion_score numeric(8,2),
  max_score numeric(8,2) not null,
  score_status text not null default 'not_calculated',
  missing_fields text[] not null default '{}',
  evidence jsonb not null default '{}'::jsonb,
  explanation text,
  calculation_version text not null default 'v1',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.data_update_log (
  id bigint generated always as identity not null,
  company_id bigint,
  symbol text,
  exchange text,
  operation_type text not null,
  target_table text,
  update_scope text,
  data_source text not null default 'unknown',
  status text not null,
  records_inserted integer not null default 0,
  records_updated integer not null default 0,
  records_deleted integer not null default 0,
  years_requested smallint[],
  years_imported smallint[],
  missing_fields text[] not null default '{}',
  error_message text,
  warning_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  request_reference text,
  source_details jsonb not null default '[]'::jsonb,
  missing_years smallint[] not null default '{}'::smallint[]
);

create table public.user_profiles (
  id uuid not null,
  full_name text,
  preferred_language text not null default 'he',
  risk_profile text,
  investment_style text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.portfolios (
  id bigint generated always as identity not null,
  user_id uuid not null,
  portfolio_name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.portfolio_holdings (
  id bigint generated always as identity not null,
  portfolio_id bigint not null,
  company_id bigint not null,
  quantity numeric(20,6) not null,
  average_cost numeric(18,4),
  cost_currency text,
  first_buy_date date,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.user_watchlist (
  id bigint generated always as identity not null,
  user_id uuid not null,
  company_id bigint not null,
  target_buffett_quality_score numeric(6,2),
  target_buffett_price_score numeric(5,2),
  target_graham_quality_score numeric(6,2),
  target_graham_price_score numeric(5,2),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ------------------------------------------------- primary keys / uniques
alter table public.companies             add constraint companies_pkey primary key (id);
alter table public.company_listings      add constraint company_listings_pkey primary key (id);
alter table public.company_score_summary add constraint company_score_summary_pkey primary key (company_id);
alter table public.data_update_log       add constraint data_update_log_pkey primary key (id);
alter table public.financial_ratios      add constraint financial_ratios_pkey primary key (company_id, fiscal_year);
alter table public.financial_yearly      add constraint financial_yearly_pkey primary key (company_id, fiscal_year);
alter table public.market_snapshot       add constraint market_snapshot_pkey primary key (company_id);
alter table public.portfolio_holdings    add constraint portfolio_holdings_pkey primary key (id);
alter table public.portfolios            add constraint portfolios_pkey primary key (id);
alter table public.score_details         add constraint score_details_pkey primary key (id);
alter table public.user_profiles         add constraint user_profiles_pkey primary key (id);
alter table public.user_watchlist        add constraint user_watchlist_pkey primary key (id);

alter table public.companies          add constraint companies_symbol_exchange_unique unique (symbol, exchange);
alter table public.company_listings   add constraint company_listings_symbol_exchange_unique unique (symbol, exchange);
alter table public.portfolio_holdings add constraint portfolio_holdings_unique_company_per_portfolio unique (portfolio_id, company_id);
alter table public.score_details      add constraint score_details_unique_current unique (company_id, model, score_type, criterion_key, detail_level, sub_criterion_key);
alter table public.user_watchlist     add constraint user_watchlist_unique_company_per_user unique (user_id, company_id);

-- ------------------------------------------------------------------- checks
alter table public.company_listings add constraint company_listings_adr_ratio_positive check (adr_ratio is null or adr_ratio > 0);

alter table public.company_score_summary
  add constraint company_score_summary_buffett_price_check   check (buffett_price_score is null or (buffett_price_score >= 0 and buffett_price_score <= 10)),
  add constraint company_score_summary_buffett_quality_check check (buffett_quality_score is null or (buffett_quality_score >= 0 and buffett_quality_score <= 100)),
  add constraint company_score_summary_fiscal_year_check     check (as_of_fiscal_year is null or (as_of_fiscal_year >= 1900 and as_of_fiscal_year <= 2100)),
  add constraint company_score_summary_graham_price_check    check (graham_price_score is null or (graham_price_score >= 0 and graham_price_score <= 10)),
  add constraint company_score_summary_graham_quality_check  check (graham_quality_score is null or (graham_quality_score >= 0 and graham_quality_score <= 100)),
  add constraint company_score_summary_status_check          check (overall_status = any (array['calculated','partial','missing_data','not_calculated','not_applicable','error'])),
  add constraint company_score_summary_years_available_check check (years_available is null or (years_available >= 0 and years_available <= 20));

alter table public.data_update_log
  add constraint data_update_log_operation_type_check check (operation_type = any (array['sync_company','import_company','refresh_company_profile','refresh_financials','refresh_market_snapshot','calculate_ratios','calculate_scores','purge_data','full_refresh'])),
  add constraint data_update_log_records_deleted_check  check (records_deleted >= 0),
  add constraint data_update_log_records_inserted_check check (records_inserted >= 0),
  add constraint data_update_log_records_updated_check  check (records_updated >= 0),
  add constraint data_update_log_source_details_array_check check (jsonb_typeof(source_details) = 'array'),
  add constraint data_update_log_status_check check (status = any (array['running','success','partial_success','no_change','failed'])),
  add constraint data_update_log_years_imported_check  check (years_imported is null or cardinality(years_imported) <= 20),
  add constraint data_update_log_years_requested_check check (years_requested is null or cardinality(years_requested) <= 20);

alter table public.financial_ratios add constraint financial_ratios_fiscal_year_check check (fiscal_year >= 1900 and fiscal_year <= 2100);
alter table public.financial_yearly add constraint financial_yearly_fiscal_year_check check (fiscal_year >= 1900 and fiscal_year <= 2100);

alter table public.portfolio_holdings
  add constraint portfolio_holdings_average_cost_check  check (average_cost is null or average_cost >= 0),
  add constraint portfolio_holdings_cost_currency_check check (cost_currency is null or cost_currency = any (array['USD','ILS','EUR','GBP','JPY'])),
  add constraint portfolio_holdings_quantity_check      check (quantity > 0);

alter table public.score_details
  add constraint score_details_detail_level_check check (detail_level = any (array['criterion','sub_criterion'])),
  add constraint score_details_max_score_check    check (max_score >= 0),
  add constraint score_details_model_check        check (model = any (array['buffett','graham'])),
  add constraint score_details_score_non_negative_check  check (criterion_score is null or criterion_score >= 0),
  add constraint score_details_score_not_above_max_check check (criterion_score is null or criterion_score <= max_score),
  add constraint score_details_score_type_check   check (score_type = any (array['quality','price'])),
  add constraint score_details_status_check       check (score_status = any (array['calculated','partial','missing_data','not_calculated','not_applicable','error']));

alter table public.user_profiles
  add constraint user_profiles_investment_style_check  check (investment_style is null or investment_style = any (array['value','growth','mixed'])),
  add constraint user_profiles_preferred_language_check check (preferred_language = any (array['he','en'])),
  add constraint user_profiles_risk_profile_check      check (risk_profile is null or risk_profile = any (array['conservative','balanced','aggressive']));

alter table public.user_watchlist
  add constraint user_watchlist_buffett_price_check   check (target_buffett_price_score is null or (target_buffett_price_score >= 0 and target_buffett_price_score <= 10)),
  add constraint user_watchlist_buffett_quality_check check (target_buffett_quality_score is null or (target_buffett_quality_score >= 0 and target_buffett_quality_score <= 100)),
  add constraint user_watchlist_graham_price_check    check (target_graham_price_score is null or (target_graham_price_score >= 0 and target_graham_price_score <= 10)),
  add constraint user_watchlist_graham_quality_check  check (target_graham_quality_score is null or (target_graham_quality_score >= 0 and target_graham_quality_score <= 100));

-- ------------------------------------------------------------- foreign keys
alter table public.user_profiles       add constraint user_profiles_id_fkey foreign key (id) references auth.users(id) on delete cascade;
alter table public.company_listings    add constraint company_listings_company_id_fkey foreign key (company_id) references public.companies(id) on delete cascade;
alter table public.company_score_summary add constraint company_score_summary_company_id_fkey foreign key (company_id) references public.companies(id) on delete cascade;
alter table public.data_update_log     add constraint data_update_log_company_id_fkey foreign key (company_id) references public.companies(id) on delete set null;
alter table public.financial_yearly    add constraint financial_yearly_company_id_fkey foreign key (company_id) references public.companies(id) on delete restrict;
alter table public.financial_ratios    add constraint financial_ratios_financial_yearly_fkey foreign key (company_id, fiscal_year) references public.financial_yearly(company_id, fiscal_year) on delete cascade;
alter table public.market_snapshot     add constraint market_snapshot_company_id_fkey foreign key (company_id) references public.companies(id) on delete restrict;
alter table public.score_details       add constraint score_details_company_score_summary_fkey foreign key (company_id) references public.company_score_summary(company_id) on delete cascade;
alter table public.portfolios          add constraint portfolios_user_id_fkey foreign key (user_id) references public.user_profiles(id) on delete cascade;
alter table public.portfolio_holdings  add constraint portfolio_holdings_company_id_fkey foreign key (company_id) references public.companies(id) on delete restrict;
alter table public.portfolio_holdings  add constraint portfolio_holdings_portfolio_id_fkey foreign key (portfolio_id) references public.portfolios(id) on delete cascade;
alter table public.user_watchlist      add constraint user_watchlist_company_id_fkey foreign key (company_id) references public.companies(id) on delete restrict;
alter table public.user_watchlist      add constraint user_watchlist_user_id_fkey foreign key (user_id) references public.user_profiles(id) on delete cascade;

-- ----------------------------------------------------------------- indexes
-- (PK / UNIQUE constraint indexes are created by the constraints above)
create unique index company_listings_figi_unique on public.company_listings using btree (figi) where (figi is not null);
create unique index company_listings_one_primary_per_company on public.company_listings using btree (company_id) where (is_primary = true);
create index idx_company_listings_company_id on public.company_listings using btree (company_id);
create index idx_company_listings_isin on public.company_listings using btree (isin) where (isin is not null);
create index idx_company_listings_symbol on public.company_listings using btree (symbol);

-- ---------------------------------------------------------------- triggers
-- NOTE: only these 9 tables have an updated_at trigger in the live DB
-- (companies, company_listings and data_update_log have none).
create trigger set_financial_yearly_updated_at     before update on public.financial_yearly     for each row execute function public.set_updated_at();
create trigger set_market_snapshot_updated_at      before update on public.market_snapshot      for each row execute function public.set_updated_at();
create trigger set_company_score_summary_updated_at before update on public.company_score_summary for each row execute function public.set_updated_at();
create trigger set_score_details_updated_at        before update on public.score_details        for each row execute function public.set_updated_at();
create trigger set_financial_ratios_updated_at     before update on public.financial_ratios     for each row execute function public.set_updated_at();
create trigger set_user_profiles_updated_at        before update on public.user_profiles        for each row execute function public.set_updated_at();
create trigger set_portfolios_updated_at           before update on public.portfolios           for each row execute function public.set_updated_at();
create trigger set_portfolio_holdings_updated_at   before update on public.portfolio_holdings   for each row execute function public.set_updated_at();
create trigger set_user_watchlist_updated_at       before update on public.user_watchlist       for each row execute function public.set_updated_at();

-- ------------------------------------------------------------------- RPC
-- SECURITY INVOKER, no fixed search_path (advisor warning), EXECUTE open to
-- PUBLIC/anon/authenticated/service_role (default).
create or replace function public.create_company_with_listing(p_company jsonb, p_listing jsonb)
 returns jsonb
 language plpgsql
as $function$
declare
    v_company public.companies%rowtype;
    v_listing public.company_listings%rowtype;
    v_existing_listing public.company_listings%rowtype;
begin
    if nullif(trim(p_company->>'company_name'), '') is null then
        raise exception 'company_name is required';
    end if;

    if nullif(trim(p_company->>'country'), '') is null then
        raise exception 'country is required';
    end if;

    if nullif(trim(p_company->>'reporting_currency'), '') is null then
        raise exception 'reporting_currency is required';
    end if;

    if nullif(trim(p_listing->>'symbol'), '') is null then
        raise exception 'symbol is required';
    end if;

    if nullif(trim(p_listing->>'exchange'), '') is null then
        raise exception 'exchange is required';
    end if;

    select *
      into v_existing_listing
      from public.company_listings
     where symbol = upper(trim(p_listing->>'symbol'))
       and exchange = upper(trim(p_listing->>'exchange'))
     limit 1;

    if found then
        return jsonb_build_object(
            'resolution_outcome', 'RESOLVED_EXISTING',
            'company', (
                select to_jsonb(c)
                from public.companies c
                where c.id = v_existing_listing.company_id
            ),
            'listing', to_jsonb(v_existing_listing)
        );
    end if;

    insert into public.companies (
        symbol,
        company_name,
        exchange,
        country,
        reporting_currency,
        sector,
        industry,
        public_since_date,
        data_source,
        is_active
    )
    values (
        upper(trim(p_listing->>'symbol')),
        trim(p_company->>'company_name'),
        upper(trim(p_listing->>'exchange')),
        upper(trim(p_company->>'country')),
        upper(trim(p_company->>'reporting_currency')),
        nullif(trim(p_company->>'sector'), ''),
        nullif(trim(p_company->>'industry'), ''),
        nullif(p_company->>'public_since_date', '')::date,
        nullif(trim(p_company->>'data_source'), ''),
        coalesce((p_company->>'is_active')::boolean, true)
    )
    returning * into v_company;

    insert into public.company_listings (
        company_id,
        symbol,
        exchange,
        mic,
        trading_currency,
        security_type,
        share_class,
        is_adr,
        adr_ratio,
        isin,
        figi,
        share_class_figi,
        is_primary,
        listing_start_date,
        data_source,
        is_active
    )
    values (
        v_company.id,
        upper(trim(p_listing->>'symbol')),
        upper(trim(p_listing->>'exchange')),
        nullif(upper(trim(p_listing->>'mic')), ''),
        nullif(upper(trim(p_listing->>'trading_currency')), ''),
        nullif(trim(p_listing->>'security_type'), ''),
        nullif(trim(p_listing->>'share_class'), ''),
        nullif(p_listing->>'is_adr', '')::boolean,
        nullif(p_listing->>'adr_ratio', '')::numeric,
        nullif(upper(trim(p_listing->>'isin')), ''),
        nullif(upper(trim(p_listing->>'figi')), ''),
        nullif(upper(trim(p_listing->>'share_class_figi')), ''),
        coalesce((p_listing->>'is_primary')::boolean, true),
        nullif(p_listing->>'listing_start_date', '')::date,
        nullif(trim(p_listing->>'data_source'), ''),
        coalesce((p_listing->>'is_active')::boolean, true)
    )
    returning * into v_listing;

    return jsonb_build_object(
        'resolution_outcome', 'RESOLVED_NEW_COMPANY',
        'company', to_jsonb(v_company),
        'listing', to_jsonb(v_listing)
    );
exception
    when unique_violation then
        select *
          into v_existing_listing
          from public.company_listings
         where symbol = upper(trim(p_listing->>'symbol'))
           and exchange = upper(trim(p_listing->>'exchange'))
         limit 1;

        if found then
            return jsonb_build_object(
                'resolution_outcome', 'RESOLVED_EXISTING',
                'company', (
                    select to_jsonb(c)
                    from public.companies c
                    where c.id = v_existing_listing.company_id
                ),
                'listing', to_jsonb(v_existing_listing)
            );
        end if;

        raise;
end;
$function$;

-- ------------------------------------------------------------------- views
create or replace view public.stock_score_overview_view with (security_invoker=true) as
 select c.id as company_id,
    c.symbol,
    c.company_name,
    c.exchange,
    c.sector,
    c.industry,
    c.is_active,
    ms.market_date,
    ms.current_price,
    ms.price_currency,
    ms.market_cap,
    ms.fifty_two_week_high,
    ms.fifty_two_week_low,
    css.as_of_fiscal_year,
    css.years_available,
    css.buffett_quality_score,
    css.buffett_price_score,
    css.graham_quality_score,
    css.graham_price_score,
    css.updated_at as score_updated_at
   from public.companies c
     left join public.market_snapshot ms on ms.company_id = c.id
     left join public.company_score_summary css on css.company_id = c.id;

create or replace view public.financial_overview_view with (security_invoker=true) as
 select c.id as company_id,
    c.symbol,
    c.company_name,
    c.exchange,
    c.reporting_currency,
    c.sector,
    c.industry,
    fy.fiscal_year,
    fy.filing_date,
    fy.revenue,
    fy.net_income,
    fy.depreciation_and_amortization,
    fy.operating_cash_flow,
    fy.capex,
    fy.free_cash_flow,
    fy.dividends_per_share,
    fy.total_assets,
    fy.total_liabilities,
    fy.total_equity,
    fy.total_debt,
    fr.gross_margin,
    fr.operating_margin,
    fr.net_margin,
    fr.fcf_margin,
    fr.adjusted_fcf_margin,
    fr.roe,
    fr.roa,
    fr.roic,
    fr.fcf_to_net_income,
    fr.operating_cash_flow_to_net_income,
    fr.capex_to_revenue,
    fr.capex_to_operating_cash_flow,
    fr.adjusted_fcf_to_net_income,
    fr.working_capital,
    fr.revenue_growth_1y,
    fr.eps_growth_1y,
    fr.fcf_growth_1y,
    fr.revenue_cagr_3y,
    fr.eps_cagr_3y,
    fr.fcf_cagr_3y,
    fr.revenue_cagr_5y,
    fr.eps_cagr_5y,
    fr.fcf_cagr_5y,
    fy.source as financial_source,
    fr.calculation_version as ratios_calculation_version,
    fy.updated_at as financial_updated_at,
    fr.updated_at as ratios_updated_at
   from public.companies c
     join public.financial_yearly fy on fy.company_id = c.id
     left join public.financial_ratios fr on fr.company_id = fy.company_id and fr.fiscal_year = fy.fiscal_year;

create or replace view public.portfolio_overview_view with (security_invoker=true) as
 select p.user_id,
    p.id as portfolio_id,
    p.portfolio_name,
    ph.id as holding_id,
    c.symbol,
    c.company_name,
    c.exchange,
    c.country,
    c.reporting_currency,
    c.sector,
    c.industry,
    ph.quantity,
    ph.average_cost,
    ph.cost_currency,
    ph.first_buy_date,
    ms.current_price,
    ms.market_date,
        case
            when ms.current_price is not null then ph.quantity * ms.current_price
            else null::numeric
        end as current_value,
        case
            when ph.average_cost is not null then ph.quantity * ph.average_cost
            else null::numeric
        end as cost_basis,
        case
            when ph.average_cost is not null and ms.current_price is not null and ph.cost_currency is not null and ms.price_currency is not null and ph.cost_currency = ms.price_currency then ph.quantity * ms.current_price - ph.quantity * ph.average_cost
            else null::numeric
        end as unrealized_gain_loss,
        case
            when ph.average_cost is not null and ph.average_cost > 0::numeric and ms.current_price is not null and ph.cost_currency is not null and ms.price_currency is not null and ph.cost_currency = ms.price_currency then (ms.current_price - ph.average_cost) / ph.average_cost
            else null::numeric
        end as unrealized_gain_loss_percent,
    css.buffett_quality_score,
    css.buffett_price_score,
    css.graham_quality_score,
    css.graham_price_score
   from public.portfolios p
     join public.portfolio_holdings ph on ph.portfolio_id = p.id
     join public.companies c on c.id = ph.company_id
     left join public.market_snapshot ms on ms.company_id = c.id
     left join public.company_score_summary css on css.company_id = c.id;

create or replace view public.watchlist_overview_view with (security_invoker=true) as
 select uw.user_id,
    uw.id as watchlist_id,
    c.symbol,
    c.company_name,
    c.exchange,
    c.sector,
    c.industry,
    ms.current_price,
    ms.price_currency,
    ms.market_date,
    uw.target_buffett_quality_score,
    uw.target_buffett_price_score,
    uw.target_graham_quality_score,
    uw.target_graham_price_score,
    css.buffett_quality_score as current_buffett_quality_score,
    css.buffett_price_score as current_buffett_price_score,
    css.graham_quality_score as current_graham_quality_score,
    css.graham_price_score as current_graham_price_score,
        case
            when uw.target_buffett_quality_score is not null and css.buffett_quality_score is not null and css.buffett_quality_score < uw.target_buffett_quality_score then false
            when uw.target_buffett_price_score is not null and css.buffett_price_score is not null and css.buffett_price_score < uw.target_buffett_price_score then false
            when uw.target_graham_quality_score is not null and css.graham_quality_score is not null and css.graham_quality_score < uw.target_graham_quality_score then false
            when uw.target_graham_price_score is not null and css.graham_price_score is not null and css.graham_price_score < uw.target_graham_price_score then false
            when uw.target_buffett_quality_score is null and uw.target_buffett_price_score is null and uw.target_graham_quality_score is null and uw.target_graham_price_score is null then null::boolean
            else true
        end as meets_all_defined_targets,
    css.overall_status as score_status,
    uw.notes
   from public.user_watchlist uw
     join public.companies c on c.id = uw.company_id
     left join public.market_snapshot ms on ms.company_id = c.id
     left join public.company_score_summary css on css.company_id = c.id;

-- ---------------------------------------------------------------- comments
comment on column public.companies.symbol is 'Temporary compatibility field. Canonical trading symbols belong in company_listings and this column is planned for removal after backend migration.';
comment on column public.companies.exchange is 'Temporary compatibility field. Canonical exchange data belongs in company_listings and this column is planned for removal after backend migration.';
comment on column public.companies.reporting_currency is 'Currency used by the company/issuer for its financial reporting; distinct from company_listings.trading_currency.';
comment on column public.companies.public_since_date is 'Date from which the canonical issuer is considered publicly listed/public for financial-history coverage purposes.';
comment on column public.company_listings.trading_currency is 'Currency in which this listing trades; distinct from the company financial reporting currency.';
comment on column public.company_listings.adr_ratio is 'Number of underlying ordinary shares represented by one ADR when applicable.';
comment on column public.company_listings.is_primary is 'Whether this is the primary listing used by ValueCompass for the company.';
comment on column public.company_listings.listing_start_date is 'Date on which this specific exchange listing began trading; distinct from the issuer public_since_date.';
comment on column public.data_update_log.request_reference is 'Original company or security reference supplied to the synchronization workflow, useful when company resolution is ambiguous or fails.';
comment on column public.data_update_log.source_details is 'JSON array containing detailed source provenance for the synchronization run, including source names, URLs, roles, fiscal years, and supplementary fields when applicable.';
comment on column public.data_update_log.missing_years is 'Fiscal years that remained unresolved after the synchronization run.';

-- --------------------------------------------------------------------- RLS
alter table public.companies             enable row level security;
alter table public.company_listings      enable row level security;
alter table public.company_score_summary enable row level security;
alter table public.data_update_log       enable row level security;
alter table public.financial_ratios      enable row level security;
alter table public.financial_yearly      enable row level security;
alter table public.market_snapshot       enable row level security;
alter table public.portfolio_holdings    enable row level security;
alter table public.portfolios            enable row level security;
alter table public.score_details         enable row level security;
alter table public.user_profiles         enable row level security;
alter table public.user_watchlist        enable row level security;
-- (companies, company_listings, company_score_summary, data_update_log,
--  financial_ratios, financial_yearly, market_snapshot, score_details have
--  NO policies: closed to anon/authenticated, open only to service_role.)

-- policies are granted TO public (default when no TO clause) - as in the live DB
create policy "Users can view their own profile"   on public.user_profiles for select using (auth.uid() = id);
create policy "Users can insert their own profile" on public.user_profiles for insert with check (auth.uid() = id);
create policy "Users can update their own profile" on public.user_profiles for update using (auth.uid() = id) with check (auth.uid() = id);

create policy "Users can view their own portfolios"   on public.portfolios for select using (auth.uid() = user_id);
create policy "Users can insert their own portfolios" on public.portfolios for insert with check (auth.uid() = user_id);
create policy "Users can update their own portfolios" on public.portfolios for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can delete their own portfolios" on public.portfolios for delete using (auth.uid() = user_id);

create policy "Users can view holdings in their own portfolios" on public.portfolio_holdings for select
  using (exists (select 1 from public.portfolios where portfolios.id = portfolio_holdings.portfolio_id and portfolios.user_id = auth.uid()));
create policy "Users can insert holdings into their own portfolios" on public.portfolio_holdings for insert
  with check (exists (select 1 from public.portfolios where portfolios.id = portfolio_holdings.portfolio_id and portfolios.user_id = auth.uid()));
create policy "Users can update holdings in their own portfolios" on public.portfolio_holdings for update
  using (exists (select 1 from public.portfolios where portfolios.id = portfolio_holdings.portfolio_id and portfolios.user_id = auth.uid()))
  with check (exists (select 1 from public.portfolios where portfolios.id = portfolio_holdings.portfolio_id and portfolios.user_id = auth.uid()));
create policy "Users can delete holdings in their own portfolios" on public.portfolio_holdings for delete
  using (exists (select 1 from public.portfolios where portfolios.id = portfolio_holdings.portfolio_id and portfolios.user_id = auth.uid()));

create policy "Users can view their own watchlist"        on public.user_watchlist for select using (auth.uid() = user_id);
create policy "Users can insert into their own watchlist" on public.user_watchlist for insert with check (auth.uid() = user_id);
create policy "Users can update their own watchlist"      on public.user_watchlist for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Users can delete from their own watchlist" on public.user_watchlist for delete using (auth.uid() = user_id);

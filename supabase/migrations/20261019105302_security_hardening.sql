-- DB stage 1 / migration 1 of 8 - security hardening.
-- Source: scripts/db_stage0_2026-10-18.md (sections 2-4). Not applied yet.

-- 1. Excess privileges. Supabase defaults give anon/authenticated ALL (incl. TRUNCATE,
--    TRIGGER, REFERENCES) on every table and view. Remove everything, then grant back
--    only what the existing RLS policies and the app need.
revoke all on all tables in schema public from anon, authenticated;

-- New objects created by this role in schema public no longer get those default grants;
-- every later migration grants explicitly. service_role is untouched.
alter default privileges in schema public revoke all on tables from anon, authenticated;

-- user-owned tables: row access is still limited by the existing policies
grant select, insert, update          on public.user_profiles      to authenticated;
grant select, insert, update, delete  on public.portfolios         to authenticated;
grant select, insert, update, delete  on public.portfolio_holdings to authenticated;
grant select, insert, update, delete  on public.user_watchlist     to authenticated;

-- data tables: read only (writes go through service_role, which bypasses RLS)
grant select on public.companies             to authenticated;
grant select on public.company_listings      to authenticated;
grant select on public.market_snapshot       to authenticated;
grant select on public.company_score_summary to authenticated;
grant select on public.score_details         to authenticated;
-- financial_yearly / financial_ratios (empty, dropped in migration 8) and
-- data_update_log (internal) get no grant.

-- views are security_invoker, so they inherit the caller's RLS on the base tables
-- (financial_overview_view is dropped in migration 8)
grant select on public.stock_score_overview_view to authenticated;
grant select on public.portfolio_overview_view   to authenticated;
grant select on public.watchlist_overview_view   to authenticated;

-- 2. RPC: service role only
revoke execute on function public.create_company_with_listing(jsonb, jsonb) from public, anon, authenticated;

-- 3. Fixed search_path (bodies only use pg_catalog functions and schema-qualified tables)
alter function public.set_updated_at() set search_path = '';
alter function public.create_company_with_listing(jsonb, jsonb) set search_path = '';

-- 4. auth.uid() -> (select auth.uid()) in the 15 policies (evaluated once per statement),
--    and restrict them to authenticated (they were TO public).
alter policy "Users can view their own profile"   on public.user_profiles
  to authenticated using ((select auth.uid()) = id);
alter policy "Users can insert their own profile" on public.user_profiles
  to authenticated with check ((select auth.uid()) = id);
alter policy "Users can update their own profile" on public.user_profiles
  to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

alter policy "Users can view their own portfolios"   on public.portfolios
  to authenticated using ((select auth.uid()) = user_id);
alter policy "Users can insert their own portfolios" on public.portfolios
  to authenticated with check ((select auth.uid()) = user_id);
alter policy "Users can update their own portfolios" on public.portfolios
  to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
alter policy "Users can delete their own portfolios" on public.portfolios
  to authenticated using ((select auth.uid()) = user_id);

alter policy "Users can view holdings in their own portfolios" on public.portfolio_holdings
  to authenticated using (exists (select 1 from public.portfolios p
    where p.id = portfolio_holdings.portfolio_id and p.user_id = (select auth.uid())));
alter policy "Users can insert holdings into their own portfolios" on public.portfolio_holdings
  to authenticated with check (exists (select 1 from public.portfolios p
    where p.id = portfolio_holdings.portfolio_id and p.user_id = (select auth.uid())));
alter policy "Users can update holdings in their own portfolios" on public.portfolio_holdings
  to authenticated
  using (exists (select 1 from public.portfolios p
    where p.id = portfolio_holdings.portfolio_id and p.user_id = (select auth.uid())))
  with check (exists (select 1 from public.portfolios p
    where p.id = portfolio_holdings.portfolio_id and p.user_id = (select auth.uid())));
alter policy "Users can delete holdings in their own portfolios" on public.portfolio_holdings
  to authenticated using (exists (select 1 from public.portfolios p
    where p.id = portfolio_holdings.portfolio_id and p.user_id = (select auth.uid())));

alter policy "Users can view their own watchlist"        on public.user_watchlist
  to authenticated using ((select auth.uid()) = user_id);
alter policy "Users can insert into their own watchlist" on public.user_watchlist
  to authenticated with check ((select auth.uid()) = user_id);
alter policy "Users can update their own watchlist"      on public.user_watchlist
  to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
alter policy "Users can delete from their own watchlist" on public.user_watchlist
  to authenticated using ((select auth.uid()) = user_id);

-- 5. Indexes for the 4 unindexed foreign keys
create index if not exists idx_data_update_log_company_id     on public.data_update_log (company_id);
create index if not exists idx_portfolio_holdings_company_id  on public.portfolio_holdings (company_id);
create index if not exists idx_portfolios_user_id             on public.portfolios (user_id);
create index if not exists idx_user_watchlist_company_id      on public.user_watchlist (company_id);

-- 6. SELECT policies for authenticated on the data tables (they had RLS and no policy)
create policy "companies_select_authenticated"             on public.companies             for select to authenticated using (true);
create policy "company_listings_select_authenticated"      on public.company_listings      for select to authenticated using (true);
create policy "market_snapshot_select_authenticated"       on public.market_snapshot       for select to authenticated using (true);
create policy "company_score_summary_select_authenticated" on public.company_score_summary for select to authenticated using (true);
create policy "score_details_select_authenticated"         on public.score_details         for select to authenticated using (true);

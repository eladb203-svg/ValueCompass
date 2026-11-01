-- Security stage / migration 2 - tables closed (spec 3a): no table privilege at all for anon and authenticated.
-- The pipeline and the server functions use the service role, which is not affected. Existing RLS policies stay as a second line of defence.
-- Before this migration authenticated could read: 20 data tables (see scripts/code_stage_security report) and read/write user_profiles, portfolios,
-- portfolio_holdings, user_watchlist; plus 9 views (3 overview + 6 internal).

revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;

alter default privileges in schema public revoke all on tables    from anon, authenticated;
alter default privileges in schema public revoke all on sequences from anon, authenticated;
alter default privileges in schema public revoke all on functions from anon, authenticated;

-- the old per-user overview views are replaced by v_my_portfolio / v_my_watchlist / v_stock_page (migration 5)

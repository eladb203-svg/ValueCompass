-- Gives authenticated back what it had before the lockdown (migration 20261019105302 grants). anon stays without privileges.
grant select, insert, update          on public.user_profiles      to authenticated;
grant select, insert, update, delete  on public.portfolios         to authenticated;
grant select, insert, update, delete  on public.portfolio_holdings to authenticated;
grant select, insert, update, delete  on public.user_watchlist     to authenticated;
grant select on public.companies, public.company_listings, public.market_snapshot, public.company_score_summary, public.score_details,
  public.ai_assessments, public.ai_texts, public.business_vocab, public.company_business_profiles, public.company_profile_history, public.dictionary_items,
  public.extraction_items, public.fact_tags, public.filing_periods, public.financial_facts, public.fx_rates, public.gov_yields, public.score_runs,
  public.term_translations, public.valuations, public.stock_score_overview_view, public.portfolio_overview_view, public.watchlist_overview_view,
  public.v_company_status, public.v_display_metrics, public.v_fin_bank, public.v_fin_insurance, public.v_fin_realestate, public.v_fin_standard to authenticated;

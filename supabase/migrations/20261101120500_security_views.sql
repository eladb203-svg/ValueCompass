-- Security stage / migration 5 (views, after the tickets rework) - the read-only views of spec 3a (the only thing an active user can read).
-- Every view: owner-run (security_invoker off), filtered by is_active(); personal views also by auth.uid().
-- A table or view that is not on this list is invisible to users.
-- Stock data shown = companies the pipeline finished scoring (scored_partial / ai_in_progress / complete); texts only when approval_status = 'approved'.

-- v_stocks: company list for search
create view public.v_stocks with (security_invoker = false) as
select c.id as company_id, c.symbol, c.company_name,
       bp.display_name,
       c.exchange, c.country,
       coalesce(c.industry_override, c.vc_industry, c.industry) as industry,
       c.sector, c.profile, c.processing_state, c.unsupported_reason
from public.companies c
left join lateral (
  select b.display_name from public.company_business_profiles b
  where b.company_id = c.id order by b.fiscal_year desc, b.id desc limit 1
) bp on true
where public.is_active() and coalesce(c.is_active, true);

-- v_stock_page: one row per stock for the stock page
create view public.v_stock_page with (security_invoker = false) as
select c.id as company_id, c.symbol, c.company_name, bp.display_name, c.exchange, c.country, c.sector,
       coalesce(c.industry_override, c.vc_industry, c.industry) as industry,
       c.profile, c.processing_state, c.reporting_currency,
       -- market
       m.current_price, m.price_currency, m.market_cap, m.fifty_two_week_high, m.fifty_two_week_low, m.market_date, m.last_price_at, m.is_stale,
       -- scores, fair values, buy prices
       s.as_of_fiscal_year, s.overall_status, s.rulebook_version,
       s.buffett_quality_score, s.buffett_price_score, s.graham_quality_score, s.graham_price_score,
       s.buffett_quality_coverage, s.graham_quality_coverage,
       s.buffett_fair_value, s.graham_fair_value, s.buffett_buy_price, s.graham_buy_price,
       s.updated_at as scored_at,
       r.run_at as score_run_at, r.price_date as score_price_date,
       -- business profile (display only)
       bp.core_activity, bp.segments, bp.products_services, bp.regions, bp.founded, bp.listed_since,
       -- price determination per model (method and components as stored)
       (select jsonb_agg(jsonb_build_object('model', v.model, 'method', v.method, 'fair_value', v.fair_value, 'price_score', v.price_score,
                'price_state', v.price_state, 'margin_of_safety', v.margin_of_safety, 'buy_price', v.buy_price, 'buy_price_state', v.buy_price_state,
                'details', v.details) order by v.model, v.method)
          from public.valuations v where v.run_id = s.latest_run_id) as valuations,
       -- the eight criteria per model: name and score only
       (select jsonb_agg(jsonb_build_object('model', d.model, 'score_type', d.score_type, 'key', d.criterion_key, 'name', d.criterion_name,
                'score', d.criterion_score, 'max_score', d.max_score, 'status', d.score_status) order by d.model, d.score_type, d.criterion_key)
          from public.score_details d where d.run_id = s.latest_run_id and d.detail_level = 'criterion') as criteria,
       -- display metrics per fiscal year (six charts)
       (select jsonb_agg(to_jsonb(dm) - 'company_id' order by dm.fiscal_year)
          from public.v_display_metrics dm where dm.company_id = c.id) as metrics,
       -- approved texts: the latest fiscal year per kind and language
       (select jsonb_agg(jsonb_build_object('kind', t.kind, 'language', t.language, 'fiscal_year', t.fiscal_year, 'text', t.text, 'human_reviewed', t.human_reviewed))
          from (select distinct on (x.kind, x.language) x.* from public.ai_texts x
                where x.company_id = c.id and x.approval_status = 'approved'
                order by x.kind, x.language, x.fiscal_year desc, x.prompt_version desc) t) as texts
from public.companies c
join public.company_score_summary s on s.company_id = c.id
left join public.market_snapshot m on m.company_id = c.id
left join public.score_runs r on r.id = s.latest_run_id
left join lateral (
  select b.* from public.company_business_profiles b where b.company_id = c.id order by b.fiscal_year desc, b.id desc limit 1
) bp on true
where public.is_active() and coalesce(c.is_active, true)
  and c.processing_state in ('scored_partial', 'ai_in_progress', 'complete');

-- v_top_ranked: Display Spec 3.3. One row per (rank_type, sector scope, country scope, rank <= 5).
-- sector_scope / country_scope NULL = no filter; the screen picks the scope it needs (where sector_scope is not distinct from ...).
create view public.v_top_ranked with (security_invoker = false) as
with base as (
  select c.id as company_id, c.symbol, c.company_name,
         coalesce(c.industry_override, c.vc_industry, c.industry) as sector, c.country,
         s.buffett_quality_score as bq, s.buffett_price_score as bp, s.graham_quality_score as gq, s.graham_price_score as gp
  from public.companies c
  join public.company_score_summary s on s.company_id = c.id
  where coalesce(c.is_active, true) and c.processing_state in ('scored_partial', 'ai_in_progress', 'complete')
),
scored as (
  select b.*, sc.sector_scope, sc.country_scope, t.rank_type, t.score
  from base b
  cross join lateral (values (null::text, null::text), (b.sector, null::text), (null::text, b.country), (b.sector, b.country)) sc(sector_scope, country_scope)
  cross join lateral (values
      ('combined', case when b.bq is not null and b.bp is not null and b.gq is not null and b.gp is not null then (b.bq + b.bp * 10 + b.gq + b.gp * 10) / 4 end),
      ('buffett_quality', b.bq), ('buffett_price', b.bp), ('graham_quality', b.gq), ('graham_price', b.gp)
  ) t(rank_type, score)
  where t.score is not null
),
ranked as (
  select scored.*, row_number() over (partition by rank_type, sector_scope, country_scope order by score desc, company_id) as rank
  from scored
)
select rank_type, sector_scope, country_scope, rank::integer as rank, company_id, symbol, company_name, sector, country, round(score::numeric, 2) as score,
       bq as buffett_quality_score, bp as buffett_price_score, gq as graham_quality_score, gp as graham_price_score
from ranked
where rank <= 5 and public.is_active();

-- personal views: own rows only
create view public.v_my_profile with (security_invoker = false) as
select p.id as user_id, p.full_name, p.preferred_language, p.role, p.status
from public.user_profiles p
where p.id = (select auth.uid()) and p.status in ('active', 'pending');   -- pending users read their own status (the waiting screen); disabled see nothing

create view public.v_my_portfolio with (security_invoker = false) as
select pf.id as portfolio_id, pf.portfolio_name, h.id as holding_id, h.company_id, c.symbol, c.company_name,
       h.quantity, h.average_cost, h.cost_currency, h.first_buy_date, h.notes, m.current_price, m.price_currency
from public.portfolios pf
left join public.portfolio_holdings h on h.portfolio_id = pf.id
left join public.companies c on c.id = h.company_id
left join public.market_snapshot m on m.company_id = h.company_id
where public.is_active() and pf.user_id = (select auth.uid());

create view public.v_my_watchlist with (security_invoker = false) as
select w.id as watch_id, w.company_id, c.symbol, c.company_name,
       w.target_buffett_quality_score, w.target_buffett_price_score, w.target_graham_quality_score, w.target_graham_price_score, w.notes, w.created_at,
       m.current_price, s.buffett_buy_price, s.graham_buy_price
from public.user_watchlist w
join public.companies c on c.id = w.company_id
left join public.market_snapshot m on m.company_id = w.company_id
left join public.company_score_summary s on s.company_id = w.company_id
where public.is_active() and w.user_id = (select auth.uid());

create view public.v_my_tickets with (security_invoker = false) as
select t.id as ticket_id, t.type, t.body, t.requested_ticker, t.status, t.fail_reason, t.admin_reply, t.replied_at, t.created_at, t.updated_at, t.closed_at
from public.support_tickets t
where public.is_active() and t.user_id = (select auth.uid());

create view public.v_my_notifications with (security_invoker = false) as
select n.id as notification_id, n.type, n.text, n.link, n.created_at, n.read_at
from public.user_notifications n
where public.is_active() and n.user_id = (select auth.uid())
order by (n.read_at is not null), n.created_at desc;

-- read-only, active users only (the is_active() filter hides everything from anyone else; anon gets no privilege at all)
grant select on public.v_stocks, public.v_stock_page, public.v_top_ranked, public.v_my_profile, public.v_my_portfolio,
  public.v_my_watchlist, public.v_my_tickets, public.v_my_notifications to authenticated;

-- internal view: the scheduler (service role) only
revoke all on public.v_holding_counts from anon, authenticated;
grant select on public.v_holding_counts to service_role;

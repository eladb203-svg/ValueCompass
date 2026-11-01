-- Security stage / migration 8 - v_stock_page reads v_display_metrics -> v_fin_*. Those were security_invoker views (they ran with the caller's rights);
-- a user has no table rights any more, so they would fail inside v_stock_page. They are not granted to users; making them owner-run is safe.
-- A later migration that recreates these views must keep security_invoker = false.
alter view public.v_display_metrics set (security_invoker = false);
alter view public.v_fin_standard set (security_invoker = false);
alter view public.v_fin_bank set (security_invoker = false);
alter view public.v_fin_insurance set (security_invoker = false);
alter view public.v_fin_realestate set (security_invoker = false);

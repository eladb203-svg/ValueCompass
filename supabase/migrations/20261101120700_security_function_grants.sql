-- Security stage / migration 7 - functions called inside the views are checked against the CALLING role (not the view owner),
-- so authenticated needs EXECUTE on is_active() / is_admin(). They return only the caller's own state. anon stays without it.
grant execute on function public.is_active(), public.is_admin() to authenticated;
revoke execute on function public.set_updated_at() from public, anon, authenticated;   -- trigger function, was executable through PUBLIC

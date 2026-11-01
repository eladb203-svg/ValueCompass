-- Security stage / migration 6 - smart-search global daily cap. Atomic: true = a call may use the model, false = cap reached (regular search answers).
create function public.smart_search_take() returns boolean
language plpgsql security definer set search_path = '' as $$
declare v_cap integer; v_calls integer;
begin
  select value::integer into v_cap from public.app_settings where key = 'smart_search_daily_cap';
  insert into public.smart_search_usage as u (day, calls) values (current_date, 1)
  on conflict (day) do update set calls = u.calls + 1 where u.calls < coalesce(v_cap, 0)
  returning calls into v_calls;
  return v_calls is not null;
end $$;
revoke execute on function public.smart_search_take() from public, anon, authenticated;
grant execute on function public.smart_search_take() to service_role;

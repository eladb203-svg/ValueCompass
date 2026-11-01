-- Security stage / migration 1 - users, settings, audit, tickets, notifications (spec 2026-11-01_10-20, sections 3a and 8).
-- Test project first. Users never write these tables: the server functions (service role) and the triggers below do.

-- 1. app_settings (key/value, service role only)
create table public.app_settings (
  key        text primary key,
  value      text not null,
  updated_at timestamptz not null default now()
);
alter table public.app_settings enable row level security;
insert into public.app_settings (key, value) values
  ('registration_mode', 'invite'),
  ('admin_email', 'eladb203@gmail.com'),
  ('smart_search_daily_cap', '200');

-- 2. user_profiles extended: role, status, invited_by
alter table public.user_profiles
  add column role text not null default 'user' check (role in ('user', 'admin')),
  add column status text not null default 'pending' check (status in ('pending', 'active', 'disabled')),
  add column invited_by uuid references auth.users (id) on delete set null;
-- rows that exist before this migration belong to people already using the system
update public.user_profiles set status = 'active';

-- the user has no insert/update right on the profile any more (privileges are revoked in migration 2; the policies go too)
drop policy "Users can insert their own profile" on public.user_profiles;
drop policy "Users can update their own profile" on public.user_profiles;

-- second line of defence: even a role with write privileges cannot change role / status / invited_by
create function public.user_profiles_guard() returns trigger
language plpgsql set search_path = '' as $$
begin
  if current_user in ('anon', 'authenticated')
     and (new.role is distinct from old.role or new.status is distinct from old.status or new.invited_by is distinct from old.invited_by) then
    raise exception 'role and status are changed by the admin only';
  end if;
  return new;
end $$;
create trigger user_profiles_guard before update on public.user_profiles
  for each row execute function public.user_profiles_guard();

-- 3. is_admin() / is_active(): the caller's own state
create function public.is_active() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.user_profiles p where p.id = (select auth.uid()) and p.status = 'active')
$$;
create function public.is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.user_profiles p where p.id = (select auth.uid()) and p.status = 'active' and p.role = 'admin')
$$;

-- 4. sign-up trigger: invited email -> active; open mode -> pending; invite mode without an invitation -> disabled.
--    The admin role goes only to the invited admin_email. Role never comes from user-supplied metadata.
create function public.handle_new_auth_user() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_mode text; v_admin text; v_status text; v_role text := 'user'; v_by uuid := null;
begin
  select value into v_mode from public.app_settings where key = 'registration_mode';
  select lower(value) into v_admin from public.app_settings where key = 'admin_email';
  if new.invited_at is not null then
    v_status := 'active';
    if lower(new.email) = v_admin then v_role := 'admin'; end if;
    begin
      select u.id into v_by from auth.users u where u.id = nullif(new.raw_user_meta_data ->> 'invited_by', '')::uuid;
    exception when others then v_by := null;
    end;
  elsif v_mode = 'open' then
    v_status := 'pending';
  else
    v_status := 'disabled';
  end if;
  insert into public.user_profiles (id, full_name, role, status, invited_by)
  values (new.id, nullif(new.raw_user_meta_data ->> 'full_name', ''), v_role, v_status, v_by)
  on conflict (id) do nothing;
  return new;
end $$;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_auth_user();

-- 5. support_tickets (no direct access: written by support-send, read through v_my_tickets or the admin function)
create table public.support_tickets (
  id               bigint generated always as identity primary key,
  user_id          uuid not null references auth.users (id) on delete cascade,
  kind             text not null check (kind in ('fault', 'request')),
  body             text not null check (length(body) between 1 and 5000),
  tech             jsonb not null default '{}'::jsonb,
  portfolio_attach jsonb,
  status           text not null default 'open' check (status in ('open', 'in_progress', 'closed')),
  admin_reply      text,
  replied_at       timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index idx_support_tickets_user_id on public.support_tickets (user_id);
alter table public.support_tickets enable row level security;
create trigger set_support_tickets_updated_at before update on public.support_tickets
  for each row execute function public.set_updated_at();

-- 6. user_notifications (written by triggers and server functions only)
create table public.user_notifications (
  id         bigint generated always as identity primary key,
  user_id    uuid not null references auth.users (id) on delete cascade,
  type       text not null check (type in ('ticket_reply', 'ticket_status', 'company_ready', 'company_failed')),
  text       text not null,
  link       text,
  created_at timestamptz not null default now(),
  read_at    timestamptz
);
create index idx_user_notifications_user on public.user_notifications (user_id, read_at, created_at desc);
alter table public.user_notifications enable row level security;

-- 7. company_requests: who asked for a company (so the user is told when it is ready)
create table public.company_requests (
  id             bigint generated always as identity primary key,
  user_id        uuid not null references auth.users (id) on delete cascade,
  company_id     bigint not null references public.companies (id) on delete cascade,
  requested_at   timestamptz not null default now(),
  notified_state text,
  unique (user_id, company_id)
);
create index idx_company_requests_company on public.company_requests (company_id);
alter table public.company_requests enable row level security;

-- 8. admin_audit_log
create table public.admin_audit_log (
  id          bigint generated always as identity primary key,
  admin_id    uuid,
  action      text not null,
  target_type text,
  target_id   text,
  before      jsonb,
  after       jsonb,
  created_at  timestamptz not null default now()
);
create index idx_admin_audit_log_created on public.admin_audit_log (created_at desc);
alter table public.admin_audit_log enable row level security;

-- 9. smart-search daily counter (service role only)
create table public.smart_search_usage (
  day   date primary key,
  calls integer not null default 0
);
alter table public.smart_search_usage enable row level security;

-- 10. notification triggers
-- 10a. admin reply / status change on a ticket -> a notification for the ticket owner only
create function public.notify_ticket_change() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.admin_reply is not null and new.admin_reply is distinct from old.admin_reply then
    insert into public.user_notifications (user_id, type, text, link)
    values (new.user_id, 'ticket_reply', 'התקבלה תשובה לפנייה שלך', '/tickets/' || new.id);
  elsif new.status is distinct from old.status then
    insert into public.user_notifications (user_id, type, text, link)
    values (new.user_id, 'ticket_status', 'מצב הפנייה שלך השתנה: ' || case new.status when 'open' then 'פתוחה' when 'in_progress' then 'בטיפול' else 'סגורה' end, '/tickets/' || new.id);
  end if;
  return new;
end $$;
create trigger notify_ticket_change after update on public.support_tickets
  for each row execute function public.notify_ticket_change();

-- 10b. a requested company reaches complete / failed / unsupported -> a notification for each requester, once per state.
--      Lives in the database, so the runner code does not change.
create function public.notify_company_state() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.processing_state in ('complete', 'failed', 'unsupported') and new.processing_state is distinct from old.processing_state then
    insert into public.user_notifications (user_id, type, text, link)
    select r.user_id,
           case when new.processing_state = 'complete' then 'company_ready' else 'company_failed' end,
           case when new.processing_state = 'complete' then 'המניה ' || new.symbol || ' מוכנה'
                when new.processing_state = 'unsupported' then 'המניה ' || new.symbol || ' אינה נתמכת כרגע' || coalesce(': ' || new.unsupported_reason, '')
                else 'לא הצלחנו להשלים את עיבוד המניה ' || new.symbol end,
           '/stocks/' || new.symbol
    from public.company_requests r
    where r.company_id = new.id and r.notified_state is distinct from new.processing_state;
    update public.company_requests set notified_state = new.processing_state where company_id = new.id;
  end if;
  return new;
end $$;
create trigger notify_company_state after update of processing_state on public.companies
  for each row execute function public.notify_company_state();

-- 11. v_holding_counts: how many portfolios / watchlists hold each company. No user ids. Service role only (scheduler, admin function).
create view public.v_holding_counts as
select company_id,
       count(*) filter (where src = 'portfolio')::integer as in_portfolios,
       count(*) filter (where src = 'watchlist')::integer as in_watchlists,
       count(*)::integer as total
from (
  select company_id, 'portfolio' as src from public.portfolio_holdings
  union all
  select company_id, 'watchlist' from public.user_watchlist
) h
group by company_id;

-- 12. helper functions are not callable by the API roles
revoke execute on function public.is_active(), public.is_admin(), public.handle_new_auth_user(),
  public.user_profiles_guard(), public.notify_ticket_change(), public.notify_company_state() from public, anon, authenticated;
grant execute on function public.is_active(), public.is_admin() to service_role;

-- Security stage / migration 4 - support_tickets also holds company requests (decided 2026-11-01, addition to 1.5).
-- type: support / bug / company_request. A company_request replaces the separate company_requests table.
-- Company request status follows the runner automatically: in_progress -> done | failed(+reason). Every status change creates a notification.
-- Retention (weekly cleanup): closed tickets deleted 180 days after closed_at, notifications 180 days after created_at.

drop trigger notify_company_state on public.companies;
drop function public.notify_company_state();
drop trigger notify_ticket_change on public.support_tickets;
drop function public.notify_ticket_change();
drop table public.company_requests;

alter table public.support_tickets rename column kind to type;
alter table public.support_tickets drop constraint support_tickets_kind_check;
alter table public.support_tickets drop constraint support_tickets_status_check;
alter table public.support_tickets
  add column requested_ticker text,
  add column company_id bigint references public.companies (id) on delete set null,
  add column fail_reason text,
  add column closed_at timestamptz,
  add constraint support_tickets_type_check check (type in ('support', 'bug', 'company_request')),
  add constraint support_tickets_status_check check (
    (type = 'company_request' and status in ('open', 'in_progress', 'done', 'failed'))
    or (type <> 'company_request' and status in ('open', 'in_progress', 'closed'))),
  add constraint support_tickets_request_ticker check (type <> 'company_request' or requested_ticker is not null);
alter table public.support_tickets alter column body drop not null;
alter table public.support_tickets drop constraint support_tickets_body_check;
alter table public.support_tickets add constraint support_tickets_body_check check (body is null or length(body) <= 5000);
create unique index uq_support_tickets_open_request on public.support_tickets (user_id, requested_ticker)
  where type = 'company_request' and status in ('open', 'in_progress');
create index idx_support_tickets_company on public.support_tickets (company_id) where company_id is not null;

alter table public.user_notifications drop constraint user_notifications_type_check;
alter table public.user_notifications add constraint user_notifications_type_check
  check (type in ('ticket_reply', 'ticket_status', 'company_started', 'company_ready', 'company_failed'));

-- closed_at follows the status
create function public.tickets_before_write() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.status in ('closed', 'done', 'failed') then
    if tg_op = 'INSERT' or old.status not in ('closed', 'done', 'failed') then new.closed_at := now(); end if;
  else
    new.closed_at := null;
  end if;
  return new;
end $$;
create trigger tickets_before_write before insert or update on public.support_tickets
  for each row execute function public.tickets_before_write();

-- every reply / status change -> a notification for the ticket owner only
create function public.notify_ticket_change() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_label text := coalesce(new.requested_ticker, '');
begin
  if new.admin_reply is not null and new.admin_reply is distinct from old.admin_reply then
    insert into public.user_notifications (user_id, type, text, link)
    values (new.user_id, 'ticket_reply', 'התקבלה תשובה לפנייה שלך', '/tickets/' || new.id);
  end if;
  if new.status is distinct from old.status then
    if new.type = 'company_request' then
      insert into public.user_notifications (user_id, type, text, link) values (
        new.user_id,
        case new.status when 'done' then 'company_ready' when 'failed' then 'company_failed' else 'company_started' end,
        case new.status when 'done' then 'המניה ' || v_label || ' מוכנה'
                        when 'failed' then 'לא הצלחנו להוסיף את המניה ' || v_label || coalesce(': ' || new.fail_reason, '')
                        else 'המניה ' || v_label || ' בעיבוד — תושלם בהמשך' end,
        '/stocks/' || v_label);
    else
      insert into public.user_notifications (user_id, type, text, link) values (
        new.user_id, 'ticket_status',
        'מצב הפנייה שלך השתנה: ' || case new.status when 'open' then 'פתוחה' when 'in_progress' then 'בטיפול' else 'סגורה' end,
        '/tickets/' || new.id);
    end if;
  end if;
  return new;
end $$;
create trigger notify_ticket_change after update on public.support_tickets
  for each row execute function public.notify_ticket_change();

-- the runner moves the company state; the matching open company requests follow (no runner code change)
create function public.sync_company_requests() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if new.processing_state is not distinct from old.processing_state then return new; end if;
  if new.processing_state = 'complete' then
    update public.support_tickets set status = 'done', fail_reason = null
    where type = 'company_request' and status in ('open', 'in_progress') and (company_id = new.id or (company_id is null and upper(requested_ticker) = upper(new.symbol)));
  elsif new.processing_state in ('failed', 'unsupported') then
    update public.support_tickets set status = 'failed',
      fail_reason = coalesce(new.unsupported_reason, case new.processing_state when 'unsupported' then 'חברה שאינה נתמכת' else 'העיבוד נכשל' end)
    where type = 'company_request' and status in ('open', 'in_progress') and (company_id = new.id or (company_id is null and upper(requested_ticker) = upper(new.symbol)));
  elsif new.processing_state in ('resolved', 'data_loaded', 'scored_partial', 'ai_in_progress') then
    update public.support_tickets set status = 'in_progress', company_id = new.id
    where type = 'company_request' and status = 'open' and (company_id = new.id or (company_id is null and upper(requested_ticker) = upper(new.symbol)));
  end if;
  return new;
end $$;
create trigger sync_company_requests after update of processing_state on public.companies
  for each row execute function public.sync_company_requests();

-- weekly retention, called by the cleanup job (service role)
create function public.security_retention(p_days integer default 180) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare t integer; n integer;
begin
  delete from public.support_tickets where status in ('closed', 'done', 'failed') and closed_at < now() - make_interval(days => p_days);
  get diagnostics t = row_count;
  delete from public.user_notifications where created_at < now() - make_interval(days => p_days);
  get diagnostics n = row_count;
  return jsonb_build_object('tickets', t, 'notifications', n);
end $$;

revoke execute on function public.tickets_before_write(), public.notify_ticket_change(), public.sync_company_requests(), public.security_retention(integer)
  from public, anon, authenticated;
grant execute on function public.security_retention(integer) to service_role;

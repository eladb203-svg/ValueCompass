-- Security stage / migration 9 - sign-up requests (spec 1.1 update of 2026-11-01): open-with-approval is the default.
-- A visitor sends name + email (no password) to signup-request; it is saved as a support_tickets row of type 'signup' with no owner (no account yet).
-- The admin approves (admin-tickets -> invitation email, status done) or rejects (status closed, no email).

update public.app_settings set value = 'open', updated_at = now() where key = 'registration_mode';

alter table public.support_tickets alter column user_id drop not null;
alter table public.support_tickets
  add column signup_name text,
  add column signup_email text,
  add column ip_hash text;
alter table public.support_tickets drop constraint support_tickets_type_check;
alter table public.support_tickets drop constraint support_tickets_status_check;
alter table public.support_tickets
  add constraint support_tickets_type_check check (type in ('support', 'bug', 'company_request', 'signup')),
  add constraint support_tickets_status_check check (
    (type = 'company_request' and status in ('open', 'in_progress', 'done', 'failed'))
    or (type = 'signup' and status in ('open', 'done', 'closed'))
    or (type in ('support', 'bug') and status in ('open', 'in_progress', 'closed'))),
  add constraint support_tickets_owner check ((type = 'signup' and user_id is null and signup_email is not null and signup_name is not null) or (type <> 'signup' and user_id is not null)),
  add constraint support_tickets_signup_lengths check (signup_name is null or (length(signup_name) between 1 and 100 and length(signup_email) between 3 and 200));
create index idx_support_tickets_signup_email on public.support_tickets (signup_email, created_at) where type = 'signup';
create index idx_support_tickets_signup_ip on public.support_tickets (ip_hash, created_at) where type = 'signup';

-- a signup request has no owner, so no notification
create or replace function public.notify_ticket_change() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_label text := coalesce(new.requested_ticker, '');
begin
  if new.user_id is null then return new; end if;
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

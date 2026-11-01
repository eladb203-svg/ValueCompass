-- Rollback of migration 9: drops the signup requests and restores the earlier constraints.
delete from public.support_tickets where type = 'signup';
drop index public.idx_support_tickets_signup_email, public.idx_support_tickets_signup_ip;
alter table public.support_tickets
  drop constraint support_tickets_signup_lengths, drop constraint support_tickets_owner,
  drop constraint support_tickets_status_check, drop constraint support_tickets_type_check,
  drop column signup_name, drop column signup_email, drop column ip_hash;
alter table public.support_tickets alter column user_id set not null;
alter table public.support_tickets
  add constraint support_tickets_type_check check (type in ('support', 'bug', 'company_request')),
  add constraint support_tickets_status_check check (
    (type = 'company_request' and status in ('open', 'in_progress', 'done', 'failed'))
    or (type <> 'company_request' and status in ('open', 'in_progress', 'closed')));
update public.app_settings set value = 'invite', updated_at = now() where key = 'registration_mode';
create or replace function public.notify_ticket_change() returns trigger
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

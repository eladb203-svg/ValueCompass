-- Back to the state after migration 3 (tickets with `kind`, company_requests table). Drops any company_request rows.
drop trigger if exists sync_company_requests on public.companies;
drop function if exists public.sync_company_requests();
drop function if exists public.security_retention(integer);
drop trigger if exists notify_ticket_change on public.support_tickets;
drop function if exists public.notify_ticket_change();
drop trigger if exists tickets_before_write on public.support_tickets;
drop function if exists public.tickets_before_write();
delete from public.user_notifications where type = 'company_started';
delete from public.support_tickets where type = 'company_request';
drop index if exists public.uq_support_tickets_open_request, public.idx_support_tickets_company;
alter table public.user_notifications drop constraint user_notifications_type_check;
alter table public.user_notifications add constraint user_notifications_type_check check (type in ('ticket_reply','ticket_status','company_ready','company_failed'));
alter table public.support_tickets drop constraint support_tickets_type_check, drop constraint support_tickets_status_check, drop constraint support_tickets_request_ticker, drop constraint support_tickets_body_check;
alter table public.support_tickets drop column requested_ticker, drop column company_id, drop column fail_reason, drop column closed_at;
update public.support_tickets set body = '' where body is null;
alter table public.support_tickets alter column body set not null;
alter table public.support_tickets add constraint support_tickets_body_check check (length(body) between 1 and 5000);
alter table public.support_tickets rename column type to kind;
update public.support_tickets set kind = 'fault' where kind = 'bug';
update public.support_tickets set kind = 'request' where kind = 'support';
alter table public.support_tickets add constraint support_tickets_kind_check check (kind in ('fault','request'));
alter table public.support_tickets add constraint support_tickets_status_check check (status in ('open','in_progress','closed'));
create table public.company_requests (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  company_id bigint not null references public.companies (id) on delete cascade,
  requested_at timestamptz not null default now(), notified_state text, unique (user_id, company_id));
alter table public.company_requests enable row level security;

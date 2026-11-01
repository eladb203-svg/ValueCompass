-- Security stage / migration 10 - the invitation sets invited_at AFTER the auth.users row is inserted (found with a real invitation from the dashboard).
-- on_auth_user_created sees invited_at = null, so the invited user got status=disabled. This trigger finishes the job when invited_at goes from null to a value:
-- active; admin only for app_settings.admin_email; invited_by and the name from the invitation metadata.
-- It touches only a profile that is still disabled/pending and that no admin has changed (an admin change is in admin_audit_log; the invite itself is not a change).
create function public.handle_invited_auth_user() returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_admin text; v_by uuid := null;
begin
  select lower(value) into v_admin from public.app_settings where key = 'admin_email';
  begin
    select u.id into v_by from auth.users u where u.id = nullif(new.raw_user_meta_data ->> 'invited_by', '')::uuid;
  exception when others then v_by := null;
  end;
  update public.user_profiles p set
    status = 'active',
    role = case when lower(new.email) = v_admin then 'admin' else p.role end,
    invited_by = coalesce(v_by, p.invited_by),
    full_name = coalesce(nullif(new.raw_user_meta_data ->> 'full_name', ''), p.full_name)
  where p.id = new.id
    and p.status in ('disabled', 'pending')
    and not exists (select 1 from public.admin_audit_log a where a.target_type = 'user' and a.target_id = new.id::text and a.action <> 'invite');
  return new;
end $$;
revoke execute on function public.handle_invited_auth_user() from public, anon, authenticated;
create trigger on_auth_user_invited after update of invited_at on auth.users
  for each row when (old.invited_at is null and new.invited_at is not null)
  execute function public.handle_invited_auth_user();

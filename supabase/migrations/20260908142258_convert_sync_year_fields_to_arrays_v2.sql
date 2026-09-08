alter table public.data_update_log
    drop constraint if exists data_update_log_years_requested_check,
    drop constraint if exists data_update_log_years_imported_check;

alter table public.data_update_log
alter column years_requested type smallint[]
using (
    case
        when update_scope = 'METADATA_REPAIR'
             and years_requested = 0
            then '{}'::smallint[]
        else null::smallint[]
    end
);

alter table public.data_update_log
alter column years_imported type smallint[]
using null::smallint[];

alter table public.data_update_log
    add constraint data_update_log_years_requested_check
        check (
            years_requested is null
            or cardinality(years_requested) <= 20
        ),
    add constraint data_update_log_years_imported_check
        check (
            years_imported is null
            or cardinality(years_imported) <= 20
        );

-- Run on the test (and later production) project: lists every privilege anon / authenticated hold in schema public.
-- Expected result after the security stage: exactly the 8 views of spec 3a with SELECT for authenticated, and execute on is_active / is_admin for authenticated. Nothing else.
select 'relation' as kind, c.relname || ' ' || r.rolname || ' ' || p.priv as grant_
from pg_class c join pg_namespace n on n.oid = c.relnamespace and n.nspname = 'public' and c.relkind in ('r', 'v', 'm', 'p')
cross join (values ('anon'), ('authenticated')) r(rolname)
cross join (values ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')) p(priv)
where has_table_privilege(r.rolname, c.oid, p.priv)
union all
select 'function', p.proname || ' ' || r.rolname from pg_proc p join pg_namespace n on n.oid = p.pronamespace and n.nspname = 'public'
cross join (values ('anon'), ('authenticated')) r(rolname) where has_function_privilege(r.rolname, p.oid, 'EXECUTE') and p.prokind = 'f'
union all
select 'sequence', c.relname || ' ' || r.rolname from pg_class c join pg_namespace n on n.oid = c.relnamespace and n.nspname = 'public' and c.relkind = 'S'
cross join (values ('anon'), ('authenticated')) r(rolname) where has_sequence_privilege(r.rolname, c.oid, 'USAGE') or has_sequence_privilege(r.rolname, c.oid, 'SELECT')
order by 1, 2;

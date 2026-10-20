-- תורץ בק5 עם מספר גרסה חדש
-- לא להריץ עד שלב הקוד — יחד עם שכתוב src/repositories/financial_repository.py ל-financial_facts
-- DB stage 1 / migration 8 of 8 - drop financial_yearly and financial_ratios (replaced by financial_facts
-- and v_display_metrics). Aborts if either table has rows.

lock table public.financial_ratios, public.financial_yearly in access exclusive mode;

do $$
declare
  n_yearly  bigint;
  n_ratios  bigint;
begin
  select count(*) into n_yearly from public.financial_yearly;
  select count(*) into n_ratios from public.financial_ratios;
  if n_yearly > 0 or n_ratios > 0 then
    raise exception 'drop_legacy aborted: financial_yearly has % rows, financial_ratios has % rows (both must be empty)',
      n_yearly, n_ratios;
  end if;
end $$;

-- dependants first; no CASCADE, so anything unexpected makes the migration fail instead of vanishing
drop view  public.financial_overview_view;   -- joins both tables
drop table public.financial_ratios;          -- FK to financial_yearly
drop table public.financial_yearly;          -- takes its updated_at trigger and checks with it

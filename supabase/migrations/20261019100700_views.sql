-- DB stage 1 / migration 7 of 8 - profile views for the engine and the display view.
-- The v_fin_* views are for reference and simple uses only. The scoring engine reads financial_facts
-- directly (value + status + flags), because these views expose the value only.
-- security_invoker = true: the caller's RLS on financial_facts / dictionary_items / companies applies.
-- One column per item_key = value of that component (null = no row = missing, or not_applicable).

-- STANDARD and TECH_ASSET_LIGHT: common fields (2.1) + 2.2
create or replace view public.v_fin_standard with (security_invoker = true) as
select
    f.company_id,
    f.fiscal_year,
    c.profile,
    max(f.value) filter (where d.item_key = 'income_tax') as income_tax,
    max(f.value) filter (where d.item_key = 'pretax_income') as pretax_income,
    max(f.value) filter (where d.item_key = 'equity') as equity,
    max(f.value) filter (where d.item_key = 'financial_debt') as financial_debt,
    max(f.value) filter (where d.item_key = 'cash') as cash,
    max(f.value) filter (where d.item_key = 'short_term_investments') as short_term_investments,
    max(f.value) filter (where d.item_key = 'net_income') as net_income,
    max(f.value) filter (where d.item_key = 'preferred_dividends') as preferred_dividends,
    max(f.value) filter (where d.item_key = 'preferred_stock') as preferred_stock,
    max(f.value) filter (where d.item_key = 'goodwill') as goodwill,
    max(f.value) filter (where d.item_key = 'intangibles') as intangibles,
    max(f.value) filter (where d.item_key = 'total_assets') as total_assets,
    max(f.value) filter (where d.item_key = 'goodwill_impairment') as goodwill_impairment,
    max(f.value) filter (where d.item_key = 'interest_expense') as interest_expense,
    max(f.value) filter (where d.item_key = 'revenue') as revenue,
    max(f.value) filter (where d.item_key = 'eps_diluted') as eps_diluted,
    max(f.value) filter (where d.item_key = 'cfo') as cfo,
    max(f.value) filter (where d.item_key = 'capex') as capex,
    max(f.value) filter (where d.item_key = 'da') as da,
    max(f.value) filter (where d.item_key = 'sbc') as sbc,
    max(f.value) filter (where d.item_key = 'dividends_paid') as dividends_paid,
    max(f.value) filter (where d.item_key = 'buybacks') as buybacks,
    max(f.value) filter (where d.item_key = 'acquisitions') as acquisitions,
    max(f.value) filter (where d.item_key = 'avg_share_price') as avg_share_price,
    max(f.value) filter (where d.item_key = 'shares_period_end') as shares_period_end,
    max(f.value) filter (where d.item_key = 'shares_diluted_weighted') as shares_diluted_weighted,
    max(f.value) filter (where d.item_key = 'dps') as dps,
    max(f.value) filter (where d.item_key = 'long_term_debt') as long_term_debt,
    max(f.value) filter (where d.item_key = 'goodwill_acquired') as goodwill_acquired,
    max(f.value) filter (where d.item_key = 'total_liabilities') as total_liabilities,
    max(f.value) filter (where d.item_key = 'cover_shares') as cover_shares,
    max(f.value) filter (where d.item_key = 'shares_basic_weighted') as shares_basic_weighted,
    max(f.value) filter (where d.item_key = 'pretax_domestic') as pretax_domestic,
    max(f.value) filter (where d.item_key = 'pretax_foreign') as pretax_foreign,
    max(f.value) filter (where d.item_key = 'net_income_common') as net_income_common,
    max(f.value) filter (where d.item_key = 'profit_loss') as profit_loss,
    max(f.value) filter (where d.item_key = 'nci_income') as nci_income,
    max(f.value) filter (where d.item_key = 'discontinued_ops') as discontinued_ops,
    max(f.value) filter (where d.item_key = 'ebit') as ebit,
    max(f.value) filter (where d.item_key = 'cost_of_revenue') as cost_of_revenue,
    max(f.value) filter (where d.item_key = 'gross_profit') as gross_profit,
    max(f.value) filter (where d.item_key = 'acq_amortization') as acq_amortization,
    max(f.value) filter (where d.item_key = 'current_assets') as current_assets,
    max(f.value) filter (where d.item_key = 'current_liabilities') as current_liabilities,
    max(f.value) filter (where d.item_key = 'deferred_revenue_current') as deferred_revenue_current,
    max(f.value) filter (where d.item_key = 'receivables') as receivables,
    max(f.value) filter (where d.item_key = 'funds_held_for_clients') as funds_held_for_clients,
    max(f.value) filter (where d.item_key = 'restricted_cash') as restricted_cash,
    max(f.value) filter (where d.item_key = 'depreciation') as depreciation,
    max(f.value) filter (where d.item_key = 'finance_lease_rou_amort') as finance_lease_rou_amort,
    max(f.value) filter (where d.item_key = 'noncurrent_marketable_debt') as noncurrent_marketable_debt,
    max(f.value) filter (where d.item_key = 'claims_expense') as claims_expense
from public.financial_facts f
join public.dictionary_items d on d.id = f.item_id
join public.companies c on c.id = f.company_id
where c.profile in ('STANDARD','TECH_ASSET_LIGHT')
group by f.company_id, f.fiscal_year, c.profile;
grant select on public.v_fin_standard to authenticated;

-- BANK: common fields (2.1) + 2.3
create or replace view public.v_fin_bank with (security_invoker = true) as
select
    f.company_id,
    f.fiscal_year,
    c.profile,
    max(f.value) filter (where d.item_key = 'income_tax') as income_tax,
    max(f.value) filter (where d.item_key = 'pretax_income') as pretax_income,
    max(f.value) filter (where d.item_key = 'equity') as equity,
    max(f.value) filter (where d.item_key = 'financial_debt') as financial_debt,
    max(f.value) filter (where d.item_key = 'cash') as cash,
    max(f.value) filter (where d.item_key = 'short_term_investments') as short_term_investments,
    max(f.value) filter (where d.item_key = 'net_income') as net_income,
    max(f.value) filter (where d.item_key = 'preferred_dividends') as preferred_dividends,
    max(f.value) filter (where d.item_key = 'preferred_stock') as preferred_stock,
    max(f.value) filter (where d.item_key = 'goodwill') as goodwill,
    max(f.value) filter (where d.item_key = 'intangibles') as intangibles,
    max(f.value) filter (where d.item_key = 'total_assets') as total_assets,
    max(f.value) filter (where d.item_key = 'goodwill_impairment') as goodwill_impairment,
    max(f.value) filter (where d.item_key = 'interest_expense') as interest_expense,
    max(f.value) filter (where d.item_key = 'revenue') as revenue,
    max(f.value) filter (where d.item_key = 'eps_diluted') as eps_diluted,
    max(f.value) filter (where d.item_key = 'cfo') as cfo,
    max(f.value) filter (where d.item_key = 'capex') as capex,
    max(f.value) filter (where d.item_key = 'da') as da,
    max(f.value) filter (where d.item_key = 'sbc') as sbc,
    max(f.value) filter (where d.item_key = 'dividends_paid') as dividends_paid,
    max(f.value) filter (where d.item_key = 'buybacks') as buybacks,
    max(f.value) filter (where d.item_key = 'acquisitions') as acquisitions,
    max(f.value) filter (where d.item_key = 'avg_share_price') as avg_share_price,
    max(f.value) filter (where d.item_key = 'shares_period_end') as shares_period_end,
    max(f.value) filter (where d.item_key = 'shares_diluted_weighted') as shares_diluted_weighted,
    max(f.value) filter (where d.item_key = 'dps') as dps,
    max(f.value) filter (where d.item_key = 'long_term_debt') as long_term_debt,
    max(f.value) filter (where d.item_key = 'goodwill_acquired') as goodwill_acquired,
    max(f.value) filter (where d.item_key = 'total_liabilities') as total_liabilities,
    max(f.value) filter (where d.item_key = 'cover_shares') as cover_shares,
    max(f.value) filter (where d.item_key = 'shares_basic_weighted') as shares_basic_weighted,
    max(f.value) filter (where d.item_key = 'pretax_domestic') as pretax_domestic,
    max(f.value) filter (where d.item_key = 'pretax_foreign') as pretax_foreign,
    max(f.value) filter (where d.item_key = 'net_income_common') as net_income_common,
    max(f.value) filter (where d.item_key = 'profit_loss') as profit_loss,
    max(f.value) filter (where d.item_key = 'nci_income') as nci_income,
    max(f.value) filter (where d.item_key = 'discontinued_ops') as discontinued_ops,
    max(f.value) filter (where d.item_key = 'net_interest_income') as net_interest_income,
    max(f.value) filter (where d.item_key = 'noninterest_income') as noninterest_income,
    max(f.value) filter (where d.item_key = 'provision_credit_losses') as provision_credit_losses,
    max(f.value) filter (where d.item_key = 'loans') as loans,
    max(f.value) filter (where d.item_key = 'deposits') as deposits,
    max(f.value) filter (where d.item_key = 'nco') as nco,
    max(f.value) filter (where d.item_key = 'acl') as acl,
    max(f.value) filter (where d.item_key = 'nonaccrual_loans') as nonaccrual_loans,
    max(f.value) filter (where d.item_key = 'cet1_ratio_standardized') as cet1_ratio_standardized,
    max(f.value) filter (where d.item_key = 'cet1_ratio_advanced') as cet1_ratio_advanced,
    max(f.value) filter (where d.item_key = 'cet1_required_standardized') as cet1_required_standardized,
    max(f.value) filter (where d.item_key = 'cet1_required_advanced') as cet1_required_advanced,
    max(f.value) filter (where d.item_key = 'lcr_q4_average') as lcr_q4_average,
    max(f.value) filter (where d.item_key = 'st_borrowings') as st_borrowings,
    max(f.value) filter (where d.item_key = 'fhlb_advances') as fhlb_advances,
    max(f.value) filter (where d.item_key = 'repo_securities_lending') as repo_securities_lending,
    max(f.value) filter (where d.item_key = 'loans_residential_mortgage') as loans_residential_mortgage,
    max(f.value) filter (where d.item_key = 'loans_cre_construction') as loans_cre_construction,
    max(f.value) filter (where d.item_key = 'loans_ci') as loans_ci,
    max(f.value) filter (where d.item_key = 'loans_consumer') as loans_consumer,
    max(f.value) filter (where d.item_key = 'loans_other') as loans_other,
    max(f.value) filter (where d.item_key = 'total_capital_standardized') as total_capital_standardized,
    max(f.value) filter (where d.item_key = 'total_capital_advanced') as total_capital_advanced,
    max(f.value) filter (where d.item_key = 'rwa_standardized') as rwa_standardized,
    max(f.value) filter (where d.item_key = 'rwa_advanced') as rwa_advanced,
    max(f.value) filter (where d.item_key = 'past_due_90_accruing') as past_due_90_accruing,
    max(f.value) filter (where d.item_key = 'uninsured_deposits') as uninsured_deposits,
    max(f.value) filter (where d.item_key = 'scb') as scb,
    max(f.value) filter (where d.item_key = 'gsib_surcharge') as gsib_surcharge
from public.financial_facts f
join public.dictionary_items d on d.id = f.item_id
join public.companies c on c.id = f.company_id
where c.profile in ('BANK')
group by f.company_id, f.fiscal_year, c.profile;
grant select on public.v_fin_bank to authenticated;

-- INSURANCE: common fields (2.1) + 2.4 + derived DRV-004..006
create or replace view public.v_fin_insurance with (security_invoker = true) as
select
    f.company_id,
    f.fiscal_year,
    c.profile,
    max(f.value) filter (where d.item_key = 'income_tax') as income_tax,
    max(f.value) filter (where d.item_key = 'pretax_income') as pretax_income,
    max(f.value) filter (where d.item_key = 'equity') as equity,
    max(f.value) filter (where d.item_key = 'financial_debt') as financial_debt,
    max(f.value) filter (where d.item_key = 'cash') as cash,
    max(f.value) filter (where d.item_key = 'short_term_investments') as short_term_investments,
    max(f.value) filter (where d.item_key = 'net_income') as net_income,
    max(f.value) filter (where d.item_key = 'preferred_dividends') as preferred_dividends,
    max(f.value) filter (where d.item_key = 'preferred_stock') as preferred_stock,
    max(f.value) filter (where d.item_key = 'goodwill') as goodwill,
    max(f.value) filter (where d.item_key = 'intangibles') as intangibles,
    max(f.value) filter (where d.item_key = 'total_assets') as total_assets,
    max(f.value) filter (where d.item_key = 'goodwill_impairment') as goodwill_impairment,
    max(f.value) filter (where d.item_key = 'interest_expense') as interest_expense,
    max(f.value) filter (where d.item_key = 'revenue') as revenue,
    max(f.value) filter (where d.item_key = 'eps_diluted') as eps_diluted,
    max(f.value) filter (where d.item_key = 'cfo') as cfo,
    max(f.value) filter (where d.item_key = 'capex') as capex,
    max(f.value) filter (where d.item_key = 'da') as da,
    max(f.value) filter (where d.item_key = 'sbc') as sbc,
    max(f.value) filter (where d.item_key = 'dividends_paid') as dividends_paid,
    max(f.value) filter (where d.item_key = 'buybacks') as buybacks,
    max(f.value) filter (where d.item_key = 'acquisitions') as acquisitions,
    max(f.value) filter (where d.item_key = 'avg_share_price') as avg_share_price,
    max(f.value) filter (where d.item_key = 'shares_period_end') as shares_period_end,
    max(f.value) filter (where d.item_key = 'shares_diluted_weighted') as shares_diluted_weighted,
    max(f.value) filter (where d.item_key = 'dps') as dps,
    max(f.value) filter (where d.item_key = 'long_term_debt') as long_term_debt,
    max(f.value) filter (where d.item_key = 'goodwill_acquired') as goodwill_acquired,
    max(f.value) filter (where d.item_key = 'total_liabilities') as total_liabilities,
    max(f.value) filter (where d.item_key = 'cover_shares') as cover_shares,
    max(f.value) filter (where d.item_key = 'shares_basic_weighted') as shares_basic_weighted,
    max(f.value) filter (where d.item_key = 'pretax_domestic') as pretax_domestic,
    max(f.value) filter (where d.item_key = 'pretax_foreign') as pretax_foreign,
    max(f.value) filter (where d.item_key = 'net_income_common') as net_income_common,
    max(f.value) filter (where d.item_key = 'profit_loss') as profit_loss,
    max(f.value) filter (where d.item_key = 'nci_income') as nci_income,
    max(f.value) filter (where d.item_key = 'discontinued_ops') as discontinued_ops,
    max(f.value) filter (where d.item_key = 'investment_gains') as investment_gains,
    max(f.value) filter (where d.item_key = 'mrb_change') as mrb_change,
    max(f.value) filter (where d.item_key = 'aoci_afs') as aoci_afs,
    max(f.value) filter (where d.item_key = 'aoci_discount_rate') as aoci_discount_rate,
    max(f.value) filter (where d.item_key = 'aoci_own_credit') as aoci_own_credit,
    max(f.value) filter (where d.item_key = 'aoci_fx') as aoci_fx,
    max(f.value) filter (where d.item_key = 'aoci_pension') as aoci_pension,
    max(f.value) filter (where d.item_key = 'insurance_revenue') as insurance_revenue,
    max(f.value) filter (where d.item_key = 'claims_benefits') as claims_benefits,
    max(f.value) filter (where d.item_key = 'non_claims_uw_expenses') as non_claims_uw_expenses,
    max(f.value) filter (where d.item_key = 'interest_credited') as interest_credited,
    max(f.value) filter (where d.item_key = 'fpb_accretion') as fpb_accretion,
    max(f.value) filter (where d.item_key = 'claims_gross') as claims_gross,
    max(f.value) filter (where d.item_key = 'claims_net') as claims_net,
    max(f.value) filter (where d.item_key = 'reins_unpaid') as reins_unpaid,
    max(f.value) filter (where d.item_key = 'fpb') as fpb,
    max(f.value) filter (where d.item_key = 'pab') as pab,
    max(f.value) filter (where d.item_key = 'unearned') as unearned,
    max(f.value) filter (where d.item_key = 'reins_prepaid') as reins_prepaid,
    max(f.value) filter (where d.item_key = 'aoci_total') as aoci_total,
    max(f.value) filter (where d.item_key = 'reg_capital_ratio') as reg_capital_ratio,
    max(f.value) filter (where d.item_key = 'prior_year_dev') as prior_year_dev,
    max(f.value) filter (where d.item_key = 'ldti_remeasurement') as ldti_remeasurement,
    max(f.value) filter (where d.item_key = 'fpb_adverse_development') as fpb_adverse_development,
    max(f.value) filter (where d.item_key = 'inv_cash') as inv_cash,
    max(f.value) filter (where d.item_key = 'inv_short_term') as inv_short_term,
    max(f.value) filter (where d.item_key = 'inv_fixed_maturities') as inv_fixed_maturities,
    max(f.value) filter (where d.item_key = 'inv_equity') as inv_equity,
    max(f.value) filter (where d.item_key = 'inv_illiquid_loans') as inv_illiquid_loans,
    max(f.value) filter (where d.item_key = 'inv_real_estate') as inv_real_estate,
    max(f.value) filter (where d.item_key = 'inv_other') as inv_other,
    max(f.value) filter (where d.item_key = 'inv_ig_fixed') as inv_ig_fixed,
    max(f.value) filter (where d.item_key = 'inv_ig_share') as inv_ig_share,
    max(f.value) filter (where d.item_key = 'divestiture_proceeds') as divestiture_proceeds,
    max(f.value) filter (where d.item_key = 'deconsolidation_cash') as deconsolidation_cash,
    max(f.value) filter (where d.item_key = 'goodwill_written_off_sale') as goodwill_written_off_sale,
    max(f.value) filter (where d.item_key = 'separate_accounts') as separate_accounts,
    max(f.value) filter (where d.item_key = 'mrb_liability') as mrb_liability,
    max(f.value) filter (where d.item_key = 'investments_total') as investments_total,
    max(f.value) filter (where d.item_key = 'cat_loss_latest') as cat_loss_latest,
    max(f.value) filter (where d.item_key = 'alm_disclosed') as alm_disclosed,
    max(f.value) filter (where d.item_key = 'op_profit_norm_after_tax') as op_profit_norm_after_tax,
    max(f.value) filter (where d.item_key = 'adjusted_equity') as adjusted_equity,
    max(f.value) filter (where d.item_key = 'eps_operating') as eps_operating
from public.financial_facts f
join public.dictionary_items d on d.id = f.item_id
join public.companies c on c.id = f.company_id
where c.profile in ('INSURANCE')
group by f.company_id, f.fiscal_year, c.profile;
grant select on public.v_fin_insurance to authenticated;

-- INCOME_REAL_ESTATE: common fields (2.1) + 2.5 + derived FIN-070, DRV-001..003
create or replace view public.v_fin_realestate with (security_invoker = true) as
select
    f.company_id,
    f.fiscal_year,
    c.profile,
    max(f.value) filter (where d.item_key = 'income_tax') as income_tax,
    max(f.value) filter (where d.item_key = 'pretax_income') as pretax_income,
    max(f.value) filter (where d.item_key = 'equity') as equity,
    max(f.value) filter (where d.item_key = 'financial_debt') as financial_debt,
    max(f.value) filter (where d.item_key = 'cash') as cash,
    max(f.value) filter (where d.item_key = 'short_term_investments') as short_term_investments,
    max(f.value) filter (where d.item_key = 'net_income') as net_income,
    max(f.value) filter (where d.item_key = 'preferred_dividends') as preferred_dividends,
    max(f.value) filter (where d.item_key = 'preferred_stock') as preferred_stock,
    max(f.value) filter (where d.item_key = 'goodwill') as goodwill,
    max(f.value) filter (where d.item_key = 'intangibles') as intangibles,
    max(f.value) filter (where d.item_key = 'total_assets') as total_assets,
    max(f.value) filter (where d.item_key = 'goodwill_impairment') as goodwill_impairment,
    max(f.value) filter (where d.item_key = 'interest_expense') as interest_expense,
    max(f.value) filter (where d.item_key = 'revenue') as revenue,
    max(f.value) filter (where d.item_key = 'eps_diluted') as eps_diluted,
    max(f.value) filter (where d.item_key = 'cfo') as cfo,
    max(f.value) filter (where d.item_key = 'capex') as capex,
    max(f.value) filter (where d.item_key = 'da') as da,
    max(f.value) filter (where d.item_key = 'sbc') as sbc,
    max(f.value) filter (where d.item_key = 'dividends_paid') as dividends_paid,
    max(f.value) filter (where d.item_key = 'buybacks') as buybacks,
    max(f.value) filter (where d.item_key = 'acquisitions') as acquisitions,
    max(f.value) filter (where d.item_key = 'avg_share_price') as avg_share_price,
    max(f.value) filter (where d.item_key = 'shares_period_end') as shares_period_end,
    max(f.value) filter (where d.item_key = 'shares_diluted_weighted') as shares_diluted_weighted,
    max(f.value) filter (where d.item_key = 'dps') as dps,
    max(f.value) filter (where d.item_key = 'long_term_debt') as long_term_debt,
    max(f.value) filter (where d.item_key = 'goodwill_acquired') as goodwill_acquired,
    max(f.value) filter (where d.item_key = 'total_liabilities') as total_liabilities,
    max(f.value) filter (where d.item_key = 'cover_shares') as cover_shares,
    max(f.value) filter (where d.item_key = 'shares_basic_weighted') as shares_basic_weighted,
    max(f.value) filter (where d.item_key = 'pretax_domestic') as pretax_domestic,
    max(f.value) filter (where d.item_key = 'pretax_foreign') as pretax_foreign,
    max(f.value) filter (where d.item_key = 'net_income_common') as net_income_common,
    max(f.value) filter (where d.item_key = 'profit_loss') as profit_loss,
    max(f.value) filter (where d.item_key = 'nci_income') as nci_income,
    max(f.value) filter (where d.item_key = 'discontinued_ops') as discontinued_ops,
    max(f.value) filter (where d.item_key = 'rental_revenue') as rental_revenue,
    max(f.value) filter (where d.item_key = 'other_property_revenue') as other_property_revenue,
    max(f.value) filter (where d.item_key = 'property_opex') as property_opex,
    max(f.value) filter (where d.item_key = 'acquisition_yield') as acquisition_yield,
    max(f.value) filter (where d.item_key = 'development_yield') as development_yield,
    max(f.value) filter (where d.item_key = 'acquisition_invested') as acquisition_invested,
    max(f.value) filter (where d.item_key = 'development_invested') as development_invested,
    max(f.value) filter (where d.item_key = 'same_property_noi_growth') as same_property_noi_growth,
    max(f.value) filter (where d.item_key = 'acq_real_estate') as acq_real_estate,
    max(f.value) filter (where d.item_key = 'acq_business') as acq_business,
    max(f.value) filter (where d.item_key = 'development_spend') as development_spend,
    max(f.value) filter (where d.item_key = 'capital_improvements') as capital_improvements,
    max(f.value) filter (where d.item_key = 'sale_proceeds') as sale_proceeds,
    max(f.value) filter (where d.item_key = 're_gross') as re_gross,
    max(f.value) filter (where d.item_key = 're_net') as re_net,
    max(f.value) filter (where d.item_key = 'straight_line_rent') as straight_line_rent,
    max(f.value) filter (where d.item_key = 'maint_capex') as maint_capex,
    max(f.value) filter (where d.item_key = 'ti_lc') as ti_lc,
    max(f.value) filter (where d.item_key = 'gains_sale') as gains_sale,
    max(f.value) filter (where d.item_key = 'impairment') as impairment,
    max(f.value) filter (where d.item_key = 'fair_value_real_estate') as fair_value_real_estate,
    max(f.value) filter (where d.item_key = 'committed_undrawn_facilities') as committed_undrawn_facilities,
    max(f.value) filter (where d.item_key = 'debt_maturity_year1') as debt_maturity_year1,
    max(f.value) filter (where d.item_key = 'debt_maturity_year2') as debt_maturity_year2,
    max(f.value) filter (where d.item_key = 'unencumbered_noi_share') as unencumbered_noi_share,
    max(f.value) filter (where d.item_key = 'unencumbered_assets_share') as unencumbered_assets_share,
    max(f.value) filter (where d.item_key = 'stabilized_noi') as stabilized_noi,
    max(f.value) filter (where d.item_key = 'stabilized_value') as stabilized_value,
    max(f.value) filter (where d.item_key = 'other_property_value') as other_property_value,
    max(f.value) filter (where d.item_key = 'occupancy') as occupancy,
    max(f.value) filter (where d.item_key = 'largest_tenant_share') as largest_tenant_share,
    max(f.value) filter (where d.item_key = 'bsa_noi') as bsa_noi,
    max(f.value) filter (where d.item_key = 'bsa_carry') as bsa_carry,
    max(f.value) filter (where d.item_key = 'bsa_carryfin') as bsa_carryfin,
    max(f.value) filter (where d.item_key = 'bsa_inre') as bsa_inre,
    max(f.value) filter (where d.item_key = 'bsa_wc') as bsa_wc,
    max(f.value) filter (where d.item_key = 'bsa_excl') as bsa_excl,
    max(f.value) filter (where d.item_key = 'bsa_other') as bsa_other,
    max(f.value) filter (where d.item_key = 'nci_total') as nci_total,
    max(f.value) filter (where d.item_key = 'nci_op') as nci_op,
    max(f.value) filter (where d.item_key = 'nci_lp') as nci_lp,
    max(f.value) filter (where d.item_key = 'nci_redeemable') as nci_redeemable,
    max(f.value) filter (where d.item_key = 'op_units_count') as op_units_count,
    max(f.value) filter (where d.item_key = 'op_units_book_value') as op_units_book_value,
    max(f.value) filter (where d.item_key = 'real_estate_tax') as real_estate_tax,
    max(f.value) filter (where d.item_key = 'repairs_maintenance') as repairs_maintenance,
    max(f.value) filter (where d.item_key = 'gains_re_entities') as gains_re_entities,
    max(f.value) filter (where d.item_key = 'fx_unrealized') as fx_unrealized,
    max(f.value) filter (where d.item_key = 're29b_fx_net') as re29b_fx_net,
    max(f.value) filter (where d.item_key = 'debt_extinguishment') as debt_extinguishment,
    max(f.value) filter (where d.item_key = 'transaction_costs') as transaction_costs,
    max(f.value) filter (where d.item_key = 're29_re_sale_gains') as re29_re_sale_gains,
    max(f.value) filter (where d.item_key = 're29_nonre_impairments') as re29_nonre_impairments,
    max(f.value) filter (where d.item_key = 're29a_nonre_inv') as re29a_nonre_inv,
    max(f.value) filter (where d.item_key = 'dev_gains_reported') as dev_gains_reported,
    max(f.value) filter (where d.item_key = 'recon_net_income') as recon_net_income,
    max(f.value) filter (where d.item_key = 'recon_re_da') as recon_re_da,
    max(f.value) filter (where d.item_key = 'recon_nci_jv') as recon_nci_jv,
    max(f.value) filter (where d.item_key = 'recon_gi_net') as recon_gi_net,
    max(f.value) filter (where d.item_key = 'reported_ffo') as reported_ffo,
    max(f.value) filter (where d.item_key = 'reported_core_ffo') as reported_core_ffo,
    max(f.value) filter (where d.item_key = 'reported_affo') as reported_affo,
    max(f.value) filter (where d.item_key = 'reported_ebitdare') as reported_ebitdare,
    max(f.value) filter (where d.item_key = 'equity_method_inv') as equity_method_inv,
    max(f.value) filter (where d.item_key = 'cip') as cip,
    max(f.value) filter (where d.item_key = 're_dev_land') as re_dev_land,
    max(f.value) filter (where d.item_key = 'pref_equity') as pref_equity,
    max(f.value) filter (where d.item_key = 'finance_lease_liab') as finance_lease_liab,
    max(f.value) filter (where d.item_key = 'profile_total_assets') as profile_total_assets,
    max(f.value) filter (where d.item_key = 'profile_property_value') as profile_property_value,
    max(f.value) filter (where d.item_key = 'profile_rental_revenue') as profile_rental_revenue,
    max(f.value) filter (where d.item_key = 'profile_total_revenue') as profile_total_revenue,
    max(f.value) filter (where d.item_key = 'shares_basis_override') as shares_basis_override,
    max(f.value) filter (where d.item_key = 'inc_share_of_bplp') as inc_share_of_bplp,
    max(f.value) filter (where d.item_key = 'partnership_units_weighted') as partnership_units_weighted,
    max(f.value) filter (where d.item_key = 'diluted_includes_op') as diluted_includes_op,
    max(f.value) filter (where d.item_key = 'secured_debt') as secured_debt,
    max(f.value) filter (where d.item_key = 'ffo_normalized') as ffo_normalized,
    max(f.value) filter (where d.item_key = 'ffo_per_share') as ffo_per_share,
    max(f.value) filter (where d.item_key = 'owner_earnings') as owner_earnings,
    max(f.value) filter (where d.item_key = 'owner_earnings_per_share') as owner_earnings_per_share,
    max(f.value) filter (where d.item_key = 'ebitdare') as ebitdare
from public.financial_facts f
join public.dictionary_items d on d.id = f.item_id
join public.companies c on c.id = f.company_id
where c.profile in ('INCOME_REAL_ESTATE')
group by f.company_id, f.fiscal_year, c.profile;
grant select on public.v_fin_realestate to authenticated;

-- v_display_metrics: the six key metrics per company and fiscal year (Display Spec part 1).
-- Display only - never feeds a score. The company's profile selects the definition.
-- Per metric: value, label (names the metric actually shown), state:
--   ok | missing (an input has no row in financial_facts) | not_applicable | not_meaningful (denominator <= 0).
-- Average equity = (this year + previous fiscal year) / 2; first available year: end of year only
-- (roe_basis = 'end_of_year_only'); a gap year gives 'missing', no imputation.
create or replace view public.v_display_metrics with (security_invoker = true) as
with p as (
    select
        f.company_id,
        f.fiscal_year,
        max(f.value) filter (where d.item_key = 'revenue') as revenue,
        max(f.value) filter (where d.item_key = 'net_interest_income') as net_interest_income,
        max(f.value) filter (where d.item_key = 'noninterest_income') as noninterest_income,
        max(f.value) filter (where d.item_key = 'investment_gains') as investment_gains,
        max(f.value) filter (where d.item_key = 'net_income') as net_income,
        max(f.value) filter (where d.item_key = 'ffo_normalized') as ffo_normalized,
        max(f.value) filter (where d.item_key = 'eps_diluted') as eps_diluted,
        max(f.value) filter (where d.item_key = 'ffo_per_share') as ffo_per_share,
        max(f.value) filter (where d.item_key = 'eps_operating') as eps_operating,
        max(f.value) filter (where d.item_key = 'equity') as equity,
        max(f.value) filter (where d.item_key = 'preferred_stock') as preferred_stock,
        max(f.value) filter (where d.item_key = 'goodwill') as goodwill,
        max(f.value) filter (where d.item_key = 'intangibles') as intangibles,
        max(f.value) filter (where d.item_key = 'preferred_dividends') as preferred_dividends,
        max(f.value) filter (where d.item_key = 'op_profit_norm_after_tax') as op_profit_norm_after_tax,
        max(f.value) filter (where d.item_key = 'adjusted_equity') as adjusted_equity,
        max(f.value) filter (where d.item_key = 'cfo') as cfo,
        max(f.value) filter (where d.item_key = 'capex') as capex,
        max(f.value) filter (where d.item_key = 'owner_earnings') as owner_earnings,
        max(f.value) filter (where d.item_key = 'financial_debt') as financial_debt,
        max(f.value) filter (where d.item_key = 'cash') as cash,
        max(f.value) filter (where d.item_key = 'short_term_investments') as short_term_investments,
        max(f.value) filter (where d.item_key = 'ebitdare') as ebitdare,
        max(f.value) filter (where d.item_key = 'cet1_ratio_standardized') as cet1_ratio_standardized,
        max(f.value) filter (where d.item_key = 'cet1_ratio_advanced') as cet1_ratio_advanced,
        max(f.value) filter (where d.item_key = 'cet1_required_standardized') as cet1_required_standardized,
        max(f.value) filter (where d.item_key = 'cet1_required_advanced') as cet1_required_advanced
    from public.financial_facts f
    join public.dictionary_items d on d.id = f.item_id
    where d.item_key in ('revenue', 'net_interest_income', 'noninterest_income', 'investment_gains', 'net_income', 'ffo_normalized', 'eps_diluted', 'ffo_per_share', 'eps_operating', 'equity', 'preferred_stock', 'goodwill', 'intangibles', 'preferred_dividends', 'op_profit_norm_after_tax', 'adjusted_equity', 'cfo', 'capex', 'owner_earnings', 'financial_debt', 'cash', 'short_term_investments', 'ebitdare', 'cet1_ratio_standardized', 'cet1_ratio_advanced', 'cet1_required_standardized', 'cet1_required_advanced')
    group by f.company_id, f.fiscal_year
),
q as (
    select
        p.*,
        c.profile,
        min(p.fiscal_year) over (partition by p.company_id) as first_year,
        max(p.fiscal_year) over (partition by p.company_id) as last_year,
        -- return-on-equity denominator by profile (before averaging)
        case c.profile
            when 'BANK'      then p.equity - p.preferred_stock - p.goodwill - p.intangibles   -- tangible common equity
            when 'INSURANCE' then p.adjusted_equity
            else p.equity
        end as roe_den,
        -- CET1 of the approach with the least headroom over its requirement (binding approach);
        -- without any requirement: the lowest reported ratio
        (select v.r
           from (values (p.cet1_ratio_standardized, p.cet1_required_standardized),
                        (p.cet1_ratio_advanced,     p.cet1_required_advanced)) as v(r, req)
          where v.r is not null
          order by (v.r - v.req) nulls last, v.r
          limit 1) as cet1_binding
    from p
    join public.companies c on c.id = p.company_id
    where c.profile is not null
),
m as (
    select q.*, prev.roe_den as roe_den_prev
    from q
    left join q prev on prev.company_id = q.company_id and prev.fiscal_year = q.fiscal_year - 1
),
r as (
    select
        m.*,
        case m.profile
            when 'BANK'      then m.net_interest_income + m.noninterest_income
            when 'INSURANCE' then m.revenue - m.investment_gains
            else m.revenue
        end as revenue_v,
        case m.profile
            when 'BANK'      then m.net_income - m.preferred_dividends
            when 'INSURANCE' then m.op_profit_norm_after_tax
            when 'INCOME_REAL_ESTATE' then m.ffo_normalized
            else m.net_income
        end as roe_num,
        case when m.roe_den is null then null
             when m.roe_den_prev is not null then (m.roe_den + m.roe_den_prev) / 2
             when m.fiscal_year = m.first_year then m.roe_den
        end as roe_den_avg,
        case when m.roe_den is null then null
             when m.roe_den_prev is not null then 'average'
             when m.fiscal_year = m.first_year then 'end_of_year_only'
        end as roe_basis_v,
        case m.profile
            when 'INCOME_REAL_ESTATE' then m.owner_earnings
            when 'BANK' then null
            when 'INSURANCE' then null
            else m.cfo - m.capex
        end as fcf_v,
        case m.profile
            when 'INSURANCE' then m.financial_debt
            when 'INCOME_REAL_ESTATE' then m.financial_debt - m.cash - m.short_term_investments   -- net debt
            when 'BANK' then null
            else m.financial_debt
        end as lev_num,
        case m.profile
            when 'INSURANCE' then m.financial_debt + m.adjusted_equity
            when 'INCOME_REAL_ESTATE' then m.ebitdare
            when 'BANK' then null
            else m.equity
        end as lev_den
    from m
)
select
    r.company_id,
    r.fiscal_year,
    r.profile,
    (r.fiscal_year = r.last_year) as is_latest_year,

    r.revenue_v as revenue,
    case r.profile
        when 'BANK'      then 'Bank revenue (net interest income + noninterest income)'
        when 'INSURANCE' then 'Operating revenue (total revenue - investment gains)'
        else 'Revenue'
    end as revenue_label,
    case when r.revenue_v is null then 'missing' else 'ok' end as revenue_state,

    r.net_income,
    case when r.net_income is null then 'missing' else 'ok' end as net_income_state,
    case when r.profile = 'INCOME_REAL_ESTATE' then r.ffo_normalized end as normalized_ffo,
    case when r.profile <> 'INCOME_REAL_ESTATE' then 'not_applicable'
         when r.ffo_normalized is null then 'missing' else 'ok' end as normalized_ffo_state,

    case r.profile when 'INCOME_REAL_ESTATE' then r.ffo_per_share else r.eps_diluted end as eps,
    case r.profile when 'INCOME_REAL_ESTATE' then 'Normalized FFO per share' else 'Diluted EPS' end as eps_label,
    case when (case r.profile when 'INCOME_REAL_ESTATE' then r.ffo_per_share else r.eps_diluted end) is null
         then 'missing' else 'ok' end as eps_state,
    case when r.profile = 'INSURANCE' then r.eps_operating end as operating_eps,
    case when r.profile <> 'INSURANCE' then 'not_applicable'
         when r.eps_operating is null then 'missing' else 'ok' end as operating_eps_state,

    case when r.roe_num is not null and r.roe_den_avg > 0 then r.roe_num / r.roe_den_avg end as roe,
    case r.profile
        when 'BANK'      then 'ROTCE'
        when 'INSURANCE' then 'Operating ROE'
        when 'INCOME_REAL_ESTATE' then 'Normalized FFO / average equity'
        else 'ROE'
    end as roe_label,
    case when r.roe_num is null or r.roe_den_avg is null then 'missing'
         when r.roe_den_avg <= 0 then 'not_meaningful'
         else 'ok' end as roe_state,
    r.roe_basis_v as roe_basis,

    r.fcf_v as fcf,
    case r.profile
        when 'INCOME_REAL_ESTATE' then 'Owner earnings'
        when 'BANK' then null
        when 'INSURANCE' then null
        else 'Free cash flow (CFO - capex)'
    end as fcf_label,
    case when r.profile in ('BANK','INSURANCE') then 'not_applicable'
         when r.fcf_v is null then 'missing' else 'ok' end as fcf_state,

    case r.profile
        when 'BANK' then r.cet1_binding
        else case when r.lev_num is not null and r.lev_den > 0 then r.lev_num / r.lev_den end
    end as leverage,
    case r.profile
        when 'BANK'      then 'CET1 ratio'
        when 'INSURANCE' then 'Financial leverage (debt / (debt + adjusted equity))'
        when 'INCOME_REAL_ESTATE' then 'Net debt / EBITDAre'
        else 'Debt / equity'
    end as leverage_label,
    case r.profile
        when 'BANK' then case when r.cet1_binding is null then 'missing' else 'ok' end
        else case when r.lev_num is null or r.lev_den is null then 'missing'
                  when r.lev_den <= 0 then 'not_meaningful'
                  else 'ok' end
    end as leverage_state
from r;
grant select on public.v_display_metrics to authenticated;

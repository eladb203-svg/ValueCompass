-- Code stage K2, step 1: dictionary additions (data only, no schema change).
-- Source: scripts/code_stage1_2026-10-20.md section 2.3 / 6.1. Engines read these items; they had no item_key.
--   * items with no key at all (insurance, real estate, bank);
--   * granularity: debt_current, noncurrent_marketable_debt_derived (the engine reads the part / tier separately);
--   * "*_extracted" and similar: the value taken from the approved extraction store where the engine reads it next to the XBRL value of
--     the same item (financial_facts holds one row per company x year x item, so the two sources need separate keys).
-- premiums_earned is the other component of FIN-110 (insurance_revenue = premiums earned + policy fees).
-- dict_id is the parent Rulebook item; net_investment_income is FIN-186 (Rulebook 2026-10-20_10-33, CL13).
insert into public.dictionary_items (id, dict_id, item_key, title, profile_scope) values
  (220, 'FIN-110', 'policy_fees', 'Insurance revenue - policy fees (component; premiums are read separately)', '{INSURANCE}'),
  (221, 'FIN-186', 'net_investment_income', 'Net investment income (insurance; Rulebook FIN-186, added 2026-10-20_10-33, CL13)', '{INSURANCE}'),
  (222, 'FIN-112', 'benefits_losses_expenses', 'Benefits, losses and expenses, total (BenefitsLossesAndExpenses; input of the underwriting-result identity)', '{INSURANCE}'),
  (223, 'FIN-011', 'debt_short_term', 'Financial debt - short-term borrowings (insurance component)', '{INSURANCE}'),
  (224, 'FIN-011', 'debt_junior_subordinated', 'Financial debt - junior subordinated notes (insurance component)', '{INSURANCE}'),
  (225, 'FIN-136', 'inv_fixed_income_total', 'Investment portfolio by category - total fixed income (denominator of the investment-grade share)', '{INSURANCE}'),
  (226, 'FIN-042', 'noi_reported', 'Company-reported NOI (reconciliation input only)', '{INCOME_REAL_ESTATE}'),
  (227, 'FIN-050', 'interest_capitalized', 'Interest expense - capitalized interest', '{INCOME_REAL_ESTATE}'),
  (228, 'FIN-082', 're_depreciation', 'D&A - Schedule III real-estate depreciation expense', '{INCOME_REAL_ESTATE}'),
  (229, 'FIN-181', 'reported_core_ffo_per_share', 'Company FFO reconciliation lines and reported figures - reported core FFO per share', '{INCOME_REAL_ESTATE}'),
  (230, 'FIN-141', 'total_capital_ratio', 'Total regulatory capital - total capital ratio', '{BANK}'),
  (231, 'FIN-101', 'avg_loans', 'Loans - average loans (NCO ratio denominator)', '{BANK}'),
  (232, 'FIN-011', 'debt_current', 'Financial debt - current part (short-term borrowings and current maturities)', '{STANDARD,TECH_ASSET_LIGHT}'),
  (233, 'FIN-167', 'noncurrent_marketable_debt_derived', 'Non-current marketable debt securities - derived tier (AFS debt total less current investments)', '{STANDARD,TECH_ASSET_LIGHT}'),
  (234, 'FIN-120', 'straight_line_rent_affo', 'Straight-line rent - company AFFO line (extraction)', '{INCOME_REAL_ESTATE}'),
  (235, 'FIN-122', 'ti_lc_extracted', 'TI/LC - income-preserving amount (extraction)', '{INCOME_REAL_ESTATE}'),
  (236, 'FIN-040', 'rental_revenue_extracted', 'Rental revenue - extracted income-statement line (when no tag exists)', '{INCOME_REAL_ESTATE}'),
  (237, 'FIN-042', 'property_opex_extracted', 'Property operating expenses - extracted income-statement line (when no tag exists)', '{INCOME_REAL_ESTATE}'),
  (238, 'FIN-138', 'debt_maturity_year1_extracted', 'Debt maturities - next 12 months (extraction, sum of instruments)', '{INCOME_REAL_ESTATE}'),
  (239, 'FIN-138', 'debt_maturity_year2_extracted', 'Debt maturities - year two (extraction, sum of instruments)', '{INCOME_REAL_ESTATE}'),
  (240, 'FIN-181', 'recon_nci_adjust', 'Company FFO reconciliation lines - NCI adjustment', '{INCOME_REAL_ESTATE}'),
  (241, 'FIN-181', 'recon_jv_other_adjust', 'Company FFO reconciliation lines - JV and other adjustments', '{INCOME_REAL_ESTATE}'),
  (242, 'FIN-011', 'financial_debt_extracted', 'Financial debt - extraction (balance-sheet total from the filing text)', '{INSURANCE,INCOME_REAL_ESTATE}'),
  (243, 'FIN-136', 'investments_total_extracted', 'Investments, total - extraction', '{INSURANCE}'),
  (244, 'FIN-118', 'prior_year_dev_extracted', 'Prior-period development - prior-year development (extraction)', '{INSURANCE}'),
  (245, 'FIN-118', 'ldti_remeasurement_extracted', 'Prior-period development - LDTI remeasurement (extraction)', '{INSURANCE}'),
  (246, 'FIN-105', 'nonaccrual_loans_extracted', 'Nonaccrual loans - extraction', '{BANK}'),
  (247, 'FIN-170', 'past_due_90_accruing_extracted', '90+ days past due accruing - extraction (total row)', '{BANK}'),
  (248, 'FIN-101', 'loans_extracted', 'Loans - latest-year extraction override', '{BANK}'),
  (249, 'FIN-104', 'acl_extracted', 'ACL - latest-year extraction override', '{BANK}'),
  (250, 'FIN-103', 'nco_extracted', 'NCO - latest-year extraction override', '{BANK}'),
  (251, 'FIN-022', 'preferred_stock_extracted', 'Preferred stock - latest-year extraction override', '{BANK}'),
  (252, 'FIN-110', 'premiums_earned', 'Insurance revenue - premiums earned (component; the engine reads premiums and policy fees separately)', '{INSURANCE}');

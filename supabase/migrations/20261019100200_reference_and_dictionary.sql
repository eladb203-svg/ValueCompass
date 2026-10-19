-- DB stage 1 / migration 2 of 8 - reference tables, dictionary, company profile, price freshness.
-- Sources: Rulebook part E (dictionary), DB structure doc 2026-10-19_09-59 (sections 1-4). Not applied yet.

-- ---------------------------------------------------------------- dictionary_items
-- One row per component (item_key) of a dictionary item. dict_id (FIN-xxx / DRV-xxx / PRC-xxx / TXT-xxx)
-- repeats for items that have several components (e.g. FIN-116). profile_scope = profiles whose
-- v_fin_* view carries the item; '{}' = not stored in financial_facts (structure doc section 3).
create table public.dictionary_items (
  id            smallint primary key,
  dict_id       text   not null,
  item_key      text   not null,
  title         text   not null,
  profile_scope text[] not null default '{}',
  constraint dictionary_items_item_key_key unique (item_key),
  constraint dictionary_items_dict_id_check check (dict_id ~ '^(FIN|DRV|PRC|TXT)-[0-9]{3}$'),
  constraint dictionary_items_item_key_check check (item_key ~ '^[a-z][a-z0-9_]*$'),
  constraint dictionary_items_profile_scope_check
    check (profile_scope <@ array['STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE']::text[])
);
create index idx_dictionary_items_dict_id on public.dictionary_items (dict_id);

insert into public.dictionary_items (id, dict_id, item_key, title, profile_scope) values
  (1, 'FIN-002', 'income_tax', 'Income tax', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (2, 'FIN-003', 'pretax_income', 'Pretax income', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (3, 'FIN-010', 'equity', 'Equity', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (4, 'FIN-011', 'financial_debt', 'Financial debt', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (5, 'FIN-012', 'cash', 'Cash', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (6, 'FIN-013', 'short_term_investments', 'Short-term investments', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (7, 'FIN-020', 'net_income', 'Net income', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (8, 'FIN-021', 'preferred_dividends', 'Preferred dividends', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (9, 'FIN-022', 'preferred_stock', 'Preferred stock', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (10, 'FIN-023', 'goodwill', 'Goodwill', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (11, 'FIN-024', 'intangibles', 'Intangibles', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (12, 'FIN-025', 'total_assets', 'Total assets', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (13, 'FIN-032', 'goodwill_impairment', 'Goodwill impairment', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (14, 'FIN-050', 'interest_expense', 'Interest expense', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (15, 'FIN-060', 'revenue', 'Revenue', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (16, 'FIN-062', 'eps_diluted', 'Diluted EPS', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (17, 'FIN-080', 'cfo', 'CFO', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (18, 'FIN-081', 'capex', 'Capex', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (19, 'FIN-082', 'da', 'D&A', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (20, 'FIN-084', 'sbc', 'SBC', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (21, 'FIN-087', 'dividends_paid', 'Dividends paid', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (22, 'FIN-088', 'buybacks', 'Buybacks', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (23, 'FIN-089', 'acquisitions', 'Acquisitions', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (24, 'FIN-090', 'avg_share_price', 'Average share price', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (25, 'FIN-091', 'shares_period_end', 'Period-end shares', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (26, 'FIN-092', 'shares_diluted_weighted', 'Weighted diluted shares', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (27, 'FIN-108', 'dps', 'DPS', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (28, 'FIN-139', 'long_term_debt', 'Long-term debt', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (29, 'FIN-160', 'goodwill_acquired', 'Goodwill acquired in the year (N-01)', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (30, 'FIN-161', 'total_liabilities', 'Total liabilities (N-02)', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (31, 'FIN-163', 'cover_shares', 'Cover-page share count (N-04)', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (32, 'FIN-164', 'shares_basic_weighted', 'Weighted basic shares (N-05)', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (33, 'FIN-165', 'pretax_domestic', 'Pretax income, domestic and foreign (N-06) - domestic', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (34, 'FIN-165', 'pretax_foreign', 'Pretax income, domestic and foreign (N-06) - foreign', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (35, 'FIN-169', 'net_income_common', 'Net income to common; profit or loss; NCI (N-10) - net income to common', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (36, 'FIN-169', 'profit_loss', 'Net income to common; profit or loss; NCI (N-10) - profit or loss', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (37, 'FIN-169', 'nci_income', 'Net income to common; profit or loss; NCI (N-10) - attributable to NCI', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (38, 'FIN-172', 'discontinued_ops', 'Discontinued operations (N-13)', '{STANDARD,TECH_ASSET_LIGHT,BANK,INSURANCE,INCOME_REAL_ESTATE}'),
  (39, 'FIN-001', 'ebit', 'EBIT', '{STANDARD,TECH_ASSET_LIGHT}'),
  (40, 'FIN-061', 'cost_of_revenue', 'Cost of revenue / gross profit - cost of revenue', '{STANDARD,TECH_ASSET_LIGHT}'),
  (41, 'FIN-061', 'gross_profit', 'Cost of revenue / gross profit - gross profit', '{STANDARD,TECH_ASSET_LIGHT}'),
  (42, 'FIN-083', 'acq_amortization', 'Amortization of acquired intangibles', '{STANDARD,TECH_ASSET_LIGHT}'),
  (43, 'FIN-085', 'current_assets', 'Current assets', '{STANDARD,TECH_ASSET_LIGHT}'),
  (44, 'FIN-086', 'current_liabilities', 'Current liabilities', '{STANDARD,TECH_ASSET_LIGHT}'),
  (45, 'FIN-093', 'deferred_revenue_current', 'Deferred revenue, current', '{STANDARD,TECH_ASSET_LIGHT}'),
  (46, 'FIN-132', 'receivables', 'Receivables', '{STANDARD,TECH_ASSET_LIGHT}'),
  (47, 'FIN-162', 'funds_held_for_clients', 'Funds held for clients; restricted cash (N-03) - funds held for clients', '{STANDARD,TECH_ASSET_LIGHT}'),
  (48, 'FIN-162', 'restricted_cash', 'Funds held for clients; restricted cash (N-03) - restricted cash', '{STANDARD,TECH_ASSET_LIGHT}'),
  (49, 'FIN-166', 'depreciation', 'Depreciation; finance-lease ROU amortization (N-07) - depreciation', '{STANDARD,TECH_ASSET_LIGHT}'),
  (50, 'FIN-166', 'finance_lease_rou_amort', 'Depreciation; finance-lease ROU amortization (N-07) - finance-lease ROU amortization', '{STANDARD,TECH_ASSET_LIGHT}'),
  (51, 'FIN-167', 'noncurrent_marketable_debt', 'Non-current marketable debt securities (N-08)', '{STANDARD,TECH_ASSET_LIGHT}'),
  (52, 'FIN-168', 'claims_expense', 'Claims / benefits expense, STANDARD (N-09)', '{STANDARD,TECH_ASSET_LIGHT}'),
  (53, 'FIN-063', 'net_interest_income', 'Net interest income', '{BANK}'),
  (54, 'FIN-064', 'noninterest_income', 'Noninterest income', '{BANK}'),
  (55, 'FIN-100', 'provision_credit_losses', 'Provision for credit losses', '{BANK}'),
  (56, 'FIN-101', 'loans', 'Loans', '{BANK}'),
  (57, 'FIN-102', 'deposits', 'Deposits', '{BANK}'),
  (58, 'FIN-103', 'nco', 'NCO', '{BANK}'),
  (59, 'FIN-104', 'acl', 'ACL', '{BANK}'),
  (60, 'FIN-105', 'nonaccrual_loans', 'Nonaccrual loans', '{BANK}'),
  (61, 'FIN-106', 'cet1_ratio_standardized', 'CET1 and required CET1 - CET1 ratio, standardized', '{BANK}'),
  (62, 'FIN-106', 'cet1_ratio_advanced', 'CET1 and required CET1 - CET1 ratio, advanced', '{BANK}'),
  (63, 'FIN-106', 'cet1_required_standardized', 'CET1 and required CET1 - required CET1, standardized', '{BANK}'),
  (64, 'FIN-106', 'cet1_required_advanced', 'CET1 and required CET1 - required CET1, advanced', '{BANK}'),
  (65, 'FIN-107', 'lcr_q4_average', 'LCR', '{BANK}'),
  (66, 'FIN-133', 'st_borrowings', 'Short-term borrowings', '{BANK}'),
  (67, 'FIN-134', 'fhlb_advances', 'Central bank / FHLB advances', '{BANK}'),
  (68, 'FIN-135', 'repo_securities_lending', 'Repo and securities lending', '{BANK}'),
  (69, 'FIN-140', 'loans_residential_mortgage', 'Loan breakdown - residential mortgage', '{BANK}'),
  (70, 'FIN-140', 'loans_cre_construction', 'Loan breakdown - CRE and construction', '{BANK}'),
  (71, 'FIN-140', 'loans_ci', 'Loan breakdown - C&I', '{BANK}'),
  (72, 'FIN-140', 'loans_consumer', 'Loan breakdown - consumer', '{BANK}'),
  (73, 'FIN-140', 'loans_other', 'Loan breakdown - other', '{BANK}'),
  (74, 'FIN-141', 'total_capital_standardized', 'Total regulatory capital - standardized', '{BANK}'),
  (75, 'FIN-141', 'total_capital_advanced', 'Total regulatory capital - advanced', '{BANK}'),
  (76, 'FIN-144', 'rwa_standardized', 'RWA - standardized', '{BANK}'),
  (77, 'FIN-144', 'rwa_advanced', 'RWA - advanced', '{BANK}'),
  (78, 'FIN-170', 'past_due_90_accruing', '90+ days past due accruing; uninsured deposits (N-11) - 90+ days past due accruing', '{BANK}'),
  (79, 'FIN-170', 'uninsured_deposits', '90+ days past due accruing; uninsured deposits (N-11) - uninsured deposits', '{BANK}'),
  (80, 'FIN-171', 'scb', 'Stress capital buffer; G-SIB surcharge (N-12) - stress capital buffer', '{BANK}'),
  (81, 'FIN-171', 'gsib_surcharge', 'Stress capital buffer; G-SIB surcharge (N-12) - G-SIB surcharge', '{BANK}'),
  (82, 'FIN-030', 'investment_gains', 'Investment gains', '{INSURANCE}'),
  (83, 'FIN-031', 'mrb_change', 'MRB remeasurement', '{INSURANCE}'),
  (84, 'FIN-033', 'aoci_afs', 'AOCI by component - AFS unrealized', '{INSURANCE}'),
  (85, 'FIN-033', 'aoci_discount_rate', 'AOCI by component - discount-rate remeasurement', '{INSURANCE}'),
  (86, 'FIN-033', 'aoci_own_credit', 'AOCI by component - own credit', '{INSURANCE}'),
  (87, 'FIN-033', 'aoci_fx', 'AOCI by component - FX', '{INSURANCE}'),
  (88, 'FIN-033', 'aoci_pension', 'AOCI by component - pension', '{INSURANCE}'),
  (89, 'FIN-110', 'insurance_revenue', 'Insurance revenue', '{INSURANCE}'),
  (90, 'FIN-111', 'claims_benefits', 'Claims and benefits', '{INSURANCE}'),
  (91, 'FIN-112', 'non_claims_uw_expenses', 'Non-claims underwriting expenses', '{INSURANCE}'),
  (92, 'FIN-114', 'interest_credited', 'Interest credited / accretion - interest credited', '{INSURANCE}'),
  (93, 'FIN-114', 'fpb_accretion', 'Interest credited / accretion - accretion on future policy benefits', '{INSURANCE}'),
  (94, 'FIN-116', 'claims_gross', 'Float components - claims liability, gross', '{INSURANCE}'),
  (95, 'FIN-116', 'claims_net', 'Float components - claims liability, net', '{INSURANCE}'),
  (96, 'FIN-116', 'reins_unpaid', 'Float components - reinsurance recoverable on unpaid', '{INSURANCE}'),
  (97, 'FIN-116', 'fpb', 'Float components - future policy benefits', '{INSURANCE}'),
  (98, 'FIN-116', 'pab', 'Float components - policyholder account balances', '{INSURANCE}'),
  (99, 'FIN-116', 'unearned', 'Float components - unearned premiums', '{INSURANCE}'),
  (100, 'FIN-116', 'reins_prepaid', 'Float components - prepaid reinsurance premiums', '{INSURANCE}'),
  (101, 'FIN-116', 'aoci_total', 'Float components - AOCI total', '{INSURANCE}'),
  (102, 'FIN-117', 'reg_capital_ratio', 'Regulatory capital ratio', '{INSURANCE}'),
  (103, 'FIN-118', 'prior_year_dev', 'Prior-period development - prior-year development', '{INSURANCE}'),
  (104, 'FIN-118', 'ldti_remeasurement', 'Prior-period development - LDTI remeasurement', '{INSURANCE}'),
  (105, 'FIN-118', 'fpb_adverse_development', 'Prior-period development - adverse development of future policy benefits', '{INSURANCE}'),
  (106, 'FIN-136', 'inv_cash', 'Investment portfolio by category - cash', '{INSURANCE}'),
  (107, 'FIN-136', 'inv_short_term', 'Investment portfolio by category - short-term', '{INSURANCE}'),
  (108, 'FIN-136', 'inv_fixed_maturities', 'Investment portfolio by category - fixed maturities', '{INSURANCE}'),
  (109, 'FIN-136', 'inv_equity', 'Investment portfolio by category - equity', '{INSURANCE}'),
  (110, 'FIN-136', 'inv_illiquid_loans', 'Investment portfolio by category - illiquid loans', '{INSURANCE}'),
  (111, 'FIN-136', 'inv_real_estate', 'Investment portfolio by category - real estate', '{INSURANCE}'),
  (112, 'FIN-136', 'inv_other', 'Investment portfolio by category - other invested', '{INSURANCE}'),
  (113, 'FIN-136', 'inv_ig_fixed', 'Investment portfolio by category - investment-grade fixed income', '{INSURANCE}'),
  (114, 'FIN-136', 'inv_ig_share', 'Investment portfolio by category - investment-grade share', '{INSURANCE}'),
  (115, 'FIN-173', 'divestiture_proceeds', 'Structural-change indicators (N-14) - divestiture proceeds', '{INSURANCE}'),
  (116, 'FIN-173', 'deconsolidation_cash', 'Structural-change indicators (N-14) - deconsolidation cash', '{INSURANCE}'),
  (117, 'FIN-173', 'goodwill_written_off_sale', 'Structural-change indicators (N-14) - goodwill written off on sale', '{INSURANCE}'),
  (118, 'FIN-174', 'separate_accounts', 'Separate accounts; MRB liability; total investments (N-15) - separate accounts', '{INSURANCE}'),
  (119, 'FIN-174', 'mrb_liability', 'Separate accounts; MRB liability; total investments (N-15) - MRB liability', '{INSURANCE}'),
  (120, 'FIN-174', 'investments_total', 'Separate accounts; MRB liability; total investments (N-15) - total investments', '{INSURANCE}'),
  (121, 'FIN-175', 'cat_loss_latest', 'Catastrophe losses; ALM disclosure (N-16) - catastrophe losses, latest year', '{INSURANCE}'),
  (122, 'FIN-175', 'alm_disclosed', 'Catastrophe losses; ALM disclosure (N-16) - ALM disclosed (1/0)', '{INSURANCE}'),
  (123, 'FIN-040', 'rental_revenue', 'Rental revenue', '{INCOME_REAL_ESTATE}'),
  (124, 'FIN-041', 'other_property_revenue', 'Other property revenue', '{INCOME_REAL_ESTATE}'),
  (125, 'FIN-042', 'property_opex', 'Property operating expenses', '{INCOME_REAL_ESTATE}'),
  (126, 'FIN-043', 'acquisition_yield', 'New-investment yields - acquisition yield', '{INCOME_REAL_ESTATE}'),
  (127, 'FIN-043', 'development_yield', 'New-investment yields - development yield', '{INCOME_REAL_ESTATE}'),
  (128, 'FIN-043', 'acquisition_invested', 'New-investment yields - acquisition invested', '{INCOME_REAL_ESTATE}'),
  (129, 'FIN-043', 'development_invested', 'New-investment yields - development invested', '{INCOME_REAL_ESTATE}'),
  (130, 'FIN-044', 'same_property_noi_growth', 'Same-property NOI growth', '{INCOME_REAL_ESTATE}'),
  (131, 'FIN-045', 'acq_real_estate', 'Growth capital - real-estate acquisitions', '{INCOME_REAL_ESTATE}'),
  (132, 'FIN-045', 'acq_business', 'Growth capital - business acquisitions', '{INCOME_REAL_ESTATE}'),
  (133, 'FIN-045', 'development_spend', 'Growth capital - development', '{INCOME_REAL_ESTATE}'),
  (134, 'FIN-045', 'capital_improvements', 'Growth capital - capital improvements', '{INCOME_REAL_ESTATE}'),
  (135, 'FIN-046', 'sale_proceeds', 'Dispositions', '{INCOME_REAL_ESTATE}'),
  (136, 'FIN-047', 're_gross', 'Gross real estate at cost - gross at cost', '{INCOME_REAL_ESTATE}'),
  (137, 'FIN-047', 're_net', 'Gross real estate at cost - net', '{INCOME_REAL_ESTATE}'),
  (138, 'FIN-120', 'straight_line_rent', 'Straight-line rent', '{INCOME_REAL_ESTATE}'),
  (139, 'FIN-121', 'maint_capex', 'Maintenance capex (RE)', '{INCOME_REAL_ESTATE}'),
  (140, 'FIN-122', 'ti_lc', 'TI/LC', '{INCOME_REAL_ESTATE}'),
  (141, 'FIN-123', 'gains_sale', 'EBITDAre components - gains on property sales', '{INCOME_REAL_ESTATE}'),
  (142, 'FIN-123', 'impairment', 'EBITDAre components - impairment of real estate', '{INCOME_REAL_ESTATE}'),
  (143, 'FIN-125', 'fair_value_real_estate', 'Economic property value', '{INCOME_REAL_ESTATE}'),
  (144, 'FIN-137', 'committed_undrawn_facilities', 'Committed undrawn facilities', '{INCOME_REAL_ESTATE}'),
  (145, 'FIN-138', 'debt_maturity_year1', 'Debt maturities - next 12 months', '{INCOME_REAL_ESTATE}'),
  (146, 'FIN-138', 'debt_maturity_year2', 'Debt maturities - year two', '{INCOME_REAL_ESTATE}'),
  (147, 'FIN-142', 'unencumbered_noi_share', 'Unencumbered NOI / assets - NOI share', '{INCOME_REAL_ESTATE}'),
  (148, 'FIN-142', 'unencumbered_assets_share', 'Unencumbered NOI / assets - assets share', '{INCOME_REAL_ESTATE}'),
  (149, 'FIN-143', 'stabilized_noi', 'Stabilized vs development split - stabilized NOI', '{INCOME_REAL_ESTATE}'),
  (150, 'FIN-143', 'stabilized_value', 'Stabilized vs development split - stabilized value', '{INCOME_REAL_ESTATE}'),
  (151, 'FIN-143', 'other_property_value', 'Stabilized vs development split - other property value', '{INCOME_REAL_ESTATE}'),
  (152, 'FIN-145', 'occupancy', 'Occupancy / utilization', '{INCOME_REAL_ESTATE}'),
  (153, 'FIN-146', 'largest_tenant_share', 'Largest tenant share', '{INCOME_REAL_ESTATE}'),
  (154, 'FIN-152', 'bsa_noi', 'NAV inputs (RP2a) - in NOI', '{INCOME_REAL_ESTATE}'),
  (155, 'FIN-152', 'bsa_carry', 'NAV inputs (RP2a) - carrying value', '{INCOME_REAL_ESTATE}'),
  (156, 'FIN-152', 'bsa_carryfin', 'NAV inputs (RP2a) - carrying value, financial', '{INCOME_REAL_ESTATE}'),
  (157, 'FIN-152', 'bsa_inre', 'NAV inputs (RP2a) - in real estate', '{INCOME_REAL_ESTATE}'),
  (158, 'FIN-152', 'bsa_wc', 'NAV inputs (RP2a) - working capital', '{INCOME_REAL_ESTATE}'),
  (159, 'FIN-152', 'bsa_excl', 'NAV inputs (RP2a) - excluded', '{INCOME_REAL_ESTATE}'),
  (160, 'FIN-152', 'bsa_other', 'NAV inputs (RP2a) - unidentified', '{INCOME_REAL_ESTATE}'),
  (161, 'FIN-153', 'nci_total', 'NCI and OP units - NCI total', '{INCOME_REAL_ESTATE}'),
  (162, 'FIN-153', 'nci_op', 'NCI and OP units - NCI, OP units', '{INCOME_REAL_ESTATE}'),
  (163, 'FIN-153', 'nci_lp', 'NCI and OP units - NCI, limited partnerships', '{INCOME_REAL_ESTATE}'),
  (164, 'FIN-153', 'nci_redeemable', 'NCI and OP units - redeemable NCI', '{INCOME_REAL_ESTATE}'),
  (165, 'FIN-153', 'op_units_count', 'NCI and OP units - OP-unit count', '{INCOME_REAL_ESTATE}'),
  (166, 'FIN-153', 'op_units_book_value', 'NCI and OP units - OP-unit book value', '{INCOME_REAL_ESTATE}'),
  (167, 'FIN-176', 'real_estate_tax', 'Real-estate taxes; repairs and maintenance (N-17) - real-estate taxes', '{INCOME_REAL_ESTATE}'),
  (168, 'FIN-176', 'repairs_maintenance', 'Real-estate taxes; repairs and maintenance (N-17) - repairs and maintenance', '{INCOME_REAL_ESTATE}'),
  (169, 'FIN-177', 'gains_re_entities', 'Gains on sale of interests in real-estate entities (N-18)', '{INCOME_REAL_ESTATE}'),
  (170, 'FIN-178', 'fx_unrealized', 'Unrealized FX result; FX net of hedges (N-19) - unrealized FX result', '{INCOME_REAL_ESTATE}'),
  (171, 'FIN-178', 're29b_fx_net', 'Unrealized FX result; FX net of hedges (N-19) - FX net of hedges', '{INCOME_REAL_ESTATE}'),
  (172, 'FIN-179', 'debt_extinguishment', 'Debt extinguishment; transaction costs (N-20) - debt extinguishment', '{INCOME_REAL_ESTATE}'),
  (173, 'FIN-179', 'transaction_costs', 'Debt extinguishment; transaction costs (N-20) - transaction costs', '{INCOME_REAL_ESTATE}'),
  (174, 'FIN-180', 're29_re_sale_gains', 'RE sale gains; non-RE impairments; non-RE investment results; development gains (N-21) - RE sale gains', '{INCOME_REAL_ESTATE}'),
  (175, 'FIN-180', 're29_nonre_impairments', 'RE sale gains; non-RE impairments; non-RE investment results; development gains (N-21) - non-RE impairments', '{INCOME_REAL_ESTATE}'),
  (176, 'FIN-180', 're29a_nonre_inv', 'RE sale gains; non-RE impairments; non-RE investment results; development gains (N-21) - non-RE investment results', '{INCOME_REAL_ESTATE}'),
  (177, 'FIN-180', 'dev_gains_reported', 'RE sale gains; non-RE impairments; non-RE investment results; development gains (N-21) - development gains', '{INCOME_REAL_ESTATE}'),
  (178, 'FIN-181', 'recon_net_income', 'Company FFO reconciliation lines and reported figures (N-22) - reconciliation: net income', '{INCOME_REAL_ESTATE}'),
  (179, 'FIN-181', 'recon_re_da', 'Company FFO reconciliation lines and reported figures (N-22) - reconciliation: real-estate D&A', '{INCOME_REAL_ESTATE}'),
  (180, 'FIN-181', 'recon_nci_jv', 'Company FFO reconciliation lines and reported figures (N-22) - reconciliation: NCI and JV adjustments', '{INCOME_REAL_ESTATE}'),
  (181, 'FIN-181', 'recon_gi_net', 'Company FFO reconciliation lines and reported figures (N-22) - reconciliation: gains / impairments, net', '{INCOME_REAL_ESTATE}'),
  (182, 'FIN-181', 'reported_ffo', 'Company FFO reconciliation lines and reported figures (N-22) - reported FFO', '{INCOME_REAL_ESTATE}'),
  (183, 'FIN-181', 'reported_core_ffo', 'Company FFO reconciliation lines and reported figures (N-22) - reported core FFO', '{INCOME_REAL_ESTATE}'),
  (184, 'FIN-181', 'reported_affo', 'Company FFO reconciliation lines and reported figures (N-22) - reported AFFO', '{INCOME_REAL_ESTATE}'),
  (185, 'FIN-181', 'reported_ebitdare', 'Company FFO reconciliation lines and reported figures (N-22) - reported EBITDAre', '{INCOME_REAL_ESTATE}'),
  (186, 'FIN-182', 'equity_method_inv', 'NAV inputs and claims (N-23) - equity-method investments', '{INCOME_REAL_ESTATE}'),
  (187, 'FIN-182', 'cip', 'NAV inputs and claims (N-23) - construction in progress', '{INCOME_REAL_ESTATE}'),
  (188, 'FIN-182', 're_dev_land', 'NAV inputs and claims (N-23) - development land', '{INCOME_REAL_ESTATE}'),
  (189, 'FIN-182', 'pref_equity', 'NAV inputs and claims (N-23) - preferred equity', '{INCOME_REAL_ESTATE}'),
  (190, 'FIN-182', 'finance_lease_liab', 'NAV inputs and claims (N-23) - finance-lease liabilities', '{INCOME_REAL_ESTATE}'),
  (191, 'FIN-183', 'profile_total_assets', 'Profile-test inputs (N-24) - total assets', '{INCOME_REAL_ESTATE}'),
  (192, 'FIN-183', 'profile_property_value', 'Profile-test inputs (N-24) - property value', '{INCOME_REAL_ESTATE}'),
  (193, 'FIN-183', 'profile_rental_revenue', 'Profile-test inputs (N-24) - rental revenue', '{INCOME_REAL_ESTATE}'),
  (194, 'FIN-183', 'profile_total_revenue', 'Profile-test inputs (N-24) - total revenue', '{INCOME_REAL_ESTATE}'),
  (195, 'FIN-184', 'shares_basis_override', 'Single-basis items (N-25) - share-basis override', '{INCOME_REAL_ESTATE}'),
  (196, 'FIN-184', 'inc_share_of_bplp', 'Single-basis items (N-25) - share of operating partnership income', '{INCOME_REAL_ESTATE}'),
  (197, 'FIN-184', 'partnership_units_weighted', 'Single-basis items (N-25) - weighted partnership units', '{INCOME_REAL_ESTATE}'),
  (198, 'FIN-184', 'diluted_includes_op', 'Single-basis items (N-25) - diluted shares include OP units (1/0)', '{INCOME_REAL_ESTATE}'),
  (199, 'FIN-185', 'secured_debt', 'Secured debt (N-26)', '{INCOME_REAL_ESTATE}'),
  (200, 'FIN-070', 'ffo_normalized', 'Normalized FFO', '{INCOME_REAL_ESTATE}'),
  (201, 'DRV-001', 'ffo_per_share', 'Normalized FFO per share', '{INCOME_REAL_ESTATE}'),
  (202, 'DRV-002', 'owner_earnings', 'Owner earnings (OE) and OE per share - owner earnings', '{INCOME_REAL_ESTATE}'),
  (203, 'DRV-002', 'owner_earnings_per_share', 'Owner earnings (OE) and OE per share - owner earnings per share', '{INCOME_REAL_ESTATE}'),
  (204, 'DRV-003', 'ebitdare', 'EBITDAre', '{INCOME_REAL_ESTATE}'),
  (205, 'DRV-004', 'op_profit_norm_after_tax', 'Normalized operating profit after tax', '{INSURANCE}'),
  (206, 'DRV-005', 'adjusted_equity', 'Adjusted equity', '{INSURANCE}'),
  (207, 'DRV-006', 'eps_operating', 'Operating EPS', '{INSURANCE}'),
  (208, 'FIN-051', 'market_cap', 'Market capitalization (computed in v_display_metrics)', '{}'),
  (209, 'FIN-119', 'gov_yield_annual', 'Government yield, annual (table gov_yields)', '{}'),
  (210, 'FIN-150', 'gov_yield_monthly', 'Government yield, monthly (table gov_yields)', '{}'),
  (211, 'FIN-130', 'fx_rates', 'FX rates (table fx_rates)', '{}'),
  (212, 'PRC-001', 'share_price', 'Share price (table market_snapshot)', '{}'),
  (213, 'FIN-131', 'first_annual_report_date', 'First annual report date', '{}'),
  (214, 'FIN-151', 'eps_history_10y', '10-year EPS history (history of FIN-062)', '{}'),
  (215, 'TXT-001', 'business_section', 'Business section (answers in ai_assessments)', '{}'),
  (216, 'TXT-002', 'risk_factors', 'Risk Factors (answers in ai_assessments)', '{}'),
  (217, 'TXT-003', 'competition', 'Competition (answers in ai_assessments)', '{}'),
  (218, 'TXT-004', 'governance_mda', 'MD&A / governance (answers in ai_assessments)', '{}'),
  (219, 'TXT-005', 'segments_customers', 'Segment and customer disclosures (answers in ai_assessments)', '{}');

-- ---------------------------------------------------------------- fact_tags
create table public.fact_tags (
  id  int generated by default as identity primary key,
  tag text not null,
  constraint fact_tags_tag_key unique (tag)
);

-- ---------------------------------------------------------------- companies: profile
alter table public.companies
  add column profile        text,
  add column profile_reason text,
  add column profile_since  smallint,
  add constraint companies_profile_check
    check (profile is null or profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE')),
  add constraint companies_profile_since_check
    check (profile_since is null or (profile_since >= 1900 and profile_since <= 2100));
alter table public.companies add column first_annual_report_date date;
comment on column public.companies.first_annual_report_date is 'FIN-131: filing date of the first annual report (earliest 10-K / 10-K405 / 10-KT in the SEC submissions, or the regulator equivalent). Used by Graham 3.1.';
comment on column public.companies.profile is 'Current scoring profile (Rulebook part B / E10). Selects the v_fin_* view and the v_display_metrics definition.';
comment on column public.companies.profile_since is 'First fiscal year in which the current profile applies.';

create table public.company_profile_history (
  company_id  bigint   not null references public.companies(id) on delete cascade,
  fiscal_year smallint not null,
  profile     text     not null,
  reason      text,
  borderline  boolean  not null default false,
  override_by uuid     references auth.users(id) on delete set null,
  created_at  timestamptz not null default now(),
  constraint company_profile_history_pkey primary key (company_id, fiscal_year),
  constraint company_profile_history_fiscal_year_check check (fiscal_year >= 1900 and fiscal_year <= 2100),
  constraint company_profile_history_profile_check
    check (profile in ('STANDARD','TECH_ASSET_LIGHT','BANK','INSURANCE','INCOME_REAL_ESTATE'))
);

-- ---------------------------------------------------------------- filing_periods
create table public.filing_periods (
  company_id          bigint   not null references public.companies(id) on delete cascade,
  fiscal_year         smallint not null,
  accession           text     not null,
  form                text     not null,
  filed_at            date,
  fiscal_year_end     date,
  reporting_currency  text,
  calculation_version text     not null,
  constraint filing_periods_pkey primary key (company_id, fiscal_year),
  constraint filing_periods_fiscal_year_check check (fiscal_year >= 1900 and fiscal_year <= 2100)
);

-- ---------------------------------------------------------------- gov_yields, fx_rates
-- period: 'YYYY' for annual, 'YYYY-MM' for monthly
create table public.gov_yields (
  currency     text        not null,
  period_type  text        not null,
  period       text        not null,
  yield_pct    numeric(9,4) not null,
  series       text        not null,
  source       text        not null,
  retrieved_at timestamptz not null default now(),
  constraint gov_yields_pkey primary key (currency, period_type, period),
  constraint gov_yields_period_type_check check (period_type in ('annual','monthly')),
  constraint gov_yields_period_check check (
    (period_type = 'annual'  and period ~ '^[0-9]{4}$') or
    (period_type = 'monthly' and period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'))
);

-- period_type: annual average / year-end rate (FIN-130, R15); period = fiscal year 'YYYY'
create table public.fx_rates (
  currency    text         not null,
  period_type text         not null,
  period      text         not null,
  rate_to_usd numeric(20,8) not null,
  source      text         not null,
  constraint fx_rates_pkey primary key (currency, period_type, period),
  constraint fx_rates_period_type_check check (period_type in ('annual_avg','year_end')),
  constraint fx_rates_period_check check (period ~ '^[0-9]{4}$'),
  constraint fx_rates_rate_check check (rate_to_usd > 0)
);

-- ---------------------------------------------------------------- market_snapshot: freshness (E1)
-- stays one row per company (PK company_id), updated in place
alter table public.market_snapshot
  add column last_price_at timestamptz,
  add column is_stale      boolean not null default false;

-- ---------------------------------------------------------------- RLS: read for authenticated, write service_role only
alter table public.dictionary_items enable row level security;
revoke all on public.dictionary_items from anon, authenticated;
grant select on public.dictionary_items to authenticated;
create policy "dictionary_items_select_authenticated" on public.dictionary_items
  for select to authenticated using (true);

alter table public.fact_tags enable row level security;
revoke all on public.fact_tags from anon, authenticated;
grant select on public.fact_tags to authenticated;
create policy "fact_tags_select_authenticated" on public.fact_tags
  for select to authenticated using (true);

alter table public.company_profile_history enable row level security;
revoke all on public.company_profile_history from anon, authenticated;
grant select on public.company_profile_history to authenticated;
create policy "company_profile_history_select_authenticated" on public.company_profile_history
  for select to authenticated using (true);

alter table public.filing_periods enable row level security;
revoke all on public.filing_periods from anon, authenticated;
grant select on public.filing_periods to authenticated;
create policy "filing_periods_select_authenticated" on public.filing_periods
  for select to authenticated using (true);

alter table public.gov_yields enable row level security;
revoke all on public.gov_yields from anon, authenticated;
grant select on public.gov_yields to authenticated;
create policy "gov_yields_select_authenticated" on public.gov_yields
  for select to authenticated using (true);

alter table public.fx_rates enable row level security;
revoke all on public.fx_rates from anon, authenticated;
grant select on public.fx_rates to authenticated;
create policy "fx_rates_select_authenticated" on public.fx_rates
  for select to authenticated using (true);


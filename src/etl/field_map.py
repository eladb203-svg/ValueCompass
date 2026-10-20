"""Engine series <-> dictionary_items.item_key (migrations 2 and 20261020075833_dictionary_additions).

Data, not logic: ``FIELDS[engine]`` maps the name of a provider series (a key of the engine inputs' ``f``) to its ``item_key``;
``EXTRAS[engine]`` lists series that are carried through but not stored as facts (no key, not read by scoring);
``extraction_key(engine, item)`` maps an extraction-store item to the fact it feeds (or None: the rows stay in extraction_items only).
"""
from __future__ import annotations

import re
from typing import Optional

# ---- general model (STANDARD / TECH_ASSET_LIGHT, managed care)
GENERAL = {
    "revenue": "revenue", "gross_profit": "gross_profit", "cost_of_revenue": "cost_of_revenue",
    "deferred_rev_current": "deferred_revenue_current", "impairments": "goodwill_impairment", "ebit": "ebit",
    "pretax": "pretax_income", "tax": "income_tax", "net_income": "net_income", "interest_expense": "interest_expense",
    "eps": "eps_diluted", "shares": "shares_diluted_weighted", "shares_basic": "shares_basic_weighted",
    "shares_out": "shares_period_end", "goodwill_acquired": "goodwill_acquired", "acq_amort": "acq_amortization",
    "cfo": "cfo", "capex": "capex", "sbc": "sbc", "acquisitions": "acquisitions", "buybacks": "buybacks",
    "dividends": "dividends_paid", "dps": "dps", "assets": "total_assets", "cur_assets": "current_assets",
    "cur_liab": "current_liabilities", "liabilities": "total_liabilities", "cash": "cash",
    "sti": "short_term_investments", "equity": "equity", "goodwill": "goodwill", "intangibles": "intangibles",
    "receivables": "receivables", "claims_expense": "claims_expense",
    "lt_mdebt_explicit": "noncurrent_marketable_debt", "lt_mdebt_derived": "noncurrent_marketable_debt_derived",
    "da": "da", "debt_current": "debt_current", "debt_lt": "long_term_debt",
}
BANK = {
    "net_income": "net_income", "ni_common": "net_income_common", "pref_div": "preferred_dividends", "pretax": "pretax_income",
    "eps": "eps_diluted", "shares_dil": "shares_diluted_weighted", "shares_basic": "shares_basic_weighted",
    "provision": "provision_credit_losses", "nii": "net_interest_income", "nonint": "noninterest_income",
    "goodwill_acquired": "goodwill_acquired", "goodwill_impairment": "goodwill_impairment",
    "securities_gain_loss": "investment_gains", "acquisitions": "acquisitions", "buybacks": "buybacks",
    "dividends": "dividends_paid", "dps": "dps", "assets": "total_assets", "equity": "equity", "preferred": "preferred_stock",
    "goodwill": "goodwill", "intangibles": "intangibles", "loans": "loans", "deposits": "deposits", "st_borrow": "st_borrowings",
    "lt_debt": "long_term_debt", "fhlb": "fhlb_advances", "shares_out": "shares_period_end", "acl": "acl",
    "nonaccrual": "nonaccrual_loans", "past_due_90": "past_due_90_accruing", "nco": "nco",
}
INSURANCE = {
    "revenue_total": "revenue", "premiums": "premiums_earned", "policy_fees": "policy_fees", "nii": "net_investment_income",
    "gains_realized": "investment_gains", "mrb_change": "mrb_change", "benefits": "claims_benefits",
    "total_expenses": "benefits_losses_expenses", "interest_credited": "interest_credited", "interest_expense": "interest_expense",
    "goodwill_impairment": "goodwill_impairment", "pretax": "pretax_income", "tax": "income_tax", "net_income": "net_income",
    "disc_ops": "discontinued_ops", "eps": "eps_diluted", "shares_dil": "shares_diluted_weighted", "shares_basic": "shares_basic_weighted",
    "dividends": "dividends_paid", "dps": "dps", "buybacks": "buybacks", "acquisitions": "acquisitions",
    "goodwill_acquired": "goodwill_acquired", "divestiture_proceeds": "divestiture_proceeds",
    "deconsolidation_cash": "deconsolidation_cash", "goodwill_written_off_sale": "goodwill_written_off_sale",
    "pretax_foreign": "pretax_foreign", "prior_year_dev": "prior_year_dev", "ldti_remeasurement": "ldti_remeasurement",
    "fpb_adverse_development": "fpb_adverse_development", "assets": "total_assets", "liabilities": "total_liabilities",
    "equity": "equity", "preferred": "preferred_stock", "goodwill": "goodwill", "intangibles": "intangibles",
    "claims_gross": "claims_gross", "claims_net": "claims_net", "fpb": "fpb", "pab": "pab", "unearned": "unearned",
    "reins_unpaid": "reins_unpaid", "reins_prepaid": "reins_prepaid", "separate_accounts": "separate_accounts",
    "mrb_liability": "mrb_liability", "cash": "cash", "investments": "investments_total", "debt_total": "financial_debt",
    "debt_lt": "long_term_debt", "debt_st": "debt_short_term", "debt_junior_sub": "debt_junior_subordinated",
    "shares_out": "shares_period_end", "aoci_total": "aoci_total", "aoci_afs": "aoci_afs", "aoci_drr": "aoci_discount_rate",
    "aoci_credit": "aoci_own_credit", "ldti_accretion_net": "fpb_accretion",
}
REALESTATE = {
    "total_revenue": "revenue", "rental_revenue": "rental_revenue", "other_property_revenue": "other_property_revenue",
    "prop_opex": "property_opex", "re_tax": "real_estate_tax", "repairs": "repairs_maintenance",
    "gains_re_entities": "gains_re_entities", "cost_of_revenue": "cost_of_revenue", "noi_reported": "noi_reported",
    "net_income": "net_income", "pref_div": "preferred_dividends", "interest_expense": "interest_expense",
    "interest_capitalized": "interest_capitalized", "income_tax": "income_tax", "da_total": "da", "re_depr": "re_depreciation",
    "gains_sale": "gains_sale", "impairment": "impairment", "debt_extinguishment": "debt_extinguishment",
    "transaction_costs": "transaction_costs", "sbc": "sbc", "fx_unrealized": "fx_unrealized", "straight_line": "straight_line_rent",
    "maint_capex": "maint_capex", "eps": "eps_diluted", "dps": "dps", "shares_dil": "shares_diluted_weighted",
    "shares_basic": "shares_basic_weighted", "shares_out": "shares_period_end", "dividends": "dividends_paid",
    "buybacks": "buybacks", "acq_real_estate": "acq_real_estate", "acq_business": "acq_business", "development": "development_spend",
    "capital_improvements": "capital_improvements", "ti_lc_total": "ti_lc", "sale_proceeds": "sale_proceeds", "assets": "total_assets",
    "intangibles_net": "intangibles", "re_net": "re_net", "re_gross": "re_gross", "debt_total": "financial_debt", "cash": "cash",
    "sti": "short_term_investments", "mat_year1": "debt_maturity_year1", "mat_year2": "debt_maturity_year2",
    "secured_debt_tag": "secured_debt", "equity_method_inv": "equity_method_inv", "cip": "cip", "re_dev_land": "re_dev_land",
    "nci_total": "nci_total", "pref_equity": "pref_equity", "finance_lease_liab": "finance_lease_liab", "goodwill": "goodwill",
    "nci_op": "nci_op", "nci_lp": "nci_lp", "nci_redeemable": "nci_redeemable",
}
# ---- profile router (code stage K4b): FIN-187 rd_expense, FIN-188 sic_code (text row), FIN-189 provider_industry (text row),
#      FIN-190 interest_income_operating, FIN-191 mortgage_loans_mbs, FIN-192 nav_per_share / investments_fair_value
from ..scoring.router import ROUTER_ITEMS as ROUTER  # noqa: E402  (data table lives with the router)

FIELDS = {"general": GENERAL, "bank": BANK, "insurance": INSURANCE, "realestate": REALESTATE, "router": ROUTER}

# series that are carried through (FactSet.extras) but not stored as facts: no dictionary key and not read by the scoring code
EXTRAS = {
    "general": {"claims_liability"},          # display diagnostic of run_managed_care only
    "bank": set(),
    "insurance": {"aoci_afs_tag"},            # tag variant of aoci_afs, not read
    "realestate": {"equity_method_income"},   # not read
    "router": set(),
}

# ---- extraction store: item -> fact key
_BANK_EXT = {
    "cet1_ratio_standardized": "cet1_ratio_standardized", "cet1_ratio_advanced": "cet1_ratio_advanced",
    "cet1_required_standardized": "cet1_required_standardized", "cet1_required_advanced": "cet1_required_advanced",
    "scb": "scb", "gsib_surcharge": "gsib_surcharge", "rwa_standardized": "rwa_standardized", "rwa_advanced": "rwa_advanced",
    "total_capital_standardized": "total_capital_standardized", "total_capital_advanced": "total_capital_advanced",
    "total_capital_ratio": "total_capital_ratio", "lcr_q4_average": "lcr_q4_average", "uninsured_deposits": "uninsured_deposits",
    "nonaccrual_loans": "nonaccrual_loans_extracted", "past_due_90_accruing:total": "past_due_90_accruing_extracted",
    "loans_2025": "loans_extracted", "acl_loans_2025": "acl_extracted", "nco_2025": "nco_extracted",
    "preferred_stock_2025": "preferred_stock_extracted", "avg_loans_2025": "avg_loans",
}
_INS_EXT = {
    "reg_capital_ratio": "reg_capital_ratio", "alm_disclosed": "alm_disclosed", "cat_loss_latest": "cat_loss_latest",
    "bs_cash": "inv_cash", "bs_short_term": "inv_short_term", "bs_fixed_maturities": "inv_fixed_maturities", "bs_equity": "inv_equity",
    "bs_illiquid_loans": "inv_illiquid_loans", "bs_real_estate": "inv_real_estate", "bs_other_invested": "inv_other",
    "bs_total_investments": "investments_total_extracted", "ig_fixed_income": "inv_ig_fixed", "ig_share_pct": "inv_ig_share",
    "total_fixed_income": "inv_fixed_income_total", "debt_total": "financial_debt_extracted",
}
_INS_EXT_PATTERNS = [(re.compile(r"adverse_prior_year_dev:FY\d{4}$"), "prior_year_dev_extracted"),
                     (re.compile(r"adverse_ldti_remeasurement:FY\d{4}$"), "ldti_remeasurement_extracted")]
_RE_EXT_SAME = (
    "occupancy same_property_noi_growth largest_tenant_share acquisition_yield development_yield acquisition_invested development_invested "
    "stabilized_noi stabilized_value other_property_value unencumbered_noi_share unencumbered_assets_share committed_undrawn_facilities "
    "fair_value_real_estate profile_total_assets profile_property_value profile_rental_revenue profile_total_revenue shares_basis_override "
    "inc_share_of_bplp partnership_units_weighted diluted_includes_op reported_ffo reported_affo recon_net_income recon_re_da recon_gi_net "
    "recon_nci_adjust recon_jv_other_adjust re29_re_sale_gains re29b_fx_net dev_gains_reported secured_debt rental_revenue_extracted property_opex_extracted"
).split()
_RE_EXT = {k: k for k in _RE_EXT_SAME}
_RE_EXT.update({"core_ffo_reported": "reported_core_ffo", "core_ffo_ps_reported": "reported_core_ffo_per_share",
                "ebitdare_reported": "reported_ebitdare", "maintenance_capex": "maint_capex", "ti_lc_income_preserving": "ti_lc_extracted",
                "straight_line_x": "straight_line_rent_affo", "debt_total_bs": "financial_debt_extracted", "nci_op_units": "op_units_count"})
# families: several extracted lines (<prefix>__<line>) are summed into one fact; the lines stay in extraction_items
_RE_FAMILIES = [("bsa_noi__", "bsa_noi"), ("bsa_carry__", "bsa_carry"), ("bsa_carryfin__", "bsa_carryfin"), ("bsa_inre__", "bsa_inre"),
                ("bsa_wc__", "bsa_wc"), ("bsa_excl__", "bsa_excl"), ("bsa_other__", "bsa_other"),
                ("mat_year1_x__", "debt_maturity_year1_extracted"), ("mat_year2_x__", "debt_maturity_year2_extracted"),
                ("nci_op_book__", "op_units_book_value"), ("re29_re_sale_gains__", "re29_re_sale_gains"),
                ("re29_nonre_impairments__", "re29_nonre_impairments"), ("re29a_nonre_inv__", "re29a_nonre_inv")]


# items that stay in extraction_items only (no single fact value): per-line detail, checks, bridges, quarterly rows
ROWS_ONLY = {
    "bank": re.compile(r"(loan:|funding:|past_due_90_accruing:(?!total$)|cet1_capital$)"),
    "insurance": re.compile(r"structural_event:"),
    "realestate": re.compile(r"(affo_|bs_check__|info_|same_store_revenue_growth$|.*_q$)"),
}


def extraction_key(engine: str, item: str) -> tuple:
    """-> (fact item_key or None, mode); mode: 'single' (one value per year), 'sum' (lines summed per year), 'rows' (extraction_items only)
    or 'unmapped' (a new item nobody classified yet: the field-map test fails on it)."""
    k = None
    if engine == "bank":
        k = _BANK_EXT.get(item)
    elif engine == "insurance":
        k = _INS_EXT.get(item) or next((key for rx, key in _INS_EXT_PATTERNS if rx.match(item)), None)
    elif engine == "realestate":
        k = _RE_EXT.get(item)
        if not k:
            for pre, key in _RE_FAMILIES:
                if item.startswith(pre):
                    return key, "sum"
    if k:
        return k, "single"
    rx = ROWS_ONLY.get(engine)
    if rx and rx.match(item):
        return None, "rows"
    return None, "unmapped"


def key_for(engine: str, field: str) -> Optional[str]:
    return FIELDS[engine].get(field)

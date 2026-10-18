"""INCOME_REAL_ESTATE pricing round 2 (rules 2026-10-14_22-35): RP2a, RP2b, RP1a (12-month NTDC, borderline), monthly yield, C16, extraction-derived inputs, loader."""
import csv

import pytest

from src.providers.realestate_facts import _sum_quarters, load_realestate_extracted
from src.scoring import realestate as RE
from src.scoring.c16 import C16_TEXT, apply_c16
from src.scoring.realestate import (conservative_cap_rate, derive_re, ext_sum, gov_yield, nav_components, re_buffett_price, re_graham_nav, score_realestate, score_realestate_pricing)
from test_realestate import N, _row, _yrs, reit

LAST = "FY2025"


def r(v):
    return {LAST: _row(v)}


def oe_reg(**more):
    reg = {"maintenance_capex": _yrs(20e6), "ti_lc_income_preserving": _yrs(10e6)}
    reg.update(more)
    return reg


# ------------------------------------------------------------------ monthly government yield
def test_monthly_yield_is_preferred_and_annual_is_the_flagged_fallback(tmp_path):
    p = tmp_path / "y.csv"
    p.write_text("currency,year,yield_pct,n_obs,series,source,url,retrieved,version,cross_check\nUSD,2025,4.2932,249,DGS10,s,u,2026-10-13,v1,\nUSD,2026-09,4.99,1,GS10,s,u,2026-10-14,v1,\n", encoding="utf-8")
    assert gov_yield("USD", p) == (pytest.approx(0.0499), "2026-09", "monthly")
    c = conservative_cap_rate("USD", p)
    assert c["value"] == pytest.approx(0.0799) and c["gov_kind"] == "monthly" and c["flags"] == []
    p.write_text("currency,year,yield_pct,n_obs,series,source,url,retrieved,version,cross_check\nUSD,2025,4.2932,249,DGS10,s,u,2026-10-13,v1,\n", encoding="utf-8")
    c2 = conservative_cap_rate("USD", p)
    assert c2["value"] == pytest.approx(0.072932) and c2["gov_kind"] == "annual" and any("monthly_not_available" in x for x in c2["flags"])
    p.write_text("currency,year,yield_pct,n_obs,series,source,url,retrieved,version,cross_check\nUSD,2026-09,1.00,1,GS10,s,u,2026-10-14,v1,\n", encoding="utf-8")
    assert conservative_cap_rate("USD", p)["value"] == pytest.approx(0.06)  # floor


def test_shipped_yield_table_has_a_monthly_gs10_row_and_the_insurance_loader_ignores_it():
    c = conservative_cap_rate("USD")
    assert c["gov_kind"] == "monthly" and c["gov_period"] >= "2026-09" and c["value"] == pytest.approx(max(c["gov_yield"] + 0.03, 0.06))
    from src.providers.insurance_facts import load_gov_yields
    assert set(load_gov_yields()["USD"]["yields"]) == set(range(2016, 2026))  # annual rows only


# ------------------------------------------------------------------ extraction-derived inputs
def test_extracted_straight_line_fills_missing_years_and_keeps_the_sign_convention():
    reg = oe_reg(straight_line_x=_yrs(-5e6))  # GAAP rent below cash rent -> negative adjustment increases OE
    ri = reit(reg=reg, straight_line=[None] * N)
    d = derive_re(ri)
    assert d["straight_line_adjustment"][-1] == -5e6 and d["straight_line_increases_oe"][-1] is True
    assert d["oe"][-1] == pytest.approx(d["norm_ffo"][-1] + 5e6 - 20e6 - 10e6)
    assert all(b == "OE" for b in d["oe_basis"])


def test_data_center_without_a_lessor_straight_line_line_is_zero_flagged_and_towers_have_no_ti_lc():
    ri = reit(reg={"maintenance_capex": _yrs(20e6)}, straight_line=[None] * N)
    ri.asset_type = "data centers"
    d = derive_re(ri)
    assert d["straight_line_adjustment"][-1] == 0.0 and d["oe_basis"][-1] == "OE" and any("straight_line_not_reported_set_to_0" in x for x in d["flags"])
    ri2 = reit(reg={"maintenance_capex": _yrs(20e6)})
    ri2.asset_type = "communication towers"
    d2 = derive_re(ri2)
    assert d2["tilc_pres"][-1] == 0.0 and d2["oe_basis"][-1] == "OE" and any("towers" in x for x in d2["flags"])


def test_maturity_components_are_summed_and_fill_missing_xbrl_years():
    reg = {"mat_year1_x__notes": r(1000e6), "mat_year1_x__mortgages": r(4e6), "mat_year2_x__notes": r(750e6), "committed_undrawn_facilities": r(1500e6)}
    ri = reit(reg=reg, mat_year1=[None] * N, mat_year2=[None] * N)
    assert ext_sum(ri, "mat_year1_x")[-1] == 1004e6 and ext_sum(ri, "mat_year1_x")[0] is None
    d = derive_re(ri)
    assert d["maturities_12m"][-1] == 1004e6 and d["maturities_24m"][-1] == 1754e6 and N - 1 in d["maturities_from_extraction"]
    assert d["ntdc12"][-1] == pytest.approx((100e6 + 1500e6) / 1004e6)


def test_reported_ebitdare_gap():
    ri = reit(reg={"ebitdare_reported": _yrs(1000e6)})
    d = derive_re(ri)
    assert d["ebitdare_reported"][-1] == 1000e6
    assert d["ebitdare_reconciliation_pct"][-1] == pytest.approx((d["ebitdare"][-1] - 1000e6) / 1000e6)


def test_loader_sums_four_quarters_and_keeps_provenance():
    out = {"BXP": {"maintenance_capex_q": {f"FY2024Q{i}": {"value": 10.0 * i, "unit": "USD", "verified": True, "quote": f"q{i}", "source": "s", "note": "n"} for i in (1, 2, 3, 4)},
                   "maintenance_capex": {}, "ti_lc_income_preserving": {}, "ti_lc_income_preserving_q": {}}}
    _sum_quarters(out)
    row = out["BXP"]["maintenance_capex"]["FY2024"]
    assert row["value"] == 100.0 and row["verified"] and "1Q: q1" in row["quote"] and "4Q: q4" in row["quote"]
    del out["BXP"]["maintenance_capex_q"]["FY2024Q3"]
    out["BXP"]["maintenance_capex"].clear()
    _sum_quarters(out)
    assert "FY2024" not in out["BXP"]["maintenance_capex"]  # three quarters are not a year


def test_shipped_csv_carries_the_round_2_items_with_quotes_and_verification():
    reg = load_realestate_extracted()
    assert reg["BXP"]["maintenance_capex"]["FY2025"]["value"] == pytest.approx(89.0e6, rel=0.01) and "||" in reg["BXP"]["maintenance_capex"]["FY2025"]["quote"]
    assert reg["O"]["straight_line_x"]["FY2025"]["value"] == pytest.approx(169.217e6) and reg["O"]["straight_line_x"]["FY2025"]["verified"]
    assert reg["EQR"]["ebitdare_reported"]["FY2025"]["value"] == pytest.approx(1854.941e6)
    assert reg["ARE"]["nci_op_units"]["FY2025"]["value"] == 0.0
    bsa = [k for k in reg["PLD"] if k.startswith("bsa_")]
    assert len(bsa) >= 15 and all(reg["PLD"][k]["FY2025"]["verified"] and reg["PLD"][k]["FY2025"]["quote"] for k in bsa)


# ------------------------------------------------------------------ RP2a
def bsa_reg(other=0.0, carry=0.0, inre=0.0):
    reg = oe_reg()
    reg.update({"bsa_noi__real_estate": r(6500e6), "bsa_excl__cash": r(1500e6), "bsa_wc__receivables": r(100e6), "bsa_other__misc": r(other),
                "bsa_carry__jv": r(carry), "bsa_inre__cip": r(inre), "bsa_noi__rest": r(8000e6 - 6500e6 - 1500e6 - 100e6 - other - carry)})
    return reg


def test_rp2a_classes_carry_values_and_unidentified_share():
    ri = reit(reg=bsa_reg(other=100e6, carry=300e6, inre=200e6), cash=[1500e6] * N)
    d = derive_re(ri)
    c = nav_components(ri, d)
    assert c["rp2a_basis"].startswith("extracted") and c["non_noi_counted"] == 500e6  # carry + inre
    assert c["unidentified_assets"] == pytest.approx(100e6) and c["unidentified_share_of_assets"] == pytest.approx(100 / 8000) and c["graham_block"] is False
    assert c["nav"] == pytest.approx(c["op_value"] + 500e6 - d["net_debt"][-1] - sum(c["other_claims"].values()))
    ri2 = reit(reg=bsa_reg(other=900e6), cash=[1500e6] * N)  # 11% of assets unidentified
    assert nav_components(ri2, derive_re(ri2))["graham_block"] is True


def test_rp2a_working_capital_goodwill_and_cash_are_excluded_from_the_nav():
    ri = reit(reg=bsa_reg(), cash=[1500e6] * N)
    c = nav_components(ri, derive_re(ri))
    assert c["non_noi_counted"] == 200e6 - 200e6 + 0.0  # no carry / dev lines in this fixture
    ri_b = reit(reg={**bsa_reg(), "bsa_wc__more": r(0.0)}, cash=[1500e6] * N)
    assert nav_components(ri_b, derive_re(ri_b))["nav"] == pytest.approx(c["nav"])


def test_rp2a_without_extracted_classification_falls_back_to_the_round_1_method_flagged():
    ri = reit(reg=oe_reg(), cash=[100e6] * N)
    c = nav_components(ri, derive_re(ri))
    assert c["rp2a_basis"].startswith("XBRL tags only") and "RP2a_classification_not_extracted" in c["flags"]


# ------------------------------------------------------------------ RP2b
def test_rp2b_share_basis_cases():
    base = dict(nci_total=[500e6] * N)
    # no OP units (verified absence)
    ri = reit(reg=oe_reg(nci_op_units=r(0.0)), **base)
    sb = nav_components(ri, derive_re(ri))["share_basis"]
    assert sb["basis"] == "no_op_units" and sb["nci_deducted"] == 500e6 and sb["shares"] == 300e6
    # OP units in the diluted shares: only the non-OP NCI is deducted, shares unchanged
    ri = reit(reg=oe_reg(nci_op_units=r(20e6), nci_op_book__units=r(150e6), diluted_includes_op=r(1.0)), **base)
    sb = nav_components(ri, derive_re(ri))["share_basis"]
    assert sb["basis"] == "op_units_in_diluted_shares" and sb["nci_deducted"] == 350e6 and sb["shares"] == 300e6
    # OP units not in the diluted shares: add the units, deduct only the non-OP NCI (never both)
    ri = reit(reg=oe_reg(nci_op_units=r(20e6), nci_op_book__units=r(150e6), diluted_includes_op=r(0.0)), **base)
    sb = nav_components(ri, derive_re(ri))["share_basis"]
    assert sb["basis"] == "op_units_added_to_shares" and sb["nci_deducted"] == 350e6 and sb["shares"] == 320e6
    # cannot split: shares exclude OP units and the whole NCI is deducted, flagged
    ri = reit(reg=oe_reg(), **base)
    c = nav_components(ri, derive_re(ri))
    assert c["share_basis"]["basis"] == "nci_not_split" and c["share_basis"]["nci_deducted"] == 500e6 and any("RP2b" in x for x in c["flags"])


def test_rp2b_redeemable_nci_is_a_claim_and_the_op_part_is_not_deducted_twice():
    ri = reit(reg=oe_reg(nci_op_units=r(10e6), nci_op_book__equity=r(150e6), nci_op_book__redeemable=r(100e6), diluted_includes_op=r(1.0)), nci_total=[160e6] * N, nci_redeemable=[100e6] * N)
    sb = nav_components(ri, derive_re(ri))["share_basis"]
    assert sb["nci_all"] == 260e6 and sb["op_book"] == 250e6 and sb["nci_deducted"] == pytest.approx(10e6)


# ------------------------------------------------------------------ RP1a
def test_rp1a_uses_the_12_month_near_term_debt_coverage_and_flags_borderline():
    ri = reit(reg=oe_reg(committed_undrawn_facilities=r(500e6)))
    sc = score_realestate(ri)
    g = re_buffett_price(ri, sc["derived"], sc["buffett_quality"])["guard"]
    assert g["ntdc12"] == pytest.approx((100e6 + 500e6) / 200e6) and not any("near-term" in x for x in g["quality_checks"])
    ri2 = reit(reg=oe_reg(), mat_year1=[None] * N)
    sc2 = score_realestate(ri2)
    assert any("near-term debt coverage (12 months)" in x for x in re_buffett_price(ri2, sc2["derived"], sc2["buffett_quality"])["guard"]["quality_checks"])
    d = score_realestate(ri)["derived"]
    eb = d["ebitdare"][-1]
    for mult, expect in ((7.4, False), (7.51, True), (8.0, True), (8.49, True), (8.6, False)):
        ri3 = reit(reg=oe_reg(committed_undrawn_facilities=r(500e6)), debt_total=[mult * eb + 100e6] * N)
        sc3 = score_realestate(ri3)
        gd = re_buffett_price(ri3, sc3["derived"], sc3["buffett_quality"])["guard"]
        assert gd["borderline"] is expect, mult
    ri4 = reit(reg=oe_reg(committed_undrawn_facilities=r(500e6)), debt_total=[8.2 * eb + 100e6] * N)
    sc4 = score_realestate(ri4)
    bp = re_buffett_price(ri4, sc4["derived"], sc4["buffett_quality"])
    assert bp["guard"]["blocked"] and bp["guard"]["borderline"] and bp["label"] == "not a buy price"  # the block is unchanged by the flag


# ------------------------------------------------------------------ C16
def test_c16_marks_price_and_buy_price_cannot_be_priced_and_keeps_quality():
    res = {"buffett_quality": "q", "buffett_price": {"price_score": {"state": "score", "points": 5.0}, "buy_price": {"state": "computed", "buy_price": 1.0}, "fair_value": 10.0},
           "graham_price": {"price_score": {"state": "score", "points": 1.0}, "buy_price": None, "value": 3.0}}
    out = apply_c16(res, "price of the successor")
    for k in ("buffett_price", "graham_price"):
        assert out[k]["price_score"]["state"] == "cannot_be_priced" and out[k]["buy_price"]["state"] == "cannot_be_priced" and C16_TEXT in out[k]["price_score"]["reason"]
    assert out["buffett_price"]["fair_value"] == 10.0 and out["buffett_quality"] == "q" and out["buffett_price"]["price_score_before_c16"]["points"] == 5.0
    untouched = {"buffett_price": {"price_score": {"state": "score", "points": 5.0}}}
    assert apply_c16(untouched, None) == {"buffett_price": {"price_score": {"state": "score", "points": 5.0}}}


def test_c16_in_real_estate_pricing_and_in_the_general_engine_default_is_off():
    ri = oe_reit_nav()
    sc = score_realestate(ri)
    base = score_realestate_pricing(ri, sc)
    assert base["graham_price"]["price_score"]["state"] in ("score", "blocked") and "c16_issue" not in base
    ri.price_entity_issue = "VMRK price vs EQR financials"
    out = score_realestate_pricing(ri, sc)
    assert out["graham_price"]["price_score"]["state"] == "cannot_be_priced" and out["buffett_price"]["buy_price"]["state"] == "cannot_be_priced"
    assert out["graham_price"]["value"] == base["graham_price"]["value"] and sc["buffett_quality"].score is not None  # quality and value are still shown
    from src.scoring.inputs import CompanyInputs
    assert CompanyInputs.__dataclass_fields__["price_entity_issue"].default is None


def oe_reit_nav():
    return reit(reg=oe_reg(), cash=[1500e6] * N, assets=[8000e6] * N, re_net=[6500e6] * N)


def test_c16_bank_and_insurance_inputs_carry_the_field_with_default_off():
    from src.scoring.bank import BankInputs
    from src.scoring.insurance import InsuranceInputs
    assert BankInputs.__dataclass_fields__["price_entity_issue"].default is None
    assert InsuranceInputs.__dataclass_fields__["price_entity_issue"].default is None

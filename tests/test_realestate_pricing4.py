"""INCOME_REAL_ESTATE confirmation round (rules 2026-10-15_09-30): RE29 normalized FFO, RP5a Graham price score under the distress flag."""
import pytest

from src.providers.realestate_facts import load_realestate_extracted
from src.scoring import graham as G
from src.scoring import realestate as RE
from src.scoring.interpolate import interpolate
from src.scoring.realestate import derive_re, re_graham_nav, score_realestate
from test_realestate import N, _row, _yrs, reit
from test_realestate_pricing2 import oe_reg, r
from test_realestate_pricing3 import nav_reg


# ------------------------------------------------------------------ RE29
def test_re29_gains_on_development_and_land_sales_are_deducted_from_normalized_ffo_only():
    base = derive_re(reit(reg=oe_reg()))
    d = derive_re(reit(reg=oe_reg(dev_gains_reported=_yrs(50e6))))
    assert d["ffo"][-1] == base["ffo"][-1]  # FFO (NAREIT form) is unchanged
    assert d["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] - 50e6)
    assert d["re29_gains_deducted"][-1] == 50e6 and d["oe"][-1] == pytest.approx(base["oe"][-1] - 50e6)
    d2 = derive_re(reit(reg=oe_reg(re29_re_sale_gains__land=_yrs(20e6), dev_gains_reported=_yrs(50e6))))
    assert d2["re29_gains_deducted"][-1] == 20e6  # a generic gains item takes precedence over the PLD alias (no double counting)


def test_re29_non_real_estate_impairments_are_added_back_to_normalized_ffo_only():
    base = derive_re(reit(reg=oe_reg()))
    d = derive_re(reit(reg=oe_reg(re29_nonre_impairments__goodwill=_yrs(80e6), re29_nonre_impairments__investments=_yrs(6.5e6))))
    assert d["ffo"][-1] == base["ffo"][-1]
    assert d["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] + 86.5e6)
    assert d["re29_nonre_added"][-1] == pytest.approx(86.5e6)


def test_re29_gains_and_impairments_together_and_ffo_per_share():
    base = derive_re(reit(reg=oe_reg()))
    d = derive_re(reit(reg=oe_reg(dev_gains_reported=_yrs(30e6), re29_nonre_impairments__x=_yrs(10e6))))
    assert d["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] - 20e6) and d["nffo_ps"][-1] == pytest.approx(d["norm_ffo"][-1] / 300e6)


def test_re29_company_reconciliation_line_replaces_the_tag_based_gains_and_impairments():
    base = derive_re(reit(reg=oe_reg()))
    d = derive_re(reit(reg=oe_reg(recon_gi_net=_yrs(700e6))))
    tag_based = -20e6 - 0.0 + 5e6  # gains_sale 20m, impairment 5m in the fixture
    assert d["ffo"][-1] - base["ffo"][-1] == pytest.approx(700e6 - tag_based)
    assert d["ffo_gi_adjustment"][-1] == 700e6 and base["ffo_gi_adjustment"][-1] == pytest.approx(tag_based)
    assert any("company_FFO_reconciliation_line" in x for x in d["ffo_flags"][-1])


def test_re29_shipped_csv_amounts_and_sources():
    reg = load_realestate_extracted()
    assert reg["PLD"]["dev_gains_reported"]["FY2021"]["value"] == pytest.approx(817e6) and reg["PLD"]["dev_gains_reported"]["FY2021"]["verified"]
    assert reg["AMT"]["recon_gi_net"]["FY2023"]["value"] == pytest.approx(732.8e6)
    assert reg["AMT"]["re29_nonre_impairments__spain_goodwill"]["FY2025"]["value"] == pytest.approx(80e6)
    assert reg["ARE"]["info_nonre_impairments_in_investment_income"]["FY2025"]["value"] == pytest.approx(95.716e6)
    for t, item, y in (("PLD", "dev_gains_reported", "FY2025"), ("AMT", "recon_gi_net", "FY2025"), ("ARE", "info_nonre_impairments_in_investment_income", "FY2023")):
        row = reg[t][item][y]
        assert row["quote"] and row["verified"] and "[source:" in row["source"]
    assert reg["O"]["core_ffo_reported"]["FY2025"]["value"] == pytest.approx(3884.5e6) and reg["PSA"]["core_ffo_ps_reported"]["FY2025"]["value"] == pytest.approx(16.97)


# ------------------------------------------------------------------ RP5a
def _graham(price, **kw):
    ri = reit(reg=nav_reg(**kw), cash=[1500e6] * N)
    sc = score_realestate(ri)
    ri.price_current = price
    return ri, sc, re_graham_nav(ri, sc["derived"], sc["graham_quality"])


def test_rp5a_price_score_and_buy_price_use_the_nav_without_development_when_distress_is_shown():
    ri, sc, gn = _graham(5.0)
    assert gn["distress"]["flag"] and gn["rp5a_applied"]
    full, ex = gn["value_full_nav"], gn["nav_without_development_per_share"]
    assert gn["value"] == pytest.approx(full) and ex < full  # the full NAV stays on display
    assert gn["value_for_score"] == pytest.approx(ex)
    assert gn["price_score"]["points"] == pytest.approx(interpolate((ex - 5.0) / ex, G.CLASSIC_PRICE))
    from src.scoring import buffett as B
    assert gn["buy_price"] == B._buy_price(ex, sc["graham_quality"], G.CLASSIC_MARGIN)
    assert "RP5a_price_score_on_NAV_without_development_and_land" in gn["flags"]


def test_rp5a_is_not_applied_without_the_distress_flag_and_buffett_is_unchanged():
    ri, sc, gn = _graham(80.0)
    if not gn["distress"]["flag"]:
        assert gn["rp5a_applied"] is False and gn["price_score"]["points"] == pytest.approx(interpolate((gn["value"] - 80.0) / gn["value"], G.CLASSIC_PRICE))
    ri2, sc2, gn2 = _graham(5.0)
    bp_flag = RE.re_buffett_price(ri2, sc2["derived"], sc2["buffett_quality"])
    ri2.price_current = 80.0
    bp_no_flag = RE.re_buffett_price(ri2, sc2["derived"], sc2["buffett_quality"])
    assert bp_flag["fair_value"] == pytest.approx(bp_no_flag["fair_value"])  # the Buffett value does not depend on the Graham flag (only the price score depends on the price)


def test_rp5a_nonpositive_nav_without_development_scores_zero():
    ri = reit(reg=nav_reg(bsa_inre__cip=r(25000e6)), cash=[1500e6] * N, debt_total=[30000e6] * N)  # NAV > 0 only because of the development at cost
    sc = score_realestate(ri)
    ri.price_current = 1.0
    gn = re_graham_nav(ri, sc["derived"], sc["graham_quality"])
    assert gn["state"] == "valued" and gn["rp5a_applied"] and gn["value_for_score"] <= 0
    assert gn["price_score"]["points"] == 0.0 and gn["buy_price"] is None

"""INCOME_REAL_ESTATE external-review round (rules 2026-10-15_11-15): RE30 signed normalized FFO, RE31 incremental return, NOI_PROXY edge cases, RP2c, RP1a 12-month liquidity, Graham 3.8.2."""
import pytest

from src.scoring.realestate import derive_re, nav_components, noi_proxy_inputs, rp2c_basis, re_buffett_price, re_graham_nav, score_realestate
from test_realestate import N, _items, _row, _yrs, reit
from test_realestate_pricing2 import oe_reg, r
from test_realestate_pricing3 import nav_reg


# ------------------------------------------------------------------ RE30
def test_re30_signed_items_fixed_order_and_formula():
    reg = oe_reg(dev_gains_reported=_yrs(10e6), re29_nonre_impairments__x=_yrs(4e6), re29a_nonre_inv__y=_yrs(-7e6))
    d = derive_re(reit(reg=reg, fx_unrealized=[3e6] * N, debt_extinguishment=[-5e6] * N, transaction_costs=[2e6] * N))
    items = d["re30_items"][-1]
    names = [n for n, _ in items]
    assert [n[:3] for n in names] == ["(1)", "(2)", "(3)", "(4)", "(5)", "(5)"]  # fixed order
    vals = dict(items)
    assert vals[names[0]] == 10e6 and vals[names[1]] == -4e6 and vals[names[2]] == -7e6 and vals[names[3]] == 3e6 and vals[names[4]] == -5e6 and vals[names[5]] == -2e6  # gain +, loss -
    assert d["norm_ffo"][-1] == pytest.approx(d["ffo"][-1] - sum(v for _, v in items))
    legacy = d["ffo"][-1] + 5e6 + 2e6 + 4e6 - 10e6 - 3e6 + 7e6  # the previous explicit formula of RE29 / RE29a
    assert d["norm_ffo"][-1] == pytest.approx(legacy)


def test_re30_loss_is_added_back_gain_is_removed_and_each_item_counts_once():
    base = derive_re(reit(reg=oe_reg()))
    loss = derive_re(reit(reg=oe_reg(re29a_nonre_inv__y=_yrs(-20e6))))
    gain = derive_re(reit(reg=oe_reg(re29a_nonre_inv__y=_yrs(20e6))))
    assert loss["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] + 20e6) and gain["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] - 20e6)
    twice = derive_re(reit(reg=oe_reg(re29a_nonre_inv__a=_yrs(20e6), re29a_nonre_inv__b=_yrs(0.0))))
    assert twice["norm_ffo"][-1] == pytest.approx(gain["norm_ffo"][-1])  # a component with a zero amount adds nothing
    src = derive_re(reit(reg=oe_reg(recon_gi_net=_yrs(700e6))))  # the company line already carries the gains and impairments in FFO: not removed again by items (1) and (2)
    assert src["re30_items"][-1][0][1] == 0.0 and src["re30_items"][-1][1][1] == 0.0
    assert src["norm_ffo"][-1] == pytest.approx(src["ffo"][-1] + 4e6 + 1e6)  # only the (5) items of the fixture: extinguishment loss 4m, transaction costs 1m


def test_re30_missing_ffo_gives_missing_normalized_ffo():
    d = derive_re(reit(reg=oe_reg(), gains_sale=[None] * N))
    assert d["norm_ffo"][-1] is None and d["re30_items"][-1] is None


# ------------------------------------------------------------------ RE31
def test_re31_direct_is_the_initial_yield_plus_2_5_percent_without_same_property_growth():
    reg = {"acquisition_yield": {"FY2025": _row(0.06)}, "development_yield": {"FY2025": _row(0.08)}, "same_property_noi_growth": _yrs(0.03)}
    inc = derive_re(reit(reg=reg))["incremental"]
    assert inc["basis"] == "direct" and inc["value"] == pytest.approx(0.07 + 0.025) and inc["growth_term"] == 0.025
    only_yield = derive_re(reit(reg={"acquisition_yield": {"FY2025": _row(0.06)}}))["incremental"]  # no same-property history is needed any more
    assert only_yield["basis"] == "direct" and only_yield["value"] == pytest.approx(0.085)
    assert only_yield["proxy_inputs"]["net_growth_capital"] is not None


def test_re31_noi_proxy_carries_the_same_2_5_percent_term():
    ri = reit(reg={"same_property_noi_growth": _yrs(0.03)}, acq_real_estate=[900e6] * N)
    d = derive_re(ri)
    inc = d["incremental"]
    noi = d["noi"]
    organic = noi[-5] * (1.03 ** 4 - 1)
    cap = 4 * (900e6 + 50e6)
    assert inc["basis"] == "NOI_PROXY" and inc["value"] == pytest.approx((noi[-1] - noi[-5] - organic) / cap + 0.025)


def test_re31_spread_is_incremental_return_minus_wacc_and_scored_on_the_unchanged_scale():
    ri = reit(reg={"acquisition_yield": {"FY2025": _row(0.09)}})
    sc = score_realestate(ri)
    d = sc["derived"]
    it = _items(sc["buffett_quality"])[("3.4", "1")]
    spread = d["incremental"]["value"] - d["wacc"]["value"]
    assert it.metric == pytest.approx(spread) and it.max_pts == 4
    expected = 0.0 if spread <= 0 else min(4.0, spread / 0.01)
    assert it.points == pytest.approx(expected, abs=1e-6)


# ------------------------------------------------------------------ NOI_PROXY edge cases
def test_noi_proxy_not_computable_when_net_growth_capital_is_not_positive():
    ri = reit(reg={"same_property_noi_growth": _yrs(0.03)}, acq_real_estate=[100e6] * N, sale_proceeds=[200e6] * N)  # disposal proceeds exceed acquisitions + development
    inc = derive_re(ri)["incremental"]
    assert inc["basis"] is None and "not positive" in inc["reason"] and inc["net_growth_capital"] < 0
    assert inc["proxy_inputs"]["gross_disposals"] == 5 * 200e6


def test_noi_proxy_not_computable_when_gross_disposals_exceed_10_percent_of_real_estate_at_t_minus_4():
    ri = reit(reg={"same_property_noi_growth": _yrs(0.03)}, acq_real_estate=[1000e6] * N, sale_proceeds=[200e6] * N)  # 5 x 200m = 1.0bn > 10% of 8.0bn
    inc = derive_re(ri)["incremental"]
    assert inc["basis"] is None and "10%" in inc["reason"] and inc["net_growth_capital"] > 0
    assert inc["proxy_inputs"]["disposals_share"] == pytest.approx(1000 / 8000)
    ok = derive_re(reit(reg={"same_property_noi_growth": _yrs(0.03)}, acq_real_estate=[1000e6] * N, sale_proceeds=[100e6] * N))["incremental"]  # 500m = 6.25%
    assert ok["basis"] == "NOI_PROXY"


def test_noi_proxy_inputs_are_reported_for_every_company():
    ri = reit()
    pi = noi_proxy_inputs(ri, derive_re(ri))
    assert pi["net_growth_capital"] == pytest.approx(4 * 150e6) and pi["gross_disposals"] == 0.0 and pi["re_t4"] == 8000e6 and pi["disposals_share"] == 0.0


# ------------------------------------------------------------------ RP2c
def test_rp2c_consolidated_basis_and_the_jv_double_count_check():
    ri = reit(reg=nav_reg(), cash=[1500e6] * N, equity_method_inv=[300e6] * N)
    d = derive_re(ri)
    b = rp2c_basis(ri, d)
    assert b["noi_basis"] == "consolidated" and b["ok"] and not b["jv_noi_capitalized_with_jv_interest"]
    d["noi_basis"][-1] = "proportionate share of NOI incl. JV"  # a proportionate NOI together with the JV interest added = the forbidden combination
    bad = rp2c_basis(ri, d)
    assert bad["noi_basis"] == "proportionate" and bad["jv_noi_capitalized_with_jv_interest"] and not bad["ok"]
    assert nav_components(ri, derive_re(ri))["rp2c"]["ok"]


# ------------------------------------------------------------------ RP1a: 12-month liquidity
def test_rp1a_blocks_below_1x_twelve_month_liquidity_and_not_at_or_above():
    for fac, expect in ((50e6, True), (100e6, False), (500e6, False)):  # cash 100m + facilities over 200m of debt due in 12 months
        ri = reit(reg=oe_reg(committed_undrawn_facilities=r(fac)))
        sc = score_realestate(ri)
        g = re_buffett_price(ri, sc["derived"], sc["buffett_quality"])["guard"]
        assert g["ntdc12"] == pytest.approx((100e6 + fac) / 200e6)
        assert any("12-month liquidity coverage" in x for x in g["hard"]) is expect, fac
        assert g["blocked"] or not expect


# ------------------------------------------------------------------ Graham 3.8.2
def _g382(net_income):
    ri = reit(reg=oe_reg(), net_income=net_income, straight_line=[-1000e6] * N)  # a large negative straight-line adjustment keeps OE positive when FFO is not
    return _items(score_realestate(ri)["graham_quality"])[("3.8", "2")]


def test_graham_382_excludes_transitions_with_a_non_positive_base_and_needs_two_valid_transitions():
    g = [1.04 ** i for i in range(N)]
    ni = [300e6 * x for x in g]
    assert _g382(ni).state != "missing"

    def neg(idx):
        return [(-900e6 if i in idx else v) for i, v in enumerate(ni)]  # FY2021 = index 5 ... FY2025 = index 9
    assert _g382(neg({6})).state != "missing"      # base FY2022 <= 0 excludes one transition, three remain
    assert _g382(neg({5, 6})).state != "missing"   # bases FY2021 and FY2022 <= 0: FY2023->FY2024 and FY2024->FY2025 remain (two valid)
    one_valid = _g382(neg({5, 6, 7}))              # only FY2024 -> FY2025 valid -> missing
    assert one_valid.state == "missing" and "fewer than 2 valid transitions" in one_valid.note


# ------------------------------------------------------------------ Graham NAV label
def test_graham_nav_carries_the_uniform_assumption_label():
    ri = reit(reg=nav_reg(), cash=[1500e6] * N)
    sc = score_realestate(ri)
    gn = re_graham_nav(ri, sc["derived"], sc["graham_quality"])
    assert gn["display_label"] == "conservative value under a uniform model assumption, not a market-value estimate"

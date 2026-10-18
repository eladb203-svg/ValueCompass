"""INCOME_REAL_ESTATE RE29b (rules 2026-10-15_10-50): the foreign exchange removed from normalized FFO is the net result including the hedging derivatives; control on the Q1 / Q6 gaps."""
import pytest

from src.providers.realestate_facts import load_realestate_extracted
from src.scoring.realestate import derive_re, re29b_gap_control
from test_realestate import N, _yrs, reit
from test_realestate_pricing2 import oe_reg


def test_re29b_hedged_fx_uses_the_net_result_instead_of_the_gross_tag():
    base = derive_re(reit(reg=oe_reg()))
    gross_only = derive_re(reit(reg=oe_reg(), fx_unrealized=[-220e6] * N))
    net = derive_re(reit(reg=oe_reg(re29b_fx_net=_yrs(-13e6)), fx_unrealized=[-220e6] * N))  # O FY2022: gross -220.9m, net of the hedge gains -13.3m
    assert gross_only["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] + 220e6)
    assert net["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] + 13e6)
    assert net["re29a_fx_result"][-1] == -13e6 and net["re29b_fx_gross"][-1] == -220e6 and net["re29b_fx_net_extracted"][-1] == -13e6
    assert net["oe"][-1] == pytest.approx(base["oe"][-1] + 13e6)


def test_re29b_without_a_hedge_net_equals_gross_and_nothing_changes():
    gross_only = derive_re(reit(reg=oe_reg(), fx_unrealized=[-51e6] * N))
    same = derive_re(reit(reg=oe_reg(re29b_fx_net=_yrs(-51e6)), fx_unrealized=[-51e6] * N))  # PSA euro notes: no hedging derivative
    assert same["norm_ffo"][-1] == pytest.approx(gross_only["norm_ffo"][-1]) and same["oe"][-1] == pytest.approx(gross_only["oe"][-1])


def test_re29b_net_row_applies_only_to_the_years_where_it_exists_and_the_tag_covers_the_rest():
    d = derive_re(reit(reg=oe_reg(re29b_fx_net={"FY2025": _yrs(-5e6)["FY2025"]}), fx_unrealized=[10e6] * N))
    assert d["re29a_fx_result"][-1] == -5e6 and d["re29a_fx_result"][-2] == 10e6


def test_re29b_gap_control_flags_a_widening_above_5pp_and_not_below():
    # no RE29a amount: nothing widens
    d0 = derive_re(reit(reg=oe_reg(core_ffo_reported=_yrs(1.0e9), reported_affo=_yrs(1.0e9)), sbc=[0.0] * N))
    c0 = re29b_gap_control(d0, N - 1)
    assert c0["adjustment"] == 0.0 and c0["flag"] is False
    base = derive_re(reit(reg=oe_reg(), ))
    nf = base["norm_ffo"][-1]
    sh = 300e6
    # the company measure sits at the pre-removal level; removing a 100m gain moves normalized FFO away from it by 100m / 300m shares
    comp_total = nf  # before the removal normalized FFO equals the company measure (adj added back)
    d = derive_re(reit(reg=oe_reg(core_ffo_reported=_yrs(comp_total + 100e6), re29a_nonre_inv__x=_yrs(100e6)), sbc=[0.0] * N))
    c = re29b_gap_control(d, N - 1)
    assert c["adjustment"] == 100e6
    gap_after = abs(c["q1_after"]) * 100
    assert c["q1_widening_pp"] == pytest.approx(gap_after - abs(c["q1_before"]) * 100)
    assert c["flag"] is (c["q1_widening_pp"] > 5)


def test_re29b_gap_control_threshold_exactness():
    base = derive_re(reit(reg=oe_reg()))
    nf = base["norm_ffo"][-1]
    # a company measure 3% above the pre-removal level and a removal that moves normalized FFO by exactly 4% of it -> widening 4 pp (not flagged); by 6% -> flagged
    comp = nf * 1.0
    for adj_pct, expect in ((0.04, False), (0.06, True)):
        d = derive_re(reit(reg=oe_reg(core_ffo_reported=_yrs(comp), re29a_nonre_inv__x=_yrs(adj_pct * comp))))
        c = re29b_gap_control(d, N - 1)
        # before = (nf_after + adj)/comp - 1 = 0.0; after = (nf_before_without_adj - adj ... ) -> widening = adj / comp * 100 pp
        assert c["q1_before"] == pytest.approx(0.0, abs=1e-9) and abs(c["q1_after"]) == pytest.approx(adj_pct, rel=1e-6)
        assert c["flag"] is expect


def test_re29b_gap_control_returns_nothing_without_a_company_measure_or_affo():
    d = derive_re(reit(reg=oe_reg(re29a_nonre_inv__x=_yrs(10e6))))
    c = re29b_gap_control(d, N - 1)
    assert c["q1_after"] is None and c["q6_after"] is None and c["flag"] is False


def test_re29b_shipped_csv_net_lines_for_o_pld_psa_amt():
    reg = load_realestate_extracted()
    assert reg["O"]["re29b_fx_net"]["FY2022"]["value"] == pytest.approx(-13.311e6) and reg["O"]["re29b_fx_net"]["FY2021"]["value"] == pytest.approx(0.71e6)
    assert reg["PLD"]["re29b_fx_net"]["FY2021"]["value"] == pytest.approx(173.026e6) and reg["PSA"]["re29b_fx_net"]["FY2025"]["value"] == pytest.approx(-215.583e6)
    assert reg["AMT"]["re29b_fx_net"]["FY2023"]["value"] == pytest.approx(-330.8e6) and reg["AMT"]["re29b_fx_net"]["FY2021"]["value"] == pytest.approx(557.9e6)
    for t, y in (("O", "FY2024"), ("PLD", "FY2025"), ("PSA", "FY2022"), ("AMT", "FY2025")):
        row = reg[t]["re29b_fx_net"][y]
        assert row["quote"] and row["verified"] and "[source:" in row["source"]

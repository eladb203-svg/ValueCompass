"""Offline end-to-end check of the Buffett/Graham pipelines on synthetic data."""
from datetime import date

import pytest

from src.scoring.buffett import buffett_price, buffett_quality
from src.scoring.graham import graham_price, graham_quality
from src.scoring.inputs import CompanyInputs
from src.scoring.metrics import derive


def synthetic(profile="STANDARD", dividends=True, sbc=True):
    n = 10
    g = [1.10 ** i for i in range(n)]  # 10% growth
    f = {
        "revenue": [1000e6 * x for x in g], "gross_profit": [600e6 * x for x in g],
        "ebit": [250e6 * x for x in g], "pretax": [240e6 * x for x in g], "tax": [48e6 * x for x in g],
        "net_income": [190e6 * x for x in g], "interest_expense": [10e6] * n,
        "eps": [1.9 * x for x in g], "shares": [100e6] * n, "da": [40e6 * x for x in g],
        "acq_amort": [None] * n, "cfo": [230e6 * x for x in g], "capex": [40e6 * x for x in g],
        "sbc": [20e6 * x for x in g] if sbc else [None] * n, "acquisitions": [0.0] * n,
        "buybacks": [30e6] * n, "dividends": [50e6 * x for x in g] if dividends else [0.0] * n,
        "dps": [0.5 * x for x in g] if dividends else [None] * n,
        "assets": [1500e6 * x for x in g], "cur_assets": [600e6 * x for x in g],
        "cur_liab": [300e6 * x for x in g], "liabilities": [700e6 * x for x in g],
        "cash": [200e6 * x for x in g], "sti": [50e6 * x for x in g], "equity": [800e6 * x for x in g],
        "goodwill": [100e6] * n, "intangibles": [20e6] * n, "receivables": [150e6 * x for x in g],
        "debt_current": [20e6] * n, "debt_lt": [200e6] * n,
    }
    return CompanyInputs(
        ticker="SYN", name="Synthetic", profile=profile, fy=[f"FY{2016 + i}" for i in range(n)],
        end=[date(2016 + i, 12, 31) for i in range(n)], f=f,
        sbc_state=["found" if sbc else "not_found"] * n, price_current=40.0,
        price_avg=[15.0 * x for x in g], first_annual_report=date(1995, 3, 1), as_of=date(2026, 10, 11))


def test_weights_sum_to_100_and_pipeline_runs():
    inp = synthetic()
    d = derive(inp)
    bq, gq = buffett_quality(inp, d), graham_quality(inp, d)
    assert sum(c.weight for c in bq.criteria) == pytest.approx(100)
    assert sum(c.weight for c in gq.criteria) == pytest.approx(100)
    assert 0 < bq.score <= 100 and 0 < gq.score <= 100
    assert bq.min_score <= bq.score <= bq.max_score + 1e-9
    # 3.1 is all AI in this round -> pending (neutral), not invalid
    assert bq.pending_criteria == ["3.1"] and not bq.invalid_criteria
    # Graham 3.1: AI items ignored by M2, so the code-decided half is judged on its own
    assert not gq.invalid_criteria and gq.status == "full"


def test_buffett_price_valuation_and_buy_price_rules():
    inp = synthetic()
    d = derive(inp)
    bq = buffett_quality(inp, d)
    bp = buffett_price(inp, d, bq)
    assert bp["state"] == "valued" and bp["fair_value"] > 0
    # v1.2 G3-C: OE grows 10% but the constant after-tax interest added back (8m) dilutes the measured growth of the unlevered series
    assert bp["stage1_growth"] == pytest.approx(0.09686, abs=1e-5)
    assert bp["price_score"]["state"] == "score"
    assert bp["buy_price"]["state"] in ("computed", "not_computed", "not_suitable")


def test_missing_sbc_blocks_valuation_m6():
    inp = synthetic(sbc=False)
    d = derive(inp)
    bp = buffett_price(inp, d, buffett_quality(inp, d))
    assert bp["state"] == "cannot_be_valued"
    assert "owner-earnings input missing" in bp["reason"]


def test_graham_no_dividend_is_zero_criterion():
    inp = synthetic(dividends=False)
    d = derive(inp)
    gq = graham_quality(inp, d)
    c35 = next(c for c in gq.criteria if c.id == "3.5")
    assert c35.normalized == 0 and all(i.state == "true_zero" for i in c35.items)


def test_graham_method_follows_profile():
    for profile, method in (("STANDARD", "graham_number"), ("TECH_ASSET_LIGHT", "graham_tech")):
        inp = synthetic(profile)
        d = derive(inp)
        gp = graham_price(inp, d, graham_quality(inp, d))
        assert gp["method"] == method
        assert gp["graham_number"]["state"] == "valued"
        assert gp["state"] == "valued"


def test_profile_guard_blocks_unsupported_sectors():
    from src.scoring.profiles import score_company
    for profile in ("BANK", "INSURANCE", "INCOME_REAL_ESTATE"):
        r = score_company(synthetic(profile))
        assert r["state"] == "sector_not_supported_v1" and "buffett_quality" not in r
    assert score_company(synthetic("STANDARD"))["state"] == "scored"
    assert score_company(synthetic("TECH_ASSET_LIGHT"))["state"] == "scored"
    assert score_company(synthetic("MYSTERY"))["state"] == "profile_unknown"


def test_buffett_base_is_rolled_forward_by_two_years_of_gated_growth():
    inp = synthetic()
    d = derive(inp)
    bp = buffett_price(inp, d, buffett_quality(inp, d))
    assert bp["growth_gate"]["passed"]
    assert bp["oe_base"] == pytest.approx(bp["oe_base_median"] * (1 + bp["stage1_growth"]) ** 2)
    assert bp["oe_base"] > bp["oe_base_median"]
    inp2 = synthetic()
    inp2.f["revenue"] = [1000e6] * 10  # revenue never rises -> gate fails -> growth 0 -> base unchanged
    d2 = derive(inp2)
    bp2 = buffett_price(inp2, d2, buffett_quality(inp2, d2))
    assert not bp2["growth_gate"]["passed"] and bp2["stage1_growth"] == 0.0
    assert bp2["oe_base"] == pytest.approx(bp2["oe_base_median"])
    assert any(f.startswith("growth_gate_failed") for f in bp2["flags"])


def test_deferred_revenue_cost_basis_only_for_tech_profile():
    for profile, expect in (("TECH_ASSET_LIGHT", True), ("STANDARD", False)):
        inp = synthetic(profile)
        inp.f["deferred_rev_current"] = [100e6 * (1.1 ** i) for i in range(10)]
        d = derive(inp)
        raw = inp.f["cur_assets"][-1] / inp.f["cur_liab"][-1]
        assert (d["current_ratio"][-1] > raw + 1e-9) == expect
        assert d["dr_adjusted"][-1] == expect
        if expect:  # gross margin 60%: only 40% of the deferred revenue stays in current liabilities
            dr = inp.f["deferred_rev_current"][-1]
            assert d["current_liabilities_adj"][-1] == pytest.approx(inp.f["cur_liab"][-1] - dr * 0.6)
        from src.scoring.graham import graham_quality
        flags = [f for c in graham_quality(inp, d).criteria if c.id in ("3.2", "3.3") for it in c.items for f in it.flags]
        assert ("deferred_revenue_cost_basis" in flags) == expect


def test_deferred_revenue_defaults_to_30pct_without_gross_margin():
    inp = synthetic("TECH_ASSET_LIGHT")
    inp.f["gross_profit"] = [None] * 10
    inp.f["deferred_rev_current"] = [100e6] * 10
    d = derive(inp)
    assert d["dr_default30"][-1]
    assert d["current_liabilities_adj"][-1] == pytest.approx(inp.f["cur_liab"][-1] - 100e6 * 0.7)


def test_graham_tech_cap_is_continuous():
    from src.scoring.graham import TECH_CAP
    from src.scoring.interpolate import interpolate
    assert [interpolate(q, TECH_CAP) for q in (50, 70, 77.5, 85, 90, 95, 100)] == pytest.approx(
        [15, 15, 16.5, 18, 20.0, 22, 22])


def test_graham_tbvps_negative_start_positive_end_gets_full_points():
    from src.scoring.graham import c37
    inp = synthetic()
    inp.f["goodwill"] = [2000e6] * 6 + [100e6] * 4  # tangible equity negative early, positive later
    d = derive(inp)
    assert d["tbvps"][-5] <= 0 < d["tbvps"][-1]
    it = next(i for i in c37(inp, d) if i.id == "3")
    assert it.points == 3 and "tbvps_first_year_nonpositive_improved" in it.flags
    inp.f["goodwill"] = [100e6] * 9 + [5000e6]  # negative at the end -> 0
    d = derive(inp)
    it = next(i for i in c37(inp, d) if i.id == "3")
    assert it.state == "true_zero" and it.points == 0


# ------------------------------------------------------------------ v1.1 production: G1 variant B, G2 variant C
def test_g1_rolls_forward_only_when_latest_owner_earnings_reach_the_median():
    inp = synthetic()
    d = derive(inp)
    bp = buffett_price(inp, d, buffett_quality(inp, d))
    assert d["owner_earnings"][-1] >= bp["oe_base_median"] and bp["oe_base"] == pytest.approx(bp["oe_base_median"] * (1 + bp["stage1_growth"]) ** 2)
    inp2 = synthetic()
    inp2.f["cfo"] = list(inp2.f["cfo"][:-1]) + [60e6]  # latest year collapses
    d2 = derive(inp2)
    bp2 = buffett_price(inp2, d2, buffett_quality(inp2, d2))
    assert d2["owner_earnings"][-1] < bp2["oe_base_median"]
    assert bp2["oe_base"] == pytest.approx(bp2["oe_base_median"]) and "G1_no_roll_latest_owner_earnings_below_5y_median" in bp2["flags"]


def test_g2_graham_number_uses_the_7_to_10_year_average_with_loss_years():
    from src.scoring.graham import graham_number
    inp = synthetic()
    d = derive(inp)
    gn = graham_number(inp, d)
    e = inp.f["eps"]
    assert gn["state"] == "valued" and gn["eps_years"] == 10 and gn["normalized_eps"] == pytest.approx(sum(e) / 10)
    inp2 = synthetic()
    inp2.f["eps"] = [-2.0, -2.0] + list(inp2.f["eps"][2:])
    gn2 = graham_number(inp2, derive(inp2))
    assert gn2["loss_years"] == 2 and gn2["normalized_eps"] == pytest.approx(sum(inp2.f["eps"]) / 10)
    inp3 = synthetic()
    inp3.f["eps"] = [None] * 4 + list(inp3.f["eps"][4:])
    assert graham_number(inp3, derive(inp3))["state"] == "cannot_be_valued"  # only 6 years
    inp4 = synthetic()
    inp4.f["eps"] = [-5.0] * 10
    assert graham_number(inp4, derive(inp4))["state"] == "cannot_be_valued"

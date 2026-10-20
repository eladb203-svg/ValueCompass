"""INSURANCE pricing round (spec 2026-10-13_12-40): Q7 and P1-P4."""
import math

import pytest

from test_insurance import N, ins
from src.providers.sec_companyfacts import guard_share_scale
from src.scoring import bank as BK
from src.scoring.insurance import (derive_insurance, insurance_buffett_price, insurance_graham_price, operating_eps_series, score_insurance,
                                   score_insurance_priced)


def _priced(**over):
    return score_insurance_priced(ins(**over))


# ------------------------------------------------------------------ Q7
def test_q7_q4_flagged_year_leaves_the_cost_of_float_series():
    ii = ins()
    base = derive_insurance(ii)
    assert all(not (f or "").startswith("structural_change_Q4") for f in base["cost_flags"])
    assert base["cost_of_float"][-1] is not None  # an ordinary year stays in the series


def test_q7_marks_year_from_extracted_event(monkeypatch):
    import src.scoring.insurance as I
    orig = I._float_cagr

    def fake(ii, d):
        out = orig(ii, d)
        out["transitions"][-1].update(valid=False, reason="acquisition (test)", source="extraction (quote in the CSV)")
        return out
    monkeypatch.setattr(I, "_float_cagr", fake)
    d = derive_insurance(ins())
    assert d["cost_of_float"][-1] is None and d["cost_flags"][-1].startswith("structural_change_Q4_year_excluded")
    assert d["cost_of_float"][-2] is not None


# ------------------------------------------------------------------ P1-P2 Buffett
def test_buffett_price_reuses_bank_engine_on_adjusted_equity():
    ii = ins()
    d = derive_insurance(ii)
    q = score_insurance(ii)["buffett_quality"]
    bp = insurance_buffett_price(ii, d, q)
    assert bp["state"] == "valued" and bp["e0"] == pytest.approx(d["adjusted_equity"][-1])
    norm = bp["roe_norm"]
    assert norm <= 0.20 and bp["roe_norm"] == pytest.approx(min(bp["roe_median"], 0.20))
    ref = BK.two_stage_value(d["adjusted_equity"][-1], norm, bp["g1"])["total"] / ii.series("shares_out")[-1]
    assert bp["fair_value"] == pytest.approx(ref)
    assert bp["value_to_adjusted_book"] == pytest.approx(bp["total_value"] / bp["e0"])
    assert bp["justified_pb_single_stage"] == pytest.approx((norm - 0.025) / 0.075)


def test_buffett_erosion_only_when_roe_norm_above_10pct():
    ii = ins()
    d = derive_insurance(ii)
    q = score_insurance(ii)["buffett_quality"]
    bp = insurance_buffett_price(ii, d, q)
    if bp["roe_norm"] > 0.10:
        assert bp["sensitivity"]["erosion"] < bp["sensitivity"]["base"]
    else:
        assert bp["sensitivity"]["erosion"] == bp["sensitivity"]["base"] and any(f.startswith("V7") for f in bp["flags"])
    lo, hi = bp["sensitivity_range"]
    assert lo <= bp["fair_value"] <= hi


def test_buffett_roe_cap_and_cannot_be_valued_cases():
    ii = ins(pretax=[40e9 * 1.05 ** i for i in range(N)])  # very high ROE
    d = derive_insurance(ii)
    q = score_insurance(ii)["buffett_quality"]
    bp = insurance_buffett_price(ii, d, q)
    assert bp["roe_norm"] == 0.20 and any("roe_capped" in f for f in bp["flags"])
    ii2 = ins(pretax=[0.5e9] * N, tax=[0.1e9] * N)  # ROE far below 2.5%
    d2 = derive_insurance(ii2)
    bp2 = insurance_buffett_price(ii2, d2, score_insurance(ii2)["buffett_quality"])
    assert bp2["state"] == "cannot_be_valued" and bp2["fair_value"] is None


def test_buffett_price_score_implied_return_and_buy_price_present():
    r = _priced()["buffett_price"]
    assert r["price_score"]["state"] == "score" and 0 <= r["price_score"]["points"] <= 10
    assert r["implied_return"] is not None
    assert (r["buy_price"] or {}).get("state") in {"computed", "not_computed", "not_suitable"}


# ------------------------------------------------------------------ P3-P4 Graham
def test_graham_number_is_sqrt_22_5_avg_operating_eps_adjusted_tbvps():
    ii = ins()
    d = derive_insurance(ii)
    q = score_insurance(ii)["graham_quality"]
    gp = insurance_graham_price(ii, d, q)
    eps, flags = operating_eps_series(ii, d)
    avg = sum(eps) / len(eps)
    assert gp["state"] == "valued" and gp["years_available"] == 10
    assert gp["value"] == pytest.approx(math.sqrt(22.5 * avg * d["tbvps_adj"][-1]))
    assert gp["reported_eps_comparison"]["graham_number"] == pytest.approx(math.sqrt(22.5 * sum(ii.series("eps")) / 10 * d["tbvps_adj"][-1]))


def test_graham_loss_years_stay_in_the_average_and_are_listed():
    pretax = [12e9 * 1.05 ** i for i in range(N)]
    pretax[3] = -20e9
    ii = ins(pretax=pretax)
    d = derive_insurance(ii)
    gp = insurance_graham_price(ii, d, score_insurance(ii)["graham_quality"])
    eps, _ = operating_eps_series(ii, d)
    assert gp["state"] == "valued" and gp["normalized_eps"] == pytest.approx(sum(eps) / 10)
    assert any(f.startswith("loss_years_included") for f in gp["flags"]) or not gp["loss_years"]


def test_graham_cannot_be_valued_when_average_non_positive():
    ii = ins(pretax=[-5e9] * N, tax=[0.0] * N)
    d = derive_insurance(ii)
    gp = insurance_graham_price(ii, d, score_insurance(ii)["graham_quality"])
    assert gp["state"] == "cannot_be_valued" and gp["value"] is None and gp["buy_price"] is None


def test_graham_price_score_shown_labelled_when_quality_below_55():  # rulebook A.5 / X1 / P3 (K3 H-01)
    ii = ins()
    d = derive_insurance(ii)
    q = score_insurance(ii)["graham_quality"]
    q.score, q.status = 50.0, "full"
    gp = insurance_graham_price(ii, d, q)
    assert gp["price_score"]["state"] == "score" and gp["price_score"]["points"] is not None and gp["price_score"]["label"]
    assert gp["buy_price"]["state"] == "not_suitable"


def test_operating_eps_has_no_scale_guard_any_more():
    sh = [1.0e9] * N
    sh[2] = 1.0e6
    ii = ins(shares_dil=sh)
    d = derive_insurance(ii)
    eps, flags = operating_eps_series(ii, d)
    assert eps[2] == pytest.approx(d["nop_after_tax"][2] / 1.0e6) and flags == []


# ------------------------------------------------------------------ ETL share-scale guard (all profiles)
def _guard(dil, out, basic=None):
    labels = [f"FY{2016 + i}" for i in range(len(dil))]
    f = {"shares_dil": list(dil), "shares_out": list(out), "shares_basic": list(basic or [None] * len(dil))}
    log = {k: {lab: {"tag": "T"} for lab in labels} for k in f}
    problems = []
    ev = guard_share_scale(f, labels, log, problems, ("shares_dil", "shares_basic", "shares_out"))
    return f, ev, problems, log


def test_guard_rescales_weighted_count_1000x_below_the_period_end_count_and_flags_the_year():
    f, ev, problems, log = _guard([430e6, 435e3, 433e3, 430e6], [410e6, 411e6, 412e6, 400e6])
    assert f["shares_dil"][1] == pytest.approx(435e6) and f["shares_dil"][2] == pytest.approx(433e6) and f["shares_out"] == [410e6, 411e6, 412e6, 400e6]
    assert [e["label"] for e in ev] == ["FY2017", "FY2018"] and all("x1000" in e["action"] for e in ev)
    assert log["shares_dil"]["FY2017"]["share_scale_guard"] and problems[0].startswith("share_scale_guard")


def test_guard_rescales_down_when_1000x_too_large_and_uses_neighbours_when_no_other_count():
    f, ev, _, _ = _guard([430e6, 430e9, 431e6, 432e6], [None] * 4)
    assert f["shares_dil"][1] == pytest.approx(430e6) and "/1000" in ev[0]["action"]


def test_guard_sets_larger_mismatch_missing_and_leaves_clean_series_untouched():
    f, ev, _, _ = _guard([430e6, 50e6, 431e6, 432e6], [410e6, 411e6, 412e6, 400e6])
    assert f["shares_dil"][1] is None and "missing" in ev[0]["action"]
    f2, ev2, p2, _ = _guard([430e6, 420e6, 431e6], [410e6, 411e6, 412e6])
    assert ev2 == [] and p2 == [] and f2["shares_dil"] == [430e6, 420e6, 431e6]


def test_guard_does_not_treat_a_genuine_period_end_series_as_wrong_when_weighted_counts_are_off():
    f, ev, _, _ = _guard([435e3] * 4, [410e6, 411e6, 412e6, 400e6])
    assert f["shares_out"] == [410e6, 411e6, 412e6, 400e6] and f["shares_dil"][0] == pytest.approx(435e6)


# ------------------------------------------------------------------ Q8 (a)-(e)
def test_q10_immaterial_policy_fees_absent_counts_as_zero_and_is_flagged():  # TRV-like: fees ~1% of expenses stop being tagged
    fees = [0.9e9] * 5 + [None] * 5
    d = derive_insurance(ins(policy_fees=fees))
    assert d["cost_of_float"][-1] is not None and d["uw_flags"][-1] == "policy_fees_absent_counted_as_0_Q10"
    assert d["cost_of_float"][-1] is not None and d["cost_flags"][-1] is None


def test_q10_material_underwriting_component_absent_makes_the_year_missing():
    fees = [8e9] * (N - 1) + [None]  # ~9% of total expenses in the adjacent year
    d = derive_insurance(ins(policy_fees=fees))
    assert d["cost_of_float"][-1] is None and d["cost_flags"][-1].startswith("underwriting_component_missing_Q10: policy_fees")


def test_q10_interest_expense_on_debt_is_not_an_underwriting_component():
    ie = [0.5e9] * (N - 1) + [None]
    d = derive_insurance(ins(interest_expense=ie))
    assert d["cost_of_float"][-1] is not None and d["uw_flags"][-1] is None


def test_q10_after_a_structural_year_later_years_are_compared_only_with_each_other(monkeypatch):
    import src.scoring.insurance as I
    orig = I._float_cagr

    def fake(ii, d):
        out = orig(ii, d)
        out["transitions"][-2].update(valid=False, reason="deconsolidation (test)", source="extraction (quote in the CSV)")
        return out
    monkeypatch.setattr(I, "_float_cagr", fake)
    # AIG-like: material fees tagged up to the year before the structural year, never tagged afterwards -> the post-break years are valid (0, flagged)
    fees = [8e9] * (N - 2) + [None, None]
    d = derive_insurance(ins(policy_fees=fees))
    assert d["cost_of_float"][-1] is not None and d["uw_flags"][-1] == "policy_fees_absent_counted_as_0_Q10"
    assert d["cost_flags"][-2].startswith("structural_change_Q4")


def test_q10_float_component_break_missing_only_when_material():
    big = derive_insurance(ins(pab=[None] * (N - 1) + [None], fpb=[2e9] * N))  # nothing differs -> comparable
    assert big["cost_of_float"][-1] is not None
    pab = [30e9] * (N - 1) + [None]
    assert derive_insurance(ins(pab=pab))["cost_of_float"][-1] is None
    pab_small = [0.5e9] * (N - 1) + [None]
    d = derive_insurance(ins(pab=pab_small))
    assert d["cost_of_float"][-1] is not None


def test_q8c_graham_gains_reliance_is_zero_when_sum_of_net_income_not_positive():
    r = score_insurance(ins(net_income=[-1e9] * N, pretax=[-1e9] * N, tax=[0.0] * N))["graham_quality"]
    it = next(i for c in r.criteria if c.id == "3.8" for i in c.items if i.id == "1")
    assert it.points == 0 and "total_net_income_nonpositive" in it.flags


def test_q8d_cheap_float_needs_negative_cumulative_gap_and_three_years_below():
    from test_insurance_r3 import _inp
    r = score_insurance(_inp(0.05))["buffett_quality"]
    it = next(i for c in r.criteria if c.id == "3.5" for i in c.items if i.id == "4")
    assert it.inputs["cumulative_cost"] < it.inputs["cumulative_yield"] and it.inputs["years_below_yield"] >= 3 and it.inputs["cheap_float_condition"]


def test_q8e_worst_year_is_zero_when_a_window_year_has_nonpositive_average_adjusted_equity():
    ii = ins(equity=[60e9] * (N - 2) + [1e9, 1e9], aoci_afs=[0.0] * (N - 2) + [5e9, 5e9], aoci_drr=[0.0] * N)
    d = derive_insurance(ii)
    assert d["operating_roe"][-1] is None and d["roe_flags"][-1].startswith("average_adjusted_equity_nonpositive_Q8e")
    it = next(i for c in score_insurance(ii)["buffett_quality"].criteria if c.id == "3.4" for i in c.items if i.id == "2")
    assert it.points == 0 and it.state == "true_zero"
    it1 = next(i for c in score_insurance(ii)["buffett_quality"].criteria if c.id == "3.4" for i in c.items if i.id == "1")
    assert it1.state in ("score", "missing")  # the undefined year is excluded from the median, not counted as 0


# ------------------------------------------------------------------ Q9
def _q9(monkeypatch, drop_share, disc):
    import src.scoring.insurance as I
    orig = I._float_cagr

    def fake(ii, d):
        out = orig(ii, d)
        t = out["transitions"][-1]
        t.update(valid=False, reason="deconsolidation (test)", source="extraction (quote in the CSV)")
        t["float_prev"] = d["float_ex_drr"][-3]
        t["float"] = d["float_ex_drr"][-3] * (1 - drop_share)
        return out
    monkeypatch.setattr(I, "_float_cagr", fake)
    return derive_insurance(ins(disc_ops=disc))


def test_q9_flags_when_remaining_liabilities_are_at_least_10pct_of_float(monkeypatch):
    disc = [None] * (N - 3) + [1.1e9] * 3
    d = _q9(monkeypatch, 0.30, disc)
    assert list(d["basis_mismatch"]) == ["FY2023", "FY2024"] or "FY2023" in d["basis_mismatch"]
    assert d["cost_flags"][-3].startswith("basis_mismatch_Q9_year_excluded") and d["cost_of_float"][-3] is None


def test_q9_does_not_flag_below_10pct_of_float(monkeypatch):
    disc = [None] * (N - 3) + [1.1e9] * 3
    d = _q9(monkeypatch, 0.05, disc)
    assert d["basis_mismatch"] == {} and d["cost_of_float"][-3] is not None


def test_q9_requires_the_discontinued_presentation_to_run_up_to_the_structural_year(monkeypatch):
    disc = [0.05e9] + [None] * (N - 2) + [None]
    d = _q9(monkeypatch, 0.30, disc)
    assert d["basis_mismatch"] == {}


# ------------------------------------------------------------------ P5
def test_p5_growth_gate_reads_insurance_revenue_and_operating_eps():
    prem = [90e9 * 1.05 ** i for i in range(N)]
    rev = [110e9 * (1.05 ** i if i % 2 == 0 else 0.8) for i in range(N)]  # total revenue zig-zags (investment gains), premiums rise steadily
    r = score_insurance_priced(ins(premiums=prem, revenue_total=rev))["buffett_price"]
    assert r["growth_gate_before_P5"]["revenue_rises"] < 3 and r["growth_gate"]["revenue_rises"] == 4
    assert r["growth_gate"]["eps_positive_years"] == 5

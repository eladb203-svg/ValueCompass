"""INSURANCE round 2 (spec 2026-10-13_11-45): Q1 accretion, Q2 balance-sheet categories, Q4 float over valid years, Q5 catastrophe flag."""
import pytest

from test_insurance import N, _item, _row, ins
from src.scoring.insurance import InsuranceInputs, derive_insurance, score_insurance


def _bs(**cats):
    return {f"bs_{k}": _row(v, "USD mm") for k, v in cats.items()}


# ------------------------------------------------------------------ Q2
def test_liquidity_and_complex_assets_from_balance_sheet_categories():
    r = score_insurance(ins())
    assert _item(r["graham_quality"], "3.2", "2").state == "missing" and _item(r["graham_quality"], "3.7", "3").state == "missing"
    reg = _bs(short_term=5000, fixed_maturities=60000, equity=10000, illiquid_loans=12000, real_estate=3000, other_invested=10000, total_investments=100000)
    lt = derive_insurance(ins(reg=reg, cash=[4000.0e6] * N))["latest"]
    # liquid = cash + short-term + fixed maturities + equity; denominator = total investments + cash
    assert lt["liquidity"] == pytest.approx((4000 + 5000 + 60000 + 10000) / 104000)
    assert lt["bs_residual"] == pytest.approx(0.0)
    # Q8b: no credit-quality table / stated share -> complex assets missing (no partial numerator)
    assert lt["complex_share"] is None
    assert "complex_assets_exclude_below_investment_grade_fixed_maturities_no_credit_quality_table" in lt["flags"]
    lt2 = derive_insurance(ins(reg={**reg, "ig_share_pct": _row(95.0)}, cash=[4000.0e6] * N))["latest"]
    assert lt2["complex_share"] == pytest.approx((10000 + 3000 + 10000 + 0.05 * 60000) / 104000) and "stated" in lt2["below_ig_source"]
    reg3 = {**reg, "ig_fixed_income": _row(57000, "USD mm"), "total_fixed_income": _row(60000, "USD mm")}
    assert derive_insurance(ins(reg=reg3, cash=[4000.0e6] * N))["latest"]["complex_parts"]["below_ig_fixed_maturities"] == pytest.approx(3000e6)


def test_reported_total_that_includes_cash_is_not_added_to_cash_again():
    reg = _bs(fixed_maturities=80000, equity=10000, other_invested=5000, total_investments=100000)
    reg["bs_cash"] = _row(5000, "USD mm")
    reg["bs_total_investments"]["note"] = "INCLUDES_CASH"
    lt = derive_insurance(ins(reg=reg))["latest"]
    assert lt["total_investments_and_cash"] == pytest.approx(100000e6) and lt["liquidity"] == pytest.approx((5000 + 80000 + 10000) / 100000)
    assert lt["bs_residual"] == pytest.approx(0.0)


def test_balance_sheet_categories_that_do_not_add_up_are_flagged():
    reg = _bs(fixed_maturities=60000, equity=10000, total_investments=100000)
    lt = derive_insurance(ins(reg=reg, cash=[1.0e9] * N))["latest"]
    assert any(f.startswith("balance_sheet_categories_residual") for f in lt["flags"])


# ------------------------------------------------------------------ Q1
def test_accretion_moves_from_benefits_to_investment_income_and_leaves_pretax_profit_unchanged():
    base = derive_insurance(ins())
    d = derive_insurance(ins(ldti_accretion_net=[3e9] * N))
    assert d["underwriting_result"][-1] == pytest.approx(base["underwriting_result"][-1] + 3e9)
    assert d["recurring_investment_income"][-1] == pytest.approx(base["recurring_investment_income"][-1] - 3e9)
    assert d["underwriting_result_r1"][-1] == pytest.approx(base["underwriting_result"][-1])
    assert d["nop_pretax"][-1] == base["nop_pretax"][-1]
    assert d["underwriting_result"][-1] + d["recurring_investment_income"][-1] == pytest.approx(base["underwriting_result"][-1] + base["recurring_investment_income"][-1])


def test_missing_accretion_is_zero_for_small_fpb_and_missing_for_life_like():
    d = derive_insurance(ins())
    assert d["accretion"][-1] == 0.0 and d["accretion_flags"][-1] == "no_ldti_rollforward_tagged_future_policy_benefits_immaterial"
    life = derive_insurance(ins(fpb=[60e9] * N, ldti_accretion_net=[None] * N))
    assert life["accretion"][-1] is None and life["underwriting_result"][-1] is None and life["accretion_flags"][-1] == "accretion_missing_life_like"


def test_ldti_rollforward_aggregation_rules():
    from src.providers.insurance_facts import _aggregate_rollforward as agg
    v, rule, _ = agg([([("a", "x:TotalExcludingOtherBusinessesMember")], 13536.0), ([("a", "x:InstitutionalMember")], 7238.0),
                      ([("a", "x:TotalExcludingOtherBusinessesMember"), ("b", "x:DeferredProfitLiabilityMember")], 583.0)])
    assert v == 13536.0 and "total member" in rule
    v, rule, _ = agg([([("seg", "x:SegmentLifeMember")], 1216.0), ([("p", "x:T"), ("seg", "x:SegmentLifeMember")], 82.0),
                      ([("p", "x:W"), ("seg", "x:SegmentLifeMember")], 407.0), ([("p", "x:A"), ("seg", "x:SegmentLifeMember")], 727.0)])
    assert v == 1216.0 and "aggregate" in rule
    v, rule, n = agg([([("p", "x:A"), ("s", "x:J")], 100.0), ([("p", "x:B"), ("s", "x:J")], 50.0)])
    assert v == 150.0 and "sum of product" in rule and n == 2


# ------------------------------------------------------------------ Q4
def _float_inp(float_total, reg=None, **over):
    n = len(float_total)
    base = dict(claims_gross=[None] * n, claims_net=[f * 0.6 for f in float_total], fpb=[f * 0.2 for f in float_total], pab=[f * 0.1 for f in float_total],
                unearned=[f * 0.1 for f in float_total], reins_unpaid=[0.0] * n, reins_prepaid=[0.0] * n, aoci_drr=[None] * n,
                liabilities=[f * 3 for f in float_total])
    base.update(over)
    return ins(reg=reg, **base)


def test_float_cagr_uses_valid_transitions_only_and_needs_two():
    fl = [100e9 * 1.06 ** i for i in range(N)]
    d = derive_insurance(_float_inp(fl))
    assert d["float_cagr"]["n_valid"] == 4 and d["float_cagr"]["cagr"] == pytest.approx(0.06)
    fl2 = fl[:8] + [fl[8] * 0.4, fl[8] * 0.4 * 1.06]  # deconsolidation in FY2024: float falls by 60%
    reg = {"structural_event:FY2024": _row("YES", "text", "FY2024", note="deconsolidation of a subsidiary")}
    d2 = derive_insurance(_float_inp(fl2, reg=reg))
    tr = {r["fy"]: r for r in d2["float_cagr"]["transitions"]}
    assert not tr["FY2024"]["valid"] and "deconsolidation" in tr["FY2024"]["reason"]
    assert d2["float_cagr"]["n_valid"] == 3 and d2["float_cagr"]["cagr"] == pytest.approx(0.06, abs=1e-6)
    reg3 = {f"structural_event:FY{2022 + k}": _row("YES", "text", f"FY{2022 + k}", note="x") for k in range(3)}
    d3 = derive_insurance(_float_inp(fl, reg=reg3))
    assert d3["float_cagr"]["n_valid"] == 1 and d3["float_cagr"]["cagr"] is None


def test_indicator_amounts_above_10pct_of_float_exclude_a_year_small_ones_do_not():
    fl = [100e9 * 1.06 ** i for i in range(N)]
    acq = [0.0] * N
    acq[-1] = 0.2 * fl[-2]
    tr = derive_insurance(_float_inp(fl, acquisitions=acq))["float_cagr"]["transitions"][-1]
    assert not tr["valid"] and "20%" in tr["reason"]
    acq[-1] = 0.01 * fl[-2]
    assert derive_insurance(_float_inp(fl, acquisitions=acq))["float_cagr"]["transitions"][-1]["valid"]


def test_change_in_tagged_float_components_is_a_data_break_and_fx_is_flagged():
    fl = [100e9 * 1.06 ** i for i in range(N)]
    pab = [f * 0.1 for f in fl]
    pab[-1] = None
    tr = derive_insurance(_float_inp(fl, pab=pab))["float_cagr"]["transitions"][-1]
    assert not tr["valid"] and tr["source"] == "data break"
    assert derive_insurance(_float_inp(fl, pretax_foreign=[5e9] * N))["float_cagr"]["fx_flag"] is True
    assert derive_insurance(_float_inp(fl))["float_cagr"]["fx_flag"] is False


def test_scoring_item_uses_the_valid_year_cagr():
    fl = [100e9 * 1.06 ** i for i in range(N)]
    it = _item(score_insurance(_float_inp(fl))["buffett_quality"], "3.5", "4")
    assert it.state == "score" and it.metric == pytest.approx(0.06) and it.points == pytest.approx(2.0)


# ------------------------------------------------------------------ Q5
def test_cat_flag_is_strictly_above_5pct_of_premiums():
    prem = 90e9 * 1.05 ** 9
    assert derive_insurance(ins(reg={"cat_loss_latest": _row(prem * 0.05 / 1e6, "USD mm")}))["latest"]["cat_flag"] is False
    assert derive_insurance(ins(reg={"cat_loss_latest": _row(prem * 0.0501 / 1e6, "USD mm")}))["latest"]["cat_flag"] is True

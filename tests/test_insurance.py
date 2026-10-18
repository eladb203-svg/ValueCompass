"""INSURANCE profile (spec 2026-10-13_11-00): definitions (section 3) and criteria (section 4/5) on synthetic data."""
from datetime import date

import pytest

from src.providers.insurance_facts import classify_aoci_member, load_insurance_regulatory
from src.scoring import insurance as I
from src.scoring.insurance import InsuranceInputs, derive_insurance, score_insurance

N = 10


def _row(v, unit="%", period="FY2025", note="", quote="q"):
    return {"value": v, "unit": unit, "period": period, "section": "", "quote": quote, "verified": True, "note": note}


def ins(reg=None, **over):
    g = [1.05 ** i for i in range(N)]
    f = {
        "revenue_total": [110e9 * x for x in g], "premiums": [90e9 * x for x in g], "policy_fees": [None] * N, "nii": [12e9 * x for x in g],
        "gains_realized": [1e9] * N, "mrb_change": [None] * N, "benefits": [60e9 * x for x in g],
        "total_expenses": [85e9 * x for x in g], "interest_credited": [None] * N, "interest_expense": [0.5e9] * N,
        "goodwill_impairment": [0.0] * N, "pretax": [12e9 * x for x in g], "tax": [2.4e9 * x for x in g],
        "net_income": [9.6e9 * x for x in g], "eps": [9.6 * x for x in g], "shares_dil": [1.0e9] * N, "shares_basic": [1.0e9] * N,
        "shares_out": [1.0e9] * N, "dividends": [2e9] * N, "buybacks": [3e9] * N, "acquisitions": [0.0] * N, "dps": [2.0] * N,
        "equity": [60e9 * x for x in g], "preferred": [0.0] * N, "goodwill": [5e9] * N, "intangibles": [1e9] * N,
        "aoci_afs": [-3e9] * N, "aoci_drr": [1e9] * N, "aoci_credit": [0.0] * N,
        "claims_gross": [70e9 * x for x in g], "claims_net": [None] * N, "fpb": [2e9] * N, "pab": [None] * N, "unearned": [20e9 * x for x in g],
        "reins_unpaid": [10e9] * N, "reins_prepaid": [1e9] * N, "liabilities": [150e9 * x for x in g],
        "prior_year_dev": [-1.0e9] * N, "ldti_remeasurement": [None] * N, "debt_total": [10e9] * N,
        "debt_lt": [None] * N, "debt_st": [None] * N, "debt_junior_sub": [None] * N,
    }
    f.update(over)
    return InsuranceInputs("TST", "Test Insurer", [f"FY{2016 + i}" for i in range(N)], [date(2016 + i, 12, 31) for i in range(N)], f,
                           reg if reg is not None else {}, price_current=50.0, price_avg=[20.0 * x for x in g],
                           first_annual_report=date(1995, 3, 1), as_of=date(2026, 10, 13), tag_log={"prior_year_dev": {f"FY{2016 + i}": {"tag": "T"} for i in range(N)}},
                           gov_yield={2016 + i: 0.03 for i in range(N)})


def _item(model, cid, iid):
    return next(i for c in model.criteria if c.id == cid for i in c.items if i.id == iid)


# ------------------------------------------------------------------ AOCI classification (I13): only rate-driven components are removed
def test_aoci_members_rate_driven_removed_fx_pension_hedges_kept():
    assert classify_aoci_member("us-gaap:AccumulatedNetUnrealizedInvestmentGainLossMember") == "afs"
    assert classify_aoci_member("us-gaap:AociGainLossDebtSecuritiesAvailableForSaleWithoutAllowanceForCreditLossParentMember") == "afs"
    assert classify_aoci_member("trv:AociLiabilityForFuturePolicyBenefitParentMember") == "drr"
    assert classify_aoci_member("x:AOCIMarketRiskBenefitChangeInDiscountRatesParentMember") == "drr"
    assert classify_aoci_member("x:AociMarketRiskBenefitInstrumentSpecificCreditRiskParentMember") == "credit"
    assert classify_aoci_member("us-gaap:AccumulatedTranslationAdjustmentMember") is None
    assert classify_aoci_member("us-gaap:AccumulatedDefinedBenefitPlansAdjustmentMember") is None
    assert classify_aoci_member("us-gaap:AccumulatedGainLossNetCashFlowHedgeParentMember") is None
    assert classify_aoci_member("us-gaap:AccumulatedNetUnrealizedInvestmentGainLossPreTaxMember") is None  # pre-tax duplicate is not used


# ------------------------------------------------------------------ section 3 definitions
def test_underwriting_normalized_profit_and_adjusted_equity():
    d = derive_insurance(ins())
    g9 = 1.05 ** 9
    # underwriting = insurance revenue - (total expenses - interest on debt - interest credited)
    assert d["underwriting_result"][-1] == pytest.approx(90e9 * g9 - (85e9 * g9 - 0.5e9))
    assert d["underwriting_margin"][-1] == pytest.approx(d["underwriting_result"][-1] / (90e9 * g9))
    # normalized operating profit = pretax - non-recurring gains - goodwill impairment
    assert d["nop_pretax"][-1] == pytest.approx(12e9 * g9 - 1e9)
    assert d["operating_revenue"][-1] == pytest.approx(110e9 * g9 - 1e9)
    # effective tax rate 20% (inside 0-40%)
    assert d["tax_rate"][-1] == pytest.approx(0.20) and d["nop_after_tax"][-1] == pytest.approx((12e9 * g9 - 1e9) * 0.8)
    # adjusted equity removes AFS (-3bn) and discount-rate (+1bn) AOCI, not preferred zero
    assert d["adjusted_equity"][-1] == pytest.approx(60e9 * g9 - (-3e9) - 1e9)
    assert d["tbvps_adj"][-1] == pytest.approx((d["adjusted_equity"][-1] - 6e9) / 1e9)


def test_tax_rate_rule_negative_pretax_and_unreasonable_rates_use_25pct():
    d = derive_insurance(ins(pretax=[-1e9] * N, tax=[0.2e9] * N))
    assert d["tax_rate"][-1] == 0.25
    d2 = derive_insurance(ins(tax=[9e9] * N))  # effective 75% -> clipped to 40%
    assert d2["tax_rate"][-1] == pytest.approx(0.40)


def test_operating_roe_undefined_with_flag_when_average_adjusted_equity_nonpositive():
    d = derive_insurance(ins(equity=[1e9] * N, aoci_afs=[5e9] * N, aoci_drr=[0.0] * N))  # adjusted equity -4bn (Q8e: undefined, not 0)
    assert d["operating_roe"][-1] is None and d["roe_flags"][-1] == "average_adjusted_equity_nonpositive_Q8e_roe_undefined"


def test_policy_interest_credited_is_an_investment_expense_not_a_claim():
    base = derive_insurance(ins())
    d = derive_insurance(ins(interest_credited=[5e9] * N))
    assert d["recurring_investment_income"][-1] == pytest.approx(base["recurring_investment_income"][-1] - 5e9)
    # expenses are fixed, so crediting 5bn more means 5bn LESS expense counted against underwriting
    assert d["underwriting_result"][-1] == pytest.approx(base["underwriting_result"][-1] + 5e9)


def test_mrb_remeasurement_is_non_recurring_and_removed_from_underwriting():
    d = derive_insurance(ins(mrb_change=[0.4e9] * N))
    base = derive_insurance(ins())
    assert d["non_recurring_gains"][-1] == pytest.approx(1e9 + 0.4e9)
    assert d["underwriting_result"][-1] == pytest.approx(base["underwriting_result"][-1] - 0.4e9)
    assert d["operating_revenue"][-1] == base["operating_revenue"][-1]  # MRB sits in expenses, not in revenue


# ------------------------------------------------------------------ float (I16)
def test_float_excludes_discount_rate_remeasurement_and_is_missing_without_claims_for_pc_like():
    d = derive_insurance(ins())
    g9 = 1.05 ** 9
    base = 70e9 * g9 - 10e9 + 2e9 + 20e9 * g9 - 1e9  # claims gross - reinsurance + fpb + unearned - prepaid
    assert d["float_reported"][-1] == pytest.approx(base) and d["float_ex_drr"][-1] == pytest.approx(base + 1e9)
    d2 = derive_insurance(ins(claims_gross=[None] * N, claims_net=[None] * N))
    assert d2["float_reported"][-1] is None and "claims_liability_not_tagged_float_missing" in d2["float_flags"][-1]


# ------------------------------------------------------------------ reserve deviation (I3, I20)
def test_reserve_deviation_sign_and_denominator_and_ldti_sign_reversal():
    d = derive_insurance(ins())
    g8 = 1.05 ** 8
    assert d["reserve_deviation"][-1] == pytest.approx(-1.0e9 / (70e9 * g8 + 2e9))  # favorable development -> negative deviation
    # LDTI tag positive = gain -> adverse is the negative of the tag
    d2 = derive_insurance(ins(prior_year_dev=[None] * N, ldti_remeasurement=[-0.7e9] * N))
    assert d2["adverse_b"][-1] == pytest.approx(0.7e9)


def test_life_like_company_needs_the_ldti_component():
    life = ins(fpb=[60e9] * N, claims_gross=[10e9] * N)  # fpb share 60/150 -> life-like
    d = derive_insurance(life)
    assert d["reserve_deviation"][-1] is None and d["reserve_flags"][-1] == "ldti_component_missing_life_like"
    d2 = derive_insurance(ins(fpb=[60e9] * N, claims_gross=[10e9] * N, ldti_remeasurement=[0.3e9] * N))
    assert d2["reserve_deviation"][-1] == pytest.approx((-1.0e9 - 0.3e9) / 70e9)


def test_missing_incurred_claims_liability_makes_the_denominator_missing():
    d = derive_insurance(ins(claims_gross=[None] * 4 + [70e9] * 6))
    assert d["reserve_deviation"][2] is None and d["reserve_deviation"][-1] is not None


def test_extracted_adverse_development_is_used_when_untagged():
    reg = {f"adverse_prior_year_dev:FY{2023 + k}": _row(v, "USD mm", f"FY{2023 + k}") for k, v in enumerate([-143, -709, -1036])}
    d = derive_insurance(ins(reg=reg, prior_year_dev=[None] * N))
    assert d["adverse_a"][-1] == pytest.approx(-1036e6) and d["adverse_a"][-3] == pytest.approx(-143e6)
    assert d["adverse_src"][-1] == ["a: extraction"]


# ------------------------------------------------------------------ regulatory capital multiple (I4/I14)
@pytest.mark.parametrize("ratio,basis,expect", [(560, "ACL", 2.8), (350, "CAL", 3.5), (242, "SCR", 2.42), (995, "SMR", 4.975)])
def test_reg_capital_multiple_by_basis(ratio, basis, expect):
    d = derive_insurance(ins(reg={"reg_capital_ratio": _row(ratio, note=f"basis={basis}; entity=lead subsidiary")}))
    assert d["latest"]["reg_multiple"] == pytest.approx(expect)


def test_reg_capital_missing_when_the_filing_gives_no_number_and_flags_for_stale_floor_derived_lead():
    ii = ins(reg={"reg_capital_ratio": _row("MISSING")})
    m = score_insurance(ii)["buffett_quality"]
    it = _item(m, "3.6", "1")
    assert it.state == "missing" and "exceeds_requirements_without_a_number_is_missing" in it.flags
    ii2 = ins(reg={"reg_capital_ratio": _row(409, period="FY2024", note="basis=CAL; STALE; lead subsidiary, not group; FLOOR; DERIVED")})
    it2 = _item(score_insurance(ii2)["buffett_quality"], "3.6", "1")
    assert {"prior_year_value_FY2024", "value_is_a_floor_in_excess_of", "ratio_derived_from_reported_amounts", "lead_subsidiary_not_group"} <= set(it2.flags)
    assert it2.points == pytest.approx(4.0)  # 4.09x >= 2.0x


# ------------------------------------------------------------------ criteria
def test_buffett_3_2_gross_margin_na_and_graham_3_5_4_na():
    r = score_insurance(ins())
    assert _item(r["buffett_quality"], "3.2", "1a").state == "not_applicable" and _item(r["buffett_quality"], "3.2", "1b").state == "not_applicable"
    assert _item(r["graham_quality"], "3.5", "4").state == "not_applicable" and "insurance" in _item(r["graham_quality"], "3.5", "4").note
    assert _item(r["buffett_quality"], "3.8", "4").state == "not_applicable"


def test_cost_free_float_condition_zero_when_underwriting_fails_else_cagr_scored():
    ok = score_insurance(ins())["buffett_quality"]
    assert _item(ok, "3.5", "4").state == "score"
    bad = score_insurance(ins(total_expenses=[130e9 * 1.05 ** i for i in range(N)]))["buffett_quality"]  # underwriting losses every year
    it = _item(bad, "3.5", "4")
    assert it.state == "true_zero" and "cheap_float_condition_failed" in it.flags
    assert _item(bad, "3.5", "2").points == 0.0 and _item(bad, "3.5", "1").points == 0.0


def test_graham_reserve_development_consistency_penalty():
    d = derive_insurance(ins(prior_year_dev=[2.0e9] * N))  # ~+2.5-3% adverse every year, deviation > 1% in all 5 years
    it = I._reserve_item("1", "Reserve development", 9, d, ins(), graham=True)
    assert it.inputs["penalty"] == 2.0 and it.inputs["years_over_1pct"] == 5 and it.points >= 0.0
    good = I._reserve_item("1", "Reserve development", 9, derive_insurance(ins()), ins(), graham=True)
    assert good.points == pytest.approx(9.0) and good.inputs["penalty"] == 0.0


def test_leverage_counts_all_debt_and_graham_scale():
    d = derive_insurance(ins(debt_total=[30e9] * N))
    lev = d["financial_leverage"][-1]
    assert lev == pytest.approx(30e9 / (30e9 + d["adjusted_equity"][-1]))
    it = I.g33(ins(debt_total=[30e9] * N), derive_insurance(ins(debt_total=[30e9] * N)))[1]
    assert it.state == "score" and it.points == pytest.approx(6 - 6 * 0 if lev <= 0.2 else it.points)


def test_investment_grade_share_from_amounts_or_stated_percentage():
    d = derive_insurance(ins(reg={"ig_fixed_income": _row(88783, "USD mm"), "total_fixed_income": _row(89833, "USD mm")}))
    assert d["latest"]["ig_share"] == pytest.approx(88783 / 89833)
    d2 = derive_insurance(ins(reg={"ig_share_pct": _row(92.1)}))
    assert d2["latest"]["ig_share"] == pytest.approx(0.921)


def test_non_recurring_gains_reliance_and_nonpositive_net_income():
    d = derive_insurance(ins())
    it = I.g38(ins(), d)[0]
    assert it.state == "score" and it.metric == pytest.approx(sum(max(0.0, 1e9 * 0.8) for _ in range(5)) / sum(9.6e9 * 1.05 ** i for i in range(5, 10)))
    z = I.g38(ins(net_income=[-1e9] * N), derive_insurance(ins(net_income=[-1e9] * N)))[0]
    assert z.state == "true_zero"


def test_cat_flag_is_display_only():
    d = derive_insurance(ins(reg={"cat_loss_latest": _row(8000, "USD mm")}))
    assert d["latest"]["cat_flag"] is True and d["latest"]["cat_share"] == pytest.approx(8e9 / (90e9 * 1.05 ** 9))
    d2 = derive_insurance(ins(reg={"cat_loss_latest": _row(500, "USD mm")}))
    assert d2["latest"]["cat_flag"] is False


def test_model_weights_ranges_and_d14_hold_for_a_complete_synthetic_insurer():
    r = score_insurance(ins(reg={"reg_capital_ratio": _row(500, note="basis=ACL")}))
    for m in (r["buffett_quality"], r["graham_quality"]):
        assert 0 <= m.score <= 100 and m.range_error is None and m.min_score - 1e-6 <= m.score <= m.max_score + 1e-6
    assert r["buffett_quality"].pending_criteria == ["3.1"]


def test_loader_reads_csv_with_period_and_text_values(tmp_path):
    p = tmp_path / "ins.csv"
    p.write_text('ticker,item,period,value,unit,10-K section,exact quote,verified,note\nCB,reg_capital_ratio,FY2025,MISSING,%,sec,"q, with comma",YES,n\n'
                 'CB,debt_total,FY2025,1234.5,USD mm,sec,q,NO,n\n', encoding="utf-8")
    out = load_insurance_regulatory(p)
    assert out["CB"]["reg_capital_ratio"]["value"] == "MISSING" and out["CB"]["debt_total"]["value"] == 1234.5 and out["CB"]["debt_total"]["verified"] is False

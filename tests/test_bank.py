"""BANK profile: pricing formulas, profile path and the spec's decided cases (D2-D9)."""
from datetime import date

import pytest

from src.scoring import bank as bk
from src.scoring.bank import BankInputs, bank_path, derive_bank, score_bank


bk.LOAN_MAP["TST"] = {"C&I": bk.CI, "Resi": bk.R_, "CRE": bk.CRE, "Card": bk.CONS}


def _reg(**over):
    reg = {
        "cet1_ratio_standardized": {"value": 12.0, "unit": "%", "section": "", "quote": "", "verified": True, "note": ""},
        "cet1_required_standardized": {"value": 8.0, "unit": "%", "section": "", "quote": "", "verified": True, "note": ""},
        "rwa_standardized": {"value": 400000.0, "unit": "USD mm", "section": "", "quote": "", "verified": True, "note": ""},
        "total_capital_standardized": {"value": 60000.0, "unit": "USD mm", "section": "", "quote": "", "verified": True, "note": ""},
        "lcr_q4_average": {"value": 115.0, "unit": "%", "section": "", "quote": "", "verified": True, "note": ""},
        "nonaccrual_loans": {"value": 1000.0, "unit": "USD mm", "section": "", "quote": "", "verified": True, "note": ""},
        "past_due_90_accruing:total": {"value": 200.0, "unit": "USD mm", "section": "", "quote": "", "verified": True, "note": ""},
    }
    for k, v in over.items():
        if v is None:
            reg.pop(k, None)
        else:
            reg[k] = {"value": v[0], "unit": v[1], "section": "", "quote": "", "verified": True, "note": ""}
    cats = {"loan:C&I": 100000.0, "loan:Resi": 100000.0, "loan:CRE": 50000.0, "loan:Card": 50000.0}
    for k, v in cats.items():
        reg[k] = {"value": v, "unit": "USD mm", "section": "", "quote": "", "verified": True, "note": ""}
    return reg


def synth(path="1", reg=None, ticker="TST", **fo):
    n = 10
    g = [1.06 ** i for i in range(n)]
    f = {
        "net_income": [1.0e9 * x for x in g], "pref_div": [0.05e9] * n, "pretax": [1.3e9 * x for x in g],
        "eps": [2.0 * x for x in g], "provision": [0.2e9] * n, "nii": [3.0e9 * x for x in g],
        "nonint": [1.0e9 * x for x in g], "assets": [60e9 * x for x in g], "equity": [6e9 * x for x in g],
        "preferred": [0.5e9] * n, "goodwill": [0.4e9] * n, "intangibles": [0.1e9] * n,
        "loans": [30e9 * x for x in g], "deposits": [45e9 * x for x in g], "st_borrow": [1e9] * n, "lt_debt": [4e9] * n,
        "fhlb": [0.0] * n, "shares_out": [500e6] * n, "shares_dil": [510e6] * n, "shares_basic": [505e6] * n,
        "dps": [0.5] * n, "dividends": [0.25e9] * n, "buybacks": [0.2e9] * n, "acquisitions": [0.0] * n,
        "goodwill_acquired": [0.0] * n, "nco": [0.15e9 * x for x in g], "acl": [0.4e9 * x for x in g],
        "nonaccrual": [None] * n, "past_due_90": [None] * n,
    }
    f.update(fo)
    return BankInputs(ticker=ticker, name="Test Bank", path=path, fy=[f"FY{2016 + i}" for i in range(n)],
                      end=[date(2016 + i, 12, 31) for i in range(n)], f=f, reg=reg if reg is not None else _reg(),
                      required_cet1=8.0, price_current=40.0, price_avg=[10.0 * x for x in g],
                      first_annual_report=date(1995, 3, 1), as_of=date(2026, 10, 12))


def _item(res, cid, iid):
    return next(i for c in res.criteria if c.id == cid for i in c.items if i.id == iid)


# ----------------------------------------------------------------- pricing formulas
def test_justified_ptbv_formula_and_implied_return_roundtrip():
    tb, norm = 20.0, 0.14
    v = bk.justified_ptbv(norm, tb)
    assert v == pytest.approx(20 * (0.14 - 0.025) / (0.10 - 0.025))
    # at the justified price the implied return equals the 10% discount rate, and the implied ROTCE equals ROTCE_norm
    assert bk.implied_return(norm, v / tb) == pytest.approx(0.10)
    assert bk.implied_rotce(v / tb) == pytest.approx(norm)


# ----------------------------------------------------------------- profile path
def test_profile_path_1_1b_and_none():
    assert bank_path("6021", 650, 1000, 320, 1000, True, True)["path"] == "1"  # JPM-like
    assert bank_path("6021", 574, 1000, 283, 1000, True, True)["path"] == "1b"  # Citi-like: loans/assets < 30%
    assert bank_path("6211", 300, 1000, 133, 1000, True, True)["path"] == "1b"  # Goldman-like investment bank
    assert bank_path("7372", 300, 1000, 133, 1000, False, False)["path"] is None


# ----------------------------------------------------------------- matrix and decided cases
def test_gross_margin_not_applicable_and_pretax_margin_used():
    res = score_bank(synth())["buffett_quality"]
    assert _item(res, "3.2", "1a").state == "not_applicable" and _item(res, "3.2", "1b").state == "not_applicable"
    assert _item(res, "3.2", "2a").state == "score"


def test_lcr_not_subject_is_not_applicable_d9():
    bi = synth(reg=_reg(lcr_q4_average=("NA", "%")))
    out = score_bank(bi)
    assert _item(out["buffett_quality"], "3.6", "5").state == "not_applicable"
    assert _item(out["graham_quality"], "3.2", "2").state == "not_applicable"


def test_path_1b_makes_deposit_items_not_applicable_and_normalizes_over_12():
    res = score_bank(synth(path="1b"))["graham_quality"]
    c = next(c for c in res.criteria if c.id == "3.2")
    assert _item(res, "3.2", "3").state == "not_applicable" and _item(res, "3.2", "4").state == "not_applicable"
    assert c.valid and c.applicable_max == pytest.approx(12.0)


def test_worst_credit_loss_year_caps_at_3_points_with_6_to_9_years_and_missing_below_6():
    nco_hi = [None, None, None] + [0.001e9] * 7  # 7 years of rates, tiny -> capped at 3 points
    res = score_bank(synth(nco=nco_hi))["graham_quality"]
    it = _item(res, "3.3", "1")
    assert it.state == "score" and it.points == pytest.approx(3.0)
    few = [None] * 6 + [0.001e9] * 4
    assert _item(score_bank(synth(nco=few))["graham_quality"], "3.3", "1").state == "missing"
    full = [0.001e9] * 10
    assert _item(score_bank(synth(nco=full))["graham_quality"], "3.3", "1").points == pytest.approx(5.0)


def test_concentration_hhi_and_cre_over_300pct_of_capital():
    ok = _item(score_bank(synth())["graham_quality"], "3.3", "4")
    # shares 1/3, 1/3, 1/6, 1/6 -> HHI = 0.2778
    assert ok.state == "score" and ok.metric == pytest.approx(0.2778, abs=1e-3)
    # CRE of $50bn vs total capital of $10bn -> 500% -> zero points regardless of HHI
    reg = _reg(total_capital_standardized=(10000.0, "USD mm"))
    it = _item(score_bank(synth(reg=reg))["graham_quality"], "3.3", "4")
    assert it.state == "true_zero" and "cre_gt_300pct_of_total_capital" in it.flags
    # insufficient breakdown -> AI question
    reg2 = _reg()
    for k in [k for k in reg2 if k.startswith("loan:")]:
        reg2.pop(k)
    assert _item(score_bank(synth(reg=reg2))["graham_quality"], "3.3", "4").state == "ai_pending"


def test_tbvps_cagr_negative_start_positive_end_gets_half_points_d5():
    bi = synth()
    bi.f["equity"] = [1.0e9, 1.0e9, 1.0e9, 1.0e9, 1.0e9, 1.0e9, 1.0e9, 1.0e9, 1.0e9, 30e9]  # TCE negative early (preferred+gw), positive at end
    res = score_bank(bi)["graham_quality"]
    it = _item(res, "3.7", "2")
    assert it.points == pytest.approx(1.5) and "negative_start_positive_end_D5" in it.flags


def test_allowance_erosion_pretax_loss_counts_as_20pct_only_if_nco_exceeds_provision_d6():
    pre = [1.0e9] * 7 + [-0.5e9, 1.0e9, 1.0e9]
    nco = [0.1e9] * 10
    prov_hi = [0.2e9] * 10  # NCO < provision -> the loss year counts as 0%
    it = _item(score_bank(synth(pretax=pre, nco=nco, provision=prov_hi))["graham_quality"], "3.8", "2")
    assert it.points == pytest.approx(3.0)
    prov_lo = [0.05e9] * 10  # NCO > provision in the loss year -> >=20% -> 0 points
    it2 = _item(score_bank(synth(pretax=pre, nco=nco, provision=prov_lo))["graham_quality"], "3.8", "2")
    assert it2.points == pytest.approx(0.0)


def test_eps_stability_loss_year_gives_zero():
    eps = [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, -0.5, 2.7, 2.8]
    it = _item(score_bank(synth(eps=eps))["graham_quality"], "3.8", "1")
    assert it.state == "true_zero"


def test_loan_growth_skips_acquisition_years_d7():
    loans = [30e9, 31e9, 32e9, 33e9, 34e9, 35e9, 36e9, 90e9, 92e9, 94e9]  # FY2023 jump is an acquisition year
    gwa = [0.0] * 7 + [3e9] + [0.0, 0.0]
    bi = synth(loans=loans, goodwill_acquired=gwa)
    it = _item(score_bank(bi)["buffett_quality"], "3.8", "4")
    assert it.state == "score" and "FY2023" in it.inputs["acquisition_years_skipped"]
    assert it.metric < 0.05  # the 150% jump is excluded
    few = _item(score_bank(synth(loans=[None] * 8 + [1e9, 1.1e9]))["buffett_quality"], "3.8", "4")
    assert few.state == "missing"


def test_tangible_value_creation_flags_share_count_jump_d2():
    so = [500e6] * 8 + [600e6, 600e6]
    it = _item(score_bank(synth(shares_out=so))["buffett_quality"], "3.5", "3")
    assert any(f.startswith("share_count_change_gt10pct") for f in it.flags)


def test_summary_weights_sum_to_100():
    out = score_bank(synth())
    for m in (out["buffett_quality"], out["graham_quality"]):
        assert sum(c.weight for c in m.criteria) == pytest.approx(100.0)


# ================================================================= bank regression round (spec 2026-10-12_21-05)
def _row(v, unit="%", section="", note=""):
    return {"value": v, "unit": unit, "section": section, "quote": "", "verified": True, "note": note}


def test_d10_buffer_is_min_over_approaches_of_ratio_minus_own_requirement():
    # Citi-like: Standardized 13.18 vs 11.6 -> 1.58; Advanced 11.93 vs 10.5 -> 1.43; binding = 1.43 (Advanced)
    reg = _reg(cet1_ratio_standardized=(13.18, "%"), cet1_required_standardized=(11.6, "%"),
               cet1_ratio_advanced=(11.93, "%"), cet1_required_advanced=(10.5, "%"),
               rwa_advanced=(450000.0, "USD mm"), total_capital_advanced=(58000.0, "USD mm"))
    lt = derive_bank(synth(reg=reg))["latest"]
    assert lt["buffer_by_approach"]["standardized"] == pytest.approx(1.58)
    assert lt["buffer_by_approach"]["advanced"] == pytest.approx(1.43)
    assert lt["capital_buffer"] == pytest.approx(1.43) and lt["approach"] == "advanced"
    assert lt["total_capital"] == pytest.approx(58000.0e6)  # RWA / total capital follow the buffer-binding approach
    # the first-round measure (lower ratio vs one supplied requirement of 8.0) is kept only for comparison
    assert lt["buffer_round1"] == pytest.approx(11.93 - 8.0)


def test_d10_approach_without_a_reported_requirement_is_excluded_and_flagged():
    reg = _reg(cet1_ratio_advanced=(9.0, "%"))  # no advanced requirement row
    lt = derive_bank(synth(reg=reg))["latest"]
    assert lt["approach"] == "standardized" and "requirement_missing_advanced_approach_excluded" in lt["flags"]


def test_d11_nonaccrual_only_rate_and_coverage():
    lt = derive_bank(synth())["latest"]
    assert lt["nonaccrual"] == pytest.approx(1000.0e6)  # the 90+ days accruing amount (200) is display only
    assert lt["past_due_90_display_only"] == pytest.approx(200.0e6)
    assert lt["acl_to_nonaccrual"] == pytest.approx(lt["acl"] / 1000.0e6)
    out = score_bank(synth())
    assert _item(out["buffett_quality"], "3.6", "3").name == "Nonaccrual loans"
    assert "ACL / nonaccrual" in _item(out["buffett_quality"], "3.6", "4").name
    reg = _reg(nonaccrual_loans=(0.0, "USD mm"))
    out0 = score_bank(synth(reg=reg))
    assert _item(out0["buffett_quality"], "3.6", "4").points == 1 and _item(out0["graham_quality"], "3.3", "3").points == 4


def test_d12_lcr_exempt_is_na_subject_without_value_is_missing_value_is_scored():
    na = score_bank(synth(reg=_reg(lcr_q4_average=("NA", "%"))))
    assert _item(na["buffett_quality"], "3.6", "5").state == "not_applicable"
    mi = score_bank(synth(reg=_reg(lcr_q4_average=("MISSING", "%"))))
    assert _item(mi["buffett_quality"], "3.6", "5").state == "missing" and _item(mi["graham_quality"], "3.2", "2").state == "missing"
    no_row = _reg()
    no_row.pop("lcr_q4_average")
    assert _item(score_bank(synth(reg=no_row))["buffett_quality"], "3.6", "5").state == "missing"
    ok = score_bank(synth(reg=_reg(lcr_q4_average=(115.0, "%"))))
    assert _item(ok["buffett_quality"], "3.6", "5").points == pytest.approx(2.0)


def test_d15_repo_is_counted_once_in_the_deposit_funding_denominator():
    reg = _reg(**{"funding:deposits:Total deposits": (700.0, "USD mm"),
                  "funding:repo:Repos": (100.0, "USD mm"),
                  "funding:short_term:Short-term borrowings": (50.0, "USD mm"),
                  "funding:long_term:Long-term debt": (150.0, "USD mm")})
    lt = derive_bank(synth(reg=reg))["latest"]
    assert lt["deposit_funding"] == pytest.approx(700 / 1000)
    assert {l["role"] for l in lt["funding_lines"]} == {"deposits", "repo", "short_term", "long_term"}
    it = _item(score_bank(synth(reg=reg))["graham_quality"], "3.2", "3")
    assert it.metric == pytest.approx(0.70) and "repo_included_D15" in it.flags


# ----------------------------------------------------------------- pricing v2
def test_two_stage_equals_single_stage_when_growth_is_the_terminal_rate():
    v = bk.two_stage_value(100.0, 0.15, 0.025)["total"]
    assert v == pytest.approx(100.0 * (0.15 - 0.025) / (0.10 - 0.025))


def test_two_stage_value_equals_tce_when_rotce_equals_cost_of_equity():
    assert bk.two_stage_value(100.0, 0.10, 0.08)["total"] == pytest.approx(100.0)


def test_two_stage_growth_creates_more_value_than_terminal_growth_for_rotce_above_cost_of_equity():
    hi = bk.two_stage_value(100.0, 0.16, 0.09)["total"]
    lo = bk.two_stage_value(100.0, 0.16, 0.025)["total"]
    assert hi > lo > 100.0
    er = bk.two_stage_value(100.0, 0.16, 0.09, erosion=True)["total"]
    assert 100.0 < er < hi  # fading ROTCE with zero terminal residual income is more conservative


def test_buffett_price_v2_inputs_and_sensitivity():
    bi = synth()
    d = derive_bank(bi)
    q = score_bank(bi)["buffett_quality"]
    bp = bk.bank_buffett_price(bi, d, q)
    assert bp["state"] == "valued" and bp["method"] == "two_stage_excess_returns"
    # payout = (dividends + buybacks) / net income over 5 years, clipped to 0-100%
    ni = sum(bi.f["net_income"][-5:])
    assert bp["payout"] == pytest.approx(min(1.0, 5 * (0.25e9 + 0.2e9) / ni))
    assert bp["g1"] == pytest.approx(min(0.12, bp["rotce_norm"] * (1 - bp["payout"])))
    lo, hi = bp["sensitivity_range"]
    assert lo <= bp["fair_value"] <= hi and bp["sensitivity"]["rotce_plus_1pp"] > bp["sensitivity"]["rotce_minus_1pp"]
    # the single-stage value is kept as a comparison only
    assert bp["v1_single_stage"]["fair_value"] is not None and bp["single_stage_sanity"] == pytest.approx(
        (bp["rotce_norm"] - 0.025) / 0.075)
    assert bp["price_score"]["state"] == "score"


def test_buffett_price_v2_growth_gate_failure_uses_terminal_growth_and_cannot_value_only_for_nonpositive_tce():
    bi = synth()
    bi.f["eps"] = [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, -1.0, 2.5, -1.0, 2.7]  # loss years inside the last 5 and two >10% declines
    d = derive_bank(bi)
    bp = bk.bank_buffett_price(bi, d, score_bank(bi)["buffett_quality"])
    assert not bp["growth_gate"]["passed"] and bp["g1"] == pytest.approx(0.025)
    assert any(f.startswith("growth_gate_failed") for f in bp["flags"])
    neg = synth(equity=[0.1e9] * 10)  # TCE negative
    dn = derive_bank(neg)
    assert bk.bank_buffett_price(neg, dn, score_bank(neg)["buffett_quality"])["state"] == "cannot_be_valued"


def test_implied_return_roundtrip_for_the_two_stage_model():
    bi = synth()
    d = derive_bank(bi)
    q = score_bank(bi)["buffett_quality"]
    base = bk.bank_buffett_price(bi, d, q)
    tce0, shares, norm, g1 = base["tce0"], base["shares"], base["rotce_norm"], base["g1"]
    bi.price_current = bk.two_stage_value(tce0, norm, g1, r=0.12)["total"] / shares
    bp = bk.bank_buffett_price(bi, d, q)
    assert bp["implied_return"] == pytest.approx(0.12, abs=2e-3)
    assert bk._solve(lambda x: x - 5.0, 0.0, 1.0, decreasing=False) == "no solution"


def test_graham_v2_uses_ten_year_average_eps_and_keeps_the_3y_value_for_comparison():
    bi = synth()
    d = derive_bank(bi)
    gq = score_bank(bi)["graham_quality"]
    gp = bk.bank_graham_price(bi, d, gq)
    ne = sum(bi.f["eps"]) / 10
    assert gp["value"] == pytest.approx((22.5 * ne * d["tbvps"][-1]) ** 0.5) and gp["eps_years"] == 10
    assert gp["v1_3y_eps"]["value"] == pytest.approx((22.5 * sum(bi.f["eps"][-3:]) / 3 * d["tbvps"][-1]) ** 0.5)
    part = synth(eps=[None] * 2 + [2.0] * 8)
    gpp = bk.bank_graham_price(part, derive_bank(part), gq)
    assert gpp["state"] == "valued" and any("available_years" in f for f in gpp["flags"])
    few = synth(eps=[None] * 4 + [2.0] * 6)
    assert bk.bank_graham_price(few, derive_bank(few), gq)["state"] == "cannot_be_valued"
    loss = synth(eps=[-3.0] * 5 + [1.0] * 5)  # loss years stay in the average -> average <= 0
    assert bk.bank_graham_price(loss, derive_bank(loss), gq)["state"] == "cannot_be_valued"


# ================================================================= final bank round (spec 2026-10-12_22-35: V5-V11, 6c)
def _gq(bi):
    return score_bank(bi)["graham_quality"]


def test_v5_one_off_loss_year_is_valued_and_flagged():
    bi = synth()
    bi.f["eps"] = list(bi.f["eps"])
    bi.f["eps"][4] = -1.0  # PPNR (pretax + provision) > 0 and provision 0.2bn <= PPNR -> one-off
    d = derive_bank(bi)
    gp = bk.bank_graham_price(bi, d, _gq(bi))
    assert gp["state"] == "valued" and gp["loss_years"][0]["kind"] == "one_off"
    assert any(f.startswith("V5_one_off_loss_year_FY2020") for f in gp["flags"])


def test_v5_operating_loss_year_cannot_be_valued():
    bi = synth()
    bi.f["eps"] = list(bi.f["eps"])
    bi.f["eps"][4] = -1.0
    bi.f["pretax"] = list(bi.f["pretax"])
    bi.f["pretax"][4] = -2.0e9
    bi.f["provision"] = list(bi.f["provision"])
    bi.f["provision"][4] = 1.0e9  # PPNR = -1bn <= 0 -> operating
    d = derive_bank(bi)
    gp = bk.bank_graham_price(bi, d, _gq(bi))
    assert gp["state"] == "cannot_be_valued" and "operating" in gp["reason"]
    bi.f["pretax"][4] = 0.5e9
    bi.f["provision"][4] = 3.0e9  # PPNR 3.5bn > 0 but provision (3.0bn) <= PPNR is one-off; make provision exceed PPNR
    bi.f["provision"][4] = 4.0e9
    bi.f["pretax"][4] = -3.0e9  # PPNR = 1bn < provision 4bn -> operating
    assert bk.bank_graham_price(bi, derive_bank(bi), _gq(bi))["state"] == "cannot_be_valued"


def test_v5_price_score_shown_labelled_when_graham_quality_below_55():  # rulebook A.5 / X1 (K3 H-01)
    bi = synth()
    d = derive_bank(bi)
    q = _gq(bi)
    assert q.score >= 55 and bk.bank_graham_price(bi, d, q)["price_score"]["state"] == "score"
    q.score = 54.9
    gp = bk.bank_graham_price(bi, d, q)
    assert gp["price_score"]["state"] == "score" and gp["price_score"]["points"] is not None and gp["price_score"]["label"] and gp["value"] is not None
    assert gp["buy_price"]["state"] == "not_suitable"


def test_v6_rotce_norm_at_or_below_2_5pct_cannot_be_valued_and_never_negative():
    bi = synth(net_income=[0.01e9] * 10)  # ROTCE ~0.2%
    d = derive_bank(bi)
    bp = bk.bank_buffett_price(bi, d, score_bank(bi)["buffett_quality"])
    assert bp["state"] == "cannot_be_valued" and "V6" in bp["reason"] and bp["fair_value"] is None


def test_v7_erosion_equals_base_when_rotce_norm_at_or_below_10pct_and_negative_scenarios_are_dropped():
    bi = synth(net_income=[0.45e9] * 10)  # ROTCE roughly 8%
    d = derive_bank(bi)
    bp = bk.bank_buffett_price(bi, d, score_bank(bi)["buffett_quality"])
    assert bp["state"] == "valued" and bp["rotce_norm"] < 0.10
    assert bp["sensitivity"]["erosion"] == pytest.approx(bp["fair_value"])
    assert all(v is None or v > 0 for v in bp["sensitivity"].values())
    hi = synth()
    dh = derive_bank(hi)
    bh = bk.bank_buffett_price(hi, dh, score_bank(hi)["buffett_quality"])
    assert bh["rotce_norm"] > 0.10 and bh["sensitivity"]["erosion"] < bh["fair_value"]


def test_v8_solver_bounds_tolerance_and_no_solution():
    assert bk._solve(lambda x: x - 0.123, -0.20, 0.40, decreasing=False) == pytest.approx(0.123, abs=0.011)
    assert bk._solve(lambda x: x - 0.9, -0.20, 0.40, decreasing=False) == "no solution"
    assert bk._solve(lambda x: x + 0.5, -0.20, 0.40, decreasing=False) == "no solution"
    # discount rate at or below terminal growth is undefined: a root there is "no solution"
    assert bk._solve(lambda r: 5.0 - r * 100, -0.20, 0.40, decreasing=True, undefined_below=0.025) == pytest.approx(0.05, abs=2e-4)
    assert bk._solve(lambda r: 1.0 - r * 100, -0.20, 0.40, decreasing=True, undefined_below=0.025) == "no solution"


def test_v9_requirement_is_computed_from_scb_and_stated_value_wins_on_mismatch(caplog):
    base = _reg(cet1_required_standardized=None, scb=(2.6, "%"))
    lt = derive_bank(synth(reg=base))["latest"]
    assert lt["required_std"] == pytest.approx(7.1) and lt["v9"]["computed"] == pytest.approx(7.1) and lt["v9"]["match"] is None
    assert "requirement_computed_V9_4.5_plus_SCB" in lt["flags"]
    ok = derive_bank(synth(reg=_reg(cet1_required_standardized=(7.1, "%"), scb=(2.6, "%"))))["latest"]
    assert ok["v9"]["match"] is True
    with caplog.at_level("WARNING"):
        bad = derive_bank(synth(reg=_reg(cet1_required_standardized=(7.5, "%"), scb=(2.6, "%"))))["latest"]
    assert bad["required_std"] == pytest.approx(7.5) and bad["v9"]["match"] is False and "V9_mismatch_stated_requirement_used" in bad["flags"]
    assert "V9" in caplog.text


def test_v10_lcr_measurement_type_and_date_are_stored():
    q4 = derive_bank(synth())["latest"]
    assert q4["lcr_measure"] == "q4_average" and q4["lcr_date"] == "2025-12-31"
    reg = _reg()
    reg["lcr_q4_average"]["note"] = "QUARTER-END figure, not a Q4 average"
    out = score_bank(synth(reg=reg))
    assert derive_bank(synth(reg=reg))["latest"]["lcr_measure"] == "quarter_end"
    assert "lcr_quarter_end_not_q4_average" in _item(out["buffett_quality"], "3.6", "5").flags


def test_v11_not_applicable_lcr_is_not_missing_and_does_not_lower_coverage():
    out = score_bank(synth(reg=_reg(lcr_q4_average=("NA", "%"))))
    it = _item(out["buffett_quality"], "3.6", "5")
    assert it.state == "not_applicable" and "lcr_not_applicable_V11" in it.flags


def test_no_credit_crisis_note_on_worst_credit_loss_year():
    out = score_bank(synth())
    it = _item(out["graham_quality"], "3.3", "1")
    assert "window contains no credit crisis" in it.flags and it.points is not None


def test_production_thresholds_are_the_current_ones_and_candidates_are_not_in_the_production_module():
    assert bk.TH["graham_buffer"] == [(0.0, 0), (3.0, 8)]
    assert bk.TH["nonaccrual_graham"] == [(0.005, 3), (0.03, 0)]
    assert bk.TH["acl_graham"] == [(0.75, 0), (2.0, 4)] and bk.TH["deposit_funding"] == [(0.50, 0), (0.80, 2)]
    assert not hasattr(bk, "TH_CANDIDATE") and not hasattr(bk, "thresholds_override")


# ----------------------------------------------------------------- V5 adjusted PPNR (2026-10-13)
BN = 1e9


def test_v5_tfc_like_goodwill_impairment_makes_the_loss_year_one_off():
    # FY2023: PPNR 1.3bn, provision 2.1bn (gap 0.8bn); goodwill impairment 6.1bn closes it
    ly = bk.classify_loss_year("FY2023", -2.0, 1.3 * BN, 2.1 * BN, -4.8 * BN, 6.1 * BN, -0.5 * BN, "GoodwillImpairmentLoss", "DebtSecuritiesRealizedGainLoss")
    assert ly["kind"] == "one_off" and ly["cause"] == "goodwill impairment" and ly["adjusted_ppnr"] == pytest.approx(1.3 * BN + 6.1 * BN + 0.5 * BN)
    assert ly["goodwill_tag"] == "GoodwillImpairmentLoss"


def test_v5_key_like_securities_loss_makes_the_loss_year_one_off():
    ly = bk.classify_loss_year("FY2024", -0.5, 0.0, 0.3 * BN, -0.3 * BN, None, -1.9 * BN)
    assert ly["kind"] == "one_off" and ly["cause"] == "securities losses" and ly["securities_loss"] == pytest.approx(1.9 * BN)
    # a securities gain is never deducted
    assert bk.classify_loss_year("FY2024", -0.5, 0.0, 0.3 * BN, -0.3 * BN, None, +1.9 * BN)["kind"] == "operating"


def test_v5_c_like_tax_cause_when_ppnr_exceeds_provision_and_pretax_is_positive():
    ly = bk.classify_loss_year("FY2017", -0.3, 30.2 * BN, 7.5 * BN, 22.0 * BN, None, None)
    assert ly["kind"] == "one_off" and ly["cause"] == "tax"
    assert bk.classify_loss_year("FY2017", -0.3, 30.2 * BN, 7.5 * BN, -1.0 * BN, None, None)["cause"] == "unidentified"


def test_v5_flg_like_credit_loss_year_stays_operating():
    ly = bk.classify_loss_year("FY2024", -1.0, -0.3 * BN, 1.1 * BN, -1.4 * BN, 0.0, -0.05 * BN)
    assert ly["kind"] == "operating" and ly["cause"] == "credit losses"
    assert bk.classify_loss_year("FY2024", -1.0, None, 1.1 * BN, None, None, None)["kind"] == "unclassified"


def test_v5_adjustments_are_read_from_bank_inputs_and_flag_the_cause():
    bi = synth()
    bi.f["eps"] = list(bi.f["eps"]); bi.f["eps"][4] = -1.0
    bi.f["pretax"] = list(bi.f["pretax"]); bi.f["pretax"][4] = -1.5e9
    bi.f["provision"] = list(bi.f["provision"]); bi.f["provision"][4] = 2.0e9  # PPNR 0.5bn < provision
    assert bk.bank_graham_price(bi, derive_bank(bi), _gq(bi))["state"] == "cannot_be_valued"
    bi.f["goodwill_impairment"] = [None] * 4 + [3.0e9] + [None] * 5
    bi.tag_log = {"goodwill_impairment": {"FY2020": {"tag": "GoodwillImpairmentLoss"}}}
    gp = bk.bank_graham_price(bi, derive_bank(bi), _gq(bi))
    assert gp["state"] == "valued" and gp["loss_years"][0]["cause"] == "goodwill impairment"
    assert gp["loss_years"][0]["goodwill_tag"] == "GoodwillImpairmentLoss" and any("goodwill impairment" in f for f in gp["flags"])


def test_v8_implied_return_bound_just_above_2_5pct_and_below_display():
    bi = synth()
    d = derive_bank(bi)
    q = score_bank(bi)["buffett_quality"]
    base = bk.bank_buffett_price(bi, d, q)
    assert isinstance(base["implied_return"], float) and base["implied_return"] > 0.025
    bi.price_current = 1e9  # the price implies a return below 2.5%
    assert bk.bank_buffett_price(bi, d, q)["implied_return"] == "below 2.5%"
    bi.price_current = 0.01  # below the value even at a 40% rate
    assert bk.bank_buffett_price(bi, d, q)["implied_return"] == "no solution"

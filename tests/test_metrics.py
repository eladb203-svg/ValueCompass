import pytest

from src.scoring import metrics as m
from src.scoring.buffett import dcf_fair_value


def test_running_peak_drawdown_msft_like():
    eps = [2.0, 3.25, 2.13, 2.5, 4.0]
    dd = m.running_peak_drawdowns(eps)
    assert dd[0] == 0 and dd[1] == 0
    assert dd[2] == pytest.approx((3.25 - 2.13) / 3.25)  # ~34%
    assert max(dd) == pytest.approx(0.3446, abs=1e-3)


def test_drawdown_nonpositive_eps_is_100pct_and_no_peak_is_skipped():
    assert m.running_peak_drawdowns([-1, -2, 1, 0.5, -0.2]) == [None, None, 0, 0.5, 1.0]


def test_smoothed_growth_kinds():
    g = m.smoothed_growth([1, 1, 99, 2, 2])
    assert g["kind"] == "growth" and g["value"] == pytest.approx(2 ** (1 / 3) - 1)
    assert m.smoothed_growth([-1, -1, 0, 2, 2])["kind"] == "turnaround"
    assert m.smoothed_growth([2, 2, 0, -1, -1])["kind"] == "negative_end"
    assert m.smoothed_growth([None, 1, 1, 2, 2])["kind"] == "insufficient"


def test_three_vs_three_growth_periods():
    eps = [1, 1, 1, 1, 1, 1, 1, 2, 2, 2]  # n=10 -> annualized over 7
    g = m.three_vs_three_growth(eps)
    assert g["value"] == pytest.approx(2 ** (1 / 7) - 1)
    assert m.three_vs_three_growth([1, 1, 1, 2, 2])["kind"] == "insufficient"
    assert m.three_vs_three_growth([-1, 0, 1, 2, 2, 2])["kind"] == "start_nonpositive"


def test_effective_tax_rate_rules():
    assert m.effective_tax_rate(20, 100) == (0.2, [])
    assert m.effective_tax_rate(60, 100)[0] == 0.40
    assert m.effective_tax_rate(-5, 100)[0] == 0.0
    assert m.effective_tax_rate(5, -100)[0] == 0.25
    assert m.effective_tax_rate(None, 100)[0] == 0.25


def _bs(equity, debt, cash, assets=0, cl=0, dc=0, sti=0):
    return dict(equity=equity, debt=debt, cash=cash, sti=sti, assets=assets, cur_liab=cl, debt_current=dc)


def test_roic_normal_year():
    r = m.roic_year(100, 100, 20, _bs(500, 100, 100), _bs(500, 100, 100))
    assert r["roic"] == pytest.approx(80 / 500)


def test_roic_operating_ic_fallback():
    # IC = equity + debt - cash = -100 + 0 - 50 = -150 (<=0); operating IC = 400 - 50 - (100-0) = 250
    b = _bs(-100, 0, 50, assets=400, cl=100)
    r = m.roic_year(100, 100, 25, b, b)
    assert "roic_fallback_operating_ic" in r["flags"]
    assert r["roic"] == pytest.approx(75 / 250)


def test_roic_fixed_fallback_20_or_0():
    b = _bs(-100, 0, 50, assets=100, cl=200)  # operating IC negative too
    assert m.roic_year(100, 100, 25, b, b)["roic"] == 0.20
    assert m.roic_year(-10, 100, 25, b, b)["roic"] == 0.0


def test_count_scaled():
    assert m.count_scaled([True, False, True, True, True], 5) == (4.0, 5, False)
    c, n, partial = m.count_scaled([True, True, True, False], 5)
    assert (c, n, partial) == (pytest.approx(3.75), 4, True)
    assert m.count_scaled([True, True], 5)[0] is None


def test_fell_more_than():
    assert m.fell_more_than(10, 8.9, 0.10) is True
    assert m.fell_more_than(10, 9.0, 0.10) is False
    assert m.fell_more_than(-1, -2, 0.10) is True  # loss deepened
    assert m.fell_more_than(0, -1, 0.10) is True
    assert m.fell_more_than(None, 1, 0.1) is None


def test_nd_ebitda_and_interest_states():
    assert m.nd_ebitda_state(-5, 10)[0] == "net_cash"
    assert m.nd_ebitda_state(20, 10) == ("ratio", 2.0)
    assert m.nd_ebitda_state(20, -1)[0] == "ebitda_nonpositive"
    assert m.interest_coverage_state(10, 1, 0, True)[0] == "no_debt"
    assert m.interest_coverage_state(10, 0, 5, True)[0] == "zero_interest"
    assert m.interest_coverage_state(-1, 1, 5, True)[0] == "ebit_nonpositive"
    assert m.interest_coverage_state(10, 2, 5, True) == ("ratio", 5.0)
    assert m.interest_coverage_state(10, None, 5, True)[0] == "missing"
    assert m.interest_coverage_state(10, None, 5, False)[0] == "zero_interest"


def test_accrual_ratio():
    assert m.accrual_ratio(100, 80, 900, 1100) == pytest.approx(0.02)


def test_dcf_collapses_to_gordon_when_growth_equals_terminal():
    r = dcf_fair_value(base=100, g1=0.025, excess_cash_less_debt=0, shares=1)
    assert r["fair_value_per_share"] == pytest.approx(100 * 1.025 / 0.075, rel=1e-9)


def test_dcf_adds_net_cash_per_share():
    a = dcf_fair_value(100, 0.05, 0, 10)["fair_value_per_share"]
    b = dcf_fair_value(100, 0.05, 50, 10)["fair_value_per_share"]
    assert b - a == pytest.approx(5.0)


def test_reverse_dcf_roundtrip_and_out_of_range():
    from src.scoring.buffett import reverse_dcf
    price = dcf_fair_value(100, 0.07, 50, 10)["fair_value_per_share"]
    r = reverse_dcf(100, 50, 10, price)
    assert r["state"] == "solved" and r["implied_growth"] == pytest.approx(0.07, abs=1e-6)
    assert reverse_dcf(100, 50, 10, 1e9)["state"] == "out_of_range"
    assert reverse_dcf(100, 50, 10, 0.001)["state"] == "out_of_range"
    assert reverse_dcf(100, 50, 10, None)["state"] == "no_price"


def test_dilution_prefers_period_end_shares_and_flags_fallback():
    from datetime import date
    from src.scoring.buffett import dilution
    from src.scoring.inputs import CompanyInputs
    f = {"shares_out": [100, 100, 100, 100, 110], "shares": [100, 100, 100, 100, 150]}
    inp = CompanyInputs("X", "x", "STANDARD", [f"FY{i}" for i in range(5)], [date(2020 + i, 12, 31) for i in range(5)], f)
    d = dilution(inp)
    assert d["value"] == pytest.approx(0.10) and d["basis"] == "period_end_shares_outstanding"
    f["shares_out"][0] = None
    d = dilution(inp)
    assert d["value"] == pytest.approx(0.50) and "dilution_fallback_weighted_diluted" in d["flags"]


def _gate_inp(rev, eps):
    from datetime import date
    from src.scoring.inputs import CompanyInputs
    n = len(rev)
    return CompanyInputs("X", "x", "STANDARD", [f"FY{i}" for i in range(n)],
                         [date(2020 + i, 12, 31) for i in range(n)], {"revenue": rev, "eps": eps})


def test_growth_gate_pass_and_each_failure():
    from src.scoring.buffett import growth_gate
    ok = growth_gate(_gate_inp([1, 2, 3, 4, 5], [1, 1.1, 1.2, 1.3, 1.4]))
    assert ok["passed"] and ok["failing"] == []
    a = growth_gate(_gate_inp([1, 2, 1.5, 1.4, 1.6], [1, 1.1, 1.2, 1.3, 1.4]))  # revenue rose 2 of 4
    assert not a["passed"] and a["failing"][0].startswith("a:")
    b = growth_gate(_gate_inp([1, 2, 3, 4, 5], [2, 1.5, 2, 1.5, 2]))  # EPS fell >10% twice
    assert not b["passed"] and any(x.startswith("b:") for x in b["failing"])
    c = growth_gate(_gate_inp([1, 2, 3, 4, 5], [-1, 1, 1.1, 1.2, 1.3]))  # a loss year
    assert not c["passed"] and any(x.startswith("c:") for x in c["failing"])
    m = growth_gate(_gate_inp([1, 2, 3, 4, 5], [None, 1, 1.1, 1.2, 1.3]))  # missing data fails
    assert not m["passed"]


def test_implied_return_roundtrip_and_out_of_range():
    from src.scoring.buffett import implied_return
    price = dcf_fair_value(100, 0.06, 20, 10, r=0.12)["fair_value_per_share"]
    r = implied_return(100, 0.06, 20, 10, price)
    assert r["state"] == "solved" and r["implied_return"] == pytest.approx(0.12, abs=1e-6)
    assert implied_return(100, 0.06, 20, 10, 1e9)["state"] == "out_of_range"
    assert implied_return(100, 0.06, 20, 10, 0.0001)["state"] == "out_of_range"
    assert implied_return(100, 0.06, 20, 10, None)["state"] == "no_price"


def test_finance_lease_flag_in_maintenance_capex():
    from datetime import date
    from src.scoring.inputs import CompanyInputs
    f = {"da": [30.0, 40.0], "acq_amort": [5.0, None]}
    inp = CompanyInputs("X", "x", "STANDARD", ["FY1", "FY2"], [date(2020, 12, 31), date(2021, 12, 31)], f,
                        tag_log={"da": {"FY1": {"tag": "DERIVED: Depreciation + AmortizationOfIntangibleAssets "
                                                       "+ FinanceLeaseRightOfUseAssetAmortization"},
                                        "FY2": {"tag": "DepreciationAndAmortization"}}})
    d = m.derive(inp)
    assert d["maint_capex"] == [25.0, 40.0]
    assert d["maint_capex_flag"][0] == "includes_finance_lease_amortization"
    assert d["maint_capex_flag"][1] == "includes_acquisition_amortization"

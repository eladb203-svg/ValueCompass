"""INSURANCE round 3 (spec 2026-10-13_12-05): Q6 cost of float vs the government bond yield; the versioned yield table."""
import csv

import pytest

from test_insurance import N, _item, ins
from src.providers.insurance_facts import load_gov_yields
from src.scoring.insurance import derive_insurance, score_insurance


def _fl(growth=1.05, base=100e9):
    return [base * growth ** i for i in range(N)]


def _inp(uw_ratio, yields=0.04, **over):
    """Insurer whose underwriting result is `uw_ratio` x insurance revenue every year (negative = loss), float 100bn growing 5%."""
    fl = _fl()
    prem = [90e9 * 1.05 ** i for i in range(N)]
    base = dict(claims_gross=[None] * N, claims_net=[f * 0.6 for f in fl], fpb=[f * 0.2 for f in fl], pab=[f * 0.1 for f in fl], unearned=[f * 0.1 for f in fl],
                reins_unpaid=[0.0] * N, reins_prepaid=[0.0] * N, aoci_drr=[None] * N, liabilities=[f * 3 for f in fl], premiums=prem, policy_fees=[None] * N,
                total_expenses=[p * (1 - uw_ratio) + 0.5e9 for p in prem], interest_expense=[0.5e9] * N, interest_credited=[None] * N)
    base.update(over)
    ii = ins(**base)
    ii.gov_yield = {2016 + i: (yields[i] if isinstance(yields, list) else yields) for i in range(N)}
    return ii


def test_cost_of_float_is_minus_underwriting_result_over_average_float():
    d = derive_insurance(_inp(-0.10))
    i = N - 1
    uw = d["underwriting_result"][i]
    fl = d["float_ex_drr"]
    assert uw == pytest.approx(-0.10 * 90e9 * 1.05 ** 9)
    assert d["avg_float"][i] == pytest.approx((fl[i] + fl[i - 1]) / 2)
    assert d["cost_of_float"][i] == pytest.approx(-uw / d["avg_float"][i])
    assert d["cost_gap"][i] == pytest.approx(d["cost_of_float"][i] - 0.04) and d["gov_yield_yr"][i] == 0.04
    # the underwriting margin is still computed (display)
    assert d["underwriting_margin"][i] == pytest.approx(-0.10)


def test_underwriting_profit_gives_negative_cost_and_full_points():
    r = score_insurance(_inp(+0.05))["buffett_quality"]
    it1, it2, it4 = _item(r, "3.5", "1"), _item(r, "3.5", "2"), _item(r, "3.5", "4")
    assert it1.metric <= 0 and it1.points == pytest.approx(6.0)
    assert it2.metric == 5 and it2.points == pytest.approx(3.0)
    assert it4.state == "score" and it4.inputs["cheap_float_condition"] is True


def test_cost_scale_zero_half_yield_and_full_yield():
    # constant yearly cost = c of average float: choose the underwriting result so that cost equals 50% / 100% of a 4% yield
    d0 = derive_insurance(_inp(0.0))
    assert _item(score_insurance(_inp(0.0))["buffett_quality"], "3.5", "1").points == pytest.approx(6.0)  # cost 0% -> full
    target = 0.02  # 50% of the yield: ratio to float, not to revenue -> iterate on the loss ratio
    ratio = target * (d0["avg_float"][-1] / (90e9 * 1.05 ** 9))
    r_half = score_insurance(_inp(-ratio))["buffett_quality"]
    it = _item(r_half, "3.5", "1")
    assert it.metric == pytest.approx(0.5, abs=0.1) and 2.5 <= it.points <= 3.5
    r_full = score_insurance(_inp(-0.40))["buffett_quality"]  # cost far above the yield
    assert _item(r_full, "3.5", "1").points == 0.0 and _item(r_full, "3.5", "2").points == 0.0


def test_consistency_counts_years_with_cost_below_the_yield():
    # alternate profit / loss years: 3 of the last 5 years below the 4% yield
    fl = _fl()
    prem = [90e9 * 1.05 ** i for i in range(N)]
    pattern = [-0.20, 0.05, -0.20, 0.05, 0.05, -0.20, 0.05, 0.05, -0.20, 0.05]  # last five: 0.05(-)...
    ii = _inp(0.0, total_expenses=[p * (1 - u) + 0.5e9 for p, u in zip(prem, pattern)])
    d = derive_insurance(ii)
    last5 = d["cost_of_float"][-5:]
    n_below = sum(1 for c in last5 if c < 0.04)
    it = _item(score_insurance(ii)["buffett_quality"], "3.5", "2")
    assert it.metric == n_below and fl


def test_cheap_float_condition_needs_cumulative_cost_below_cumulative_yield_and_three_years():
    prem = [90e9 * 1.05 ** i for i in range(N)]
    # three years below the yield but one huge loss: cumulative cost above the cumulative yield -> 0
    pattern = [0.05] * 5 + [0.05, 0.05, 0.05, -2.0, -2.0]
    ii = _inp(0.0, total_expenses=[p * (1 - u) + 0.5e9 for p, u in zip(prem, pattern)])
    it = _item(score_insurance(ii)["buffett_quality"], "3.5", "4")
    assert it.state == "true_zero" and "cheap_float_condition_failed" in it.flags
    assert it.inputs["years_below_yield"] == 3 and it.inputs["cumulative_cost"] > it.inputs["cumulative_yield"]


def test_non_positive_yield_year_counts_a_positive_cost_as_above_the_yield():
    d = derive_insurance(_inp(-0.05, yields=-0.001))
    assert d["cost_ratio"][-1] == 2.0 and "yield_nonpositive_positive_cost_counted_as_above_yield" in d["cost_flags"][-1]
    d2 = derive_insurance(_inp(+0.05, yields=-0.001))
    assert d2["cost_ratio"][-1] == 0.0  # a profit is below any yield


def test_missing_yield_or_float_or_incomparable_components_make_the_year_missing():
    ii = _inp(-0.05)
    ii.gov_yield = {}
    d = derive_insurance(ii)
    assert all(x is None for x in d["cost_gap"]) and "government_yield_missing" in d["cost_flags"][-1]
    assert _item(score_insurance(ii)["buffett_quality"], "3.5", "1").state == "missing"
    pab = [f * 0.1 for f in _fl()]
    pab[-1] = None  # component stops being tagged: the two year-ends are not comparable
    d2 = derive_insurance(_inp(-0.05, pab=pab))
    assert d2["cost_of_float"][-1] is None and d2["cost_flags"][-1].startswith("float_components_changed_not_comparable")
    d3 = derive_insurance(_inp(-0.05, claims_net=[None] * N, claims_gross=[None] * N))
    assert d3["cost_of_float"][-1] is None


def test_yield_table_loader_and_versioning(tmp_path):
    p = tmp_path / "y.csv"
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["currency", "year", "yield_pct", "n_obs", "series", "source", "url", "retrieved", "version", "cross_check"])
        w.writerow(["USD", 2025, 4.2932, 249, "DGS10", "Federal Reserve via FRED", "u", "2026-10-13", "v1", ""])
        w.writerow(["JPY", 2025, 1.5434, 243, "JGB 10Y", "Japan MoF", "u", "2026-10-13", "v1", ""])
    out = load_gov_yields(p)
    assert out["USD"]["yields"][2025] == pytest.approx(0.042932) and out["JPY"]["yields"][2025] == pytest.approx(0.015434)
    assert out["USD"]["version"] == "v1" and "DGS10" in out["USD"]["source"] and out["USD"]["retrieved"] == "2026-10-13"


def test_shipped_yield_table_covers_2016_2025_for_usd_and_jpy():
    out = load_gov_yields()
    for cur in ("USD", "JPY"):
        assert set(out[cur]["yields"]) == set(range(2016, 2026)), cur
    assert out["USD"]["yields"][2025] == pytest.approx(0.0429, abs=1e-3) and out["JPY"]["yields"][2016] < 0

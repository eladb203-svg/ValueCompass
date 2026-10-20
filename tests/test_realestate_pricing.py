"""INCOME_REAL_ESTATE pricing (spec 2026-10-14_22-30, section 6: RP1, RP1a, RP2, RP3, display) and the quality clarifications RE24, RE26, RE27."""
import pytest

from src.scoring import buffett as B
from src.scoring import graham as G
from src.scoring import realestate as RE
from src.scoring.realestate import (conservative_cap_rate, derive_re, nav_components, price_display, re_buffett_price, re_graham_nav, score_realestate)
from test_realestate import N, _items, _yrs, reit

OE_REG = {"maintenance_capex": _yrs(20e6), "ti_lc_income_preserving": _yrs(10e6)}


def oe_reit(**over):
    return reit(reg=OE_REG, **over)


def run(ri):
    sc = score_realestate(ri)
    return sc, re_buffett_price(ri, sc["derived"], sc["buffett_quality"]), re_graham_nav(ri, sc["derived"], sc["graham_quality"])


# ------------------------------------------------------------------ RP2 cap rate
def test_conservative_cap_rate_is_gov_yield_plus_3pp_with_a_6pct_floor(tmp_path):
    p = tmp_path / "y.csv"
    p.write_text("currency,year,yield_pct\nUSD,2024,4.0\nUSD,2025,4.2932\nJPY,2025,1.5\n", encoding="utf-8")
    c = conservative_cap_rate("USD", p)
    assert c["value"] == pytest.approx(0.072932) and c["gov_year"] == "2025" and c["gov_kind"] == "annual"
    p.write_text("currency,year,yield_pct\nUSD,2025,1.0\n", encoding="utf-8")
    assert conservative_cap_rate("USD", p)["value"] == pytest.approx(0.06)  # floor
    assert conservative_cap_rate("EUR", p)["value"] is None and "gov_yield_missing_cannot_be_valued" in conservative_cap_rate("EUR", p)["flags"]  # K3 H-06: no 6% floor


def test_repo_yields_file_gives_the_documented_cap_rate():
    c = conservative_cap_rate("USD")
    assert c["gov_year"] is not None and c["value"] == pytest.approx(max(c["gov_yield"] + 0.03, 0.06))


# ------------------------------------------------------------------ RP1 DCF of OE per share
def test_rp1_needs_oe_basis_in_all_five_years_the_ffo_proxy_is_never_a_level():
    ri = reit()  # no maintenance capex / TI-LC -> FFO_PROXY
    sc, bp, _ = run(ri)
    assert bp["state"] == "cannot_be_valued" and "all of the last 5 years" in bp["reason"] and bp["buy_price"] is None
    assert bp["indicative_ffo_dcf_per_share"] is not None  # analysis only


def test_rp1_value_is_the_unlevered_per_share_dcf_with_no_debt_subtraction_and_no_excess_cash():
    ri = oe_reit()
    sc, bp, _ = run(ri)
    d = sc["derived"]
    assert bp["state"] == "valued" and all(b == "OE" for b in d["oe_basis"])
    bg = bp["base_growth"]
    assert bp["fair_value"] == pytest.approx(B.dcf_fair_value(bg["base"], bg["g1"], 0.0, 1.0, r=0.10)["fair_value_per_share"])
    # debt and cash do not enter the value
    ri2 = oe_reit(debt_total=[9000e6] * N, cash=[5000e6] * N)
    bp2 = run(ri2)[1]
    assert bp2["fair_value"] == pytest.approx(bp["fair_value"])
    # the discount rate is a parameter
    sc_ = score_realestate(ri)
    assert re_buffett_price(ri, sc_["derived"], sc_["buffett_quality"], r=0.12)["fair_value"] < bp["fair_value"]
    # sensitivities: r +/-1 pp and stage-1 growth +/-1 pp
    s = bp["sensitivities"]
    assert s["r-1pp"] > bp["fair_value"] > s["r+1pp"] and s["g+1pp"] > bp["fair_value"] > s["g-1pp"]


def test_rp1_uses_the_g1_rollforward_and_growth_gate_of_the_general_model():
    ri = oe_reit()
    sc, bp, _ = run(ri)
    bg = bp["base_growth"]
    med = bg["median"]
    last = bg["last5"][-1]
    assert bg["base"] == pytest.approx(med * (1 + bg["g1"]) ** 2 if last >= med else med)
    assert 0.0 <= bg["g1"] <= B.STAGE1_CAP[1]
    # gate on normalized FFO per share and revenue: falling revenue fails the gate -> growth 0
    g = [1.04 ** i for i in range(N)]
    ri2 = oe_reit(total_revenue=[1000e6 / x for x in g])
    bg2 = run(ri2)[1]["base_growth"]
    assert not bg2["growth_gate"]["passed"] and bg2["g1"] == 0.0


def test_rp1_value_not_positive_is_c15(monkeypatch):
    ri = oe_reit()
    sc = score_realestate(ri)
    monkeypatch.setattr(RE, "_dcf_ps", lambda base, g1, r: -1.0)
    bp = re_buffett_price(ri, sc["derived"], sc["buffett_quality"])
    assert bp["state"] == "cannot_be_valued" and bp["fair_value"] is None and bp["price_score"]["points"] == 0.0 and bp["buy_price"] is None


def test_rp3_price_score_uses_the_general_buffett_scale_and_margin_of_safety():
    ri = oe_reit()
    sc, bp, _ = run(ri)
    if bp["price_score"]["state"] == "score":
        disc = (bp["fair_value"] - ri.price_current) / bp["fair_value"]
        assert bp["price_score"]["points"] == pytest.approx(B.interpolate(disc, B.PRICE_ANCHORS))
    else:  # blocked only for a documented RP1a reason
        assert bp["guard"]["blocked"]
    # a cheap price gets the top score when not blocked
    cheap = oe_reit()
    cheap.price_current = 1.0
    sc2, bp2, _ = run(cheap)
    if not bp2["guard"]["blocked"]:
        assert bp2["price_score"]["points"] == pytest.approx(10.0)


# ------------------------------------------------------------------ RP1a guard
def test_rp1a_blocks_above_8x_net_debt_to_ebitdare_but_still_shows_the_value():
    ri = oe_reit(debt_total=[60000e6] * N)
    sc, bp, _ = run(ri)
    assert sc["derived"]["nd_ebitdare_state"][-1][1] > 8
    assert bp["guard"]["blocked"] and any("> 8x" in r for r in bp["guard"]["hard"])
    assert bp["state"] == "valued" and bp["label"] == "not a buy price" and bp["price_score"]["state"] == "blocked" and bp["buy_price"] is None


def test_rp1a_blocks_when_ebitdare_not_positive_or_debt_missing():
    neg = oe_reit(net_income=[-900e6] * N, gains_sale=[0.0] * N, da_total=[10e6] * N, interest_expense=[10e6] * N, income_tax=[0.0] * N, impairment=[0.0] * N)
    g = run(neg)[1]["guard"]
    assert g["blocked"] and "EBITDAre <= 0" in g["hard"]
    nodebt = oe_reit(debt_total=[None] * N)
    g2 = run(nodebt)[1]["guard"]
    assert g2["blocked"] and "debt data missing" in g2["hard"]


def test_rp1a_requires_the_quality_checks_below_8x():
    ri = oe_reit(mat_year1=[None] * N, mat_year2=[None] * N)  # near-term debt coverage not computable
    g = run(ri)[1]["guard"]
    assert g["blocked"] and not g["hard"] and any("near-term debt coverage" in r for r in g["quality_checks"])


# ------------------------------------------------------------------ RP2 conservative NAV
def nav_reit(**over):
    base = dict(cash=[1500e6] * N, assets=[8000e6] * N, re_net=[6500e6] * N, nci_total=[100e6] * N, pref_equity=[200e6] * N, finance_lease_liab=[50e6] * N,
                equity_method_inv=[300e6] * N, cip=[200e6] * N, re_dev_land=[None] * N)
    base.update(over)
    return oe_reit(**base)


def test_rp2_nav_formula_and_other_claims_without_double_counting():
    ri = nav_reit()
    sc = score_realestate(ri)
    d = sc["derived"]
    c = nav_components(ri, d)
    cap = conservative_cap_rate()["value"]
    assert c["ok"] and c["cap_rate"] == pytest.approx(cap)
    noi = d["noi"][-1]
    claims = 200e6 + 100e6 + 50e6  # preferred + NCI + finance leases
    assert c["other_claims"] == {"preferred": 200e6, "noncontrolling_interests_non_op": 100e6, "finance_lease_liabilities": 50e6}
    assert c["nav"] == pytest.approx(noi / cap + (200e6 + 300e6) - d["net_debt"][-1] - claims)  # development / CIP + JV at carrying value
    assert c["nav_per_share"] == pytest.approx(c["nav"] / 300e6)
    gn = re_graham_nav(ri, d, sc["graham_quality"])
    assert gn["value"] == pytest.approx(c["nav_per_share"]) and set(gn["sensitivities"]) == {"cap-1pp", "cap+1pp"}
    assert gn["sensitivities"]["cap-1pp"] > gn["value"] > gn["sensitivities"]["cap+1pp"]


def test_rp3_graham_price_score_uses_the_classic_scale_and_margin():
    ri = nav_reit()
    sc = score_realestate(ri)
    gn = re_graham_nav(ri, sc["derived"], sc["graham_quality"])
    assert gn["price_score"]["state"] == "score"
    disc = (gn["value"] - ri.price_current) / gn["value"]
    assert gn["price_score"]["points"] == pytest.approx(G.interpolate(disc, G.CLASSIC_PRICE))
    assert gn["buy_price"]["state"] in ("computed", "not_computed", "not_suitable")


def test_rp2_no_graham_price_score_when_non_noi_assets_are_missing_and_material():
    ri = oe_reit(cash=[100e6] * N)  # 8000 - 6500 - 100 = 1400m unidentified = 17.5% of assets
    sc = score_realestate(ri)
    gn = re_graham_nav(ri, sc["derived"], sc["graham_quality"])
    assert gn["state"] == "valued" and gn["price_score"]["state"] == "blocked" and gn["buy_price"] is None and "RP2" in gn["price_score"]["reason"] and "indicative" in gn["label"]
    ok = nav_reit()
    assert nav_components(ok, derive_re(ok))["graham_block"] is False


def test_rp2_nav_not_positive_cannot_be_valued_with_score_zero():
    ri = nav_reit(debt_total=[40000e6] * N)
    sc = score_realestate(ri)
    gn = re_graham_nav(ri, sc["derived"], sc["graham_quality"])
    assert gn["state"] == "cannot_be_valued" and gn["value"] is None and gn["price_score"]["points"] == 0.0


def test_pricing_display_price_to_average_ffo():
    ri = oe_reit()
    d = derive_re(ri)
    dsp = price_display(ri, d)
    avg = sum(d["nffo_ps"][-5:]) / 5
    assert dsp["price_to_avg_ffo"] == pytest.approx(40.0 / avg) and dsp["within_15x"] == (40.0 / avg <= 15)


# ------------------------------------------------------------------ RE24 / RE26 / RE27
def test_re24_negative_straight_line_adjustment_increases_owner_earnings():
    pos = derive_re(oe_reit(straight_line=[8e6] * N))
    neg = derive_re(oe_reit(straight_line=[-8e6] * N))
    assert neg["oe"][-1] - pos["oe"][-1] == pytest.approx(16e6)  # OE = normalized FFO - (GAAP rent - cash rent) - maintenance capex - TI/LC
    assert neg["straight_line_increases_oe"][-1] is True and pos["straight_line_increases_oe"][-1] is False


def test_re26_stressed_ltv_needs_the_carrying_value_of_the_other_property():
    reg = {"stabilized_noi": {"FY2025": {"value": 100.0, "unit": "", "quote": "q", "source": "s", "verified": True, "note": ""}},
           "stabilized_value": {"FY2025": {"value": 2000.0, "unit": "", "quote": "q", "source": "s", "verified": True, "note": ""}}}
    d = derive_re(reit(reg=reg))
    assert d["stressed_ltv"] is None  # other property carrying value missing -> missing, not 0
    reg["other_property_value"] = {"FY2025": {"value": 300.0, "unit": "", "quote": "q", "source": "s", "verified": True, "note": ""}}
    d2 = derive_re(reit(reg=reg))
    cap = 100.0 / 2000.0
    assert d2["stressed_ltv"] == pytest.approx(d2["net_debt"][-1] / (2000.0 * cap / (cap + 0.01) + 300.0))


def test_re27_graham_382_requires_positive_oe_and_shows_the_oe_to_ffo_diagnostic():
    sc = score_realestate(oe_reit())
    it = _items(sc["graham_quality"])[("3.8", "2")]
    assert it.state != "missing" or "RE27" not in (it.note or "")
    assert "oe_to_ffo_diagnostic" in it.inputs
    neg = score_realestate(oe_reit(maint_capex=[5000e6] * N))  # maintenance capex larger than FFO -> OE <= 0
    it2 = _items(neg["graham_quality"])[("3.8", "2")]
    assert it2.state == "missing" and "RE27" in it2.note

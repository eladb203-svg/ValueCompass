"""INCOME_REAL_ESTATE pricing round 3 (rules 2026-10-14_23-25): RP1b recent-trend condition, RP5 market-distress flag and NAV without development, RE28 single basis, Q6 inputs, EQIX / PLD checks."""
import pytest

from src.providers.realestate_facts import _sum_quarters, load_realestate_extracted
from src.scoring import realestate as RE
from src.scoring.realestate import (derive_re, nav_components, re_buffett_price, re_graham_nav, recent_trend, score_realestate)
from test_realestate import N, _row, _yrs, reit
from test_realestate_pricing2 import bsa_reg, oe_reg, r


def years(**last):
    """Series of N years from a dict of {offset_from_end: value}; the rest stay None."""
    out = {}
    for k, v in last.items():
        out[f"FY{2025 - int(k[1:])}"] = _row(v)
    return out


def priced(ri):
    sc = score_realestate(ri)
    return sc, re_buffett_price(ri, sc["derived"], sc["buffett_quality"])


# ------------------------------------------------------------------ RP1b
def test_rp1b_same_property_noi_decline_in_the_latest_year_zeroes_stage1_growth():
    ri = reit(reg=oe_reg(same_property_noi_growth=years(y0=-0.035, y1=0.03, y2=0.04)))
    d = derive_re(ri)
    rt = recent_trend(ri, d)
    assert rt["failed"] and "same-property" in rt["failed"][0]
    ri_ok = reit(reg=oe_reg(same_property_noi_growth=years(y0=0.01, y1=0.03)))
    assert recent_trend(ri_ok, derive_re(ri_ok))["failed"] == []
    _, bp = priced(ri)
    assert bp["stage1_growth"] == 0.0 and any("growth_gate_recent_trend" in x for x in bp["flags"]) and bp["base_growth"]["growth_before_gate"] >= 0.0


def test_rp1b_occupancy_fall_above_2pp_fails_and_exactly_2pp_passes():
    sp = years(y0=0.02)
    ri = reit(reg=oe_reg(same_property_noi_growth=sp, occupancy={**years(y0=0.93), **years(y1=0.96)}))
    assert recent_trend(ri, derive_re(ri))["failed"]
    ri2 = reit(reg=oe_reg(same_property_noi_growth=sp, occupancy={**years(y0=0.94), **years(y1=0.96)}))
    assert recent_trend(ri2, derive_re(ri2))["failed"] == []
    ri3 = reit(reg=oe_reg(same_property_noi_growth=sp, occupancy=years(y0=0.80)))  # previous year missing -> not tested
    rt = recent_trend(ri3, derive_re(ri3))
    assert rt["failed"] == [] and any("occupancy missing" in x for x in rt["not_tested"])


def test_rp1b_missing_same_property_falls_back_to_the_latest_revenue_decline_and_towers_skip_occupancy():
    g = [1.04 ** i for i in range(N)]
    ri = reit(reg=oe_reg(), total_revenue=[1000e6 * x for x in g[:-1]] + [900e6 * g[-2]])
    rt = recent_trend(ri, derive_re(ri))
    assert rt["failed"] and "revenue" in rt["failed"][0]
    ri_up = reit(reg=oe_reg())
    assert recent_trend(ri_up, derive_re(ri_up))["failed"] == []
    ri_t = reit(reg=oe_reg(occupancy={**years(y0=0.5), **years(y1=0.99)}))
    ri_t.asset_type = "communication towers"
    rt_t = recent_trend(ri_t, derive_re(ri_t))
    assert rt_t["failed"] == [] and any("not applicable" in x for x in rt_t["not_tested"])


# ------------------------------------------------------------------ RP5 and NAV without development
def nav_reg(**kw):
    reg = bsa_reg(other=0.0, carry=300e6, inre=700e6)
    reg.update(kw)
    return reg


def test_rp5_distress_flag_when_the_implied_cap_rate_exceeds_the_conservative_one_by_more_than_3pp():
    ri = reit(reg=nav_reg(), cash=[1500e6] * N)
    cap = RE.conservative_cap_rate()["value"]
    sc = score_realestate(ri)
    ri.price_current = 5.0  # a very low price -> a very high implied cap rate
    gn = re_graham_nav(ri, sc["derived"], sc["graham_quality"])
    assert gn["distress"]["flag"] and gn["distress"]["gap_pp"] > 3 and "check the latest results" in gn["distress"]["text"]
    assert gn["distress"]["market_implied_cap_rate"] > cap + 0.03
    ri.price_current = 40.0
    gn2 = re_graham_nav(ri, sc["derived"], sc["graham_quality"])
    assert gn2["distress"]["flag"] == (gn2["distress"]["market_implied_cap_rate"] - cap > 0.03)
    assert gn["price_score"]["state"] in ("score", "blocked")  # display only: the score is computed as before


def test_rp5_flag_does_not_change_the_price_score():
    ri = reit(reg=nav_reg(), cash=[1500e6] * N)
    sc = score_realestate(ri)
    ri.price_current = 5.0
    a = re_graham_nav(ri, sc["derived"], sc["graham_quality"])
    from src.scoring.interpolate import interpolate
    from src.scoring import graham as G
    disc = (a["value"] - 5.0) / a["value"]
    assert a["price_score"]["points"] == pytest.approx(interpolate(disc, G.CLASSIC_PRICE))


def test_nav_without_development_and_land_removes_the_inside_real_estate_items_and_construction_in_progress_carry_lines():
    reg = nav_reg(bsa_carry__construction_in_process=r(100e6))
    ri = reit(reg=reg, cash=[1500e6] * N)
    c = nav_components(ri, derive_re(ri))
    assert c["development_and_land"] == pytest.approx(700e6 + 100e6)  # inre + the carry line named construction
    assert c["nav_without_development_per_share"] == pytest.approx((c["nav"] - 800e6) / c["shares"])
    assert c["nav_without_development_per_share"] < c["nav_per_share"]
    ri2 = reit(reg=oe_reg(), cash=[100e6] * N)  # no classification extracted -> not available
    assert nav_components(ri2, derive_re(ri2))["nav_without_development_per_share"] is None


# ------------------------------------------------------------------ RE28
def test_re28_bxp_partnership_basis_deductions_are_scaled_to_the_inc_share():
    base = derive_re(reit(reg=oe_reg(straight_line_x=_yrs(10e6)), straight_line=[None] * N))
    scaled = derive_re(reit(reg=oe_reg(straight_line_x=_yrs(10e6), inc_share_of_bplp=_yrs(0.9)), straight_line=[None] * N))
    assert scaled["maint_capex"][-1] == pytest.approx(0.9 * 20e6) and scaled["tilc_pres"][-1] == pytest.approx(0.9 * 10e6) and scaled["straight_line_adjustment"][-1] == pytest.approx(0.9 * 10e6)
    assert scaled["oe"][-1] - base["oe"][-1] == pytest.approx(0.1 * (20e6 + 10e6 + 10e6))
    assert any(x.startswith("RE28") for x in scaled["flags"]) and not any(x.startswith("RE28") for x in base["flags"])


def test_re28_spg_operating_partnership_basis_uses_shares_plus_units_and_counts_units_once_in_the_nav():
    ri = reit(reg=oe_reg(shares_basis_override=_yrs(350e6), nci_op_units=r(50e6), nci_op_book__units=r(100e6)), nci_total=[500e6] * N)
    d = derive_re(ri)
    assert d["shares_eff"][-1] == 350e6 and d["ffo_ps"][-1] == pytest.approx(d["ffo"][-1] / 350e6)
    sb = nav_components(ri, d)["share_basis"]
    assert sb["basis"] == "op_units_in_diluted_shares" and sb["shares"] == 350e6 and sb["nci_deducted"] == 400e6  # units not added again, only the non-OP NCI deducted
    ri0 = reit(reg=oe_reg())
    assert derive_re(ri0)["shares_eff"][-1] == 300e6


def test_re28_spg_consolidated_net_income_start_replaces_the_attributable_income():
    d0 = derive_re(reit(reg=oe_reg()))
    d1 = derive_re(reit(reg=oe_reg(recon_net_income=_yrs(400e6))))
    assert d1["ffo"][-1] - d0["ffo"][-1] == pytest.approx(400e6 - 300e6 * 1.04 ** 9 + 10e6)  # consolidated start replaces the attributable income; the preferred deduction is inside the company's reconciliation
    assert any("net_income_start_from_company_reconciliation" in x for x in d1["ffo_flags"][-1])


# ------------------------------------------------------------------ Q6 / PLD inputs and EQIX finance leases
def test_q6_inputs_are_exposed_by_the_derivation():
    ri = reit(reg=oe_reg(reported_affo=_yrs(1000e6), partnership_units_weighted=_yrs(320e6), core_ffo_reported=_yrs(900e6), dev_gains_reported=_yrs(50e6)), sbc=[12e6] * N)
    d = derive_re(ri)
    assert d["affo_reported"][-1] == 1000e6 and d["sbc"][-1] == 12e6 and d["partnership_units_weighted"][-1] == 320e6
    assert d["core_ffo_reported"][-1] == 900e6 and d["dev_gains_reported"][-1] == 50e6


def test_quarter_items_for_straight_line_and_affo_are_summed():
    items = {"straight_line_x_q": {f"FY2024Q{i}": {"value": 5.0, "unit": "USD", "verified": True, "quote": "q", "source": "s", "note": "n"} for i in (1, 2, 3, 4)},
             "reported_affo_q": {f"FY2024Q{i}": {"value": 7.0, "unit": "USD", "verified": True, "quote": "q", "source": "s", "note": "n"} for i in (1, 2, 3, 4)}}
    out = {"BXP": items}
    _sum_quarters(out)
    assert out["BXP"]["straight_line_x"]["FY2024"]["value"] == 20.0 and out["BXP"]["reported_affo"]["FY2024"]["value"] == 28.0


def test_shipped_csv_round_3_items():
    reg = load_realestate_extracted()
    assert reg["BXP"]["inc_share_of_bplp"]["FY2025"]["value"] == pytest.approx(0.9003) and reg["SPG"]["recon_net_income"]["FY2025"]["value"] == pytest.approx(5364.12e6)
    assert reg["SPG"]["shares_basis_override"]["FY2025"]["value"] == pytest.approx(377.925e6) and reg["PLD"]["core_ffo_reported"]["FY2021"]["value"] == pytest.approx(3172e6)
    assert reg["PLD"]["dev_gains_reported"]["FY2021"]["value"] == pytest.approx(817e6) and reg["EQIX"]["reported_affo"]["FY2025"]["value"] == pytest.approx(3761e6)


def test_eqix_finance_lease_liabilities_are_not_in_the_debt_tag():
    reg = load_realestate_extracted()["EQIX"]
    comp = {k[len("bs_check__"):]: v["FY2025"]["value"] for k, v in reg.items() if k.startswith("bs_check__")}
    borrowings = sum(comp[k] for k in ("mortgage_current", "senior_notes_current", "mortgage_noncurrent", "senior_notes_noncurrent"))
    leases = comp["finance_lease_current"] + comp["finance_lease_noncurrent"]
    tag = 19062e6  # DebtInstrumentCarryingAmount FY2025 (cached XBRL)
    assert abs(tag - borrowings) < abs(tag - (borrowings + leases)) and abs(tag - borrowings) / tag < 0.01

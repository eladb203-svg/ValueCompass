"""INCOME_REAL_ESTATE (spec 2026-10-14_10-05): definitions (section 3), proxies, missing vs not applicable, scoring thresholds."""
from datetime import date

import pytest

from src.providers.realestate_facts import load_realestate_extracted
from src.scoring.realestate import REInputs, derive_re, score_realestate

N = 10


def _row(v):
    return {"value": v, "unit": "", "quote": "q", "source": "s", "verified": True, "note": ""}


def _yrs(v):
    return {f"FY{2016 + i}": _row(v) for i in range(N)}


def reit(reg=None, **over):
    g = [1.04 ** i for i in range(N)]
    f = {
        "total_revenue": [1000e6 * x for x in g], "rental_revenue": [950e6 * x for x in g], "other_property_revenue": [None] * N, "prop_opex": [300e6 * x for x in g],
        "re_tax": [None] * N, "cost_of_revenue": [None] * N, "noi_reported": [None] * N, "net_income": [300e6 * x for x in g], "pref_div": [10e6] * N,
        "interest_expense": [100e6] * N, "interest_capitalized": [5e6] * N, "income_tax": [2e6] * N, "da_total": [250e6 * x for x in g], "re_depr": [240e6 * x for x in g],
        "gains_sale": [20e6] * N, "impairment": [5e6] * N, "debt_extinguishment": [-4e6] * N, "transaction_costs": [1e6] * N, "straight_line": [8e6] * N,
        "maint_capex": [None] * N, "equity_method_income": [None] * N, "eps": [1.0] * N, "dps": [0.8] * N, "shares_dil": [300e6] * N, "shares_basic": [298e6] * N,
        "shares_out": [300e6] * N, "dividends": [240e6] * N, "buybacks": [0.0] * N, "acq_real_estate": [100e6] * N, "acq_business": [0.0] * N, "development": [50e6] * N,
        "capital_improvements": [10e6] * N, "ti_lc_total": [None] * N, "sale_proceeds": [None] * N, "assets": [8000e6] * N, "re_net": [6500e6] * N, "re_gross": [8000e6] * N,
        "debt_total": [3000e6] * N, "cash": [100e6] * N, "sti": [None] * N, "mat_year1": [200e6] * N, "mat_year2": [300e6] * N, "secured_debt_tag": [None] * N,
    }
    f.update(over)
    fy = [f"FY{2016 + i}" for i in range(N)]
    return REInputs("TST", "Test REIT", fy, [date(2016 + i, 12, 31) for i in range(N)], f, reg or {}, asset_type="office", noi_method="rental_less_opex",
                    price_current=40.0, price_date="2026-10-13", price_avg=[30.0] * N, first_annual_report=date(1995, 3, 1), as_of=date(2026, 10, 14),
                    tag_log={"net_income": {k: {"tag": "NetIncomeLoss"} for k in fy}, "gains_sale": {k: {"tag": "GainLossOnSaleOfProperties"} for k in fy},
                             "impairment": {k: {"tag": "ImpairmentOfRealEstate"} for k in fy}})


def _items(model):
    return {(c.id, i.id): i for c in model.criteria for i in c.items}


def test_noi_and_margin_exclude_straight_line_and_use_property_revenue():
    d = derive_re(reit())
    g9 = 1.04 ** 9
    assert d["noi"][-1] == pytest.approx((950e6 - 300e6) * g9) and d["noi_margin"][-1] == pytest.approx(650 / 950)


def test_uniform_ffo_normalized_ffo_and_ebitdare():
    d = derive_re(reit())
    g9 = 1.04 ** 9
    assert d["ffo"][-1] == pytest.approx(300e6 * g9 + 240e6 * g9 - 20e6 + 5e6 - 10e6)  # NI + real-estate D&A (Schedule III tag, RE17 priority 2) - gains + impairments - preferred
    assert d["norm_ffo"][-1] == pytest.approx(d["ffo"][-1] + 4e6 + 1e6)  # debt-extinguishment loss and transaction costs added back
    assert d["ebitdare"][-1] == pytest.approx(300e6 * g9 + 100e6 + 2e6 + 250e6 * g9 - 20e6 + 5e6)  # EBITDAre uses total D&A
    assert d["fcc"][-1] == pytest.approx(d["ebitdare"][-1] / (100e6 + 5e6 + 10e6))


def test_gains_on_sale_missing_makes_ffo_missing_not_estimated():
    d = derive_re(reit(gains_sale=[None] * N))
    assert d["ffo"][-1] is None and d["ebitdare"][-1] is None and "gains_on_sale_AI_extraction_needed" in d["ffo_flags"][-1]


def test_owner_earnings_need_maintenance_capex_and_tilc_otherwise_ffo_proxy():
    d = derive_re(reit())
    assert d["oe_basis"][-1] == "FFO_PROXY" and d["oe_ps"][-1] == pytest.approx(d["nffo_ps"][-1]) and d["oe"][-1] is None
    reg = {"maintenance_capex": _yrs(30e6), "ti_lc_income_preserving": _yrs(20e6)}
    d2 = derive_re(reit(reg=reg))
    assert d2["oe_basis"][-1] == "OE" and d2["oe"][-1] == pytest.approx(d2["norm_ffo"][-1] - 8e6 - 30e6 - 20e6)


def test_ntdc_needs_committed_facilities_and_no_maturities_is_full_score():
    assert derive_re(reit())["ntdc"][-1] is None
    reg = {"committed_undrawn_facilities": _yrs(1000e6)}
    assert derive_re(reit(reg=reg))["ntdc"][-1] == pytest.approx((100e6 + 1000e6) / 500e6)
    s = score_realestate(reit(reg=reg, mat_year1=[0.0] * N, mat_year2=[0.0] * N))
    assert _items(s["graham_quality"])[("3.2", "2")].points == pytest.approx(8.0)


def test_wacc_proxy_uses_market_weights_and_no_tax_shield():
    w = derive_re(reit())["wacc"]
    nd, mcap, kd = 3000e6 - 100e6, 40.0 * 300e6, 100e6 / 3000e6
    assert w["value"] == pytest.approx(nd / (nd + mcap) * kd + mcap / (nd + mcap) * 0.10)


def test_incremental_return_direct_has_priority_and_proxy_needs_inputs():
    assert derive_re(reit())["incremental"]["value"] is None
    reg = {"same_property_noi_growth": _yrs(0.03)}
    assert derive_re(reit(reg=reg))["incremental"]["basis"] in ("NOI_PROXY", None)  # valid only when net growth capital >= 5% of property value
    reg2 = {**reg, "acquisition_yield": {"FY2025": _row(0.06)}, "development_yield": {"FY2025": _row(0.08)}}
    inc = derive_re(reit(reg=reg2))["incremental"]
    assert inc["basis"] == "direct" and inc["value"] == pytest.approx(0.07 + 0.025) and inc["stabilized_yield"] == pytest.approx(0.07)  # RE31: yield + fixed 2.5% (no same-property growth)


def test_economic_ltv_only_with_economic_value_reported_leverage_is_display_only():
    d = derive_re(reit())
    assert d["economic_ltv"][-1] is None and d["reported_leverage"][-1] == pytest.approx(3000 / 8000)
    d2 = derive_re(reit(reg={"fair_value_real_estate": {"FY2025": _row(10000e6)}}))
    assert d2["economic_ltv"][-1] == pytest.approx((3000 - 100) / 10000)


def test_missing_items_are_reported_not_scored_and_ranges_are_consistent():
    s = score_realestate(reit())
    b, g = _items(s["buffett_quality"]), _items(s["graham_quality"])
    for key in (("3.6", "3"), ("3.4", "1"), ("3.4", "2")):
        assert b[key].state == "missing"
    for key in (("3.7", "1"), ("3.3", "3"), ("3.3", "2"), ("3.2", "2")):
        assert g[key].state == "missing"
    assert not s["buffett_quality"].range_error and not s["graham_quality"].range_error


def test_leverage_thresholds():
    s = score_realestate(reit())
    b = _items(s["buffett_quality"])
    d = derive_re(reit())
    nd_e = d["nd_ebitdare"][-1]
    assert 0 <= b[("3.6", "1")].points <= 4 and nd_e < 5 and b[("3.6", "1")].points == pytest.approx(4.0)
    assert b[("3.6", "2")].points == pytest.approx(4.0)  # coverage above 5x


def test_towers_utilization_is_not_applicable_not_missing():
    ri = reit()
    ri.utilization = "not_applicable"
    assert _items(score_realestate(ri)["graham_quality"])[("3.7", "1")].state == "not_applicable"


def test_extracted_occupancy_scores_and_guardrail_caps_at_two_points():
    g = _items(score_realestate(reit(reg={"occupancy": _yrs(0.96)}))["graham_quality"])
    assert g[("3.7", "1")].points == pytest.approx(4.0)
    occ = _yrs(0.96)
    occ["FY2025"] = _row(0.90)
    g2 = _items(score_realestate(reit(reg={"occupancy": occ}))["graham_quality"])
    assert g2[("3.7", "1")].points <= 2.0 + 1e-9


def test_dividend_coverage_by_oe_and_gap_item_missing_when_oe_is_proxy():
    g = _items(score_realestate(reit())["graham_quality"])
    assert g[("3.5", "4")].state == "missing" and g[("3.8", "2")].state == "missing"


def test_extracted_csv_loader(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text('ticker,item,year,value,unit,quote,source,verified,note\n# comment\nO,occupancy,FY2025,0.98,fraction,"98.0% leased",10-K p.30,true,\n', encoding="utf-8")
    out = load_realestate_extracted(p)
    assert out["O"]["occupancy"]["FY2025"]["value"] == pytest.approx(0.98) and out["O"]["occupancy"]["FY2025"]["verified"] is True


# ------------------------------------------------------------------ round 2: RE10-RE14, S3a
def test_re12_gain_on_sale_of_investment_in_real_estate_entity_is_excluded_from_ffo():
    base = derive_re(reit())
    d = derive_re(reit(gains_re_entities=[0.0] * (N - 1) + [2000e6]))
    assert d["ffo"][-1] == pytest.approx(base["ffo"][-1] - 2000e6)
    assert any(x.startswith("RE12_gain_on_sale") for x in d["ffo_flags"][-1]) and d["ebitdare"][-1] == pytest.approx(base["ebitdare"][-1] - 2000e6)


def test_re13_noi_is_computed_by_us_and_reported_noi_is_only_a_reconciliation_input():
    ri = reit(noi_reported=[1.0e9] * N)
    ri.noi_method = ["prop_opex", "re_tax"]
    ri.f["re_tax"] = [50e6] * N
    d = derive_re(ri)
    g9 = 1.04 ** 9
    assert d["noi"][-1] == pytest.approx(950e6 * g9 - 300e6 * g9 - 50e6)  # our NOI, not the reported 1.0bn
    assert d["noi_reported"][-1] == 1.0e9 and d["noi_reconciliation_pct"][-1] == pytest.approx(d["noi"][-1] / 1.0e9 - 1)


def test_noi_uses_extracted_income_statement_lines_when_untagged():
    ri = reit(rental_revenue=[None] * N, prop_opex=[None] * N, reg={"rental_revenue_extracted": _yrs(500e6), "property_opex_extracted": _yrs(150e6)})
    d = derive_re(ri)
    assert d["noi"][-1] == pytest.approx(350e6) and "extracted" in d["noi_basis"][-1]


def test_re10_re11_profile_test_on_tags_and_on_extracted_data():
    ri = reit()
    assert derive_re(ri)["profile_check"]["assignment"] == "INCOME_REAL_ESTATE"
    ri2 = reit(rental_revenue=[100e6] * N)  # lease income 10% of revenue (WELL-like) -> STANDARD
    p2 = derive_re(ri2)["profile_check"]
    assert p2["assignment"] == "STANDARD" and p2["rental_ok"] is False
    # RE11: investment-property tag missing -> extracted PP&E-carried real estate decides (AMT-like: 32% of assets fails)
    ri3 = reit(re_net=[None] * N, reg={"profile_property_value": {"FY2025": _row(20e9)}, "profile_total_assets": {"FY2025": _row(63e9)}})
    p3 = derive_re(ri3)["profile_check"]
    assert p3["basis"]["property"].startswith("extracted") and p3["assignment"] == "STANDARD" and p3["investment_property_share"] == pytest.approx(20 / 63)
    # lease-income tag missing -> extracted revenue breakdown (EQIX-like: colocation 70% passes)
    ri4 = reit(rental_revenue=[None] * N, reg={"profile_rental_revenue": {"FY2025": _row(6.475e9)}, "profile_total_revenue": {"FY2025": _row(9.217e9)}})
    p4 = derive_re(ri4)["profile_check"]
    assert p4["basis"]["rental"].startswith("extracted") and p4["assignment"] == "INCOME_REAL_ESTATE"


def test_s3a_borderline_flag_within_5pp_of_a_threshold():
    from src.scoring.profile_flags import borderline_flag, borderline_tests
    assert borderline_tests({"a": (0.54, 0.5), "b": (0.56, 0.5), "c": (0.45, 0.5), "d": (None, 0.5)}) == ["a", "c"]
    assert borderline_flag({"x": (0.80, 0.5)})["borderline_assignment"] is False
    p = derive_re(reit(re_net=[4300e6] * N))["profile_check"]  # 4300 / 8000 = 53.75% vs 50%
    assert p["borderline_assignment"] and "investment_property_share" in p["borderline_tests"] and p["assignment"] == "INCOME_REAL_ESTATE"


def test_bank_path_carries_the_borderline_flag():
    from src.scoring.bank import bank_path
    p = bank_path("6022", 700, 1000, 320, 1000, True, True)  # loans / assets 32% vs 30%
    assert p["borderline_assignment"] and "loans_to_assets" in p["borderline_tests"]


def test_residential_and_storage_ti_lc_straight_line_not_applicable_and_tenant_concentration_na():
    ri = reit(straight_line=[None] * N)
    ri.asset_type = "residential"
    d = derive_re(ri)
    assert all(x == 0.0 for x in d["tilc_pres"]) and any("straight_line_not_applicable" in x for x in d["flags"])
    g = _items(score_realestate(ri)["graham_quality"])
    assert g[("3.7", "3")].state == "not_applicable"


def test_total_debt_from_extraction_fills_a_missing_year():
    debt = [None] + [3000e6] * (N - 1)
    d = derive_re(reit(debt_total=debt, reg={"debt_total_bs": {"FY2016": _row(2900e6)}}))
    assert d["net_debt"][0] == pytest.approx(2900e6 - 100e6) and d["debt_from_extraction"] == [0]


def test_extraction_spec_rows_are_verified_in_the_csv():
    import csv
    from src.providers.realestate_facts import EXTRACTED_CSV
    rows = [r for r in csv.DictReader(EXTRACTED_CSV.open(encoding="utf-8")) if r["ticker"] and not r["ticker"].startswith("#")]
    assert rows
    bad = [r for r in rows if r["value"] not in ("not extracted",) and r["verified"] != "true"]
    assert not bad, bad[:3]
    assert all(r["quote"] for r in rows if r["value"] not in ("not extracted",))


def test_re17_ffo_uses_company_reconciliation_da_and_nci_adjustment_first():
    g9 = 1.04 ** 9
    d = derive_re(reit(reg={"recon_re_da": {"FY2025": _row(500e6)}, "recon_nci_adjust": {"FY2025": _row(-12e6)}}))
    assert d["ffo"][-1] == pytest.approx(300e6 * g9 + 500e6 - 20e6 + 5e6 - 10e6 - 12e6)
    assert "D&A_from_company_FFO_reconciliation (RE17)" in d["ffo_flags"][-1]
    d2 = derive_re(reit(re_depr=[None] * N))
    assert "total_DA_used_may_include_non_real_estate_amortization" in d2["ffo_flags"][-1]  # priority 3, flagged


def test_re17_gap_above_10pct_is_flagged():
    d = derive_re(reit(reg={"reported_ffo": _yrs(1.0e9)}))
    assert d["ffo_gap_flag_over_10pct"][-1] is True


def test_re18_noi_proxy_when_no_yield_and_validity_test():
    reg = {"same_property_noi_growth": _yrs(0.03)}
    inc = derive_re(reit(reg=reg, acq_real_estate=[900e6] * N))["incremental"]  # net growth capital >= 5% of property value
    assert inc["basis"] == "NOI_PROXY"
    inc2 = derive_re(reit(reg=reg, acq_real_estate=[1e6] * N, development=[0.0] * N))["incremental"]
    assert inc2["value"] is None and "NOI_PROXY_validity_test_failed" in inc2["flags"]


def test_re19_noi_margin_stability_scale():
    s = score_realestate(reit())
    it = _items(s["buffett_quality"])[("3.4", "3")]
    assert it.name == "NOI margin stability" and it.points == pytest.approx(5.0)  # RE23 weight 5; constant margin: range 0
    f = reit(prop_opex=[300e6 * 1.04 ** i * (1 + (0.0 if i < N - 1 else 0.3)) for i in range(N)])
    it2 = _items(score_realestate(f)["buffett_quality"])[("3.4", "3")]
    assert it2.points < 5.0


def test_re15_lease_related_intangibles_count_as_real_estate_in_the_profile_test():
    ri = reit(re_net=[None] * N, intangibles_net=[14e9] * N, reg={"profile_property_value": {"FY2025": _row(20e9)}, "profile_total_assets": {"FY2025": _row(63e9)}})
    p = derive_re(ri)["profile_check"]
    assert p["investment_property_share"] == pytest.approx(34 / 63) and p["assignment"] == "INCOME_REAL_ESTATE" and any(x.startswith("RE15") for x in p["notes"])


def test_c15_nonpositive_fair_value_is_cannot_be_valued_with_price_score_zero():
    from test_models_smoke import synthetic
    from src.scoring.buffett import buffett_price, buffett_quality
    from src.scoring.metrics import derive
    inp = synthetic()
    inp.f["debt_lt"] = [5e12] * 10
    d = derive(inp)
    bp = buffett_price(inp, d, buffett_quality(inp, d))
    assert bp["state"] == "cannot_be_valued" and bp["fair_value"] is None and bp["price_score"]["points"] == 0.0 and bp["buy_price"] is None
    assert "debt exceeds modeled value" in bp["reason"]


def test_re22_noi_proxy_materiality_uses_gross_real_estate_at_cost_without_economic_value():
    reg = {"same_property_noi_growth": _yrs(0.03)}
    # net real estate 6.5bn, gross 8bn: net growth capital 4 x (100+50)m = 600m: 9% of 6.5bn would pass, 7.5% of 8bn passes; make it fail on gross only
    ri = reit(reg=reg, acq_real_estate=[90e6] * N, development=[0.0] * N, re_gross=[8000e6] * N, re_net=[6500e6] * N)
    inc = derive_re(ri)["incremental"]
    assert inc["basis"] is None and inc["property_base_kind"].startswith("gross real estate at cost")  # 360m < 5% x 8bn = 400m
    ok = derive_re(reit(reg=reg, acq_real_estate=[110e6] * N, development=[0.0] * N))["incremental"]
    assert ok["basis"] == "NOI_PROXY" and ok["property_base_kind"].startswith("gross")
    ev = derive_re(reit(reg={**reg, "fair_value_real_estate": _yrs(20000e9 / 1000)}, acq_real_estate=[110e6] * N))["incremental"]
    assert ev["property_base_kind"] == "economic value"  # economic value wins when present


def test_amt_style_reconciliation_starts_from_consolidated_net_income():
    reg = {"recon_net_income": {"FY2025": _row(2628.5e6)}, "recon_re_da": {"FY2025": _row(1899.6e6)}, "recon_nci_adjust": {"FY2025": _row(-450.7e6)}}
    d = derive_re(reit(reg=reg))
    assert d["ffo"][-1] == pytest.approx(2628.5e6 + 1899.6e6 - 20e6 + 5e6 - 450.7e6) and "net_income_start_from_company_reconciliation (consolidated, RE17)" in d["ffo_flags"][-1]


def test_re23_buffett_34_weights():
    items = _items(score_realestate(reit())["buffett_quality"])
    assert [items[("3.4", k)].max_pts for k in ("1", "2", "3")] == [4, 6, 5]

"""v1.1 candidates: C13 (claims expense in cost of revenue, ON by default), C12 (display-only alternative current ratio; the flag was removed) and the ETL tag fixes (inline-XBRL extension fallback, premium receivables)."""
from datetime import date

import pytest

from src.providers import sec_ixbrl as ix
from src.providers.sec_companyfacts import FIELD_MAP
from src.scoring.buffett import buffett_price, buffett_quality
from src.scoring.candidates import CANDIDATES, candidates
from src.scoring.graham import graham_price, graham_quality
from src.scoring.inputs import CompanyInputs
from src.scoring.metrics import derive


def mc(n=10, claims=True, gross_reported=False, cost_of_revenue=True, lt_explicit=True, lt_derived=False):
    """Managed-care-like company: big current liabilities, a long-term bond portfolio, claims expense."""
    g = [1.05 ** i for i in range(n)]
    rev = [100e9 * x for x in g]
    f = {
        "revenue": rev, "ebit": [6e9 * x for x in g], "pretax": [5.5e9 * x for x in g], "tax": [1.2e9 * x for x in g],
        "net_income": [4.3e9 * x for x in g], "interest_expense": [0.5e9] * n, "eps": [4.0 * x for x in g],
        "shares": [1.0e9] * n, "da": [1e9] * n, "acq_amort": [None] * n, "cfo": [6e9 * x for x in g], "capex": [1e9] * n,
        "sbc": [0.3e9] * n, "acquisitions": [0.0] * n, "buybacks": [1e9] * n, "dividends": [1e9] * n, "dps": [1.0] * n,
        "assets": [80e9 * x for x in g], "cur_assets": [30e9] * n, "cur_liab": [40e9] * n, "liabilities": [55e9] * n,
        "cash": [10e9] * n, "sti": [2e9] * n, "equity": [25e9] * n, "goodwill": [10e9] * n, "intangibles": [2e9] * n,
        "receivables": [5e9] * n, "debt_current": [1e9] * n, "debt_lt": [15e9] * n,
        "gross_profit": [(r - 5e9 * x) if gross_reported else (r - 5e9 * x) for r, x in zip(rev, g)],
        "cost_of_revenue": [5e9 * x for x in g] if cost_of_revenue else [None] * n,
        "claims_expense": [75e9 * x for x in g] if claims else [None] * n,
        "lt_mdebt_explicit": [20e9] * n if lt_explicit else [None] * n,
        "lt_mdebt_derived": [25e9] * n if lt_derived else [None] * n,
    }
    fy = [f"FY{2016 + i}" for i in range(n)]
    tag = "GrossProfit" if gross_reported else "DERIVED: Revenues - CostOfRevenue (CostOfGoodsAndServicesSold)"
    return CompanyInputs("MC", "mc", "STANDARD", fy, [date(2016 + i, 12, 31) for i in range(n)], f, sbc_state=["found"] * n,
                         price_current=50.0, price_avg=[20.0 * x for x in g], first_annual_report=date(1995, 3, 1),
                         as_of=date(2026, 10, 13), tag_log={"gross_profit": {l: {"tag": tag} for l in fy}})


# ------------------------------------------------------------------ defaults: C13 ON (approved), C12 removed (rejected)
def test_c13_is_on_by_default_and_can_be_switched_off_and_c12_does_not_exist():
    assert CANDIDATES.c13 is True and not hasattr(CANDIDATES, "c12")
    with candidates(c13=False):
        assert CANDIDATES.c13 is False
    assert CANDIDATES.c13 is True


def test_scored_liquidity_ignores_noncurrent_marketable_debt_alternative_is_display_only():
    inp = mc()
    d = derive(inp)
    assert d["current_ratio"][-1] == pytest.approx(30 / 40)  # explicit tag present, still not counted
    assert d["working_capital"][-1] == pytest.approx(-10e9)
    assert d["quick_ratio"][-1] == pytest.approx((10 + 2 + 5) / 40)
    assert d["current_ratio_alt"][-1] == pytest.approx((30 + 20) / 40)
    assert d["working_capital_alt"][-1] == pytest.approx(10e9)
    assert d["quick_ratio_alt"][-1] == pytest.approx((10 + 2 + 5 + 20) / 40)
    # alt uses the derived estimate only when there is no explicit tag
    d2 = derive(mc(lt_explicit=False, lt_derived=True))
    assert d2["current_ratio_alt"][-1] == pytest.approx((30 + 25) / 40) and d2["current_ratio"][-1] == pytest.approx(30 / 40)


def test_liquidity_scores_and_valuation_do_not_depend_on_the_marketable_debt_tags():
    a, b = mc(), mc(lt_explicit=False)
    da, db = derive(a), derive(b)
    ga, gb = graham_quality(a, da), graham_quality(b, db)
    assert ga.score == pytest.approx(gb.score)
    pa, pb = buffett_price(a, da, buffett_quality(a, da)), buffett_price(b, db, buffett_quality(b, db))
    assert pa["fair_value"] == pytest.approx(pb["fair_value"]) and pa["excess_cash_less_debt"] == pb["excess_cash_less_debt"]
    assert graham_price(a, da, ga)["graham_number"]["ncav_per_share"] == graham_price(b, db, gb)["graham_number"]["ncav_per_share"]


# ------------------------------------------------------------------ C13
def test_c13_includes_claims_in_cost_of_revenue_when_gross_profit_is_derived():
    inp = mc()
    d = derive(inp)  # default ON
    assert d["gross_margin"][0] == pytest.approx(1 - (5e9 + 75e9) / 100e9)
    with candidates(c13=False):
        assert derive(inp)["gross_margin"][0] == pytest.approx(1 - 5e9 / 100e9)


def test_c13_keeps_a_company_reported_gross_profit():
    inp = mc(gross_reported=True)
    with candidates(c13=False):
        off = derive(inp)["gross_margin"]
    assert derive(inp)["gross_margin"] == off


def test_c13_gives_a_gross_margin_when_only_the_claims_tag_exists_and_is_neutral_without_it():
    inp = mc(cost_of_revenue=False)
    inp.f["gross_profit"] = [None] * 10
    d = derive(inp)
    bq = buffett_quality(inp, d)
    assert d["gross_margin"][0] == pytest.approx(1 - 75e9 / 100e9)
    assert next(i for c in bq.criteria if c.id == "3.2" for i in c.items if i.id == "1a").state != "not_applicable"
    # without a claims tag nothing changes
    inp2 = mc(claims=False)
    with candidates(c13=False):
        base = derive(inp2)["gross_margin"]
    assert derive(inp2)["gross_margin"] == base


# ------------------------------------------------------------------ ETL: inline XBRL extension fallback
IXBRL = """
<xbrli:context id="c-1"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="c-2"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="c-3"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier>
 <xbrli:segment><xbrldi:explicitMember dimension="srt:Seg">ci:A</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
 <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="c-4"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="c-5"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:startDate>2025-10-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<ix:nonFraction name="ci:PaymentsForProceedsFromPropertyPlantAndEquipment" contextRef="c-1" unitRef="usd" scale="6" decimals="-6">1,212</ix:nonFraction>
<ix:nonFraction name="ci:PaymentsForProceedsFromPropertyPlantAndEquipment" contextRef="c-2" unitRef="usd" scale="6" decimals="-6"><span>1,406</span></ix:nonFraction>
<ix:nonFraction name="ci:PaymentsForProceedsFromPropertyPlantAndEquipment" contextRef="c-3" unitRef="usd" scale="6">999</ix:nonFraction>
<ix:nonFraction name="ci:PaymentsForProceedsFromPropertyPlantAndEquipment" contextRef="c-5" unitRef="usd" scale="6">300</ix:nonFraction>
<ix:nonFraction name="ci:LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent" contextRef="c-4" unitRef="usd" scale="6">4,180</ix:nonFraction>
<ix:nonFraction name="ci:LiabilityForClaimsAndClaimsAdjustmentExpenseNoncurrent" contextRef="c-4" unitRef="usd" scale="6" sign="-">61</ix:nonFraction>
<ix:nonFraction name="ci:Other" contextRef="c-1" unitRef="usd" scale="6" format="ixt:fixed-zero">&#8212;</ix:nonFraction>
<ix:nonFraction name="ci:Eps" contextRef="c-1" unitRef="usdPerShare">3.5</ix:nonFraction>
"""


def test_ixbrl_flow_facts_scale_dimension_and_period_length():
    got = ix.extract_facts(IXBRL, ["PaymentsForProceedsFromPropertyPlantAndEquipment"], "flow")
    v = got["PaymentsForProceedsFromPropertyPlantAndEquipment"]
    assert v[date(2025, 12, 31)][0] == pytest.approx(1212e6) and v[date(2024, 12, 31)][0] == pytest.approx(1406e6)
    assert v[date(2025, 12, 31)][1] == "ci:PaymentsForProceedsFromPropertyPlantAndEquipment"  # dimensional (999) and 3-month (300) skipped


def test_ixbrl_instant_facts_sign_and_dash_and_non_usd():
    got = ix.extract_facts(IXBRL, ["LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent", "LiabilityForClaimsAndClaimsAdjustmentExpenseNoncurrent",
                                   "Other", "Eps"], "instant")
    assert got["LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent"][date(2025, 12, 31)][0] == pytest.approx(4180e6)
    assert got["LiabilityForClaimsAndClaimsAdjustmentExpenseNoncurrent"][date(2025, 12, 31)][0] == pytest.approx(-61e6)
    assert "Eps" not in got and "Other" not in got  # flows/instants are separated by kind; per-share units are ignored
    assert ix.extract_facts(IXBRL, ["Other"], "flow")["Other"][date(2025, 12, 31)][0] == 0.0


SEG = """
<xbrli:context id="s-1"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment>
 <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">ci:CignaHealthcareMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
 <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="s-2"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment>
 <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">ci:AllSegmentsExcludingCignaHealthcareMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
 <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="s-3"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment>
 <xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">ci:CignaHealthcareMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
 <xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period></xbrli:context>
<ix:nonFraction name="ci:LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent" contextRef="s-1" unitRef="usd" scale="6">4,180</ix:nonFraction>
<ix:nonFraction name="ci:LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent" contextRef="s-2" unitRef="usd" scale="6">167</ix:nonFraction>
<ix:nonFraction name="ci:LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent" contextRef="s-3" unitRef="usd" scale="6">4,500</ix:nonFraction>
"""


def test_ixbrl_segment_members_are_summed_only_when_exhaustive_and_only_on_request():
    name = "LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent"
    assert ix.extract_facts(SEG, [name], "instant") == {}
    got = ix.extract_facts(SEG, [name], "instant", segment_sum=True)[name]
    assert got[date(2025, 12, 31)][0] == pytest.approx(4347e6) and "sum of segment members" in got[date(2025, 12, 31)][1]
    assert date(2024, 12, 31) not in got  # one member only, no remainder member: not exhaustive


def test_extension_fallback_fills_only_missing_years_and_logs_the_tag(monkeypatch):
    from src.providers import sec_companyfacts as sc
    assert "PremiumsReceivableAtCarryingValue" in FIELD_MAP["receivables"][2] and "PremiumsAndOtherReceivablesNet" in FIELD_MAP["receivables"][2]
    # the fallback only fires for the configured fields, and insurer-only for the claims liability
    assert sc.EXT_FALLBACK["capex"][0] == ["PaymentsForProceedsFromPropertyPlantAndEquipment"] and sc.EXT_FALLBACK["capex"][2] is False
    assert sc.EXT_FALLBACK["claims_liability"][0] == ["LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent"] and sc.EXT_FALLBACK["claims_liability"][2] is True

    class _Sec:
        pass
    raw_calls = []

    def fake_filings(sec, cik):
        return [{"accession": "0001-26-000001", "primary": "ci.htm", "report_date": date(2025, 12, 31), "filed": date(2026, 2, 5)}]

    def fake_raw(sec, url, name):
        raw_calls.append(name)
        return IXBRL
    monkeypatch.setattr(ix, "tenk_filings", fake_filings)
    monkeypatch.setattr(ix, "_get_raw", fake_raw)
    out = ix.extension_series(_Sec(), "0001739940", ["PaymentsForProceedsFromPropertyPlantAndEquipment"], "flow",
                              [date(2025, 12, 31), date(2024, 12, 31), date(2023, 12, 31)])
    assert out[date(2025, 12, 31)].val == pytest.approx(1212e6) and out[date(2024, 12, 31)].tag == "ixbrl:ci:PaymentsForProceedsFromPropertyPlantAndEquipment"
    assert date(2023, 12, 31) not in out and raw_calls == ["000126000001_ci.htm"]


# ------------------------------------------------------------------ v1.2 G3-C (production): unlevered owner earnings
def test_g3c_unlevered_owner_earnings_are_the_only_path_and_debt_is_still_subtracted():
    a = mc()
    da = derive(a)
    assert not hasattr(CANDIDATES, "g3c_unlevered") and not hasattr(CANDIDATES, "g3_no_debt")
    p = buffett_price(a, da, buffett_quality(a, da))
    rate = 1.2 / 5.5  # tax / pretax, inside the 0-40% clip
    add = 0.5e9 * (1 - rate)
    assert p["owner_earnings_last5"] == pytest.approx([x + add for x in p["owner_earnings_levered_last5"]])
    assert p["excess_cash_less_debt"] == pytest.approx(da["cash_sti"][-1] - da["fin_debt"][-1])
    # implied return / reverse DCF solve the same unlevered DCF: the value at the solved return equals the price
    ir = p["implied_return"]
    from src.scoring.buffett import dcf_fair_value
    assert ir["state"] == "solved"
    v = dcf_fair_value(p["base"], p["stage1_growth"], p["excess_cash_less_debt"], 1.0e9, r=ir["implied_return"])["fair_value_per_share"]
    assert v == pytest.approx(50.0, rel=1e-6)

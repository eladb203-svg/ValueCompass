"""K6d-2 fixes (2026-11-01): the four batch-7 fixes (dividend per share by class, same-property NOI from a table, the tenant ceiling, the investment-grade share from amounts) and the three general
mechanisms (the data_gap_review list, derivation hints with components computed by the code, the wide XBRL search)."""
import json
from datetime import date

from fakedb import FakeClient
from src.ai import ext_checks as X
from src.ai import gap_review as GR
from src.ai import keyword_depth as KD
from src.ai.checks import normalize
from src.ai.prompt import build_extraction_prompt, extraction_blocks
from src.providers import xbrl_wide as W

# ---------------------------------------------------------------- inline XBRL of a two-class company
CTX = """
<xbrli:context id="c-1"><xbrli:entity/><xbrli:period><xbrli:startDate>2024-09-29</xbrli:startDate><xbrli:endDate>2025-09-27</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="cA"><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassAMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2024-09-29</xbrli:startDate><xbrli:endDate>2025-09-27</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="cB"><xbrli:entity><xbrli:segment><xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">us-gaap:CommonClassBMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2024-09-29</xbrli:startDate><xbrli:endDate>2025-09-27</xbrli:endDate></xbrli:period></xbrli:context>
"""
COVER = '<ix:nonNumeric contextRef="c-1" name="dei:Security12bTitle">Class A Common Stock</ix:nonNumeric><ix:nonNumeric contextRef="c-1" name="dei:TradingSymbol">TSN</ix:nonNumeric>'


def nf(name, ctx, val, unit="usdPerShare"):
    return f'<ix:nonFraction name="{name}" contextRef="{ctx}" unitRef="{unit}" decimals="2">{val}</ix:nonFraction>'


class FakeSec:
    requests_made = 0


def run_search(monkeypatch, raw, fld="dps", ticker="TSN"):
    monkeypatch.setattr(W, "tenk_filings", lambda sec, cik: [{"accession": "0000100493-25-000095", "primary": "x.htm", "report_date": date(2025, 9, 27), "filed": date(2025, 11, 14)}])
    monkeypatch.setattr(W, "_get_raw", lambda sec, url, name: raw)
    return W.search(FakeSec(), "0000100493", ticker, fld, [date(2025, 9, 27)])


def test_the_dividend_per_share_of_the_traded_class_is_taken_when_only_class_values_exist(monkeypatch):
    raw = CTX + COVER + nf("us-gaap:CommonStockDividendsPerShareDeclared", "cA", "2.01") + nf("us-gaap:CommonStockDividendsPerShareDeclared", "cB", "1.809")
    got, conflicts = run_search(monkeypatch, raw)
    fact = got[date(2025, 9, 27)]
    assert fact.val == 2.01 and conflicts == []
    assert fact.tag.startswith("DERIVED") and "class=CommonClassAMember" in fact.tag                  # source_kind derived (a tag with a space), the class named


def test_the_class_is_found_from_the_trading_symbol_with_the_class_axis(monkeypatch):
    cover = '<ix:nonNumeric contextRef="cB" name="dei:TradingSymbol">TSN.B</ix:nonNumeric>'
    raw = CTX + cover + nf("us-gaap:CommonStockDividendsPerShareDeclared", "cA", "2.01") + nf("us-gaap:CommonStockDividendsPerShareDeclared", "cB", "1.809")
    got, _ = run_search(monkeypatch, raw, ticker="TSN.B")
    assert got[date(2025, 9, 27)].val == 1.809


def test_an_unidentified_class_leaves_the_year_missing_and_is_a_conflict(monkeypatch):
    raw = CTX + nf("us-gaap:CommonStockDividendsPerShareDeclared", "cA", "2.01") + nf("us-gaap:CommonStockDividendsPerShareDeclared", "cB", "1.809")        # no cover page: no way to say which class trades
    got, conflicts = run_search(monkeypatch, raw)
    assert got == {} and len(conflicts) == 1 and "traded class" in conflicts[0]["reason"]


def test_share_counts_by_class_are_added_up_and_flagged(monkeypatch):
    raw = CTX + COVER + nf("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", "cA", "290000000", "shares") + nf("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", "cB", "70000000", "shares")
    got, _ = run_search(monkeypatch, raw, fld="shares_basic")
    f = got[date(2025, 9, 27)]
    assert f.val == 360000000 and "sum of 2 classes" in f.tag


def test_a_company_element_with_a_close_name_is_used_and_marked_custom_tag(monkeypatch):
    raw = CTX + COVER + nf("tsn:DividendsDeclaredPerShareClassA", "c-1", "2.01")
    got, _ = run_search(monkeypatch, raw)
    f = got[date(2025, 9, 27)]
    assert f.val == 2.01 and f.tag.startswith("ixbrl:custom_tag")                                     # source_kind ixbrl


def test_two_company_elements_that_disagree_leave_the_year_missing(monkeypatch):
    raw = CTX + COVER + nf("tsn:DividendsDeclaredPerShareClassA", "c-1", "2.01") + nf("tsn:CashDividendsPerShare", "c-1", "1.96")
    got, conflicts = run_search(monkeypatch, raw)
    assert got == {} and len(conflicts) == 1 and "disagree" in conflicts[0]["reason"]


def test_fill_writes_the_value_the_tag_and_the_split_adjustment(monkeypatch):
    raw = CTX + COVER + nf("us-gaap:CommonStockDividendsPerShareDeclared", "cA", "2.01")
    monkeypatch.setattr(W, "tenk_filings", lambda sec, cik: [{"accession": "0000100493-25-000095", "primary": "x.htm", "report_date": date(2025, 9, 27), "filed": date(2025, 11, 14)}])
    monkeypatch.setattr(W, "_get_raw", lambda sec, url, name: raw)
    f, log, problems = {"dps": [None]}, {"dps": {"FY2025": {"tag": None}}}, []
    conf = W.fill(FakeSec(), "0000100493", "TSN", f, log, ["FY2025"], [date(2025, 9, 27)], problems, split_factor=lambda filed: 1.0, fields=("dps",))
    assert f["dps"] == [2.01] and "traded class" in log["dps"]["FY2025"]["tag"] and conf == [] and any("wide XBRL search filled FY2025" in p for p in problems)


# ---------------------------------------------------------------- REXR: same-property NOI from revenues and expenses; the tenant ceiling
REXR = ("Comparison of the Year Ended December 31, 2025 to the Year Ended December 31, 2024 For the comparison, our Same Property Portfolio includes all properties. "
        "Same Property Portfolio Total Portfolio 2025 2024 $ Change % Change REVENUES Rental income $ 759,209 $ 745,932 $ 13,277 1.8 % $ 980,376 $ 922,096 $ 58,280 6.3 % "
        "Management and leasing services - - - - % 589 611 (22) (3.6) % TOTAL REVENUES 759,209 745,932 13,277 1.8 % 1,003,133 936,407 66,726 7.1 % OPERATING EXPENSES "
        "Property expenses 170,034 163,053 6,981 4.3 % 227,725 210,260 17,465 8.3 % General and administrative - - - - % 78,856 82,153 (3,297) (4.0) %")


def test_same_property_noi_growth_is_derived_from_the_revenue_and_expense_lines():
    g, quote, basis = KD.same_table(REXR)
    assert abs(g - ((759209 - 170034) / (745932 - 163053) - 1) * 100) < 1e-3 and 1.07 < g < 1.09                      # +1.1%
    assert "759,209" in quote and "170,034" in quote and "163,053" in quote and "=" in basis
    rows = KD.same_noi_rows({2025: ("0001571283-26-000006", REXR)})
    assert len(rows) == 1 and rows[0][0] == 2025


def test_a_stated_noi_line_is_used_before_the_table():
    txt = "Total same property net operating income $ 600,000 $ 580,000 " + REXR
    rows = KD.same_noi_rows({2025: ("a", txt)})
    assert abs(rows[0][2] - (600000 / 580000 - 1) * 100) < 1e-4 and "both levels" in rows[0][4]


def test_a_table_where_expenses_exceed_revenues_gives_nothing():
    bad = "Same Property Portfolio Rental income $ 1,000 $ 1,100 TOTAL REVENUES 1,000 1,100 Property expenses 2,000 1,500"
    assert KD.same_table(bad) is None


TENANT = ("As of December 31, 2025, our consolidated properties were 90.9% leased to tenants in a variety of industries, with no single tenant accounting for more than 2.4% of our total annualized in-place base rent. "
          "Our 10 largest tenants combined accounted for 13.9% of our annualized base rent as of December 31, 2025.")


def test_no_single_tenant_above_x_is_a_ceiling_and_the_top_ten_is_a_separate_item():
    rows = {r[0]: r for r in KD.tenant_rows({2025: ("acc", TENANT)})}
    assert rows["largest_tenant_share"][3] == 2.4 and rows["largest_tenant_share"][6] is True and "bound=max" in rows["largest_tenant_share"][5]
    assert rows["top10_tenants_share"][3] == 13.9 and rows["top10_tenants_share"][6] is False
    built = KD.build_rows("REXR", {2025: ("acc", TENANT)}, True, set(), set())
    by = {r["item_key"]: r for r in built}
    assert by["largest_tenant_share"]["value"] == 2.4 and "bound=max" in by["largest_tenant_share"]["basis"] and by["top10_tenants_share"]["value"] == 13.9
    assert KD.build_rows("REXR", {2025: ("acc", TENANT)}, True, set(), set(), {"largest_tenant_share": {2025}}) != built      # a model answer for the year is not replaced
    left = [r["item_key"] for r in KD.build_rows("REXR", {2025: ("acc", TENANT)}, True, set(), set(), {"largest_tenant_share": {2025}})]
    assert "top10_tenants_share" in left and "largest_tenant_share" not in left


# ---------------------------------------------------------------- RLI: investment-grade share from amounts
RLI = ("Non-investment grade bonds totaled $148 million while non-rated Regulation D securities totaled $90 million at the end of 2024. While these Regulation D securities are not rated, all but one carry an "
       "equivalent investment-grade rating.")


def test_the_investment_grade_share_comes_from_the_amounts_and_the_total():
    rows = KD.ig_amount_rows({2024: ("acc", RLI)}, {2024: (2_380e6, "test total")})
    assert len(rows) == 1
    y, acc, share, quote, basis = rows[0]
    assert abs(share - (1 - (148 + 90) / 2380) * 100) < 1e-6 and share == 90.0
    assert "$148 million" in quote and "$90 million" in quote and "non-rated" in basis and "test total" in basis


def test_without_a_total_the_investment_grade_share_stays_missing():
    assert KD.ig_amount_rows({2024: ("acc", RLI)}, {}) == []
    assert KD.ig_amount_rows({2024: ("acc", RLI)}, {2024: (200e6, "too small")}) == []                   # the amounts exceed the total: no share


def test_the_fixed_income_total_comes_from_the_report_row_else_the_xbrl_fair_value():
    rows = [{"item_key": "inv_fixed_maturities", "state": "value", "value_full": 2_000e6, "year": 2024, "approval_status": "approved"}]
    facts = {"facts": {"us-gaap": {"AvailableForSaleSecuritiesDebtSecurities": {"units": {"USD": [{"form": "10-K", "fp": "FY", "end": "2023-12-31", "val": 1.9e9}, {"form": "10-K", "fp": "FY", "end": "2024-12-31", "val": 2.1e9}]}}}}}
    t = KD.fixed_income_totals(rows, facts, [2023, 2024])
    assert t[2024][0] == 2_000e6 and "report" in t[2024][1] and t[2023][0] == 1.9e9 and "XBRL" in t[2023][1]


# ---------------------------------------------------------------- derivation hints: the model gives components, the code computes
TEXT = ("Same Property Portfolio Rental income $ 759,209 $ 745,932 Property expenses 170,034 163,053 and the group has fixed maturities of $ 2,380 million. "
        "Non-investment grade bonds totaled $148 million while non-rated securities totaled $90 million.")


def comp(name, value, scale, quote):
    return {"name": name, "value": value, "scale": scale, "quote": {"text": quote, "section": "X"}}


def derive(item, keys, text=TEXT):
    return X.derive_item(item, keys, normalize(text), 2025)


def test_the_code_computes_the_growth_from_components_each_with_a_quote():
    it = {"item_key": "same_property_noi_growth", "period": "December 31, 2025", "value": None, "value_state": "components",
          "components": [comp("revenue_current", 759209, 1000, "Rental income $ 759,209 $ 745,932"), comp("revenue_prior", 745932, 1000, "Rental income $ 759,209 $ 745,932"),
                         comp("expense_current", 170034, 1000, "Property expenses 170,034 163,053"), comp("expense_prior", 163053, 1000, "Property expenses 170,034 163,053")]}
    r = derive(it, {"same_property_noi_growth": "percent"})
    assert r.ok and "derived" in r.flags and abs(it["value"] - 1.0802) < 1e-3 and it["value_state"] == "value" and "||" in it["quote"]["text"] and "components" in it["basis"]


def test_a_component_whose_quote_is_not_in_the_text_rejects_the_item():
    it = {"item_key": "inv_ig_share", "period": "2025", "value": None, "value_state": "components",
          "components": [comp("non_investment_grade", 148, 1000000, "Non-investment grade bonds totaled $148 million"), comp("total_fixed_income", 2380, 1000000, "fixed maturities of $ 9,999 million")]}
    r = derive(it, {"inv_ig_share": "percent"})
    assert not r.ok and any(x.startswith("component_quote_not_found") for x in r.reasons)


def test_a_final_number_given_with_the_components_is_refused():
    it = {"item_key": "inv_ig_share", "period": "2025", "value": 90.0, "value_state": "components",
          "components": [comp("non_investment_grade", 148, 1000000, "Non-investment grade bonds totaled $148 million")]}
    r = derive(it, {"inv_ig_share": "percent"})
    assert not r.ok and "value_state_inconsistent" in r.reasons


def test_a_missing_required_component_rejects_and_the_share_is_computed_when_complete():
    keys = {"inv_ig_share": "percent"}
    base = [comp("non_investment_grade", 148, 1000000, "Non-investment grade bonds totaled $148 million"), comp("non_rated", 90, 1000000, "non-rated securities totaled $90 million")]
    r = derive({"item_key": "inv_ig_share", "period": "2025", "value": None, "value_state": "components", "components": base}, keys)
    assert not r.ok and "component_missing:total_fixed_income" in r.reasons
    full = {"item_key": "inv_ig_share", "period": "2025", "value": None, "value_state": "components", "components": base + [comp("total_fixed_income", 2380, 1000000, "fixed maturities of $ 2,380 million")]}
    r = derive(full, keys)
    assert r.ok and abs(full["value"] - 90.0) < 1e-6


def test_check_reply_routes_an_item_with_components_to_the_derivation():
    block = {"skill_id": "EXT-INS-INV", "items": [{"key": "inv_ig_share", "unit": "percent"}]}
    reply = {"skill_id": "EXT-INS-INV", "items": [{"item_key": "inv_ig_share", "period": "2025", "value": None, "value_state": "components", "components": [
        comp("non_investment_grade", 148, 1000000, "Non-investment grade bonds totaled $148 million"), comp("non_rated", 90, 1000000, "non-rated securities totaled $90 million"),
        comp("total_fixed_income", 2380, 1000000, "fixed maturities of $ 2,380 million")]}]}
    res, reasons = X.check_reply(json.dumps(reply), block, TEXT, 2025)
    assert res[0].ok and abs(res[0].item["value"] - 90.0) < 1e-6 and "derived" in res[0].flags


def test_the_prompt_carries_the_hints_and_the_component_format_only_when_an_item_has_one():
    blocks = {b["skill_id"]: b for b in extraction_blocks().values()}
    p, _, _ = build_extraction_prompt(blocks["EXT-RE-OPS"], {"company_name": "X", "ticker": "X", "fiscal_year": "FY2025"}, {"X-REOPS": "some text"})
    assert "derivation hint:" in p and "bound=max" in p and "components" in p and "Never compute the final number" in p
    p2, _, _ = build_extraction_prompt(blocks["EXT-BANK-CAP"], {"company_name": "X", "ticker": "X", "fiscal_year": "FY2025"}, {"X-BANKCAP": "some text"})
    assert "derivation hint" not in p2.lower()
    assert blocks["EXT-RE-OPS"]["version"] >= 3 and blocks["EXT-INS-INV"]["version"] >= 8                      # a changed prompt is a new version: stored answers of the old text are asked again


def test_the_b14_gross_profit_item_has_a_hint():
    from src.ai import b14
    rows = [{"id": "FIN-1", "item": "Gross profit", "definition": "revenue less cost", "statement": "Income statement", "fields": {"G": ["gross_profit"]}, "extracts": "Code"}]
    items, _, _ = b14.b14_items(rows, "general", {"gross_profit": {"FY2025": None}}, ["FY2025"])
    assert items and "derivation_hints" in items[0] and "cost_of_revenue" in items[0]["derivation_hints"]


# ---------------------------------------------------------------- data_gap_review
def gap_db():
    c = FakeClient()
    c.tables["companies"] = [{"id": 1, "symbol": "REXR"}, {"id": 2, "symbol": "TSN"}]
    c.tables["score_runs"] = [{"id": 10, "company_id": 1}, {"id": 11, "company_id": 2}]
    mk = lambda run, model, ck, sub, state, note: {"run_id": run, "model": model, "criterion_key": ck, "sub_criterion_key": sub, "detail_level": "sub_criterion", "evidence": {"state": state, "note": note}}   # noqa: E731
    c.tables["score_details"] = [mk(10, "buffett", "3.4", "2", "missing", "same-property NOI growth not extracted (AI extraction needed; fewer than 3 years)"),
                                 mk(10, "graham", "3.7", "3", "missing", "largest tenant share not extracted (AI extraction needed)"),
                                 mk(10, "buffett", "3.7", "4", "missing", "OE is a proxy (maintenance capex / TI-LC not extracted): level item missing by rule"),
                                 mk(10, "graham", "3.2", "2", "not_applicable", "bank not subject to the LCR"), mk(10, "buffett", "3.1", "1", "score", ""),
                                 {"run_id": 10, "model": "buffett", "criterion_key": "total", "sub_criterion_key": "", "detail_level": "criterion", "evidence": {"state": "missing"}},
                                 mk(11, "graham", "3.5", "2", "missing", "dividend per share missing for most years")]
    c.tables["filing_periods"] = [{"company_id": 1, "fiscal_year": 2025, "accession": "0001571283-26-000006"}, {"company_id": 2, "fiscal_year": 2025, "accession": "0000100493-25-000095"}]
    return c


def test_families_group_the_same_kind_of_gap():
    assert GR.family_of("same-property NOI growth not extracted (AI extraction needed)")[0] == "same_property_noi"
    assert GR.family_of("largest tenant share not extracted")[0] == "largest_tenant"
    assert GR.family_of("dividend per share missing for most years")[0] == "dividend_per_share"
    assert GR.family_of("OE is a proxy (maintenance capex / TI-LC not extracted): level item missing by rule")[::2] == ("oe_proxy", True)
    assert GR.family_of("something new and odd")[0].startswith("other:")


def test_the_closest_passage_is_about_300_characters_around_the_keywords():
    p = GR.closest_passage("x " * 400 + "no single tenant accounting for more than 2.4% of rent " + "y " * 400, GR.family_of("largest tenant")[1])
    assert "no single tenant" in p and len(p) <= 300 and GR.closest_passage("nothing here", "tenant") == "" and GR.closest_passage("text", "") == ""


def test_refresh_lists_only_missing_items_with_reason_family_and_passage(tmp_path):
    c = gap_db()
    (tmp_path / "000157128326000006_rexr.htm").write_text("<p>no single tenant accounting for more than 2.4% of our total annualized base rent</p>", encoding="utf-8")
    counts = GR.refresh(c, 1, tmp_path, text_of=lambda p: p.read_text(encoding="utf-8"))
    rows = {r["item_key"]: r for r in c.tables["data_gap_review"]}
    assert set(rows) == {"B 3.4.2", "G 3.7.3", "B 3.7.4"}                                      # not_applicable, score and the criterion totals are not gaps
    assert rows["G 3.7.3"]["family"] == "largest_tenant" and "no single tenant" in rows["G 3.7.3"]["closest_passage"] and rows["G 3.7.3"]["accession"] == "0001571283-26-000006" and rows["G 3.7.3"]["fiscal_year"] == 2025
    assert rows["B 3.4.2"]["state"] == "open" and rows["B 3.7.4"]["state"] == "genuine" and rows["B 3.7.4"]["closed_at"] and counts["added"] == 3


def test_a_later_score_that_no_longer_lists_the_item_closes_it_and_a_genuine_row_stays_genuine(tmp_path):
    c = gap_db()
    GR.refresh(c, 1, tmp_path, text_of=lambda p: "")
    c.tables["score_details"] = [r for r in c.tables["score_details"] if not (r["run_id"] == 10 and r["criterion_key"] == "3.4")]
    counts = GR.refresh(c, 1, tmp_path, text_of=lambda p: "")
    rows = {r["item_key"]: r for r in c.tables["data_gap_review"]}
    assert rows["B 3.4.2"]["state"] == "fixed" and rows["B 3.4.2"]["closed_at"] and counts["closed"] == 1 and rows["B 3.7.4"]["state"] == "genuine"
    assert len(c.tables["data_gap_review"]) == 3                                                # one row per company and criterion: a repeat does not add


def test_conflicts_of_the_wide_search_are_rows_of_their_own_family():
    c = gap_db()
    n = GR.record_conflicts(c, 2, [{"field": "dps", "end": "2025-09-27", "reason": "two company elements disagree"}])
    r = c.tables["data_gap_review"][0]
    assert n == 1 and r["family"] == "wide_xbrl_conflict" and r["item_key"] == "XBRL dps 2025" and r["state"] == "open"


def test_the_list_is_grouped_by_family_with_the_number_of_companies(tmp_path):
    c = gap_db()
    for cid in (1, 2):
        GR.refresh(c, cid, tmp_path, text_of=lambda p: "")
    c.tables["data_gap_review"].append({"id": 99, "company_id": 2, "item_key": "G 3.7.3", "family": "largest_tenant", "state": "open", "reason": "x", "fiscal_year": 2025})
    g = GR.grouped(c)
    fam = {name: (states, n) for name, states, n, _ in g}
    assert fam["largest_tenant"][1] == 2 and fam["dividend_per_share"][1] == 1
    only = GR.grouped(c, "dividend_per_share")
    assert [x[0] for x in only] == ["dividend_per_share"] and only[0][3][0][0] == "TSN"
    assert [x[0] for x in GR.grouped(c, None, "genuine")] == ["oe_proxy"]


def test_the_table_has_no_access_for_the_public_roles():
    sql = open(__file__.replace("tests\\test_k6d2_gaps_wide.py", "supabase\\migrations\\20261101150100_data_gap_review.sql").replace("tests/test_k6d2_gaps_wide.py", "supabase/migrations/20261101150100_data_gap_review.sql"), encoding="utf-8").read()
    assert "enable row level security" in sql and "revoke all on public.data_gap_review from anon, authenticated" in sql and "grant all on public.data_gap_review to service_role" in sql
    assert "state in ('open','fixed','genuine')" in sql and "unique (company_id, item_key)" in sql


def test_a_healthcare_reit_calls_its_tenants_operators():
    floor = "In addition, at December 31, 2025, one operator represented greater than 10% of our investments, and the three geographic locations were the U.K. (17.7%)."
    rows = {r[0]: r for r in KD.tenant_rows({2025: ("acc", floor)})}
    assert rows["largest_tenant_floor"][3] == 10.0 and "bound=min" in rows["largest_tenant_floor"][5] and "largest_tenant_share" not in rows          # a floor is not a share to score
    cap = "with no single operator accounting for more than 12.5% of our total revenue. The 10 largest operators accounted for 40% of revenue."
    rows = {r[0]: r for r in KD.tenant_rows({2025: ("acc", cap)})}
    assert rows["largest_tenant_share"][3] == 12.5 and rows["top10_tenants_share"][3] == 40.0


def test_an_answer_given_without_sections_is_stale_once_the_sections_exist():
    from src.ai import assess

    class Sec:
        def __init__(self, found):
            self.found, self.text = found, "x"

    class Co:
        def __init__(self, found):
            self._s = {"TXT-004": Sec(found), "NOTE-UNUSUAL": Sec(False)}

        def sections(self):
            return self._s

    skill = {"sections": ["TXT-004", "NOTE-UNUSUAL"]}
    no_call = {"state": "insufficient_evidence", "evidence": {"flags": ["section_not_found:TXT-004"], "reasons": ["primary_section_missing"]}}
    partly = {"state": "insufficient_evidence", "evidence": {"flags": ["section_not_found:TXT-004"], "reasons": []}}
    model_said = {"state": "insufficient_evidence", "evidence": {"flags": [], "reasons": []}}
    answered = {"state": "answered", "evidence": {"flags": ["section_not_found:TXT-004"]}}
    assert assess.stale_insufficient(no_call, Co(True), skill) and assess.stale_insufficient(partly, Co(True), skill)
    assert not assess.stale_insufficient(no_call, Co(False), skill)                          # the sections are still missing: nothing new to ask with
    assert not assess.stale_insufficient(model_said, Co(True), skill) and not assess.stale_insufficient(answered, Co(True), skill)


SUI = ("Same Property MH and RV portfolios Year Ended December 31, 2025 2024 Total Change % Change(2) MH(1) RV(1) Total Same Property Revenues Total Same Property operating revenues 928.4 520.1 1,448.5 866.1 519.9 1,386.0 "
       "Same Property operating expenses(1)(3) 241.5 243.3 484.8 235.2 239.0 474.2 Real Property NOI $ 686.9 $ 276.8 $ 963.7 $ 630.9 $ 280.9 $ 911.8 $ 51.9 8.9 % (1.4) % 5.7 % "
       "Increased Same Property adjusted blended occupancy for MH and RV by 40 basis points to 99.1% as compared to 98.7% in 2024.")


def test_the_segment_columns_of_a_same_property_noi_row_give_the_total_growth():
    g, quote, basis = KD.same_table(SUI)
    assert abs(g - (963.7 / 911.8 - 1) * 100) < 1e-3 and 5.6 < g < 5.8 and "686.9" in quote and "adds up" not in basis and "add up" in basis
    bad = SUI.replace("$ 963.7", "$ 999.9")                                           # the parts do not add up to the total: not read
    assert KD.same_table(bad) is None or "segments" not in KD.same_table(bad)[2]


def test_the_same_property_occupancy_sentence_is_read():
    rows = KD.occupancy_rows({2025: ("acc", SUI)})
    assert rows and rows[0][2] == 99.1 and rows[0][4] == "Same Property occupancy sentence"


def test_manufactured_housing_is_a_residential_asset_type():
    from src.pipeline import auto_config
    assert "manufactured housing" in auto_config.ASSET_WORDS["residential"]


def test_the_investment_grade_share_from_the_unrated_share_and_from_a_whole_portfolio_statement():
    knsl = ("Additionally, at December 31, 2025, approximately 81.9% of our fixed-maturity portfolio, excluding cash equivalents, was rated A- or better. Our policy is to invest in investment grade securities. "
            "At December 31, 2025, approximately 1.4% of our fixed-maturity portfolio, excluding cash equivalents, was unrated or rated below investment grade.")
    r = KD.ig_share_rows({2025: ("acc", knsl)})
    assert len(r) == 1 and abs(r[0][2] - 98.6) < 1e-9 and "unrated counted as not investment grade" in r[0][4]
    whole = "At year end all of our fixed maturities were rated A- or better by at least one rating agency."
    r = KD.ig_share_rows({2025: ("acc", whole)})
    assert len(r) == 1 and r[0][2] == 100.0 and "whole portfolio" in r[0][4]
    assert KD.ig_share_rows({2025: ("acc", "Most of our bonds were rated A- or better.")}) == []                      # "most" is not "all"


SUI22 = ("Real Property Operations - Same Property - MH and RV United States and Canada The following tables reflect certain financial and other information for our Same Property MH and RV portfolio. "
         "Total Same Property MH RV Year Ended Financial Information December 31, 2022 December 31, 2021 Change % Change(1) Revenue Total Operating 1,217.8 1,152.4 65.4 5.7 % "
         "Expense Property Operating 398.1 374.9 23.2 6.2 % Real Property NOI $ 819.7 $ 777.5 $ 42.2 5.4 % $ 558.2 $ 540.4 $ 17.8 3.3 % $ 261.5 $ 237.1 $ 24.4 10.3 %")
SUI24 = ("Same Property Expenses Same Property operating expenses(b)(d) 235.2 231.3 134.4 600.9 220.1 222.8 125.7 568.6 32.3 6.8 % 3.8 % 6.9 % 5.7 % "
         "Real Property NOI(d) $ 631.6 $ 272.4 $ 266.3 $ 1,170.3 $ 591.7 $ 280.4 $ 252.7 $ 1,124.8 $ 45.5 6.7 % (2.8) % 5.4 % 4.1 %")


def test_other_layouts_of_the_same_property_table_give_the_total_growth():
    g, quote, basis = KD.same_table(SUI22)                                             # the first block is the total, the change column agrees
    assert abs(g - (819.7 / 777.5 - 1) * 100) < 1e-3 and "819.7" in quote and "change column agrees" in basis
    g, quote, basis = KD.same_table(SUI24)                                             # four columns per year (MH, RV, Marina, Total) and a footnote mark after the label
    assert abs(g - (1170.3 / 1124.8 - 1) * 100) < 1e-3 and "3 segment columns add up" in basis
    wrong = SUI22.replace("$ 42.2", "$ 99.9")                                          # the change column does not agree: not read
    assert KD.same_table(wrong) is None


def test_only_a_timberland_or_farmland_reit_has_no_rent_roll_items():
    from src.scoring import realestate as RE
    from src.scoring.common import miss

    class Ri:
        def __init__(self, t):
            self.asset_type = t

    def fake(ri, d):
        return [miss("2", "Same-property NOI growth", 6, "not extracted"), miss("1", "Other", 4, "x")]

    wrapped = RE._op_na("b34")(fake)
    wt = wrapped(Ri("timberland"), {"flags": []})
    assert wt[0].state == "not_applicable" and "timberland" in wt[0].note and wt[1].state == "missing"             # only the listed item changes
    assert wrapped(Ri("diversified"), {"flags": ["operating_reit"]})[0].state == "missing"                         # hotels / senior-housing operations stay Missing
    assert wrapped(Ri("data centers"), {"flags": ["operating_reit"]})[0].state == "missing"
    from src.pipeline import auto_config as AC
    assert AC.reit_asset_type("We own timberlands. Our timber is harvested; timberland values rise.")[0] == "timberland" and AC.reit_utilization("timberland") == "not_applicable"


def test_operating_reit_wording_is_read():
    shop = "Same-store SHOP NOI grew 4.1% year over year. SHOP same-store occupancy was 83.4% at year end."
    r = KD.same_noi_rows({2025: ("acc", shop)})
    assert r and r[0][2] == 4.1 and "not derived" in r[0][4]
    assert KD.same_noi_rows({2025: ("acc", "Comparable hotel EBITDA decreased 2.0% compared to 2024.")})[0][2] == -2.0
    occ = KD.occupancy_rows({2025: ("acc", shop)})
    assert occ and occ[0][2] == 83.4 and occ[0][4] == "SHOP occupancy sentence"
    hotel = "Comparable hotels occupancy was 71.2% for the year."
    assert KD.occupancy_rows({2025: ("acc", hotel)})[0][2] == 71.2


def test_equity_method_investments_outside_the_total_are_left_out_of_the_sum():
    def row(k, v, basis=None):
        return {"item_key": k, "year": 2025, "value_full": v, "state": "value", "basis": basis}
    base = [row("inv_fixed_maturities", 17_797_986e3), row("inv_equity", 13_004_312e3), row("inv_short_term", 2_033_662e3), row("inv_total", 32_835_960e3)]
    mkl = base + [row("inv_equity_method", 737_600e3)]                        # MKL: the equity-method line is in other assets, not in Total Investments
    c = X.control_inv_sum(mkl)
    assert c["result"] == "pass" and ("inv_equity_method", 2025, 737_600e3) in [tuple(x) for x in c["rejected"]]
    afg = [row("inv_fixed_maturities", 80e9), row("inv_equity_method", 2.4e9), row("inv_total", 82.4e9)]       # AFG: the equity-method line belongs to the total: kept
    c2 = X.control_inv_sum(afg)
    assert c2["result"] == "pass" and c2["rejected"] == []


def test_the_pages_of_the_parent_company_alone_are_never_a_source():
    from src.ai import parent_only as PO
    cons = "CONSOLIDATED BALANCE SHEETS ASSETS Total Investments 32,835,960 Total assets 60,000,000 "
    ref = "See Schedule II included under Item 8 for condensed financial information of our holding company. "
    sched = ("SCHEDULE II CONDENSED FINANCIAL INFORMATION OF REGISTRANT PARENT COMPANY ONLY The following parent company only condensed financial information reflects the financial position. "
             "Condensed Balance Sheets ASSETS Investments in subsidiaries 23,313,057 Total Investments 4,100,000 Total assets 23,313,057 SCHEDULE III Supplementary Insurance Information Premiums 1")
    text = ref + cons + sched
    spans = PO.parent_spans(text)
    assert len(spans) == 1 and text[spans[0][0]:].startswith("SCHEDULE II CONDENSED")                      # the reference "See Schedule II" is not the schedule
    out = PO.remove(text)
    assert "23,313,057" not in out and "32,835,960" in out and "SCHEDULE III" in out
    assert PO.in_parent(text, "Total Investments 4,100,000") and not PO.in_parent(text, "Total Investments 32,835,960")
    assert PO.parent_spans("A bank without any such schedule. Total assets 1,000") == []


def fill_db():
    c = gap_db()
    for co in c.tables["companies"]:
        co["exchange"] = "US"
    c.tables["extraction_items"] = [{"id": 1, "company_id": 1, "item_key": "cet1_ratio_standardized", "period": "FY2025", "value": 7.0, "value_state": "value", "document_ref": "doc", "approval_status": "approved",
                                      "approval_source": "ai_controls", "model": "gemini"}]
    c.tables["data_gap_review"] = [{"id": 1, "company_id": 1, "item_key": "B 3.7.3", "family": "largest_tenant", "state": "open", "reason": "x", "priority": 3}]
    return c


def test_a_figure_entered_by_the_administrator_is_a_human_review_row_with_audit_and_the_gap_closes():
    from src.ai import gap_fill as GF
    c = fill_db()
    called = []

    def rescore(cid):
        called.append(cid)
        c.tables["score_details"] = [r for r in c.tables["score_details"] if not (r["run_id"] == 10 and r["criterion_key"] == "3.7")]      # the new score no longer lists the item

    out = GF.fill(c, "REXR", "cet1_ratio_standardized", 2025, 10.3, "Common Equity Tier 1 Capital Ratio 4.50 7.00 N/A 10.3", "https://example.org/10k", by="elad", rescore=rescore)
    rows = c.tables["extraction_items"]
    human = [r for r in rows if r.get("approval_source") == "human_review"]
    assert len(human) == 1 and human[0]["value"] == 10.3 and human[0]["period"] == "FY2025" and "Common Equity Tier 1" in human[0]["exact_quote"] and "elad" in human[0]["note"]
    old = next(r for r in rows if r["id"] == 1)
    assert old["approval_status"] == "rejected" and "replaced by a figure entered by elad" in old["note"] and out["rejected"] == 1      # one value is read for the item and the year
    log = c.tables["data_update_log"][-1]
    d = log["source_details"][0]
    assert log["update_scope"] == "gaps_fill" and d["who"] == "elad" and d["before"][0]["value"] == 7.0 and d["after"] == 10.3 and d["quote"] and d["source_url"] and d["when"]
    assert called == [1] and "B 3.7.3" in out["closed"] and next(r for r in c.tables["data_gap_review"] if r["item_key"] == "B 3.7.3")["state"] == "fixed"


def test_a_figure_without_a_quote_is_refused():
    import pytest
    from src.ai import gap_fill as GF
    with pytest.raises(ValueError):
        GF.fill(fill_db(), "REXR", "cet1_ratio_standardized", 2025, 10.3, "", by="elad")


def test_a_core_gap_is_an_alert_and_a_top_priority_row_and_a_suspect_figure_is_wrong_for_the_administrator():
    c = FakeClient()
    c.tables["companies"] = [{"id": 1, "symbol": "X", "exchange": "US", "profile": "STANDARD"}]
    c.tables["dictionary_items"] = [{"id": i, "item_key": k} for i, k in enumerate(["revenue", "net_income", "equity"], 1)]
    c.tables["financial_facts"] = [{"company_id": 1, "fiscal_year": 2025, "item_id": 1}, {"company_id": 1, "fiscal_year": 2025, "item_id": 2}]       # no equity, cfo ...
    alerts = []
    out = GR.record_core(c, 1, "STANDARD", alert=lambda label, reason, detail: alerts.append(reason))
    keys = {r["item_key"]: r for r in c.tables["data_gap_review"]}
    assert "CORE equity FY2025" in keys and keys["CORE equity FY2025"]["priority"] == 1 and keys["CORE equity FY2025"]["family"] == "core_missing" and out["new"] >= 1 and any("equity" in a for a in alerts)
    n = len(alerts)
    GR.record_core(c, 1, "STANDARD", alert=lambda *a: alerts.append(a))
    assert len(alerts) == n                                                                                    # the same gap alerts once
    GR.record_suspects(c, 1, [("suspect_magnitude", "held", 2023, "revenue", "50,000,000 against 5,000 and 6,000")])
    s = next(r for r in c.tables["data_gap_review"] if r["family"] == "suspect_data")
    assert s["priority"] == 1 and s["reason"].startswith("wrong (suspect_magnitude)") and s["item_key"] == "SUSPECT revenue FY2023"


def test_a_figure_far_from_both_neighbours_is_held_back_as_suspect():
    from src.etl.facts import Fact
    from src.pipeline import dq as D

    def f(y, v):
        return Fact("X", y, "revenue", v, "found", "xbrl", tag="Revenues")

    res: list = []
    out = D.check_suspect_magnitude([f(2022, 5e9), f(2023, 5e12), f(2024, 6e9), f(2025, 6.5e9)], res)
    assert [x.fiscal_year for x in out] == [2022, 2024, 2025] and res[0].check == "suspect_magnitude" and res[0].outcome == "held"
    res2: list = []
    assert len(D.check_suspect_magnitude([f(2022, 5e9), f(2023, 2e10), f(2024, 6e9)], res2)) == 3 and not res2                     # 4x is a normal swing
    assert len(D.check_suspect_magnitude([f(2022, 1e6), f(2023, 5e9)], [])) == 2                                                   # an edge year is not judged


VTR_TXT = ("See Non-GAAP Financial Measures-NOI for additional disclosure regarding same-store NOI for each of our reportable segments. "
           "Same-Store NOI-SHOP Resident fees and services $ 3,096,685 $ 2,861,461 $ 235,224 8.2 % Less: Property-level operating expenses (2,218,687) (2,100,930) (117,757) (5.6) NOI $ 877,998 $ 760,531 $ 117,467 15.4 % "
           "Same-Store NOI-OM&R Rental income $ 834,413 $ 812,667 $ 21,746 2.7 % Less: Property-level operating expenses (279,807) (270,216) (9,591) (3.5) NOI $ 554,606 $ 542,451 $ 12,155 2.2 % "
           "Same-Store NOI-NNN Rental income $ 482,055 $ 455,785 $ 26,270 5.8 % Less: Property-level operating expenses (11,801) (11,463) (338) (2.9) NOI $ 470,254 $ 444,322 $ 25,932 5.8 %")


def test_same_store_noi_of_the_segments_is_summed_when_the_report_says_it_gives_it_for_each_segment():
    r = KD.same_noi_rows({2025: ("acc", VTR_TXT)})
    assert len(r) == 1 and abs(r[0][2] - ((877998 + 554606 + 470254) / (760531 + 542451 + 444322) - 1) * 100) < 1e-4 and 8.8 < r[0][2] < 9.0       # +8.9%
    assert "SHOP" in r[0][3] and "OM&R" in r[0][3] and "NNN" in r[0][3] and "877,998" in r[0][3] and "sum of the same-store NOI of the reportable segments" in r[0][4]
    no_def = VTR_TXT.replace("for each of our reportable segments", "for our company")              # without the statement that the segments are the whole pool: not summed
    assert KD.same_noi_rows({2025: ("acc", no_def)}) == []
    one = VTR_TXT[:VTR_TXT.index("Same-Store NOI-OM&R")]                                                # a single segment is not the pool
    assert KD.same_noi_rows({2025: ("acc", one)}) == []

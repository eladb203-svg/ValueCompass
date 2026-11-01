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
    assert blocks["EXT-RE-OPS"]["version"] >= 2 and blocks["EXT-INS-INV"]["version"] >= 6                      # a changed prompt is a new version: stored answers of the old text are asked again


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

"""K6d-2 fixes: a quote with zero-width spaces between table cells is found; a debt maturity of the next years is stored for the report year."""
from src.ai.checks import normalize
from src.ai.ext_checks import check_item

KEYS = {"debt_maturity_year1": "USD", "debt_maturity_year2": "USD"}


def item(key, period, value, quote):
    return {"item_key": key, "value_state": "value", "value": value, "unit": "USD", "scale": 1000, "period": period, "quote": {"text": quote, "section": "s"}}


def test_zero_width_spaces_between_cells_do_not_hide_a_quote():
    text = normalize("2026 ​ $ ​ — ​ $ 440,475 ​ $ 346,918 ​ $ 117,290 ​ $ 904,683 ​ 2027")
    r = check_item(item("debt_maturity_year1", "2026", 904683, "2026 $ — $ 440,475 $ 346,918 $ 117,290 $ 904,683"), KEYS, text, 2025)
    assert "quote_not_found" not in r.reasons and r.year == 2025


def test_the_maturity_year_after_the_report_is_not_a_period_mismatch():
    text = normalize("2026 $ 676,000 $ 299,516 $ — $ 975,516 2027 — 598,907 — 598,907")
    r1 = check_item(item("debt_maturity_year1", "FY2026", 975516, "2026 $ 676,000 $ 299,516 $ — $ 975,516"), KEYS, text, 2025)
    r2 = check_item(item("debt_maturity_year2", "FY2027", 598907, "2027 — 598,907 — 598,907"), KEYS, text, 2025)
    assert r1.ok and r1.year == 2025 and r2.ok and r2.year == 2025
    r3 = check_item(item("debt_maturity_year1", "FY2029", 975516, "2026 $ 676,000 $ 299,516 $ — $ 975,516"), KEYS, text, 2025)      # a wrong year still fails
    assert "period_mismatch" in r3.reasons


def test_a_sentence_with_a_date_and_an_amount_keeps_the_year_the_model_gave():
    from src.ai.ext_norm import assign_year
    q = "At December 31, 2025, approximately $3.3 billion was available under this facility, net of outstanding letters of credit."
    text = normalize("x " + q + " y")
    year, how, _ = assign_year({"item_key": "committed_undrawn_facilities"}, 3.3, 1000000000, "USD", q, text, 2025, 2025)
    assert year is None and how == "unresolved"                      # not "column_order" (which gave 2023)


def _inv(key, year, val, basis=""):
    return {"item_key": key, "year": year, "value_full": float(val), "basis": basis, "state": "value"}


def test_inv_sum_uses_the_duplicate_that_matches_and_a_total_that_includes_cash():
    from src.ai.ext_checks import control_inv_sum
    rows = [_inv("inv_total", 2025, 17182, "INCLUDES_CASH"), _inv("inv_cash", 2025, 1727), _inv("inv_fixed_maturities", 2025, 11052), _inv("inv_equity", 2025, 785),
            _inv("inv_illiquid_loans", 2025, 947), _inv("inv_illiquid_loans", 2025, 791), _inv("inv_real_estate", 2025, 1431), _inv("inv_other", 2025, 990)]
    c = control_inv_sum(rows)
    assert c["result"] == "pass" and ("inv_illiquid_loans", 2025, 791.0) in c["rejected"] and ("inv_illiquid_loans", 2025, 947.0) not in c["rejected"]


def test_inv_sum_total_without_cash_and_a_real_mismatch():
    from src.ai.ext_checks import control_inv_sum
    ok = [_inv("inv_total", 2025, 1500), _inv("inv_cash", 2025, 100), _inv("inv_fixed_maturities", 2025, 1000), _inv("inv_equity", 2025, 500)]
    assert control_inv_sum(ok)["result"] == "pass"                      # the total has no cash: cash is left out of the sum
    bad = [_inv("inv_total", 2025, 3000), _inv("inv_fixed_maturities", 2025, 1000), _inv("inv_equity", 2025, 500)]
    assert control_inv_sum(bad)["result"] == "fail"


def test_a_number_that_is_part_of_the_label_is_not_a_column():
    from src.ai.ext_norm import assign_year, data_tokens
    q = "Common equity tier 1 | $ | 7,003 | | | $ | 6,311"
    label, toks = data_tokens(normalize(q))
    assert label.lower().startswith("common equity tier 1") and [t[0].lstrip("$ ") for t in toks] == ["7,003", "6,311"]
    text = normalize("x " + q + " y")
    y1, how1, _ = assign_year({"item_key": "cet1_capital"}, 7003, 1000000, "USD", q, text, 2025, 2025)
    y2, how2, _ = assign_year({"item_key": "cet1_capital"}, 6311, 1000000, "USD", q, text, 2025, 2024)
    assert (y1, y2) == (2025, 2024)


def test_a_quote_that_is_only_the_cell_is_extended_to_the_row_when_it_occurs_once():
    text = normalize("Long-Term Debt: Principal (1) $ 881.7 $ 1,176.5 $ 636.8 $ 238.6 Interest (2) $ 321.3 $ 258.7")
    it = item("debt_maturity_year1", "FY2026", 881.7, "$881.7")
    it["scale"] = 1000000
    r = check_item(it, KEYS, text, 2025)
    assert "quote_not_found" not in r.reasons and "quote_extended_to_the_row" in r.flags and "Principal" in it["quote"]["text"] and "881.7" in it["quote"]["text"]
    twice = normalize("a $ 881.7 and again $ 881.7 here")
    it2 = item("debt_maturity_year1", "FY2026", 881.7, "$881.7")
    it2["scale"] = 1000000
    assert "quote_not_found" in check_item(it2, KEYS, twice, 2025).reasons               # ambiguous: stays rejected


def test_equity_method_investments_are_a_category_of_the_inv_sum_control():
    from src.ai.ext_checks import control_inv_sum
    rows = [_inv("inv_total", 2025, 17182, "INCLUDES_CASH"), _inv("inv_cash", 2025, 1727), _inv("inv_fixed_maturities", 2025, 11052), _inv("inv_equity", 2025, 785),
            _inv("inv_illiquid_loans", 2025, 947), _inv("inv_real_estate", 2025, 159), _inv("inv_equity_method", 2025, 2421), _inv("inv_other", 2025, 91)]
    assert control_inv_sum(rows)["result"] == "pass"                       # 1727 + 11052 + 785 + 947 + 159 + 2421 + 91 = 17182
    assert control_inv_sum([r for r in rows if r["item_key"] != "inv_equity_method"])["result"] == "fail"

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

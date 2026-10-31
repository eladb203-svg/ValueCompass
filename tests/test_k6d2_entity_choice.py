"""K6d-2 fixes: a capital table with the group and its subsidiary bank gives the group's value (CFG 9.0 required / 10.6 ratio, not CBNA 7.0 / 12.3)."""
from src.scoring.ext_items import to_reg


def row(key, val, basis, ticker="CFG", year=2025):
    return {"item_key": key, "year": year, "value_full": val, "unit": "percent", "quote": "q", "section": "s", "basis": basis, "accession": "a", "ticker": ticker}


def test_the_group_wins_whatever_the_order_of_the_rows():
    g = row("cet1_required_standardized", 9.0, "CFG, U.S. Basel III Standardized rules")
    s = row("cet1_required_standardized", 7.0, "CBNA, U.S. Basel III Standardized rules")
    for rows in ([g, s], [s, g]):
        assert to_reg("bank", rows, 2025)["cet1_required_standardized"]["value"] == 9.0


def test_without_a_ticker_match_the_first_entity_listed_stays():
    a = row("cet1_ratio_standardized", 10.6, "Citizens Financial Group, Inc.")
    b = row("cet1_ratio_standardized", 12.3, "Citizens Bank, N.A.")
    assert to_reg("bank", [a, b], 2025)["cet1_ratio_standardized"]["value"] == 10.6


def test_two_rows_of_the_same_entity_keep_the_later_one():
    a = row("scb", 4.0, "CFG")
    b = row("scb", 4.5, "CFG")
    assert to_reg("bank", [a, b], 2025)["scb"]["value"] == 4.5

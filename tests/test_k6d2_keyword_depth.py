"""K6d-2 fixes: the REIT depth items by keyword search (occupancy over the years, same-property NOI growth, unencumbered assets share)."""
from src.ai import keyword_depth as KD
from src.ai.checks import normalize


def T(by_year):
    return {int(y): (f"acc-{y}", normalize(t)) for y, t in by_year.items()}


def test_occupancy_uses_one_pattern_for_all_years_the_one_that_matches_the_latest_report():
    texts = {2025: ("a25", normalize("Our average occupancy for our same-store pool for 2025 was 93.7%. About 99% leased elsewhere.")),
             2024: ("a24", normalize("Our average occupancy for our same-store pool for 2024 was 93.4%.")),
             2023: ("a23", normalize("the portfolio was approximately 91.0% leased"))}          # another wording: no match with the pattern of the latest report, not forced
    rows = KD.occupancy_rows(texts)
    assert [(y, v) for y, _, v, _, _ in rows] == [(2024, 93.4), (2025, 93.7)]


def test_occupancy_patterns_of_the_known_wordings():
    assert KD.occupancy_rows(T({"2025": "our portfolio was approximately 84.7% leased"}))[0][2] == 84.7
    assert KD.occupancy_rows(T({"2025": "As of December 31, 2025, our properties are 100% leased with a lease term"}))[0][2] == 100.0
    assert KD.occupancy_rows(T({"2025": "Same Store 278 96,568 95.6 % $ 1,690"}))[0][2] == 95.6


def test_same_property_noi_growth_is_current_over_prior_from_both_levels_in_one_quote():
    t = T({"2025": "Total same-store net operating income $ 1,884,797 $ 1,917,206 Comparison of the Year", "2024": "Same Store NOI $ 1,304,264 $ 1,322,186 $ 1,339,810 Total NOI"})
    rows = {y: (v, q) for y, _, v, q, _ in KD.same_noi_rows(t)}
    assert rows[2025][0] == round((1884797 / 1917206 - 1) * 100, 4) and "1,884,797" in rows[2025][1] and "1,917,206" in rows[2025][1]
    assert round(rows[2024][0], 2) == round((1304264 / 1322186 - 1) * 100, 2)


def test_unencumbered_assets_share_from_the_two_values_of_the_bond_definition():
    t = T({"2025": "Our unencumbered asset value was calculated as $30,247,545 and our total asset value was calculated as $35,894,312 according to the calculations"})
    (y, acc, v, q, b), = KD.unencumbered_rows(t)
    assert y == 2025 and round(v, 1) == 84.3 and "30,247,545" in q


def test_rows_leave_a_model_value_alone_and_replace_nothing_when_unencumbered_exists():
    t = T({"2025": "Our unencumbered asset value was $30 and total asset value was $36. approximately 84.7% leased", "2024": "approximately 83.0% leased"})
    rows = KD.build_rows("TST", t, have_unenc_value=True, have_same_noi_years=set(), have_occupancy_years={2025})
    assert [(r["item_key"], r["year"]) for r in rows] == [("occupancy", 2024)]
    assert rows[0]["approval_status"] == "approved" and rows[0]["model"] == "keyword-search" and rows[0]["unit"] == "percent"


def test_investment_grade_share_from_the_sentence_forms_of_three_insurers():
    sigi = T({2025: "Non-investment grade exposure represented approximately 3% of the total fixed income and short-term investments at both dates"})
    thg = T({2025: "approximately 95% of our fixed maturity portfolio consisted of investment-grade securities at December 31, 2025"})
    afg = T({2025: "Approximately 96% of the fixed maturities held by AFG at December 31, 2025, were rated investment grade (credit rating of AAA to BBB)"})
    assert KD.ig_share_rows(sigi)[0][2] == 97.0 and "complement" in KD.ig_share_rows(sigi)[0][4] or "100 -" in KD.ig_share_rows(sigi)[0][4]
    assert KD.ig_share_rows(thg)[0][2] == 95.0
    assert KD.ig_share_rows(afg)[0][2] == 96.0

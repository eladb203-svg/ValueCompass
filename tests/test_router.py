"""Code stage K4b: the profile router (Part B / B.1) - every row, every classification tier, S3a, undetermined, stability, override."""
import pytest

from src.scoring import router as R
from src.scoring.router import AIAnswer, Override, RouterData, route, stability

T = R.default_tables()
YEARS = [f"FY{y}" for y in range(2021, 2026)]


def data(sic, provider=None, per_year=None, **common):
    vals = {}
    for fy in YEARS:
        v = dict(common)
        v.update((per_year or {}).get(fy, {}))
        vals[fy] = v
    return RouterData("TST", YEARS, vals, None if sic is None else str(sic), None, provider)


def prof(d, **kw):
    return route(d, T, **kw)


# ------------------------------------------------------------------ tier 1: SIC table
@pytest.mark.parametrize("sic,industry", [(6021, "Banks"), (6036, "Banks"), (6082, "Banks"), (6211, "Investment banks and brokers"), (6141, "Consumer and commercial credit"),
                                           (6331, "Insurance carriers"), (6324, "Managed health insurance"), (6411, "Insurance brokers and services"),
                                           (6510, "Property REITs and income real estate"), (6531, "Other"), (6552, "Homebuilders and developers"),
                                           (1531, "Homebuilders and developers"), (6282, "Asset managers"), (6726, "BDCs and credit funds"),
                                           (6770, "SPACs and asset-backed issuers"), (6189, "SPACs and asset-backed issuers"), (7372, "Software"),
                                           (7374, "IT services"), (3571, "Hardware"), (3674, "Semiconductors"), (3663, "Communications equipment"),
                                           (3672, "Electronic components"), (3678, "Electronic components"), (2080, "Other")])
def test_tier1_sic_maps_to_one_industry(sic, industry):
    c = R.classify(data(sic), T)
    assert c.industry == industry and c.status == "decided"


def test_tier1_sic_decides_over_the_provider_but_notes_the_difference():
    c = R.classify(data(6331, "Banks - Regional"), T)
    assert c.industry == "Insurance carriers" and c.tier == "sic" and any("cross-check" in r for r in c.reasons)


# ------------------------------------------------------------------ tier 2: provider industry for multi / Other
def test_tier2_multi_sic_decided_by_the_provider_industry():
    assert R.classify(data(7389, "Software - Application"), T).industry == "Software"
    assert R.classify(data(7389, "Credit Services"), T).industry == "Payments"
    assert R.classify(data(6200, "Capital Markets"), T).industry == "Investment banks and brokers"   # the provider says broker (allowed for 6200)
    assert R.classify(data(6200, "Software - Application"), T).industry == "Exchanges and data"      # not allowed for 6200 -> the default
    assert R.classify(data(6200, None), T).industry == "Exchanges and data"          # default of 6200
    assert R.classify(data(7370, "Internet Content & Information"), T).industry == "Internet platforms and advertising"
    assert R.classify(data(3559, "Semiconductor Equipment & Materials"), T).industry == "Semiconductor equipment"


def test_tier2_runs_for_a_sic_that_maps_to_other_only_when_the_provider_industry_is_a_candidate():
    assert R.classify(data(5961, "Software - Application"), T).industry == "Software"
    c = R.classify(data(5961, "Internet Retail"), T)           # online retail with own inventory: not an internet platform
    assert c.industry == "Other" and c.status == "decided"
    assert R.classify(data(2080, "Beverages - Non-Alcoholic"), T).industry == "Other"


def test_tier2_provider_decision_tier3_marks_classification_pending_until_ai_decides():
    c = R.classify(data(7011, "Travel Services"), T)
    assert c.industry == "Other" and c.status == "classification_pending"
    r = prof(data(7011, "Travel Services"))
    assert r.profile == "STANDARD" and "classification_pending" in r.flags


# ------------------------------------------------------------------ tier 3: interface only
def test_tier3_ai_answer_agreeing_with_tier2_or_approved_decides_a_disagreement_needs_approval():
    d = data(7389, None)                                                   # multi, no provider industry
    assert R.classify(d, T).status == "classification_pending"
    assert R.classify(d, T, ai=AIAnswer("Payments", "quote", approved=True)).industry == "Payments"
    d2 = data(7389, "Software - Application")
    assert R.classify(d2, T, ai=AIAnswer("Software")).industry == "Software"
    c = R.classify(d2, T, ai=AIAnswer("Payments"))
    assert c.status == "classification_pending" and "admin approval" in " ".join(c.reasons)


def test_no_sic_and_no_provider_is_pending_and_standard():
    r = prof(data(None, None))
    assert r.profile == "STANDARD" and r.classification.status == "classification_pending"


# ------------------------------------------------------------------ rows 1a / 1b
BANK = dict(assets=1000.0, liabilities=900.0, deposits=600.0, loans=400.0)


def test_row_1a_passes_with_deposits_and_loans_shares():
    r = prof(data(6021, **BANK))
    assert r.profile == "BANK" and r.per_year["FY2025"]["row"] == "1a"


def test_row_1a_fails_then_1b_decides_bank_with_cet1_and_lcr_else_unsupported():
    low = dict(BANK, loans=200.0)
    assert prof(data(6021, **low, reports_cet1=True, reports_lcr=True)).per_year["FY2025"]["row"] == "1b"
    assert prof(data(6021, **low, reports_cet1=True, reports_lcr=True)).profile == "BANK"
    assert prof(data(6021, **low)).profile == "UNSUPPORTED"
    assert prof(data(6141, **low)).profile == "UNSUPPORTED"                          # consumer and commercial credit not passing 1b
    assert prof(data(6141, **low, reports_cet1=True, reports_lcr=True)).profile == "BANK"


def test_row_1b_investment_bank_or_broker_is_bank_only_with_cet1_and_lcr_else_standard():
    assert prof(data(6211, **BANK, reports_cet1=True, reports_lcr=True)).profile == "BANK"
    assert prof(data(6211, **BANK)).profile == "STANDARD"


def test_bank_liabilities_fall_back_to_assets_minus_equity_and_missing_inputs_are_undetermined():
    v = dict(assets=1000.0, equity=100.0, deposits=600.0, loans=400.0)
    t = prof(data(6021, **v))
    assert t.profile == "BANK" and any("assets - equity" in n for n in t.per_year["FY2025"]["notes"])
    u = prof(data(6021, assets=1000.0, equity=100.0, deposits=600.0))      # no loans
    assert u.per_year["FY2025"]["profile"] is None and "profile_undetermined_standard_default" in u.flags


def test_bank_path_wrapper_keeps_the_legacy_shape():
    p = R.bank_path("6021", 600.0, 900.0, 400.0, 1000.0, True, True)
    assert p["path"] == "1" and p["industry_is_banks"] and p["deposits_to_liabilities"] == pytest.approx(600 / 900)
    assert R.bank_path("6211", 100.0, 900.0, 100.0, 1000.0, True, True)["path"] == "1b"
    assert R.bank_path("6211", 100.0, 900.0, 100.0, 1000.0, False, True)["path"] is None


# ------------------------------------------------------------------ row 2
def ins(claims, other=0.0, liab=100.0):
    return dict(claims_gross=claims, unearned=other, liabilities=liab)


def test_row_2_pass_fail_and_undetermined():
    assert prof(data(6331, **ins(60.0))).profile == "INSURANCE"
    assert prof(data(6324, **ins(10.0))).profile == "STANDARD"                       # managed care fails the test
    r = prof(data(6331, claims_gross=None, unearned=20.0, liabilities=100.0))          # claims missing: undetermined, not a failure
    assert r.per_year["FY2025"]["profile"] is None
    assert prof(data(6331, claims_gross=None, unearned=60.0, liabilities=100.0)).profile == "INSURANCE"   # other components reach 50% on their own


def test_row_2_insurance_brokers_guard_and_fail_to_standard():
    assert prof(data(6411, **ins(5.0))).profile == "STANDARD"
    assert prof(data(6411, **ins(70.0))).profile == "INSURANCE"                       # a misclassified carrier passes the guard


# ------------------------------------------------------------------ row 3 and the mortgage REIT split
PROP = dict(assets=1000.0, re_net=800.0, rental_revenue=90.0, revenue=100.0)


def test_row_3_pass_fail_undetermined_and_extracted_fallback():
    assert prof(data(6510, **PROP)).profile == "INCOME_REAL_ESTATE"
    assert prof(data(6510, **dict(PROP, rental_revenue=30.0))).profile == "STANDARD"
    assert prof(data(6510, assets=1000.0, rental_revenue=90.0, revenue=100.0)).per_year["FY2025"]["profile"] is None
    r = prof(data(6510, x_assets=1000.0, x_prop=800.0, x_rent=90.0, x_total=100.0))
    assert r.profile == "INCOME_REAL_ESTATE"


def test_row_3_acquired_lease_intangibles_count_re15():
    r = prof(data(6510, assets=1000.0, re_net=450.0, intangibles_net=100.0, rental_revenue=90.0, revenue=100.0))
    assert r.profile == "INCOME_REAL_ESTATE"


@pytest.mark.parametrize("extra,expected", [
    (dict(interest_income=80.0, revenue=100.0, mortgage_assets=100.0), "Mortgage REITs"),              # interest share
    (dict(interest_income=10.0, revenue=100.0, mortgage_assets=600.0), "Mortgage REITs"),              # mortgage-asset share
    (dict(interest_income=10.0, revenue=100.0, mortgage_assets=100.0), "Property REITs and income real estate"),
    (dict(re_net=800.0, interest_income=80.0, revenue=100.0, mortgage_assets=100.0), "Property REITs and income real estate"),   # investment property >= 50%
])
def test_sic_6798_numeric_split(extra, expected):
    d = data(6798, assets=1000.0, **extra)
    assert R.classify(d, T).industry == expected


def test_sic_6798_undetermined_numbers_fall_back_to_the_provider_then_to_property():
    d = data(6798, "REIT - Mortgage", assets=1000.0, mortgage_assets=100.0)       # interest share cannot be computed
    c = R.classify(d, T)
    assert c.industry == "Mortgage REITs" and c.tier == "provider"
    assert R.classify(data(6798, "REIT - Retail", assets=1000.0, mortgage_assets=100.0), T).industry == "Property REITs and income real estate"
    assert prof(data(6798, "REIT - Mortgage", assets=1000.0)).profile == "UNSUPPORTED"


def test_mortgage_reit_test_cases():
    assert R.mortgage_reit_test(1000.0, None, 600.0, 1000.0, None).result == "pass"     # absent property line = 0 (C5)
    assert R.mortgage_reit_test(1000.0, 600.0, 600.0, 1000.0, None).result == "fail"
    assert R.mortgage_reit_test(None, None, None, None, None).result == "undetermined"


# ------------------------------------------------------------------ row 4: BDCs, SPACs
def test_bdc_identification_by_sic_or_nav_and_fair_value_share():
    assert prof(data(6726)).profile == "UNSUPPORTED"
    r = prof(data(None, "Asset Management", assets=1000.0, nav_per_share=18.0, investments_fair_value=900.0))
    assert r.industry == "BDCs and credit funds" and r.profile == "UNSUPPORTED"
    assert R.classify(data(None, "Asset Management", assets=1000.0, nav_per_share=18.0, investments_fair_value=300.0), T).industry == "Asset managers"
    assert R.classify(data(None, "Asset Management", assets=1000.0, investments_fair_value=900.0), T).industry == "Asset managers"   # no NAV per share
    assert prof(data(6770)).profile == "UNSUPPORTED" and prof(data(6189)).profile == "UNSUPPORTED"


# ------------------------------------------------------------------ rows 5a / 5b
def test_row_5a_needs_no_test():
    for sic in (7372, 7374):
        assert prof(data(sic)).profile == "TECH_ASSET_LIGHT"
    assert prof(data(7389, "Software - Application")).profile == "TECH_ASSET_LIGHT"


def tech(rd, gm, years=5):
    return {fy: dict(revenue=100.0, rd=rd, gross_profit=gm) for fy in YEARS[-years:]}


def test_row_5b_pass_fail_and_both_tests_must_pass():
    assert prof(data(3674, per_year=tech(15.0, 60.0))).profile == "TECH_ASSET_LIGHT"
    assert prof(data(3674, per_year=tech(15.0, 40.0))).profile == "STANDARD"
    assert prof(data(3674, per_year=tech(5.0, 60.0))).profile == "STANDARD"


def test_row_5b_gross_profit_may_be_derived_and_missing_inputs_are_undetermined():
    py = {fy: dict(revenue=100.0, rd=15.0, cost_of_revenue=30.0) for fy in YEARS}
    r = prof(data(3674, per_year=py))
    assert r.profile == "TECH_ASSET_LIGHT" and any("derived" in n for n in r.per_year["FY2025"]["notes"])
    u = prof(data(3674, per_year={fy: dict(revenue=100.0, gross_profit=60.0) for fy in YEARS}))      # no R&D at all
    assert u.per_year["FY2025"]["profile"] is None and "profile_undetermined_standard_default" in u.flags


def test_row_5b_uses_five_year_medians():
    py = {fy: dict(revenue=100.0, rd=15.0, gross_profit=60.0) for fy in YEARS}
    py["FY2025"] = dict(revenue=100.0, rd=15.0, gross_profit=10.0)          # one bad year does not move the median
    assert prof(data(3674, per_year=py)).per_year["FY2025"]["profile"] == "TECH_ASSET_LIGHT"


# ------------------------------------------------------------------ row 6
def test_row_6_everything_else_is_standard():
    for sic in (2080, 6282, 6200, 1531, 6531):
        assert prof(data(sic)).profile == "STANDARD"


# ------------------------------------------------------------------ S3a
def test_s3a_borderline_within_5pp_of_the_threshold():
    near = prof(data(6021, assets=1000.0, liabilities=900.0, deposits=600.0, loans=320.0))      # loans / assets 32% (30% +- 5pp)
    assert near.borderline and "loans_to_assets" in near.borderline_tests
    assert not prof(data(6021, **BANK)).borderline
    assert prof(data(3674, per_year=tech(12.0, 60.0))).borderline          # R&D 12% is within 5pp of 10% (both 5b tests count)


# ------------------------------------------------------------------ stability and "undetermined"
def test_stability_changes_only_after_two_consecutive_different_years():
    eff, since, pend = stability([("FY1", "T"), ("FY2", "T"), ("FY3", "S")])
    assert (eff, pend) == ("T", "S")
    assert stability([("FY1", "T"), ("FY2", "T"), ("FY3", "S"), ("FY4", "S")]) == ("S", "FY3", None)
    assert stability([("FY1", "T"), ("FY2", "S"), ("FY3", "T"), ("FY4", "S")])[0] == "T"          # alternating never switches
    assert stability([("FY1", "T"), ("FY2", "S"), ("FY3", "B"), ("FY4", "B")])[0] == "B"


def test_undetermined_year_is_neither_a_different_result_nor_a_break():
    assert stability([("FY1", "T"), ("FY2", None), ("FY3", "T")])[0] == "T"
    assert stability([("FY1", "T"), ("FY2", "S"), ("FY3", None), ("FY4", "S")])[0] == "S"        # the gap does not break the S, S sequence
    assert stability([("FY1", None), ("FY2", None), ("FY3", "I")])[0] == "I"
    assert stability([("FY1", None)]) == (None, None, None)


def test_previous_profile_seeds_the_sequence():
    assert stability([("FY1", "S"), ("FY2", "S")], previous_profile="T")[0] == "S"
    assert stability([("FY1", "S")], previous_profile="T") == ("T", None, "S")


def test_route_applies_stability_over_the_window():
    py = {fy: dict(revenue=100.0, rd=15.0, gross_profit=60.0) for fy in YEARS[:2]}
    py.update({fy: dict(revenue=100.0, rd=15.0, gross_profit=20.0) for fy in YEARS[2:]})
    r = prof(data(3674, per_year=py))
    seq = [r.per_year[fy]["profile"] for fy in YEARS]
    assert seq == [None, None, "TECH_ASSET_LIGHT", "STANDARD", "STANDARD"]        # medians need 3 years; the 5-year median turns in FY2024
    assert r.profile == "STANDARD" and r.since == "FY2024" and r.pending_change is None


# ------------------------------------------------------------------ manual override (P1)
def test_override_needs_a_reason_and_shows_the_computed_profile():
    with pytest.raises(ValueError):
        Override(reason=" ", profile="STANDARD")
    with pytest.raises(ValueError):
        Override(reason="x")
    ov = Override(reason="holding company, not a bank", set_by="admin", profile="STANDARD")
    r = prof(data(6021, **BANK), override=ov)
    assert r.profile == "STANDARD" and r.computed_profile == "BANK" and r.override_applied["reason"] == "holding company, not a bank"


def test_industry_override_replaces_the_classification_with_a_stored_reason():
    r = prof(data(7389, "Credit Services"), override=Override(reason="platform, not a payments company", industry="Internet platforms and advertising"))
    assert r.industry == "Internet platforms and advertising" and r.profile == "TECH_ASSET_LIGHT" and r.classification.tier == "override"


# ------------------------------------------------------------------ data tables
def test_tables_are_data_and_cover_every_industry_of_part_b():
    used = {r.industry for r in T.sic_rules if r.industry} | {i for r in T.sic_rules for i in r.allowed if i != "*"} | {v[0] for v in T.provider.values()}
    assert used <= set(R.INDUSTRIES)
    assert {r.profile for r in R.ROWS} == {"BANK", "INSURANCE", "INCOME_REAL_ESTATE", "UNSUPPORTED", "TECH_ASSET_LIGHT", "STANDARD"}
    assert [r.order for r in R.ROWS] == ["1a", "1b", "2", "3", "4", "5a", "5b", "6"]


def test_property_test_single_implementation():
    out = R.property_test(1000.0, 800.0, 90.0, 100.0, None)
    assert out["confirmed"] is True and out["assignment"] == "INCOME_REAL_ESTATE"
    assert R.property_test(None, None, None, None, None)["assignment"] == "undetermined"

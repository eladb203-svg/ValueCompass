"""Calibration decisions of 2026-11-05: the acquisition break of the 10-year growth window, the REIT-only prompt version, the debt-type-axis debt total."""
from src.ai import assess
from src.ai.prompt import scoring_skills
from src.scoring import breaks, metrics


def _facts(acq, stk, eq, ni_ends):
    def node(vals, instant):
        rows = []
        for end, v in vals.items():
            r = {"end": end, "val": v, "form": "10-K", "filed": end[:4] + "-12-31"}
            if not instant:
                r["start"] = str(int(end[:4]) - 1) + end[4:]
            rows.append(r)
        return {"units": {"USD": rows}}
    g = {"PaymentsToAcquireBusinessesNetOfCashAcquired": node(acq, False), "StockIssuedDuringPeriodValueAcquisitions": node(stk, False),
         "StockholdersEquity": node(eq, True), "NetIncomeLoss": node({e: 1.0 for e in ni_ends}, False)}
    return {"facts": {"us-gaap": g}}


def test_a_break_is_acquisitions_of_at_least_40_percent_of_the_opening_equity_and_the_latest_one_counts():
    f = _facts({"2019-12-31": 100.0, "2022-12-31": 30.0}, {"2019-12-31": 50.0}, {"2018-12-31": 300.0, "2019-12-31": 400.0, "2021-12-31": 500.0}, ["2024-12-31", "2025-12-31"])
    assert breaks.acquisition_break(f)[:2] == (2019, 2025)            # 150 / 300 = 50% in 2019; 30 / equity of 2021 (the previous year end 2021) = 6% in 2022 is no break
    assert breaks.acquisition_break(f, 0.60) is None
    assert breaks.acquisition_break(_facts({}, {}, {}, ["2025-12-31"])) is None


def test_the_growth_window_after_a_break_has_the_years_after_it_and_falls_back_when_fewer_than_five():
    series = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]
    assert metrics.growth10(series)["window_years"] == 10
    with breaks.scoring_window(6):
        assert metrics.growth10(series)["window_years"] == 6
    with breaks.scoring_window(4):                                       # fewer than 5 years after the break: insufficient, so the callers use the 5-year window
        assert metrics.growth10(series)["kind"] == "insufficient"
    assert breaks.years_after() is None


def test_a_reit_has_its_own_prompt_version_for_the_reworded_questions_and_the_other_profiles_keep_theirs():
    sk = scoring_skills()
    for q in ("B3.2-Q4", "B3.2-Q5", "B3.7-Q5", "B3.8-Q6"):
        assert assess.prompt_version_of(sk[q], "3.1", "INCOME_REAL_ESTATE").endswith("-reit.1")
        assert assess.prompt_version_of(sk[q], "3.1", "BANK") == assess.prompt_version_of(sk[q], "3.1") and "reit" not in assess.prompt_version_of(sk[q], "3.1", "BANK")
        assert "REPLACE the scale above" in sk[q]["profile_notes"]["INCOME_REAL_ESTATE"]

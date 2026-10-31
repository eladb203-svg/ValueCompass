"""K6d-2 fixes: a filer with no gross interest-expense tag but a net interest line (NKE) gets interest expense and EBIT derived, with the right sign, marked derived."""
from datetime import date

from src.providers import sec_companyfacts as SC


def fact(end_year, val, fy_start_month=6):
    return {"start": f"{end_year - 1}-06-01", "end": f"{end_year}-05-31", "val": val, "fy": end_year, "fp": "FY", "form": "10-K", "filed": f"{end_year}-07-20", "accn": f"a{end_year}"}


class FakeSec:
    def __init__(self, net_interest):
        years = range(2020, 2026)
        us = {"NetIncomeLoss": [fact(y, 100.0) for y in years],
              "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": [fact(y, 130.0) for y in years],
              "Revenues": [fact(y, 1000.0) for y in years]}
        if net_interest is not None:
            us["InterestIncomeExpenseNonoperatingNet"] = [fact(y, net_interest) for y in years]
        self.facts = {"facts": {"us-gaap": {k: {"units": {"USD": v}} for k, v in us.items()}}}

    def cik_for(self, t):
        return "0000000001", "TEST"

    def companyfacts(self, cik):
        return self.facts

    def first_annual_report(self, cik):
        return date(2010, 1, 1)


def build(net_interest):
    return SC.build_inputs(FakeSec(net_interest), "TST", "STANDARD", [], 5)


def test_net_interest_income_gives_a_non_positive_interest_expense_and_ebit_below_pretax():
    r = build(+20.0)                                              # the company earned 20 net interest: interest expense = -20, EBIT = 130 - 20 = 110
    assert r["f"]["interest_expense"][-1] == -20.0 and r["f"]["ebit"][-1] == 110.0
    assert r["tag_log"]["interest_expense"][r["labels"][-1]]["tag"].startswith("DERIVED")
    assert r["tag_log"]["ebit"][r["labels"][-1]]["tag"].startswith("DERIVED")


def test_net_interest_expense_gives_a_positive_interest_expense_and_ebit_above_pretax():
    r = build(-30.0)
    assert r["f"]["interest_expense"][-1] == 30.0 and r["f"]["ebit"][-1] == 160.0


def test_a_gross_interest_tag_is_never_replaced_by_the_net_line():
    sec = FakeSec(+20.0)
    sec.facts["facts"]["us-gaap"]["InterestExpense"] = {"units": {"USD": [fact(y, 15.0) for y in range(2020, 2026)]}}
    r = SC.build_inputs(sec, "TST", "STANDARD", [], 5)
    assert r["f"]["interest_expense"][-1] == 15.0 and r["f"]["ebit"][-1] == 145.0


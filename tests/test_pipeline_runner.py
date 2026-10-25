"""K6b: the pipeline end to end on a fake database and fake SEC answers: load, idempotency, dry run, restatement (10-K/A), new annual report, unsupported, unknown ticker, status.
The providers and the router are replaced by stubs (they are tested elsewhere and need real SEC documents); everything else - RESOLVE, AUDIT, SRC, DQ, WRITE, log, state - is the real code."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from fakedb import FakeClient
from src.etl import field_map as fm
from src.pipeline import runner as RN
from src.pipeline.runner import Pipeline

KEYS = sorted({v for e in fm.FIELDS.values() for v in e.values()})
AMENDMENT = "0000000001-26-000099"


def submissions(extra=(), sic="2080", forms=None):
    rows = [("10-K", f"0000000001-{y + 1 - 2000}-00000{y % 10}", f"{y + 1}-02-20", f"{y}-12-31") for y in range(2016, 2026)] if forms is None else forms
    rows = list(rows) + list(extra)
    return {"cik": "1", "name": "Acme Corp", "sic": sic, "sicDescription": "x", "fiscalYearEnd": "1231", "tickers": ["ACM"], "exchanges": ["NYSE"], "formerNames": [],
            "filings": {"recent": {"form": [r[0] for r in rows], "accessionNumber": [r[1] for r in rows], "filingDate": [r[2] for r in rows], "reportDate": [r[3] for r in rows],
                                   "primaryDocument": ["d.htm"] * len(rows)}, "files": []}}


class FakeSec:
    def __init__(self, sub):
        self.sub, self.requests_made = sub, 0
        self.facts = {"facts": {"us-gaap": {"Assets": {"units": {"USD": [{"accn": AMENDMENT, "val": 1, "end": "2025-12-31", "form": "10-K/A"}]}}}}}

    def cik_for(self, ticker):
        if ticker != "ACM":
            raise KeyError(ticker)
        return "0000000001", "ACME CORP"

    def companyfacts(self, cik):
        return self.facts

    def get_json(self, url, name, refresh=False):
        return self.sub


def kw_for(years, revenue_last=100.0):
    n = len(years)
    revenue = [float(50 + 5 * i) for i in range(n)]
    revenue[-1] = revenue_last
    return {"ticker": "ACM", "name": "Acme Corp", "fy": [f"FY{y}" for y in years], "end": [f"{y}-12-31" for y in years],
            "f": {"revenue": revenue, "net_income": [float(5 + i) for i in range(n)], "assets": [200.0 + i for i in range(n)], "liabilities": [120.0 + i for i in range(n)],
                  "equity": [80.0] * n},
            "tag_log": {"revenue": {f"FY{y}": {"tag": "Revenues"} for y in years}}, "sbc_state": ["found"] * n, "assumed_zero": {}, "flags": [], "data_problems": ["a data problem"]}


@pytest.fixture
def env(monkeypatch):
    state = SimpleNamespace(years=list(range(2016, 2026)), revenue_last=100.0, profile="STANDARD")
    monkeypatch.setattr(RN, "route", lambda *a, **k: SimpleNamespace(profile=state.profile, reason=["test"], since=None, borderline=False))
    monkeypatch.setattr(RN.C, "provider_kwargs", lambda engine, sec, ticker, profile, splits_fn=None, n_years=10: (kw_for(state.years, state.revenue_last), {
        "f": kw_for(state.years)["f"], "labels": [f"FY{y}" for y in state.years], "ends": [date(y, 12, 31) for y in state.years]}))
    client = FakeClient(KEYS)
    sec = FakeSec(submissions())
    tick = iter(range(0, 10 ** 6, 1))
    state.make = lambda dry=False: Pipeline(sec, client=client, dry_run=dry, splits_fn=lambda t: [], industry_fn=lambda t: "Beverages",
                                            price_fn=lambda t: {"price": 12.0, "previous_close": 11.0, "market_date": date.today()}, clock=lambda: float(next(tick)))
    state.sec, state.client = sec, client
    return state


def test_load_a_new_company_writes_everything_and_a_second_load_writes_nothing(env):
    r = env.make().load("acm")
    c = env.client
    assert r.status == "success" and r.state == "data_loaded" and r.profile == "STANDARD" and r.engine == "general" and r.years == list(range(2016, 2026))
    company = c.tables["companies"][0]
    assert company["cik"] == "0000000001" and company["processing_state"] == "data_loaded" and company["profile"] == "STANDARD" and len(c.tables["company_listings"]) == 1
    assert len(c.tables["filing_periods"]) == 10 and all(p["accession"].startswith("0000000001-") and p["form"] == "10-K" and p["filed_at"] for p in c.tables["filing_periods"])
    assert c.tables["company_profile_history"][0]["fiscal_year"] == 2025 and c.tables["market_snapshot"][0]["current_price"] == 12.0
    assert r.facts["inserted"] == len(c.tables["financial_facts"]) == 50 and r.sources == {"xbrl": 50}
    log = c.tables["data_update_log"][0]
    assert log["operation_type"] == "import_company" and log["status"] == "success" and log["records_inserted"] == 60 and isinstance(log["source_details"], list)
    assert log["source_details"][0]["sources"] == {"xbrl": 50} and log["years_imported"] == list(range(2016, 2026))
    w = c.writes
    r2 = env.make().load("ACM")
    assert r2.status == "no_change" and r2.rows_written == 0 and r2.facts["unchanged"] == 50 and r2.periods["unchanged"] == 10
    assert len(c.tables["data_update_log"]) == 2 and c.tables["data_update_log"][1]["status"] == "no_change"
    assert c.writes - w <= 2                                                          # only the new log row (+ the price snapshot refreshed in place), no fact or period rows


def test_dry_run_computes_and_reports_but_writes_nothing(env):
    r = env.make(dry=True).load("ACM")
    assert env.client.writes == 0 and r.dry_run and r.facts["inserted"] == 50 and r.status == "success" and "companies" not in env.client.tables or env.client.tables["companies"] == []
    assert not env.client.tables.get("data_update_log")


def test_amendment_rewrites_the_affected_year_flags_restated_and_logs_it(env):
    env.make().load("ACM")
    env.sec.sub = submissions(extra=[("10-K/A", AMENDMENT, "2026-06-01", "2025-12-31")])
    env.revenue_last = 105.0
    pipe = env.make()
    resolved, plans = pipe.audit("ACM")
    assert {p.fiscal_year: p.status for p in plans}[2025] == "superseded" and sum(1 for p in plans if p.status == "superseded") == 1
    r = pipe.load("ACM", "amendment")
    assert r.years == [2025] and r.facts == {"inserted": 0, "updated": 1, "unchanged": 4} and r.periods["updated"] == 1 and r.restated == [(2025, "revenue")]
    rev = next(f for f in env.client.tables["financial_facts"] if f["fiscal_year"] == 2025 and f["value"] == 105.0)
    assert "restated" in rev["flags"]
    p25 = next(p for p in env.client.tables["filing_periods"] if p["fiscal_year"] == 2025)
    assert p25["accession"] == AMENDMENT and p25["form"] == "10-K/A"
    last = env.client.tables["data_update_log"][-1]
    assert last["update_scope"] == "amendment" and last["source_details"][0]["restated"] == [[2025, "revenue"]]
    again = env.make().load("ACM", "amendment")                                       # the amendment is the stored filing now: nothing is superseded
    assert again.status == "no_change" and again.years == []
    again_full = env.make().load("ACM")                                               # the full load keeps the flag and writes nothing
    assert again_full.rows_written == 0


def test_new_annual_report_adds_the_new_year_runs_the_router_and_records_ai_required(env):
    env.make().load("ACM")
    env.sec.sub = submissions(extra=[("10-K", "0000000001-27-000001", "2027-02-20", "2026-12-31")])
    env.years = list(range(2017, 2027))
    r = env.make().load("ACM", "new_report")
    assert r.years == [2026] and r.facts["inserted"] == 5 and r.periods["inserted"] == 1
    assert r.ai_required and r.ai_required[0]["fiscal_year"] == 2026
    assert max(p["fiscal_year"] for p in env.client.tables["filing_periods"]) == 2026
    assert env.client.tables["company_profile_history"][0]["fiscal_year"] == 2026 or {h["fiscal_year"] for h in env.client.tables["company_profile_history"]} == {2025, 2026}
    assert env.client.tables["data_update_log"][-1]["source_details"][0]["ai_required"][0]["fiscal_year"] == 2026
    assert env.make().load("ACM", "new_report").years == []                            # nothing new the second time


def test_backfill_loads_only_the_missing_years(env):
    env.make().load("ACM")
    c = env.client
    c.tables["filing_periods"] = [p for p in c.tables["filing_periods"] if p["fiscal_year"] not in (2019, 2020)]
    c.tables["financial_facts"] = [f for f in c.tables["financial_facts"] if f["fiscal_year"] not in (2019, 2020)]
    r = env.make().load("ACM", "backfill")
    assert r.years == [2019, 2020] and r.facts["inserted"] == 10 and r.periods["inserted"] == 2


def test_unsupported_issuer_is_stored_with_its_reason_and_nothing_else_runs(env):
    env.sec.sub = submissions(forms=[("20-F", "a-1", "2026-03-01", "2025-12-31")], sic="3674")
    r = env.make().load("ACM")
    c = env.client
    assert r.state == "unsupported" and r.status == "no_change" and c.tables["companies"][0]["processing_state"] == "unsupported" and "20-F" in c.tables["companies"][0]["unsupported_reason"]
    assert not c.tables.get("financial_facts") and not c.tables.get("filing_periods") and not c.tables.get("market_snapshot")
    assert c.tables["data_update_log"][0]["status"] == "no_change"


def test_unknown_ticker_is_a_failed_job_in_the_log(env):
    r = env.make().load("ZZZZ")
    assert r.status == "failed" and "not_found" in r.error and env.client.tables["data_update_log"][0]["status"] == "failed"


def test_unknown_job_and_status_report(env):
    with pytest.raises(ValueError):
        env.make().load("ACM", "nonsense")
    assert env.make().status("ACM") == {"ticker": "ACM", "in_db": False}
    env.make().load("ACM")
    s = env.make().status("ACM")
    assert s["state"] == "data_loaded" and s["profile"] == "STANDARD" and s["years"] == list(range(2016, 2026)) and s["facts"] == 50 and s["sources"] == {"xbrl": 50}
    assert s["last_job"]["status"] == "success" and s["price"]["current_price"] == 12.0 and len(s["accessions"]) == 10


def test_dq_holds_a_wrong_scale_share_count_as_missing_not_zero(env, monkeypatch):
    kw = kw_for(env.years)
    kw["f"]["shares"] = [1.0e9] * 8 + [1.0e12, 5.0e11]
    monkeypatch.setattr(RN.C, "provider_kwargs", lambda *a, **k: (kw, {"f": kw["f"], "labels": kw["fy"], "ends": [date(y, 12, 31) for y in env.years]}))
    r = env.make().load("ACM")
    shares = {f["fiscal_year"]: f for f in env.client.tables["financial_facts"] if f["flags"] and "share_scale_rescaled" in f["flags"]}
    assert 2024 in shares and 2025 not in {f["fiscal_year"] for f in env.client.tables["financial_facts"] if f["item_id"] == next(i["id"] for i in env.client.tables["dictionary_items"] if i["item_key"] == "shares_diluted_weighted")}
    assert r.status == "partial_success" and any(x[0] == "share_scale" and x[1] == "held" for x in r.dq)


def test_engine_candidates_prefer_a_confirmed_specialised_engine_over_general():
    from src.pipeline.runner import _candidates
    tags = {"facts": {"us-gaap": {"RealEstateInvestmentPropertyNet": {}}}}
    assert _candidates("4899", "general", tags) == ["realestate", "general"]            # a tower company: SIC says communications, the tags say real estate
    assert _candidates("6798", "general", None) == ["realestate", "general"]
    assert _candidates("2080", "general", {"facts": {"us-gaap": {}}}) == ["general"]
    assert _candidates("6021", "bank", None) == ["bank"] and _candidates("6021", "general", None) == ["bank", "general"]

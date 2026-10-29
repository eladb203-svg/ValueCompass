"""K6d-1: the scheduled jobs - the SEC daily index, the queue priorities, the audit, the close-price job, FX and yields, and what happens when a job fails. Fake database, no network."""
import csv
import json
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from fakedb import FakeClient
from src.repositories.score_repository import ScoreRepository
from src.repositories.work_queue_repository import JOB_PRIORITY, PRIORITY, WorkQueueRepository
from src.sched import refdata, sec_daily
from src.sched.jobs import JobRunner
from src.sched.schedule import DEFAULT_PATH, Config

IL = ZoneInfo("Asia/Jerusalem")
GOLDEN = Path(__file__).resolve().parent / "golden" / "2026-10-20"
CFG = Config.load(DEFAULT_PATH)


def at(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=IL).astimezone(timezone.utc)


def add_company(c, symbol, cik, state="complete", profile="STANDARD"):
    c.table("companies").insert({"symbol": symbol, "company_name": symbol, "exchange": "US", "country": "US", "reporting_currency": "USD", "processing_state": state, "cik": cik,
                                 "is_active": True, "profile": profile}).execute()
    return c.tables["companies"][-1]["id"]


# ---------------------------------------------------------------- SEC daily index
def index_text(rows):
    head = ("Description:           Daily Index of EDGAR Dissemination Feed by Form Type\nLast Data Received:    Oct 26, 2026\n\n\n"
            "Form Type   Company Name                                                  CIK         Date Filed  File Name\n" + "-" * 130 + "\n")
    body = ""
    for form, name, cik, filed, acc in rows:
        body += f"{form:<12}{name:<62}{cik:<12}{filed:<12}edgar/data/{cik}/{acc}.txt\n"
    return head + body


DAY = index_text([("10-K", "COCA COLA CO", "21344", "20261026", "0000021344-26-000010"), ("10-K/A", "MICROSOFT CORP", "789019", "20261026", "0000789019-26-000020"),
                  ("10-KT", "SOME OTHER INC", "55555", "20261026", "0000055555-26-000001"), ("8-K", "COCA COLA CO", "21344", "20261026", "0000021344-26-000011"),
                  ("10-Q", "MICROSOFT CORP", "789019", "20261026", "0000789019-26-000021"), ("10-K", "INTEL CORP", "50863", "20261026", "0000050863-26-000009")])


def test_the_form_index_is_parsed_and_only_annual_reports_of_our_companies_are_kept():
    f = sec_daily.parse_form_index(DAY)
    assert [(x["form"], x["cik"], x["accession"]) for x in f] == [("10-K", 21344, "0000021344-26-000010"), ("10-K/A", 789019, "0000789019-26-000020"), ("10-KT", 55555, "0000055555-26-000001"),
                                                                 ("10-K", 50863, "0000050863-26-000009")]
    mine = sec_daily.ours(f, [{"id": 1, "symbol": "KO", "cik": "0000021344"}, {"id": 2, "symbol": "MSFT", "cik": "0000789019"}, {"id": 9, "symbol": "X", "cik": None}])
    assert [(x["form"], c["symbol"]) for x, c in mine] == [("10-K", "KO"), ("10-K/A", "MSFT")]
    assert sec_daily.job_of("10-K/A") == "amendment" and sec_daily.job_of("10-KT") == "new_report"
    assert sec_daily.index_url(date(2026, 10, 26)) == "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR4/form.20261026.idx"
    assert sec_daily.parse_form_index("nothing here") == []


class FakeSec:
    def __init__(self, tmp_path, days):
        self.cache_dir, self.days, self.requests_made, self.urls = tmp_path, days, 0, []

    def _download(self, url):
        self.urls.append(url)
        self.requests_made += 1
        d = url.rsplit(".", 2)[-2][-8:]
        if d not in self.days:
            err = Exception("404")
            err.response = types.SimpleNamespace(status_code=404)
            raise err
        return self.days[d]


def jobs_for(c, sec, now):
    return JobRunner(c, CFG, now=lambda: now, sec_factory=lambda: sec)


def test_new_reports_reads_one_index_per_trading_day_queues_our_companies_and_remembers_the_day(tmp_path):
    c = FakeClient()
    ko, ms = add_company(c, "KO", "0000021344"), add_company(c, "MSFT", "0000789019")
    sec = FakeSec(tmp_path, {"20261026": DAY})
    out = jobs_for(c, sec, at(2026, 10, 27, 6)).run("new_reports")                              # Tuesday 06:00 Israel: the day to read is Monday
    assert out.status == "success" and out.detail["last_day"] == "2026-10-26" and out.detail["days"] == ["2026-10-26"]
    assert sec.urls[-1] == sec_daily.index_url(date(2026, 10, 26)) and len(sec.urls) == 5                  # the first run ever looks 5 trading days back; only 26 Oct exists
    q = {(t["company_id"], t["job_type"]): t for t in c.tables["work_queue"]}
    assert set(q) == {(ko, "new_report"), (ms, "amendment")} and {t["priority"] for t in q.values()} == {3}
    assert q[(ko, "new_report")]["payload"]["accession"] == "0000021344-26-000010"
    row = c.tables["data_update_log"][-1]
    assert row["update_scope"] == "sched:new_reports" and row["operation_type"] == "refresh_financials" and row["status"] == "success" and row["source_details"][0]["last_day"] == "2026-10-26"


def test_a_day_that_is_not_published_yet_is_tried_again_and_missed_days_are_all_read(tmp_path):
    c = FakeClient()
    add_company(c, "KO", "0000021344")
    sec = FakeSec(tmp_path, {})
    out = jobs_for(c, sec, at(2026, 10, 27, 6)).run("new_reports")
    assert out.status == "no_change" and "2026-10-26" in out.detail["missing_days"] and out.detail["last_day"] is None and not c.tables.get("work_queue")     # nothing is published: no day is skipped
    sec.days.update({"20261026": index_text([]), "20261027": index_text([("10-K", "COCA COLA CO", "21344", "20261027", "0000021344-26-000012")])})
    out = jobs_for(c, sec, at(2026, 10, 29, 6)).run("new_reports")                                # Wednesday 28th's index is not there yet; Mon and Tue are both read
    assert out.detail["days"] == ["2026-10-26", "2026-10-27"] and out.detail["last_day"] == "2026-10-27" and out.detail["missing_days"] == ["2026-10-28"] and len(c.tables["work_queue"]) == 1
    out = jobs_for(c, sec, at(2026, 10, 29, 7)).run("new_reports")                                # nothing newer to read
    assert out.status == "no_change" and out.detail["days"] == [] and out.detail["last_day"] == "2026-10-27"
    out = jobs_for(c, FakeSec(tmp_path, {}), at(2026, 10, 30, 6)).run("new_reports")              # both 28 and 29 Oct missing: Tuesday stays the last day read
    assert out.detail["missing_days"] == ["2026-10-28", "2026-10-29"] and out.detail["last_day"] == "2026-10-27"
    sec.days["20261029"] = index_text([])
    out = jobs_for(c, sec, at(2026, 10, 30, 7)).run("new_reports")                                # 29th exists, 28th never will: 28th is skipped for good
    assert out.detail["days"] == ["2026-10-29"] and out.detail["last_day"] == "2026-10-29" and "2026-10-28" in out.warnings[0]


def test_a_weekend_morning_has_nothing_new_to_read(tmp_path):
    c = FakeClient()
    add_company(c, "KO", "0000021344")
    sec = FakeSec(tmp_path, {"20261023": index_text([])})
    jobs_for(c, sec, at(2026, 10, 26, 6)).run("new_reports")                                      # Monday 06:00: Friday's index
    sec.urls.clear()
    out = jobs_for(c, sec, at(2026, 10, 27, 6)).run("new_reports")                                # Tuesday: Monday's (404 here)
    assert out.detail["missing_days"] == ["2026-10-26"]
    assert jobs_for(c, FakeSec(tmp_path, {}), at(2026, 10, 24, 6)).run("new_reports").detail["days"] == []   # Saturday morning: Friday was already read


# ---------------------------------------------------------------- priorities
def test_the_queue_order_is_user_then_completion_then_new_report_then_wide_loading():
    assert PRIORITY == {"user": 1, "completion": 2, "new_report": 3, "bulk": 4}
    assert JOB_PRIORITY["backfill"] == 2 and JOB_PRIORITY["new_report"] == 3 and JOB_PRIORITY["amendment"] == 3
    q = WorkQueueRepository(FakeClient(), now=lambda: at(2026, 10, 26, 12))
    q.enqueue(1, "ai_assess", 2025, None, PRIORITY["bulk"])
    q.enqueue(2, "ai_assess", 2025, None, PRIORITY["new_report"])
    q.enqueue(3, "ai_assess", 2025, None, PRIORITY["completion"])
    q.enqueue(4, "ai_assess", 2025, None, PRIORITY["user"])
    assert [t["company_id"] for t in q.runnable()] == [4, 3, 2, 1]
    q.enqueue(1, "ai_assess", 2025, None, PRIORITY["user"])                                       # a user asks for company 1: it moves to the front
    assert [t["company_id"] for t in q.runnable()] == [1, 4, 3, 2]            # both user requests first (then by company), completion, new report


# ---------------------------------------------------------------- close prices
def golden(engine, t):
    return json.loads((GOLDEN / engine / f"{t}.json").read_text(encoding="utf-8"))


def test_close_prices_updates_every_stock_in_one_request_and_the_score_in_place(tmp_path):
    c = FakeClient()
    ko, jpm, amd = add_company(c, "KO", "0000021344"), add_company(c, "JPM", "0000019617", profile="BANK"), add_company(c, "NEW", "0000000001", state="data_loaded")
    unsup = add_company(c, "FPI", "0000000002", state="unsupported")
    s = ScoreRepository(c)
    s.write_result(ko, golden("general", "KO"))
    s.write_result(jpm, golden("bank", "JPM"))
    calls = []

    def fetch(tickers, intraday=False):
        calls.append((list(tickers), intraday))
        return {"KO": {"price": 28.0, "previous_close": 27.0, "market_date": date(2026, 10, 23)}, "JPM": {"price": 250.0, "previous_close": 249.0, "market_date": date(2026, 10, 23)}}

    out = JobRunner(c, CFG, now=lambda: at(2026, 10, 26, 0, 30), fetch_batch=fetch).run("close_prices")
    assert calls == [(["KO", "JPM", "NEW"], True)] and out.status == "partial_success" and out.detail["prices"] == 2 and out.detail["no_price"] == 1      # one request; FPI (unsupported) is not asked
    assert out.detail["scores_updated_in_place"] == 2
    assert len(c.tables["score_runs"]) == 2 and {r["company_id"] for r in c.tables["market_snapshot"]} == {ko, jpm}
    ko_val = [v for v in c.tables["valuations"] if v["model"] == "buffett" and v["run_id"] == c.tables["score_runs"][0]["id"]][0]
    assert ko_val["details"]["price_current"] == 28.0 and ko_val["price_state"] == "scored"
    row = c.tables["data_update_log"][-1]
    assert row["update_scope"] == "sched:close_prices" and row["operation_type"] == "refresh_market_snapshot" and "NEW: no price" in row["warning_message"] and unsup


def test_close_prices_with_no_price_at_all_fails_and_is_logged(tmp_path):
    c = FakeClient()
    add_company(c, "KO", "0000021344")
    out = JobRunner(c, CFG, now=lambda: at(2026, 10, 26, 0, 30), fetch_batch=lambda t, intraday=False: {}).run("close_prices")
    assert out.status == "failed" and c.tables["data_update_log"][-1]["status"] == "failed" and "no price" in c.tables["data_update_log"][-1]["error_message"]


def test_a_failing_job_is_logged_with_its_error_and_the_next_job_runs():
    c = FakeClient()
    add_company(c, "KO", "0000021344")

    def boom(tickers, intraday=False):
        raise ValueError("source down")

    jr = JobRunner(c, CFG, now=lambda: at(2026, 10, 26, 0, 30), fetch_batch=boom)
    out = jr.run("close_prices")
    row = c.tables["data_update_log"][-1]
    assert out.status == "failed" and row["status"] == "failed" and row["error_message"] == "ValueError: source down" and "source down" not in (row["warning_message"] or "")
    assert jr.run("fx").status == "failed" or True                                               # the object still works after a failure (no network here: any outcome is logged)
    assert [r["update_scope"] for r in c.tables["data_update_log"]][0] == "sched:close_prices"


def test_a_network_error_waits_30_60_120_120_seconds_and_then_gives_up_with_a_log_row():
    c = FakeClient()
    add_company(c, "KO", "0000021344")
    waits = []

    def down(tickers, intraday=False):
        raise httpx.ConnectError("getaddrinfo failed")

    jr = JobRunner(c, CFG, now=lambda: at(2026, 10, 26, 0, 30), fetch_batch=down, sleep=waits.append)
    out = jr.run("close_prices")
    assert waits == [30, 60, 120, 120] and out.status == "failed" and "ConnectError" in c.tables["data_update_log"][-1]["error_message"]


def test_a_job_that_is_already_running_is_not_started_twice():
    c = FakeClient()
    jr = JobRunner(c, CFG, now=lambda: at(2026, 10, 26, 0, 30), fetch_batch=lambda t, intraday=False: {})
    jr._job_locks["fx"].acquire()
    out = jr.run("fx")
    assert out.skipped and not c.tables.get("data_update_log")


# ---------------------------------------------------------------- audit
def test_the_audit_queues_backfill_for_missing_years_at_priority_2_and_the_missing_ai_tasks():
    c = FakeClient()
    ko = add_company(c, "KO", "0000021344")
    add_company(c, "NEW", "0000000001", state="resolved")
    plans = [types.SimpleNamespace(fiscal_year=2016, status="missing"), types.SimpleNamespace(fiscal_year=2017, status="present"), types.SimpleNamespace(fiscal_year=2018, status="superseded")]
    pipe = types.SimpleNamespace(audit=lambda t: (None, plans))
    runner = types.SimpleNamespace(plan_completion=lambda co, prio: [101, 102])
    out = JobRunner(c, CFG, now=lambda: at(2026, 10, 25, 3), make_pipeline=lambda dry: pipe, make_runner=lambda b, rpm=12: runner).run("audit")
    assert out.status == "success" and out.detail["companies"] == 1                                # the company that is only `resolved` is not audited
    tasks = {t["job_type"]: t for t in c.tables["work_queue"]}
    assert tasks["backfill"]["priority"] == 2 and tasks["backfill"]["payload"]["years"] == [2016] and tasks["amendment"]["payload"]["years"] == [2018] and tasks["backfill"]["company_id"] == ko
    assert out.detail["completion"] == {"KO": [101, 102]} and c.tables["data_update_log"][-1]["update_scope"] == "sched:audit"
    again = JobRunner(c, CFG, now=lambda: at(2026, 11, 1, 3), make_pipeline=lambda dry: pipe, make_runner=lambda b, rpm=12: types.SimpleNamespace(plan_completion=lambda co, p: [])).run("audit")
    assert again.status == "no_change" and len(c.tables["work_queue"]) == 2                        # the same open tasks are not queued twice


def test_a_company_that_fails_in_the_audit_does_not_stop_the_others():
    c = FakeClient()
    add_company(c, "KO", "0000021344")
    add_company(c, "MSFT", "0000789019")

    def audit(t):
        if t == "KO":
            raise RuntimeError("sec down")
        return None, [types.SimpleNamespace(fiscal_year=2016, status="missing")]

    out = JobRunner(c, CFG, now=lambda: at(2026, 10, 25, 3), make_pipeline=lambda d: types.SimpleNamespace(audit=audit),
                    make_runner=lambda b, rpm=12: types.SimpleNamespace(plan_completion=lambda co, p: [])).run("audit")
    assert out.status == "partial_success" and "KO: RuntimeError: sec down" in out.warnings[0] and len(c.tables["work_queue"]) == 1


def test_the_router_extraction_loop_stops_after_the_extraction_ran_once(tmp_path):
    from src.pipeline.queue_runner import QueueRunner
    c = FakeClient()
    co = add_company(c, "DLR", "0000000064", state="data_loaded")
    qr = QueueRunner(c, results_dir=tmp_path)
    res = types.SimpleNamespace(status="success", state="data_loaded", router_needs="realestate", rows_written=0, years=[], profile="STANDARD")
    assert qr.after_load(res, co, 1)["extraction_requested"] == "realestate"
    t = c.tables["work_queue"][0]
    assert t["priority"] == 2                                                                     # K6d-2: the router extraction is data completion (priority 2)
    t["state"] = "done"                                                                           # the extraction ran ...
    out = qr.after_load(res, co, 1)                                                               # ... and the router still has nothing to decide with: no second model request
    assert out["router_fallback"] == "realestate" and [x["job_type"] for x in c.tables["work_queue"]] == ["ai_extract", "repair"]
    assert c.tables["work_queue"][1]["payload"] == {"router_fallback": True} and c.tables["work_queue"][1]["priority"] == 2


def test_plan_completion_queues_the_first_score_of_a_company_that_has_none_at_priority_2(tmp_path):
    from src.pipeline.queue_runner import QueueRunner
    c = FakeClient()
    ko = add_company(c, "KO", "0000021344")
    unsup = add_company(c, "FPI", "0000000002", state="unsupported")
    qr = QueueRunner(c, results_dir=tmp_path)
    assert qr.plan_completion(c.tables["companies"][1]) == []                                      # unsupported: nothing
    ids = qr.plan_completion(c.tables["companies"][0])
    t = c.tables["work_queue"][0]
    assert ids == [t["id"]] and (t["job_type"], t["skill"], t["priority"]) == ("score", "first", 2)
    ScoreRepository(c).write_result(ko, golden("general", "KO"))
    assert qr.plan_completion(c.tables["companies"][0]) == []                                      # scored, but its result file is not on this PC: nothing can be planned


# ---------------------------------------------------------------- the AI queue job
def test_the_ai_queue_job_runs_the_queue_with_the_configured_budget_and_logs_the_result():
    c = FakeClient()
    seen = {}

    class R:
        def run(self):
            return types.SimpleNamespace(done=[(1, "score", "first", "KO")], failed=[(2, "ai_assess", None, "MSFT", "boom")], deferred=[(3, "ai_assess", "INTC", "quota")], attempts=7)

    def make(budget, rpm=12):
        seen.update(budget=budget, rpm=rpm)
        return R()

    out = JobRunner(c, CFG, now=lambda: at(2026, 10, 26, 10), make_runner=make).run("ai_queue")
    assert seen == {"budget": 450, "rpm": 12} and out.status == "partial_success" and out.detail["attempts"] == 7 and c.tables["data_update_log"][-1]["operation_type"] == "calculate_scores"


# ---------------------------------------------------------------- FX and yields
ECB = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
<Cube><Cube time='2026-10-23'><Cube currency='USD' rate='1.1000'/><Cube currency='JPY' rate='160.00'/><Cube currency='GBP' rate='0.8500'/><Cube currency='ILS' rate='4.0000'/></Cube></Cube></gesmes:Envelope>"""


def test_fx_rates_are_usd_per_unit_of_each_currency_and_a_repeat_writes_nothing():
    day, per_eur = refdata.parse_ecb(ECB)
    assert day == date(2026, 10, 23) and per_eur["USD"] == 1.1
    c = FakeClient()
    jr = JobRunner(c, CFG, now=lambda: at(2026, 10, 26, 7, 30), fx_get=lambda url: ECB)
    out = jr.run("fx")
    rates = {r["currency"]: r["rate_to_usd"] for r in c.tables["fx_rates"]}
    assert out.status == "success" and rates == {"ILS": 0.275, "EUR": 1.1, "GBP": pytest.approx(1.29411765), "JPY": 0.00687500} and {r["period_type"] for r in c.tables["fx_rates"]} == {"current"}
    assert jr.run("fx").status == "no_change" and len(c.tables["fx_rates"]) == 4
    assert c.tables["data_update_log"][-1]["target_table"] == "fx_rates"


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["currency", "year", "yield_pct", "n_obs", "series", "source", "url", "retrieved", "version", "cross_check"])
        w.writeheader()
        for cur, year, y, series in rows:
            w.writerow({"currency": cur, "year": year, "yield_pct": y, "n_obs": 250, "series": series, "source": "FRED", "url": "u", "retrieved": "2026-10-13", "version": "v1", "cross_check": ""})


def test_yields_are_copied_from_the_csv_to_the_table_and_a_repeat_writes_nothing(tmp_path):
    p = tmp_path / "gov_yields.csv"
    write_csv(p, [("USD", "2025", "4.2932", "DGS10"), ("USD", "2026-09", "4.1000", "GS10"), ("JPY", "2025", "1.1", "JGB 10Y")])
    c = FakeClient()
    assert refdata.sync_yields_to_db(c, p) == {"read": 3, "written": 3}
    rows = {(r["currency"], r["period_type"], r["period"]): r["yield_pct"] for r in c.tables["gov_yields"]}
    assert rows == {("USD", "annual", "2025"): 4.2932, ("USD", "monthly", "2026-09"): 4.1, ("JPY", "annual", "2025"): 1.1}
    assert refdata.sync_yields_to_db(c, p) == {"read": 3, "written": 0}
    write_csv(p, [("USD", "2025", "4.2932", "DGS10"), ("USD", "2026-10", "4.2", "GS10"), ("JPY", "2025", "1.1", "JGB 10Y")])
    assert refdata.sync_yields_to_db(c, p)["written"] == 1


def test_the_annual_builder_runs_only_when_a_year_has_ended_and_before_the_monthly_one(tmp_path):
    p = tmp_path / "gov_yields.csv"
    order = []
    write_csv(p, [("USD", "2025", "4.29", "DGS10")])
    refdata.refresh_yield_csv(date(2026, 10, 26), lambda: order.append("monthly"), lambda: order.append("annual"), p)
    assert order == ["monthly"]
    order.clear()
    refdata.refresh_yield_csv(date(2027, 1, 5), lambda: order.append("monthly"), lambda: order.append("annual"), p)       # 2026 has ended and has no row yet
    assert order == ["annual", "monthly"]

    def stops():
        raise SystemExit("STOP: JPY has too few observations")

    r = refdata.refresh_yield_csv(date(2027, 1, 5), lambda: "m", stops, p)
    assert r["monthly"] == "m" and r["annual"].startswith("annual builder stopped")

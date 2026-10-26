"""K6d-1: the trading calendar, the due times of every job (daylight-saving changes in New York and in Israel, a holiday, a half day), missed jobs, the single instance, an orderly stop. No network."""
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from fakedb import FakeClient
from src.sched import service
from src.sched.jobs import JobRunner
from src.sched.nyse import NY, Calendar, easter, holidays
from src.sched.schedule import DEFAULT_PATH, Config

IL = ZoneInfo("Asia/Jerusalem")
CAL = Calendar()


def cfg(**jobs):
    base = Config.load(DEFAULT_PATH).raw
    raw = {**base, "jobs": {**base["jobs"], **jobs}}
    return Config(raw, DEFAULT_PATH)


# ---------------------------------------------------------------- calendar
def test_holidays_half_days_and_the_observed_rules_of_2026():
    h = holidays(2026)
    assert h[date(2026, 4, 3)] == "Good Friday" and easter(2026) == date(2026, 4, 5)
    assert h[date(2026, 5, 25)] == "Memorial Day" and h[date(2026, 11, 26)] == "Thanksgiving" and h[date(2026, 12, 25)] == "Christmas"
    assert date(2026, 7, 3) in h and h[date(2026, 7, 3)] == "Independence Day"                 # 4 July is a Saturday: observed on Friday 3 July
    assert date(2026, 6, 19) in h                                                               # Juneteenth, a Friday
    assert not CAL.is_trading_day(date(2026, 7, 3)) and not CAL.is_trading_day(date(2026, 10, 24)) and CAL.is_trading_day(date(2026, 10, 26))
    assert CAL.is_half_day(date(2026, 11, 27)) and CAL.is_half_day(date(2026, 12, 24)) and not CAL.is_half_day(date(2026, 11, 26))
    assert CAL.is_half_day(date(2025, 7, 3)) and not CAL.is_trading_day(date(2027, 1, 1)) and CAL.is_trading_day(date(2027, 12, 31))   # 1 Jan 2028 is a Saturday: no observed day on 31 Dec 2027


def test_prev_trading_day_skips_weekends_and_holidays_and_the_extra_closed_list():
    assert CAL.prev_trading_day(date(2026, 10, 26)) == date(2026, 10, 23)                       # Monday -> Friday
    assert CAL.prev_trading_day(date(2026, 11, 27)) == date(2026, 11, 25)                       # after Thanksgiving: Wednesday
    assert Calendar(["2026-10-23"]).prev_trading_day(date(2026, 10, 26)) == date(2026, 10, 22)
    assert CAL.trading_days_between(date(2026, 10, 22), date(2026, 10, 27)) == 3                # Fri, Mon, Tue


# ---------------------------------------------------------------- due times
def test_close_prices_run_30_minutes_after_the_close_in_israel_time_across_both_clock_changes():
    c = cfg()
    # Israel changed to winter time on 25 Oct 2026, New York on 1 Nov: three different offsets in three weeks
    assert c.slots("close_prices", date(2026, 10, 23)) == [datetime(2026, 10, 23, 23, 30, tzinfo=IL)]    # both still on summer time: close 23:00 Israel
    assert c.slots("close_prices", date(2026, 10, 26)) == [datetime(2026, 10, 26, 22, 30, tzinfo=IL)]    # Israel on winter time, New York still on summer time: close 22:00
    assert c.slots("close_prices", date(2026, 11, 2)) == [datetime(2026, 11, 2, 23, 30, tzinfo=IL)]      # both on winter time again
    assert c.slots("close_prices", date(2026, 11, 27)) == [datetime(2026, 11, 27, 20, 30, tzinfo=IL)]    # a half day: close 13:00 New York = 20:00 Israel
    assert c.slots("close_prices", date(2026, 11, 26)) == [] and c.slots("close_prices", date(2026, 10, 24)) == []   # Thanksgiving, a Saturday
    assert c.slots("close_prices", date(2026, 7, 3)) == []                                              # the observed Independence Day


def test_a_close_after_midnight_israel_time_belongs_to_the_next_calendar_day():
    c = cfg(close_prices={"enabled": True, "minutes_after_close": 120})
    assert c.slots("close_prices", date(2026, 11, 3)) == [datetime(2026, 11, 3, 1, 0, tzinfo=IL)]       # Monday 2 Nov close 23:00 + 2h
    assert c.slots("close_prices", date(2026, 11, 2)) == [] or c.slots("close_prices", date(2026, 11, 2))[0].hour < 3


def test_intraday_slots_follow_the_exchange_hours_inside_10_to_23():
    c = cfg()
    slots = c.slots("intraday_prices", date(2026, 10, 26))
    assert slots[0] == datetime(2026, 10, 26, 15, 30, tzinfo=IL) and slots[-1] == datetime(2026, 10, 26, 21, 30, tzinfo=IL) and len(slots) == 13     # open 15:30, the 22:00 close is not a slot
    slots = c.slots("intraday_prices", date(2026, 11, 2))
    assert slots[0] == datetime(2026, 11, 2, 16, 30, tzinfo=IL) and slots[-1] == datetime(2026, 11, 2, 22, 30, tzinfo=IL)
    assert c.slots("intraday_prices", date(2026, 11, 27))[-1] == datetime(2026, 11, 27, 19, 30, tzinfo=IL)   # a half day ends at 20:00 Israel
    assert c.slots("intraday_prices", date(2026, 10, 24)) == [] and c.slots("intraday_prices", date(2026, 11, 26)) == []
    assert cfg(intraday_prices={"enabled": True, "every_minutes": 45, "from": "10:00", "to": "23:00"}).slots("intraday_prices", date(2026, 10, 26))[1] - slots[0] != timedelta(0)
    assert all(t.hour >= 10 and (t.hour, t.minute) <= (23, 0) for t in c.slots("intraday_prices", date(2026, 10, 26)))


def test_the_intraday_gate_needs_an_open_exchange_and_the_window():
    c = cfg()
    assert c.intraday_open(datetime(2026, 10, 26, 18, 0, tzinfo=IL))
    assert not c.intraday_open(datetime(2026, 10, 26, 12, 0, tzinfo=IL))                         # before the exchange opens
    assert not c.intraday_open(datetime(2026, 10, 24, 18, 0, tzinfo=IL))                         # Saturday
    c.ignore_market_hours = True
    assert c.intraday_open(datetime(2026, 10, 24, 18, 0, tzinfo=IL)) and not c.intraday_open(datetime(2026, 10, 24, 9, 0, tzinfo=IL))   # the window still applies


def test_daily_weekly_and_monthly_jobs_and_next_and_last_due():
    c = cfg()
    assert c.slots("new_reports", date(2026, 10, 26)) == [datetime(2026, 10, 26, 6, 0, tzinfo=IL)]
    assert c.slots("audit", date(2026, 10, 25)) == [datetime(2026, 10, 25, 3, 0, tzinfo=IL)] and c.slots("audit", date(2026, 10, 26)) == []      # Sunday
    assert c.slots("yields", date(2026, 11, 3)) == [datetime(2026, 11, 3, 7, 0, tzinfo=IL)] and c.slots("yields", date(2026, 11, 4)) == []
    ai = c.slots("ai_queue", date(2026, 10, 26))
    assert ai[0] == datetime(2026, 10, 26, 10, 0, tzinfo=IL) and ai[1] == datetime(2026, 10, 26, 10, 30, tzinfo=IL) and ai[-1].hour == 23
    now = datetime(2026, 10, 26, 12, 0, tzinfo=IL)
    assert c.last_due("new_reports", now) == datetime(2026, 10, 26, 6, 0, tzinfo=IL)
    assert c.last_due("audit", now) == datetime(2026, 10, 25, 3, 0, tzinfo=IL)
    assert c.last_due("yields", now) == datetime(2026, 10, 3, 7, 0, tzinfo=IL)
    assert c.last_due("close_prices", now) == datetime(2026, 10, 23, 23, 30, tzinfo=IL)
    assert c.next_due("close_prices", now) == datetime(2026, 10, 26, 22, 30, tzinfo=IL)
    assert c.next_due("new_reports", now) == datetime(2026, 10, 27, 6, 0, tzinfo=IL)


def test_a_test_interval_overrides_the_times_and_a_disabled_job_has_none():
    c = cfg(fx={"enabled": True, "interval_minutes": 2})
    assert len(c.slots("fx", date(2026, 10, 26))) == 720 and c.next_due("fx", datetime(2026, 10, 26, 12, 1, tzinfo=IL)) == datetime(2026, 10, 26, 12, 2, tzinfo=IL)
    d = cfg(cleanup={"enabled": False})
    assert d.slots("cleanup", date(2026, 10, 25)) == [] and d.next_due("cleanup", datetime(2026, 10, 26, tzinfo=IL)) is None


def test_the_trigger_gives_apscheduler_the_next_due_time():
    from src.sched.schedule import SlotTrigger
    c = cfg()
    t = SlotTrigger(c, "new_reports")
    now = datetime(2026, 10, 26, 12, 0, tzinfo=IL)
    first = t.get_next_fire_time(None, now)
    assert first == datetime(2026, 10, 27, 6, 0, tzinfo=IL) and t.get_next_fire_time(first, first + timedelta(seconds=3)) == datetime(2026, 10, 28, 6, 0, tzinfo=IL)


def test_the_config_file_has_every_job_and_the_admin_email():
    c = Config.load(DEFAULT_PATH)
    assert c.admin_email == "eladb203@gmail.com" and c.tz == IL and all(c.enabled(j) for j in ("close_prices", "intraday_prices", "new_reports", "ai_queue", "audit", "yields", "fx", "cleanup"))
    assert c.get("ai_queue", "budget") == 450 and c.get("ai_queue", "rpm") == 12 and c.get("intraday_prices", "every_minutes") == 30 and c.get("cleanup", "apply") is False


# ---------------------------------------------------------------- missed jobs
def ok_row(job, when, status="success"):
    return {"update_scope": f"sched:{job}", "status": status, "created_at": when.isoformat()}


def test_a_missed_job_runs_once_and_a_job_that_ran_after_its_due_time_does_not():
    c = cfg()
    db = FakeClient()
    now = datetime(2026, 10, 26, 12, 0, tzinfo=IL)
    jobs = JobRunner(db, c, now=lambda: now.astimezone(timezone.utc))
    assert jobs.missed(now) == ["close_prices", "new_reports", "audit", "yields", "fx", "cleanup", "ai_queue"]     # the catch-up order; the intraday job is never caught up
    db.tables["data_update_log"] = [ok_row("new_reports", datetime(2026, 10, 26, 6, 5, tzinfo=IL)), ok_row("audit", datetime(2026, 10, 25, 3, 1, tzinfo=IL)),
                                    ok_row("close_prices", datetime(2026, 10, 23, 23, 31, tzinfo=IL)), ok_row("fx", datetime(2026, 10, 26, 7, 31, tzinfo=IL), "no_change"),
                                    ok_row("yields", datetime(2026, 10, 3, 7, 1, tzinfo=IL)), ok_row("cleanup", datetime(2026, 10, 25, 4, 0, tzinfo=IL)),
                                    ok_row("ai_queue", datetime(2026, 10, 26, 12, 0, 30, tzinfo=IL), "partial_success")]
    assert jobs.missed(now) == []
    db.tables["data_update_log"][0]["status"] = "failed"                                          # a failed run does not count as done
    assert jobs.missed(now) == ["new_reports"]


# ---------------------------------------------------------------- the process: one instance, an orderly stop
def test_only_one_instance_can_hold_the_lock(tmp_path):
    a, b = service.InstanceLock(tmp_path / "x.lock"), service.InstanceLock(tmp_path / "x.lock")
    assert a.acquire() and not b.acquire()
    a.release()
    assert b.acquire()
    b.release()
    assert not service.is_running(tmp_path)


class StubJobs:
    def __init__(self):
        self.ran = []

    def run(self, name, **kw):
        self.ran.append(name)
        return type("O", (), {"status": "success", "error": None})()

    def missed(self, now=None):
        return ["fx"]


def test_a_second_scheduler_exits_with_a_message_and_a_stop_ends_the_first_in_order(tmp_path):
    c = Config({"timezone": "Asia/Jerusalem", "jobs": {}}, None)
    msgs = []
    jobs = StubJobs()
    th = threading.Thread(target=lambda: results.append(service.serve(c, lambda: FakeClient(), tmp_path, 0.05, jobs, msgs.append)))
    results = []
    th.start()
    for _ in range(100):
        if service.is_running(tmp_path):
            break
        time.sleep(0.05)
    assert service.is_running(tmp_path) and service.read_info(tmp_path)["pid"]
    second = []
    assert service.serve(c, lambda: FakeClient(), tmp_path, 0.05, StubJobs(), second.append) == 1 and "already running" in second[0]
    ok, msg = service.stop(tmp_path, wait_seconds=10, poll=0.05)
    th.join(10)
    assert ok and results == [0] and not service.is_running(tmp_path) and jobs.ran == ["fx"]            # the missed job ran once at the start
    assert not (tmp_path / "scheduler.stop").exists() and any("stopped" in m for m in msgs)
    assert service.stop(tmp_path)[1] == "The scheduler is not running."


def test_ensure_starts_a_detached_process_only_when_none_runs(tmp_path):
    calls = []

    class P:
        pid = 4242

    started, msg = service.ensure(None, tmp_path, popen=lambda cmd, **kw: calls.append((cmd, kw)) or P())
    assert started and "4242" in msg and calls[0][0][-1] == "scheduler" and calls[0][1]["cwd"]
    lk = service.InstanceLock(service.lock_path(tmp_path))
    assert lk.acquire()
    started, msg = service.ensure(None, tmp_path, popen=lambda *a, **k: calls.append("again"))
    lk.release()
    assert not started and "already running" in msg and len(calls) == 1                             # the second call started nothing

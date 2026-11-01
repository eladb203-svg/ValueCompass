"""K6d-2 fixes (decisions of 2026-10-29): company after company, only the loaded ticker, the per-company call limit, a spent run budget is not a deferral, temporary network errors, stay awake. Fake database."""
from datetime import datetime, timezone

import pytest

from fakedb import FakeClient
from src.pipeline import queue_runner as QR
from src.pipeline.queue_runner import COMPANY_CALL_CAP, QueueRunner, is_transient
from src.sched import awake

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


class Inner:
    model = "fake"

    def __init__(self):
        self.sent = 0

    def generate(self, prompt, seed_offset=0, **kw):
        self.sent += 1
        return type("Reply", (), {"text": "ok", "model": "fake"})()


def runner(client, budget=0, executors=None, clock=None, sleep=None):
    return QueueRunner(client, gemini=Inner() if budget else None, budget=budget, now=clock or Clock(), executors=executors, sleep=sleep,
                       results_dir=__import__("pathlib").Path("scripts/output_k6c/test_results_unused"))


def company(client, symbol):
    client.table("companies").insert({"symbol": symbol, "company_name": symbol, "exchange": "US", "country": "US", "reporting_currency": "USD"}).execute()
    return client.tables["companies"][-1]["id"]


@pytest.fixture(autouse=True)
def _quiet(monkeypatch, tmp_path):
    monkeypatch.setattr(QR.S, "seed_results", lambda *a, **k: 0)
    monkeypatch.setattr(QR, "ALERT_LOG", tmp_path / "alerts.log")


def test_companies_run_one_after_the_other_until_each_is_finished():
    client = FakeClient()
    a, b = company(client, "AAA"), company(client, "BBB")
    seen = []
    ex = {k: (lambda t, seen=seen: seen.append((t["company_id"], t["job_type"])) or {}) for k in ("score", "analysis", "ai_assess")}
    r = runner(client, executors=ex)
    r.queue.enqueue(a, "score", None, "first", 3)
    r.queue.enqueue(b, "score", None, "first", 2)
    r.queue.enqueue(a, "analysis", None, None, 2)              # A's later task has a better priority than its first one: the two companies still do not mix
    r.queue.enqueue(b, "analysis", None, None, 3)
    r.run()
    assert [c for c, _ in seen] == [a, a, b, b]                # A arrived first and has the best priority (2, like B): A is finished, then B


def test_only_the_tasks_of_the_given_ticker_run():
    client = FakeClient()
    a, b = company(client, "AAA"), company(client, "BBB")
    seen = []
    r = runner(client, executors={"score": lambda t: seen.append(t["company_id"]) or {}})
    r.queue.enqueue(a, "score", None, "first", 3)
    r.queue.enqueue(b, "score", None, "first", 3)
    r.run(only={"BBB"})
    assert seen == [b] and {t["company_id"]: t["state"] for t in r.queue.list()} == {a: "queued", b: "done"}


def test_a_company_that_uses_its_call_limit_fails_with_an_alert_and_is_not_postponed():
    client = FakeClient()
    a = company(client, "AAA")
    real = client.table
    client.table = lambda name: (_ for _ in ()).throw(RuntimeError("no such table")) if name == "support_tickets" else real(name)      # the tickets table does not exist yet: the log is the record

    def loop(task):                                             # a loop: asks again and again
        while True:
            r.gemini.generate("again")

    r = runner(client, budget=200, executors={"ai_assess": loop})
    r.queue.enqueue(a, "ai_assess", 2025, "S1", 3)
    r.queue.enqueue(a, "ai_assess", 2025, "S2", 3)
    rep = r.run()
    assert rep.calls_by_company == {"AAA": COMPANY_CALL_CAP} and len(rep.alerts) == 1
    states = {t["skill"]: t["state"] for t in r.queue.list(a)}
    assert states == {"S1": "failed", "S2": "failed"}
    assert "חשד ללולאה" in r.queue.list(a)[0]["last_error"] and not rep.deferred
    assert client.tables["companies"][0]["processing_state"] == "failed"
    assert "admin_alert" in QR.ALERT_LOG.read_text(encoding="utf-8")


def test_calls_of_earlier_tasks_count_against_the_same_annual_report():
    client = FakeClient()
    a = company(client, "AAA")
    r = runner(client, budget=200, executors={"ai_assess": lambda t: [r.gemini.generate("q") for _ in range(25)] and {}})
    r.queue.enqueue(a, "ai_assess", 2025, "S1", 3)
    r.queue.enqueue(a, "ai_assess", 2025, "S2", 3)
    rep = r.run()
    assert [x[2] for x in rep.done] == ["S1"] and rep.calls_by_company["AAA"] == COMPANY_CALL_CAP        # S1 used 25, S2 got the remaining 15 and tripped the limit
    assert {t["skill"]: t["state"] for t in r.queue.list(a)} == {"S1": "done", "S2": "failed"}


def test_the_daily_cap_defers_but_a_spent_run_budget_does_not():
    client = FakeClient()
    a = company(client, "AAA")

    def daily(task):
        raise RuntimeError("shared daily request cap of 450 reached")

    r = runner(client, budget=5, executors={"ai_assess": daily})
    r.queue.enqueue(a, "ai_assess", 2025, "S1", 3)
    rep = r.run()
    t = r.queue.list(a)[0]
    assert len(rep.deferred) == 1 and t["state"] == "deferred_quota" and "450" in t["last_error"]


@pytest.mark.parametrize("err", [type("ConnectError", (Exception,), {})("boom"), type("ReadError", (Exception,), {})("x"), OSError("[WinError 10054] reset"),
                                 RuntimeError("getaddrinfo failed"), TimeoutError("timed out")])
def test_a_temporary_network_error_waits_and_tries_again_up_to_five_attempts(err):
    client, clock = FakeClient(), Clock()
    a = company(client, "AAA")

    def net(task):
        raise err

    r = runner(client, executors={"score": net}, clock=clock)
    r.queue.enqueue(a, "score", None, "first", 3)
    waits = []
    for attempt in range(1, 6):
        rep = r.run()
        t = r.queue.list(a)[0]
        if attempt < 5:
            assert t["state"] == "queued" and t["attempts"] == attempt and rep.retried
            waits.append((datetime.fromisoformat(t["next_run_at"]) - clock.t).total_seconds() / 60)
            clock.t = datetime.fromisoformat(t["next_run_at"])
    assert t["state"] == "failed" and t["attempts"] == 5 and waits == [1, 2, 4, 8]


def test_a_permanent_error_fails_after_three_attempts():
    client, clock = FakeClient(), Clock()
    a = company(client, "AAA")

    def bad(task):
        raise ValueError("a bug")

    r = runner(client, executors={"score": bad}, clock=clock)
    r.queue.enqueue(a, "score", None, "first", 3)
    for _ in range(3):
        r.run()
        t = r.queue.list(a)[0]
        clock.t = datetime.fromisoformat(t["next_run_at"])
    assert t["state"] == "failed" and t["attempts"] == 3


def test_the_run_waits_for_a_due_network_retry_when_it_may_sleep():
    client, clock = FakeClient(), Clock()
    a = company(client, "AAA")
    calls = {"n": 0}

    def flaky(task):
        calls["n"] += 1
        if calls["n"] == 1:
            raise type("ConnectError", (Exception,), {})("down")
        return {}

    slept = []
    r = runner(client, executors={"score": flaky}, clock=clock, sleep=lambda s: (slept.append(s), setattr(clock, "t", datetime.fromtimestamp(clock.t.timestamp() + s, timezone.utc))))
    r.queue.enqueue(a, "score", None, "first", 3)
    rep = r.run()
    assert r.queue.list(a)[0]["state"] == "done" and calls["n"] == 2 and 60 <= rep.waited_seconds < 70 and len(rep.retried) == 1


def test_is_transient_sees_through_a_wrapper():
    try:
        try:
            raise type("ReadError", (Exception,), {})("reset")
        except Exception as e:
            raise RuntimeError("model call failed") from e
    except RuntimeError as w:
        assert is_transient(w)
    assert not is_transient(ValueError("bad value"))


def test_keep_awake_asks_windows_and_releases(monkeypatch):
    calls = []
    monkeypatch.setattr(awake, "_set", lambda flags: calls.append(flags) or True)
    with awake.keep_awake() as ok:
        assert ok
    assert calls == [awake.ES_CONTINUOUS | awake.ES_SYSTEM_REQUIRED, awake.ES_CONTINUOUS]


def test_a_direct_load_retries_a_temporary_network_error_like_the_queue():
    from src.pipeline.net_retry import with_network_retry
    calls, slept = {"n": 0}, []

    def load():
        calls["n"] += 1
        if calls["n"] < 3:
            raise type("ReadError", (Exception,), {})("[WinError 10054] reset")
        return "loaded"

    out, waited = with_network_retry(load, sleep=slept.append, log=lambda m: None)
    assert out == "loaded" and slept == [60, 120] and waited == 180

    def bad():
        raise ValueError("a bug")
    with pytest.raises(ValueError):
        with_network_retry(bad, sleep=slept.append, log=lambda m: None)


def test_a_direct_load_gives_up_after_five_attempts():
    from src.pipeline.net_retry import with_network_retry
    n = {"c": 0}

    def down():
        n["c"] += 1
        raise type("ConnectError", (Exception,), {})("down")
    with pytest.raises(Exception):
        with_network_retry(down, sleep=lambda s: None, log=lambda m: None)
    assert n["c"] == 5


def test_rows_of_an_older_skill_version_are_retired_when_the_new_version_has_the_period():
    from src.ai.prompt import extraction_blocks
    ver = str(next(b["version"] for b in extraction_blocks().values() if b["skill_id"] == "EXT-INS-INV"))
    client = FakeClient()
    a = company(client, "AAA")
    mk = lambda key, v, per, src=None: client.table("extraction_items").insert({"company_id": a, "item_key": key, "period": per, "skill_id": "EXT-INS-INV", "skill_version": v, "approval_status": "approved", "approval_source": src}).execute()   # noqa: E731
    mk("old_a", "1", "FY2025")
    mk("old_h", "1", "FY2025", "human_review")
    mk("old_b", "1", "FY2024")                                   # no row of the new version for this period: stays
    mk("new_a", ver, "FY2025")
    r = runner(client)
    assert r.retire_old_skill_rows(a) == 1
    st = {x["item_key"]: x["approval_status"] for x in client.tables["extraction_items"]}
    assert st == {"old_a": "rejected", "old_h": "approved", "old_b": "approved", "new_a": "approved"}


def test_the_heartbeat_writes_a_line_and_flags_a_gap_much_longer_than_the_interval():
    from src.sched.awake import Heartbeat
    t = {"now": 1000.0}
    lines = []
    hb = Heartbeat(300, emit=lines.append, wall=lambda: t["now"])
    hb.beat()
    t["now"] += 300
    assert "GAP" not in hb.beat()
    t["now"] += 7000                                              # the computer slept for about two hours
    assert "GAP" in hb.beat() and "asleep" in lines[-1]
    assert lines[0].startswith("[heartbeat]") and "+0 s" in lines[0]

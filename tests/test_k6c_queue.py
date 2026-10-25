"""K6c: the work queue (order, priority, uniqueness, retries), the queue runner (budget, deferral, waiting for earlier tasks), the attempt cap of the model client. Fake database, no network."""
from datetime import datetime, timedelta, timezone

import pytest

from fakedb import FakeClient
from src.ai.content import BudgetExceeded
from src.pipeline.queue_runner import CappedGemini, QueueRunner, next_reset
from src.repositories.work_queue_repository import MAX_ATTEMPTS, WorkQueueRepository, task_rank

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def repo(client=None, clock=None):
    return WorkQueueRepository(client or FakeClient(), now=clock or Clock())


def test_the_same_open_task_is_queued_once_and_a_user_request_lifts_its_priority():
    q = repo()
    a, s1 = q.enqueue(1, "ai_assess", 2025, None, 3)
    b, s2 = q.enqueue(1, "ai_assess", 2025, None, 1)
    assert (s1, s2) == ("queued", "exists") and a["id"] == b["id"] and b["priority"] == 1
    c, s3 = q.enqueue(1, "ai_assess", 2024, None, 3)                                    # another year is another task
    assert s3 == "queued" and c["id"] != a["id"]
    q.done(q.claim(q.runnable()[0]))
    assert q.enqueue(1, "ai_assess", 2025, None, 3)[1] == "queued"                      # a finished task can be queued again


def test_order_priority_then_the_jobs_of_a_company_in_their_order_and_the_final_score_after_the_ai():
    q = repo()
    for c, jt, sk in [(2, "analysis", None), (2, "score", "final"), (2, "ai_background", None), (2, "ai_assess", None), (2, "ai_extract", None), (2, "ai_classify", None), (2, "score", "first"),
                      (1, "ai_assess", None), (3, "score", "first")]:
        q.enqueue(c, jt, None, sk, 3 if c != 3 else 1)
    order = [(t["company_id"], t["job_type"], t.get("skill")) for t in q.runnable()]
    assert order[0] == (3, "score", "first")                                            # priority 1 first, whatever the company
    assert [o[1:] for o in order if o[0] == 2] == [("score", "first"), ("ai_classify", None), ("ai_extract", None), ("ai_assess", None), ("ai_background", None), ("score", "final"), ("analysis", None)]
    assert task_rank({"job_type": "score", "skill": "final"}) > task_rank({"job_type": "ai_background", "skill": None})


def test_a_task_waits_for_the_open_tasks_before_it_in_its_company():
    q = repo()
    first, _ = q.enqueue(1, "score", None, "first", 3)
    ai, _ = q.enqueue(1, "ai_assess", 2025, None, 3)
    fin, _ = q.enqueue(1, "score", None, "final", 3)
    assert q.open_before(first) == [] and [t["id"] for t in q.open_before(fin)] == [first["id"], ai["id"]]
    q.done(q.claim(first))
    assert [t["id"] for t in q.open_before(fin)] == [ai["id"]]


def test_retries_then_failed_and_a_deferred_task_returns_after_the_reset():
    clock = Clock()
    q = repo(clock=clock)
    t, _ = q.enqueue(1, "score", None, "first", 3)
    for n in range(MAX_ATTEMPTS):
        t = q.claim(q.client.table("work_queue").select("*").eq("id", t["id"]).execute().data[0])
        t = q.fail(t, "boom")
        assert t["state"] == ("failed" if n == MAX_ATTEMPTS - 1 else "queued")
        clock.t += timedelta(hours=2)
    assert q.runnable() == []
    d, _ = q.enqueue(2, "ai_assess", 2025, None, 3)
    d = q.defer(q.claim(d), next_reset(clock()))
    assert d["state"] == "deferred_quota" and d["attempts"] == 0 and q.runnable() == []
    clock.t = next_reset(clock()) + timedelta(minutes=1)
    assert [x["id"] for x in q.runnable()] == [d["id"]]                                 # nothing is lost: it runs after the reset


def test_next_reset_is_ten_oclock_israel_time():
    assert next_reset(datetime(2026, 10, 25, 5, 0, tzinfo=timezone.utc)) == datetime(2026, 10, 25, 8, 0, tzinfo=timezone.utc)      # 10:00 in Israel (UTC+2 after the clock change of 2026-10-25)
    assert next_reset(datetime(2026, 10, 25, 8, 0, tzinfo=timezone.utc)) == datetime(2026, 10, 26, 8, 0, tzinfo=timezone.utc)


class Inner:
    model = "fake"

    def __init__(self):
        self.sent = 0

    def generate(self, prompt, seed_offset=0, **kw):
        self.sent += 1
        return type("Reply", (), {"text": "ok", "model": "fake"})()


def test_the_model_client_cap_counts_attempts_and_refuses_the_call_over_the_cap():
    inner = Inner()
    g = CappedGemini(inner, 2)
    g.generate("a")
    g.generate("b")
    with pytest.raises(BudgetExceeded):
        g.generate("c")
    assert inner.sent == 2 and g.attempts == 2


def make_runner(client, gemini=None, budget=0, clock=None, executors=None):
    return QueueRunner(client, gemini=gemini, budget=budget, now=clock or Clock(), executors=executors, results_dir=__import__("pathlib").Path("scripts/output_k6c/test_results_unused"))


def add_company(client, symbol="ACM"):
    client.table("companies").insert({"symbol": symbol, "company_name": symbol, "exchange": "US", "country": "US", "reporting_currency": "USD"}).execute()
    return client.tables["companies"][-1]["id"]


def test_the_budget_stops_ai_tasks_and_the_next_run_continues_without_asking_twice(monkeypatch):
    monkeypatch.setattr("src.pipeline.queue_runner.S.seed_results", lambda *a, **k: 0)
    client, clock = FakeClient(), Clock()
    cid = add_company(client)
    answers = {}                                                                         # the "store": a stored answer is never asked again
    inner = Inner()

    def assess(runner, task):
        for k in range(2):                                                               # a task needs two model calls
            key = (task["skill"], k)
            if key not in answers:
                runner.gemini.generate("question")
                answers[key] = "answer"
        return {"asked": 2}

    def make(budget):
        r = make_runner(client, gemini=inner, budget=budget, clock=clock)
        r.executors["ai_assess"] = lambda task, r=r: assess(r, task)
        return r
    r1 = make(5)
    for i in range(4):
        r1.queue.enqueue(cid, "ai_assess", 2025, f"S{i}", 3)
    rep1 = r1.run()
    assert rep1.attempts == 5 and len(rep1.done) == 2 and len(rep1.deferred) == 1          # S0, S1 done (4 calls); S2 got one call, then the cap: deferred, not failed
    states = {t["skill"]: t["state"] for t in r1.queue.list(cid)}
    assert states == {"S0": "done", "S1": "done", "S2": "deferred_quota", "S3": "queued"}
    assert inner.sent == 5
    clock.t = next_reset(clock()) + timedelta(minutes=1)                                  # the quota is back
    r2 = make(10)
    r2.run()
    states = {t["skill"]: t["state"] for t in r2.queue.list(cid) if t["job_type"] == "ai_assess"}
    assert states == {"S0": "done", "S1": "done", "S2": "done", "S3": "done"}
    follow = {(t["job_type"], t["skill"]): t["state"] for t in r2.queue.list(cid) if t["job_type"] != "ai_assess"}
    assert follow == {("score", "final"): "queued", ("analysis", None): "queued"}                # the last AI task of the company queues the score with the AI answers and D2
    assert inner.sent == 8 and len(answers) == 8                                           # 3 more calls only: S2's second call, S3's two: no answer was asked twice


def test_a_company_without_budget_still_gets_its_data_tasks_and_the_ai_tasks_wait(monkeypatch):
    monkeypatch.setattr("src.pipeline.queue_runner.S.seed_results", lambda *a, **k: 0)
    client = FakeClient()
    cid = add_company(client)
    ran = []
    r = make_runner(client, budget=0, executors={"score": lambda t: ran.append(("score", t["skill"])) or {}, "ai_assess": lambda t: ran.append("ai") or {}, "analysis": lambda t: ran.append("analysis") or {}})
    r.queue.enqueue(cid, "score", None, "first", 1)
    r.queue.enqueue(cid, "ai_assess", 2025, None, 1)
    r.queue.enqueue(cid, "score", None, "final", 1)
    r.queue.enqueue(cid, "analysis", None, None, 1)
    rep = r.run()
    assert ran == [("score", "first")] and len(rep.done) == 1                              # the AI task waits (queued), and the final score and D2 wait for it
    assert {t["job_type"] + (t["skill"] or ""): t["state"] for t in r.queue.list(cid)} == {"scorefirst": "done", "ai_assess": "queued", "scorefinal": "queued", "analysis": "queued"}


def test_a_failing_task_is_recorded_and_the_loop_goes_on(monkeypatch):
    monkeypatch.setattr("src.pipeline.queue_runner.S.seed_results", lambda *a, **k: 0)
    client = FakeClient()
    c1, c2 = add_company(client, "AAA"), add_company(client, "BBB")

    def score(t):
        if t["company_id"] == c1:
            raise RuntimeError("no profile yet")
        return {"ok": True}
    r = make_runner(client, executors={"score": score})
    r.queue.enqueue(c1, "score", None, "first", 3)
    r.queue.enqueue(c2, "score", None, "first", 3)
    rep = r.run()
    assert [x[3] for x in rep.done] == ["BBB"] and rep.failed[0][3] == "no profile yet"
    row = next(t for t in r.queue.list(c1))
    assert row["state"] == "queued" and row["attempts"] == 1 and "no profile yet" in row["last_error"]

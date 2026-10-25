"""K6c section 8.2 on the TEST database (refuses VC_DB_TARGET=prod): the quota test and the idempotency of the queue. No model is called (a counting stub stands in for it).

  quota          a run budget of 10 request attempts: the queue stops at 10, the task that hit the cap is deferred (not failed), the next run (after the reset) continues, and no answer is asked twice
  idempotency    queueing the same task twice gives one task; a second score of an unchanged company writes no new run
The tasks it creates are deleted at the end (they are this script's own).

    .venv/Scripts/python scripts/k6c_acceptance.py [--ticker AVB] [--out scripts/output_k6c/acceptance.json]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target, get_supabase_client  # noqa: E402
from src.pipeline.queue_runner import QueueRunner  # noqa: E402
from src.repositories.score_repository import ScoreRepository  # noqa: E402

RESULTS: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"test": name, "pass": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  - {detail}" if detail else ""))


class CountingModel:
    """Stands in for Gemini: counts the calls, returns text."""
    model = "stub"

    def __init__(self):
        self.sent = 0

    def generate(self, prompt, seed_offset=0, **kw):
        self.sent += 1
        return type("Reply", (), {"text": "answer", "model": "stub"})()


def main(argv) -> int:
    if db_target() == "prod":
        raise SystemExit("refused for VC_DB_TARGET=prod")
    ticker = argv[argv.index("--ticker") + 1] if "--ticker" in argv else "AVB"
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    client = get_supabase_client()
    print(f"[database target: {db_target()}]  queue test company: {ticker}")
    cid = client.table("companies").select("id").eq("symbol", ticker).eq("exchange", "US").execute().data[0]["id"]
    client.table("work_queue").delete().eq("company_id", cid).execute()
    model, answers = CountingModel(), {}

    def make(budget: int) -> QueueRunner:
        r = QueueRunner(client, gemini=model, budget=budget, results_dir=ROOT / "scripts" / "output_k6c" / "results")

        def assess(task, r=r):
            for k in range(2):                                          # a task needs two model calls; a stored answer is not asked again
                if (task["skill"], k) not in answers:
                    r.gemini.generate("question")
                    answers[(task["skill"], k)] = "answer"
            return {"asked": 2}
        r.executors["ai_assess"] = assess
        return r

    print("quota: budget 10, 8 tasks of 2 calls each")
    r1 = make(10)
    for i in range(8):
        r1.queue.enqueue(cid, "ai_assess", 2025, f"Q{i}", 3)
    rep = r1.run(only={ticker})
    st = {t["skill"]: t["state"] for t in r1.queue.list(cid)}
    check("quota: the queue stops at the budget", rep.attempts == 10 and model.sent == 10 and sum(1 for s in st.values() if s == "done") == 5, f"attempts {rep.attempts}, done {sum(1 for s in st.values() if s == 'done')}, states {sorted(set(st.values()))}")
    r_open = [t for t in r1.queue.list(cid) if t["state"] != "done"]
    check("quota: the rest waits (queued), nothing failed", all(t["state"] in ("queued", "deferred_quota") for t in r_open) and not rep.failed, f"{[t['state'] for t in r_open]} failed={rep.failed}")
    # the next day: the reset has passed
    for t in r_open:
        client.table("work_queue").update({"next_run_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}).eq("id", t["id"]).execute()
    r2 = make(10)
    rep2 = r2.run(only={ticker})
    st2 = {t["skill"]: t["state"] for t in r2.queue.list(cid)}
    check("quota: the next run continues and finishes", set(st2.values()) == {"done"} and not rep2.failed, f"states {sorted(set(st2.values()))}, attempts {rep2.attempts}")
    check("quota: no answer was asked twice", model.sent == 16 and len(answers) == 16, f"{model.sent} calls for {len(answers)} answers")

    print("idempotency")
    t1, s1 = r2.queue.enqueue(cid, "ai_assess", 2025, "Z", 3)
    t2, s2 = r2.queue.enqueue(cid, "ai_assess", 2025, "Z", 3)
    check("the same open task is queued once", (s1, s2) == ("queued", "exists") and t1["id"] == t2["id"])
    scores = ScoreRepository(client)
    ko = client.table("companies").select("id").eq("symbol", "KO").eq("exchange", "US").execute().data[0]["id"]
    runs_before = len(client.table("score_runs").select("id").eq("company_id", ko).execute().data)
    q = QueueRunner(client, results_dir=ROOT / "scripts" / "output_k6c" / "results")
    q.enqueue(ko, "score", None, "first", 3)
    q.run(max_tasks=1, only={"KO"})
    q.enqueue(ko, "score", None, "first", 3)
    q.run(max_tasks=1, only={"KO"})
    runs_after = len(client.table("score_runs").select("id").eq("company_id", ko).execute().data)
    check("scoring an unchanged company twice adds at most one run", runs_after - runs_before <= 1, f"runs before {runs_before}, after {runs_after}")

    client.table("work_queue").delete().eq("company_id", cid).execute()
    bad = [r for r in RESULTS if not r["pass"]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} passed")
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

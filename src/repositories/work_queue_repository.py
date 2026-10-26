"""The work queue (K6c, table ``work_queue``): one queue for data jobs and AI tasks. Only the runner (service role) uses it.

A task is *open* while it is ``queued``, ``running`` or ``deferred_quota``; the same open task is queued once (``enqueue`` returns the existing one). ``next_task`` picks by priority (K6 spec 2.8, decided
2026-10-26: 1 a user asked, 2 data completion, 3 a new annual report, 4 wide loading), then the order of the jobs inside a company (``JOB_ORDER``), then age. A task that ran out of budget is
``deferred_quota`` with the next reset as its time; nothing is lost. A failed attempt goes back to ``queued`` with a delay until ``MAX_ATTEMPTS`` is reached.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.db import get_supabase_client

PRIORITY = {"user": 1, "completion": 2, "new_report": 3, "bulk": 4}
JOB_PRIORITY = {"initial_import": PRIORITY["completion"], "backfill": PRIORITY["completion"], "repair": PRIORITY["completion"], "new_report": PRIORITY["new_report"],
                "amendment": PRIORITY["new_report"]}

OPEN = ("queued", "running", "deferred_quota")
RUNNABLE = ("queued", "deferred_quota")
MAX_ATTEMPTS = 3
RETRY_DELAY = timedelta(minutes=10)
# the order of the jobs inside one company (K6 spec 2.8): the first score, then C1, B, A, the score with the AI answers, D2, and last the background text (D1 + T1). The background does not
# gate the score: the company is `complete` when its final score is written and no scoring item waits for the AI; a failed or waiting background is shown by itself (v_company_status).
JOB_ORDER = {"initial_import": 0, "backfill": 0, "new_report": 0, "amendment": 0, "repair": 0, "score": 1, "ai_classify": 2, "ai_extract": 3, "ai_assess": 4, "analysis": 7, "ai_background": 8}
SCORING_AI = ("ai_classify", "ai_extract", "ai_assess")          # the AI tasks whose answers feed the score
FINAL_SCORE_RANK = 6                       # skill "final" of a score task runs after the scoring AI tasks


def task_rank(t: dict) -> int:
    return FINAL_SCORE_RANK if (t["job_type"] == "score" and t.get("skill") == "final") else JOB_ORDER[t["job_type"]]


class WorkQueueRepository:
    def __init__(self, client=None, now=None):
        self.client = client or get_supabase_client()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _find_open(self, company_id, job_type, fiscal_year, skill) -> Optional[dict]:
        q = self.client.table("work_queue").select("*").eq("job_type", job_type)
        q = q.eq("company_id", company_id) if company_id is not None else q
        for r in q.execute().data:
            if r["state"] in OPEN and r["company_id"] == company_id and r["fiscal_year"] == fiscal_year and (r["skill"] or None) == (skill or None):
                return r
        return None

    def enqueue(self, company_id: Optional[int], job_type: str, fiscal_year: Optional[int] = None, skill: Optional[str] = None, priority: int = 3, payload: Optional[dict] = None) -> tuple:
        """-> (task row, "queued" | "exists"). A user's request (priority 1) lifts an open task of a lower priority."""
        old = self._find_open(company_id, job_type, fiscal_year, skill)
        if old:
            if priority < old["priority"]:
                old = self.client.table("work_queue").update({"priority": priority, "updated_at": self._now().isoformat()}).eq("id", old["id"]).execute().data[0]
            return old, "exists"
        row = {"company_id": company_id, "job_type": job_type, "fiscal_year": fiscal_year, "skill": skill, "priority": priority, "payload": payload or {}, "state": "queued", "attempts": 0,
               "last_error": None, "next_run_at": self._now().isoformat()}
        return self.client.table("work_queue").insert(row).execute().data[0], "queued"

    def runnable(self) -> list:
        """The tasks that may run now, in the order they should run."""
        now = self._now().isoformat()
        rows = [r for r in self.client.table("work_queue").select("*").execute().data if r["state"] in RUNNABLE and r["next_run_at"] <= now]
        return sorted(rows, key=lambda r: (r["priority"], r["company_id"] or 0, task_rank(r), r["fiscal_year"] or 0, r["skill"] or "", r["id"]))

    def open_before(self, task: dict) -> list:
        """Open tasks of the same company that come earlier in the order (a task waits for them)."""
        mine = task_rank(task)
        return [r for r in self.client.table("work_queue").select("*").eq("company_id", task["company_id"]).execute().data
                if r["id"] != task["id"] and r["state"] in OPEN and task_rank(r) < mine]

    def claim(self, task: dict) -> dict:
        return self.client.table("work_queue").update({"state": "running", "attempts": task["attempts"] + 1, "updated_at": self._now().isoformat()}).eq("id", task["id"]).execute().data[0]

    def done(self, task: dict, payload: Optional[dict] = None) -> dict:
        fields = {"state": "done", "last_error": None, "updated_at": self._now().isoformat()}
        if payload is not None:
            fields["payload"] = {**(task.get("payload") or {}), "result": payload}
        return self.client.table("work_queue").update(fields).eq("id", task["id"]).execute().data[0]

    def fail(self, task: dict, error: str) -> dict:
        """A failed attempt: queued again after a delay, failed for good after MAX_ATTEMPTS."""
        final = task["attempts"] >= MAX_ATTEMPTS
        fields = {"state": "failed" if final else "queued", "last_error": str(error)[:500], "updated_at": self._now().isoformat(),
                  "next_run_at": (self._now() + RETRY_DELAY * task["attempts"]).isoformat()}
        return self.client.table("work_queue").update(fields).eq("id", task["id"]).execute().data[0]

    def defer(self, task: dict, until: datetime, reason: str = "daily budget spent") -> dict:
        """Out of budget: the attempt does not count; the task waits for the next reset."""
        return self.client.table("work_queue").update({"state": "deferred_quota", "attempts": max(0, task["attempts"] - 1), "next_run_at": until.isoformat(), "last_error": reason,
                                                       "updated_at": self._now().isoformat()}).eq("id", task["id"]).execute().data[0]

    def counts(self, company_id: Optional[int] = None) -> dict:
        q = self.client.table("work_queue").select("job_type,state,priority,company_id")
        rows = q.eq("company_id", company_id).execute().data if company_id is not None else q.execute().data
        out: dict = {}
        for r in rows:
            out[r["state"]] = out.get(r["state"], 0) + 1
        return out

    def list(self, company_id: Optional[int] = None) -> list:
        q = self.client.table("work_queue").select("*")
        rows = q.eq("company_id", company_id).execute().data if company_id is not None else q.execute().data
        return sorted(rows, key=lambda r: r["id"])

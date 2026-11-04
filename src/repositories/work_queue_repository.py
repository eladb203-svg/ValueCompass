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

OPEN = ("queued", "running", "deferred_quota", "deferred_network")
RUNNABLE = ("queued", "deferred_quota", "deferred_network")
NETWORK_ROUNDS = 6                       # K6d-2 fixes: after 5 attempts lost to a network error the task waits 30 minutes (deferred_network) and returns, up to 6 times; only a permanent error fails it
NETWORK_ROUND_WAIT = timedelta(minutes=30)
MAX_ATTEMPTS = 3
MAX_TRANSIENT_ATTEMPTS = 5                  # K6d-2 fixes: a temporary network error (ConnectError, ReadError, timeout, DNS) goes back to the queue with a wait, up to 5 attempts
NETWORK_MARK = "[network] "                 # last_error of a task that waits for a network retry
TRANSIENT_DELAY = timedelta(minutes=1)      # waits 1, 2, 4, 8 minutes after attempt 1, 2, 3, 4
RETRY_DELAY = timedelta(minutes=10)
STALE_RUNNING = timedelta(minutes=30)       # a task that has been `running` this long was cut off (a dropped connection, a killed process): the run is single-process, so nobody else owns it
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

    def _all(self, company_id: Optional[int] = None) -> list:
        """Every row of the queue (or of one company), page by page: the API returns at most 1000 rows per request, and the queue passed 1000 rows (calibration stage, 2026-11-04: the newest tasks were invisible to the runner)."""
        out, start = [], 0
        while True:
            q = self.client.table("work_queue").select("*")
            if company_id is not None:
                q = q.eq("company_id", company_id)
            page = q.order("id").range(start, start + 999).execute().data
            out += page
            if len(page) < 1000:
                return out
            start += 1000

    def runnable(self, sticky: Optional[dict] = None) -> list:
        """The tasks that may run now, in the order they should run: company after company until it is finished (K6d-2 fixes, decided 2026-10-29). The company's turn is set by the best
        priority among its open tasks and then by its arrival (its oldest open task); inside the company the tasks follow the job order. Tasks of different companies are not mixed.
        ``sticky``: a dict the caller keeps for the length of a run, so that the turn of a company does not change while its own tasks finish."""
        now = self._now().isoformat()
        allrows = self._all()
        group: dict = {}
        for r in allrows:
            if r["state"] in OPEN:
                g = group.setdefault(r["company_id"], [99, r["id"]])
                g[0], g[1] = min(g[0], r["priority"]), min(g[1], r["id"])
        if sticky is not None:
            for cid, g in group.items():
                g[0], g[1] = sticky.setdefault(cid, (g[0], g[1]))
        rows = [r for r in allrows if r["state"] in RUNNABLE and r["next_run_at"] <= now]
        return sorted(rows, key=lambda r: (group[r["company_id"]][0], group[r["company_id"]][1] if r["company_id"] is not None else r["id"], r["company_id"] or 0, task_rank(r),
                                           r["fiscal_year"] or 0, r["skill"] or "", r["id"]))

    def next_wait(self, labels_of: Optional[set] = None) -> Optional[datetime]:
        """The earliest time a queued task that is only waiting for its retry time becomes runnable (None when there is none). ``labels_of``: company ids to look at."""
        now = self._now().isoformat()
        times = [r["next_run_at"] for r in self._all()
                 if r["state"] in ("queued", "deferred_network") and r["next_run_at"] > now and str(r.get("last_error") or "").startswith(NETWORK_MARK) and (labels_of is None or r["company_id"] in labels_of)]
        return datetime.fromisoformat(min(times)) if times else None

    def open_before(self, task: dict) -> list:
        """Open tasks of the same company that come earlier in the order (a task waits for them)."""
        mine = task_rank(task)
        return [r for r in self.client.table("work_queue").select("*").eq("company_id", task["company_id"]).execute().data
                if r["id"] != task["id"] and r["state"] in OPEN and task_rank(r) < mine]

    def claim(self, task: dict) -> dict:
        return self.client.table("work_queue").update({"state": "running", "attempts": task["attempts"] + 1, "updated_at": self._now().isoformat()}).eq("id", task["id"]).execute().data[0]

    def recover_stale(self, max_age: timedelta = STALE_RUNNING) -> list:
        """K6d-2: a task left `running` by a process that died goes back to `queued` (or `failed` when it has used all its attempts). -> the recovered task rows."""
        cutoff = self._now() - max_age
        out = []
        for r in self.client.table("work_queue").select("*").eq("state", "running").execute().data:
            if datetime.fromisoformat(r["updated_at"]) >= cutoff:
                continue
            final = r["attempts"] >= MAX_ATTEMPTS
            out.append(self.client.table("work_queue").update({"state": "failed" if final else "queued", "next_run_at": self._now().isoformat(), "updated_at": self._now().isoformat(),
                                                               "last_error": f"interrupted: running since {r['updated_at'][:16]} without finishing; " + ("out of attempts" if final else "queued again")}
                                                              ).eq("id", r["id"]).execute().data[0])
        return out

    def done(self, task: dict, payload: Optional[dict] = None) -> dict:
        fields = {"state": "done", "last_error": None, "updated_at": self._now().isoformat()}
        if payload is not None:
            fields["payload"] = {**(task.get("payload") or {}), "result": payload}
        return self.client.table("work_queue").update(fields).eq("id", task["id"]).execute().data[0]

    def fail(self, task: dict, error: str, transient: bool = False) -> dict:
        """A failed attempt: queued again after a delay, failed for good after MAX_ATTEMPTS (3). A temporary network error (``transient``) waits 1, 2, 4, 8 minutes and has 5 attempts."""
        final = task["attempts"] >= (MAX_TRANSIENT_ATTEMPTS if transient else MAX_ATTEMPTS)
        if transient and final:
            rounds = int((task.get("payload") or {}).get("network_rounds", 0))
            if rounds < NETWORK_ROUNDS:                                   # the five attempts are used by a network error: not failed - 30 minutes in deferred_network, then the attempts start again
                payload = {**(task.get("payload") or {}), "network_rounds": rounds + 1}
                fields = {"state": "deferred_network", "attempts": 0, "payload": payload, "last_error": (NETWORK_MARK + f"network round {rounds + 1} of {NETWORK_ROUNDS}: " + str(error))[:500],
                          "updated_at": self._now().isoformat(), "next_run_at": (self._now() + NETWORK_ROUND_WAIT).isoformat()}
                return self.client.table("work_queue").update(fields).eq("id", task["id"]).execute().data[0]
        delay = TRANSIENT_DELAY * (2 ** max(0, task["attempts"] - 1)) if transient else RETRY_DELAY * task["attempts"]
        fields = {"state": "failed" if final else "queued", "last_error": ((NETWORK_MARK if transient else "") + str(error))[:500], "updated_at": self._now().isoformat(), "next_run_at": (self._now() + delay).isoformat()}
        return self.client.table("work_queue").update(fields).eq("id", task["id"]).execute().data[0]

    def fail_for_good(self, task: dict, reason: str) -> dict:
        return self.client.table("work_queue").update({"state": "failed", "last_error": str(reason)[:500], "updated_at": self._now().isoformat()}).eq("id", task["id"]).execute().data[0]

    def release(self, task: dict, reason: str) -> dict:
        """The run ran out of its own request budget (not the daily cap): the task goes back to ``queued``, due now, the attempt does not count. Nothing is postponed to another day."""
        return self.client.table("work_queue").update({"state": "queued", "attempts": max(0, task["attempts"] - 1), "next_run_at": self._now().isoformat(), "last_error": reason[:200],
                                                       "updated_at": self._now().isoformat()}).eq("id", task["id"]).execute().data[0]

    def add_calls(self, task: dict, calls: int) -> dict:
        """The model request attempts this task has used (summed over its attempts), kept in its payload: the per-company limit counts them."""
        if calls <= 0:
            return task
        payload = {**(task.get("payload") or {}), "calls": int((task.get("payload") or {}).get("calls", 0)) + int(calls)}
        task["payload"] = payload
        self.client.table("work_queue").update({"payload": payload}).eq("id", task["id"]).execute()
        return task

    def company_calls(self, company_id: int, fiscal_year: Optional[int]) -> int:
        """Model request attempts already used for one company's annual report (tasks of that fiscal year, or of no fiscal year)."""
        return sum(int((r.get("payload") or {}).get("calls", 0)) for r in self.client.table("work_queue").select("*").eq("company_id", company_id).execute().data
                   if r["fiscal_year"] in (None, fiscal_year))

    def defer(self, task: dict, until: datetime, reason: str = "daily budget spent") -> dict:
        """Out of budget: the attempt does not count; the task waits for the next reset."""
        return self.client.table("work_queue").update({"state": "deferred_quota", "attempts": max(0, task["attempts"] - 1), "next_run_at": until.isoformat(), "last_error": reason,
                                                       "updated_at": self._now().isoformat()}).eq("id", task["id"]).execute().data[0]

    def counts(self, company_id: Optional[int] = None) -> dict:
        rows = self._all(company_id)
        out: dict = {}
        for r in rows:
            out[r["state"]] = out.get(r["state"], 0) + 1
        return out

    def list(self, company_id: Optional[int] = None) -> list:
        return sorted(self._all(company_id), key=lambda r: r["id"])

"""The work queue runner (K6c, K6 spec 2.8 and section 3): picks tasks from ``work_queue`` and runs them, one at a time.

Order: priority (1 a user asked, 2 data completion, 3 a new annual report, 4 wide loading; K6 spec 2.8), then inside one company: the data job, the first score (without AI), C1, B extraction, A questions, BP background (BP-1 -> profile -> phrase translation -> rendering), the score
with the AI answers (``final``), D2. A task waits for the earlier open tasks of its company. A model call is made only through ``self.gemini`` (a ``CappedGemini``): every request attempt
counts against the run's budget, the company's limit (40 per annual report: a guard against loops) and the shared daily counter (cap 450). Only the daily cap postpones a task
(``deferred_quota`` until midnight Pacific = 10:00 Israel); a spent run budget leaves the task queued; the company limit fails the company and alerts the administrator.
Companies run one after the other until each is finished. Data tasks (import, score, D2) need no budget and keep running. A stored answer is never asked again (R18).
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from src.ai.content import BudgetExceeded
from src.ai.db_stores import DbAiItemStore, DbAssessmentStore, DbTextStore
from src.pipeline import scoring as S
from src.repositories.company_repository import CompanyRepository
from src.repositories.score_repository import ScoreRepository
from src.repositories.work_queue_repository import PRIORITY, SCORING_AI, WorkQueueRepository

ROOT = Path(__file__).resolve().parents[2]
ISRAEL = ZoneInfo("Asia/Jerusalem")
AI_JOBS = ("ai_classify", "ai_extract", "ai_assess", "ai_background")
DATA_JOBS = ("initial_import", "backfill", "new_report", "amendment", "repair")
MIN_SCORE_YEARS = 3                                      # K6d-2 fixes: fewer loaded fiscal years than this and the company has no score: a final state with the reason, no analysis / AI task
BLOCKS_OF = {"BANK": ["EXT-BANK-CAP", "EXT-BANK-LOANS"], "INSURANCE": ["EXT-INS-CAP", "EXT-INS-INV"],
             "INCOME_REAL_ESTATE": ["EXT-RE-OPS", "EXT-RE-MAINT", "EXT-RE-VALUE", "EXT-RE-LIQ", "EXT-RE-UNENC", "EXT-RE-NAV", "EXT-RE-OPU", "EXT-RE-FFO", "EXT-PROFILE"]}


COMPANY_CALL_CAP = 40                                  # model request attempts for one company's annual report: a guard against a loop, not a quota (K6d-2 fixes, 2026-10-29)
COMPANY_CAP_MSG = "company call limit"
MAX_RETRY_WAIT = 31 * 60                                # a run waits for a network retry that is due within this many seconds; a later one is left to the next run
TRANSIENT_TYPES = ("ConnectError", "ReadError", "ConnectTimeout", "ReadTimeout", "WriteError", "PoolTimeout", "TimeoutException", "Timeout", "TimeoutError", "gaierror", "ConnectionError",
                   "ConnectionResetError", "ConnectionAbortedError", "RemoteProtocolError", "NetworkError", "ServerDisconnectedError")
TRANSIENT_TEXT = ("WinError 10054", "WinError 10060", "WinError 10053", "getaddrinfo failed", "name resolution", "timed out", "Connection reset", "Connection aborted", "ConnectError", "ReadError")
ALERT_LOG = ROOT / "scripts" / "state" / "admin_alerts.log"


class QuotaSpent(Exception):
    """The run's budget or the shared daily cap is spent."""


def is_transient(e: BaseException) -> bool:
    """A temporary network error (ConnectError, ReadError, timeout, DNS), also when it is wrapped in another exception: the task is tried again later."""
    seen = set()
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if type(e).__name__ in TRANSIENT_TYPES or any(m in str(e) for m in TRANSIENT_TEXT):
            return True
        e = e.__cause__ or e.__context__
    return False


def next_reset(now: Optional[datetime] = None) -> datetime:
    """The next 10:00 Israel time (the Gemini daily quota resets at midnight Pacific)."""
    now = (now or datetime.now(timezone.utc)).astimezone(ISRAEL)
    t = now.replace(hour=10, minute=0, second=0, microsecond=0)
    return (t if t > now else t + timedelta(days=1)).astimezone(timezone.utc)


class CappedGemini:
    """Wraps the Gemini client: at most ``cap`` request attempts in this run (enforced here, before the shared daily counter)."""

    def __init__(self, inner, cap: int):
        self.inner, self.cap = inner, cap
        self.model = getattr(inner, "model", "")
        self.attempts = 0
        self.task_start, self.task_cap = 0, None          # the attempts the running task may still make for its company (set by the runner before each task)

    def check(self) -> None:
        if self.attempts >= self.cap:
            raise BudgetExceeded(f"run budget of {self.cap} request attempts reached")
        if self.task_cap is not None and self.attempts - self.task_start >= self.task_cap:
            raise BudgetExceeded(f"{COMPANY_CAP_MSG} reached ({COMPANY_CALL_CAP} request attempts for this annual report)")

    @property
    def calls(self) -> int:
        return self.attempts

    def generate(self, prompt: str, seed_offset: int = 0, **kw):
        self.check()
        inner_guard = getattr(self.inner, "_shared_guard", None)
        if inner_guard is not None:                         # count every attempt (also the retries inside one call)
            def guard():
                self.check()
                inner_guard()
                self.attempts += 1
            self.inner._shared_guard = guard
            try:
                return self.inner.generate(prompt, seed_offset=seed_offset, **kw)
            finally:
                self.inner._shared_guard = inner_guard
        self.attempts += 1
        return self.inner.generate(prompt, seed_offset=seed_offset, **kw)

    def __getattr__(self, name):
        return getattr(self.inner, name)


@dataclass
class RunReport:
    done: list = field(default_factory=list)
    failed: list = field(default_factory=list)
    deferred: list = field(default_factory=list)
    skipped_blocked: int = 0
    attempts: int = 0
    notes: list = field(default_factory=list)
    released: list = field(default_factory=list)           # tasks queued again because this run's own request budget was spent (never postponed to another day)
    retried: list = field(default_factory=list)            # tasks that hit a temporary network error and wait for another attempt
    alerts: list = field(default_factory=list)             # companies stopped by the per-company call limit (admin_alert)
    calls_by_company: dict = field(default_factory=dict)
    waited_seconds: float = 0.0                             # time spent waiting for network retries
    recovered: list = field(default_factory=list)          # K6d-2: (task id, job, company) of tasks a dead process left running, and companies whose state had no task behind it


class QueueRunner:
    def __init__(self, client, gemini=None, budget: int = 0, pipeline_factory: Optional[Callable] = None, results_dir: Path = S.RESULTS_DIR, now: Optional[Callable] = None,
                 executors: Optional[dict] = None, sleep: Optional[Callable] = None):
        self.client, self.budget, self.sleep = client, budget, sleep
        self._turns: dict = {}
        self.gemini = CappedGemini(gemini, budget) if (gemini is not None and budget > 0) else None
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.queue = WorkQueueRepository(client, now=self.now)
        self.companies, self.scores = CompanyRepository(client), ScoreRepository(client)
        self.ai_store, self.item_store, self.texts = DbAssessmentStore(client), DbAiItemStore(client), DbTextStore(client)
        self.pipeline_factory, self.results_dir = pipeline_factory, results_dir
        self.executors = {"initial_import": self.exec_import, "backfill": self.exec_import, "new_report": self.exec_import, "amendment": self.exec_import, "repair": self.exec_import,
                          "score": self.exec_score, "analysis": self.exec_analysis, "ai_classify": self.exec_classify, "ai_extract": self.exec_extract, "ai_assess": self.exec_assess,
                          "ai_background": self.exec_background, **(executors or {})}

    # ------------------------------------------------------------ helpers
    def ticker(self, company_id: int) -> str:
        return self.ai_store.co.symbol(company_id)

    def company(self, company_id: int) -> dict:
        return self.companies.get_by_id(company_id)

    def ai_allowed(self) -> bool:
        return self.gemini is not None and self.gemini.attempts < self.gemini.cap

    def load_result(self, ticker: str) -> Optional[dict]:
        """The stored result of the company. K6d-2 fixes: the engine of the company's profile first - a company routed to another engine after its first pass (VTR: general, then real estate) keeps
        the result file of the old engine, which has no ``inputs`` and used to win."""
        order = list(S.ENGINE_KEYS)
        try:
            co = self.companies.get_by_symbol(ticker, "US")
            if co and co.get("profile"):
                want = S.runner_engine(co["profile"], ticker)
                order = [want] + [e for e in order if e != want]
        except Exception:   # noqa: BLE001 - without a profile the old order stays
            pass
        for eng in order:
            p = self.results_dir / eng / f"{ticker}.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        return None

    def enqueue(self, company_id, job_type, fiscal_year=None, skill=None, priority=3, payload=None):
        return self.queue.enqueue(company_id, job_type, fiscal_year, skill, priority, payload)

    # ------------------------------------------------------------ the loop
    def run(self, max_tasks: int = 1000, only: Optional[set] = None) -> RunReport:
        """Run tasks until nothing is runnable. ``only``: tickers to restrict the run to."""
        rep = RunReport()
        S.seed_results(self.results_dir)
        self.only = {t.upper() for t in only} if only else None
        self._turns = {}
        self.recover(rep)
        for _ in range(max_tasks):
            task = self._next(rep)
            if task is None:
                if self._wait_retry(rep):
                    continue
                break
            is_ai = task["job_type"] in AI_JOBS and task.get("skill") != "render"
            remaining = COMPANY_CALL_CAP - self.queue.company_calls(task["company_id"], task["fiscal_year"]) if (is_ai and task["company_id"]) else None
            if remaining is not None and remaining <= 0:
                self._trip(task, rep, COMPANY_CALL_CAP - remaining)
                continue
            why = self.not_relevant(task)
            if why:
                self.queue.done(task, {"skipped": "not relevant: " + why})
                rep.done.append((task["id"], task["job_type"], task.get("skill"), self._label(task)))
                continue
            task = self.queue.claim(task)
            if task["job_type"] in SCORING_AI and task["company_id"]:
                self.companies.set_processing_state(task["company_id"], "ai_in_progress")
            before = self.gemini.attempts if self.gemini else 0
            if self.gemini:
                self.gemini.task_start, self.gemini.task_cap = before, remaining

            def book(task=task, before=before):
                calls = (self.gemini.attempts - before) if self.gemini else 0
                if calls:
                    rep.calls_by_company[self._label(task)] = rep.calls_by_company.get(self._label(task), 0) + calls
                    self.queue.add_calls(task, calls)

            try:
                payload = self.executors[task["job_type"]](task) or {}
                book()
                self.queue.done(task, payload)
                rep.done.append((task["id"], task["job_type"], task.get("skill"), self._label(task)))
                if task["job_type"] in SCORING_AI and task["company_id"]:
                    self.after_ai(task)
            except (BudgetExceeded, QuotaSpent) as e:
                book()
                if COMPANY_CAP_MSG in str(e):
                    self._trip(task, rep, self.queue.company_calls(task["company_id"], task["fiscal_year"]))
                else:                                               # the run's own budget: the task stays in the queue, due now; only the daily cap postpones work (below)
                    self.queue.release(task, str(e)[:200])
                    rep.released.append((task["id"], task["job_type"], self._label(task), str(e)[:120]))
            except RuntimeError as e:
                book()
                if "shared daily request cap" in str(e):
                    self.queue.defer(task, next_reset(self.now()), "daily request cap (450) spent; " + str(e)[:150])
                    rep.deferred.append((task["id"], task["job_type"], self._label(task), "shared daily cap"))
                else:
                    self._failed(task, e, rep)
            except Exception as e:   # noqa: BLE001 - a failed task is recorded, never dropped
                book()
                self._failed(task, e, rep)
        rep.attempts = self.gemini.attempts if self.gemini else 0
        return rep

    def _failed(self, task: dict, e: BaseException, rep: RunReport) -> None:
        """A failed attempt. A temporary network error waits and tries again (up to 5 attempts); anything else has 3 attempts."""
        transient = is_transient(e)
        row = self.queue.fail(task, f"{type(e).__name__}: {e}" + ("" if transient else f"\n{traceback.format_exc()[-300:]}"), transient=transient)
        if row["state"] == "deferred_network":
            rep.retried.append((task["id"], task["job_type"], self._label(task), f"5 attempts lost to the network: deferred_network until {row['next_run_at'][11:16]} UTC ({row['payload'].get('network_rounds')} of 6)"))
        elif transient and row["state"] == "queued":
            rep.retried.append((task["id"], task["job_type"], self._label(task), f"attempt {task['attempts']} of 5, next try {row['next_run_at'][11:16]} UTC: {type(e).__name__}"))
        else:
            rep.failed.append((task["id"], task["job_type"], self._label(task), (str(e) if isinstance(e, RuntimeError) else f"{type(e).__name__}: {e}")[:160]))
            if row["state"] == "failed" and task["job_type"] in SCORING_AI and task["company_id"]:
                self.mark_extraction_failed(task, str(e))

    def mark_extraction_failed(self, task: dict, error: str) -> None:
        """K6d-2 fixes: a score is final only after the extraction of the latest year ended. When that task fails for good the company is `failed` with the reason (in the queue row and the administrator log),
        and the score it already has is marked partial (``flags.partial`` of the run)."""
        cid = task["company_id"]
        reason = f"{task['job_type']} failed for good: {error[:200]}"
        try:
            self.companies.set_processing_state(cid, "failed", reason)
            run = self.client.table("score_runs").select("id,flags").eq("company_id", cid).order("id", desc=True).limit(1).execute().data
            if run:
                self.client.table("score_runs").update({"flags": {**(run[0].get("flags") or {}), "partial": reason}}).eq("id", run[0]["id"]).execute()
            self.alert(self._label(task), reason, {"company_id": cid, "task": task["job_type"]})
        except Exception:   # noqa: BLE001 - the marking never hides the failure itself
            pass

    def _wait_retry(self, rep: RunReport) -> bool:
        """Nothing is runnable but a task of this run waits for its network retry: wait for it (up to MAX_RETRY_WAIT) when the runner may sleep (the command line); the time is reported apart."""
        if self.sleep is None:
            return False
        ids = None
        if getattr(self, "only", None):
            ids = {co["id"] for co in (self.companies.get_by_symbol(t, "US") for t in self.only) if co}
        due = self.queue.next_wait(ids)                         # only tasks waiting for a network retry (a permanent failure is retried by a later run)
        if due is None:
            return False
        wait = (due - self.now()).total_seconds()
        if wait > MAX_RETRY_WAIT:
            return False
        self.sleep(max(1.0, wait) + 1.0)
        rep.waited_seconds += max(1.0, wait) + 1.0
        return True

    def _trip(self, task: dict, rep: RunReport, calls: int) -> None:
        """The company used its call limit for this annual report: a suspected loop. Its open tasks fail, the company is marked failed, the administrator is alerted. Not postponed to another day."""
        label, cid = self._label(task), task["company_id"]
        reason = f"חריגה ממספר הקריאות — חשד ללולאה ({calls} קריאות; הגבול {COMPANY_CALL_CAP} לדוח שנתי; {COMPANY_CAP_MSG})"
        for t in self.queue.list(cid):
            if t["state"] in ("queued", "running", "deferred_quota", "deferred_network"):
                self.queue.fail_for_good(t, reason)
        self.companies.set_processing_state(cid, "failed", reason)
        self.alert(label, reason, {"company_id": cid, "task": task["job_type"], "calls": calls})
        rep.alerts.append((label, reason))
        rep.failed.append((task["id"], task["job_type"], label, reason[:160]))

    def alert(self, label: str, reason: str, detail: dict) -> None:
        """An alert for the administrator: a row in ``support_tickets`` when the table exists, else a line marked ``admin_alert`` in the log (scripts/state/admin_alerts.log)."""
        try:
            self.client.table("support_tickets").insert({"kind": "admin_alert", "subject": f"{label}: {reason[:120]}", "body": json.dumps(detail, default=str)}).execute()
            return
        except Exception:   # noqa: BLE001 - the table does not exist yet (security stage): the log is the record
            pass
        line = f"{datetime.now(timezone.utc).isoformat()} admin_alert {label}: {reason} {json.dumps(detail, default=str)}"
        print(line, file=sys.stderr)
        try:
            ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with ALERT_LOG.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def recover(self, rep: RunReport) -> None:
        """K6d-2, automatic recovery at the start of every run (the manual and the scheduled one): (1) a task a dead process left `running` is queued again; (2) a company that says it is
        `ai_in_progress` / `scored_partial` but has no open task behind it gets the tasks it still needs (``plan_completion``), or its final score when nothing is missing - so no company stays
        half-done without a task that will finish it."""
        for t in self.queue.recover_stale():
            rep.recovered.append((t["id"], t["job_type"], self._label(t), t["state"]))
        for co in self.companies.client.table("companies").select("*").in_("processing_state", ["ai_in_progress", "scored_partial"]).execute().data:
            if getattr(self, "only", None) and co["symbol"] not in self.only:
                continue
            tasks = self.queue.list(co["id"])
            if any(t["state"] in ("queued", "running", "deferred_quota", "deferred_network", "failed") for t in tasks):          # a task that failed for good is looked at by a person, not re-planned on every run
                continue
            planned = self.plan_completion(co, PRIORITY["completion"])
            if not planned and not co.get("profile") and not self.scores.latest_run(co["id"]):         # a shell that was never loaded (no profile, no score): load it
                planned = [self.enqueue(co["id"], "initial_import", None, None, PRIORITY["completion"])[0]["id"]]
            if not planned and self.scores.latest_run(co["id"]):
                planned = [self.enqueue(co["id"], "score", None, "final", PRIORITY["completion"])[0]["id"]]
            if planned:
                rep.recovered.append((planned[0], "plan", co["symbol"], f"{len(planned)} task(s) planned for state {co['processing_state']}"))

    def after_ai(self, task: dict) -> None:
        """When the last open scoring AI task (C1, B, A) of a company is done: the score with the AI answers and D2 follow (both are idempotent), and the state goes back to scored_partial until that
        score decides. The background text is not waited for."""
        cid = task["company_id"]
        if any(t["job_type"] in SCORING_AI and t["state"] in ("queued", "running", "deferred_quota", "deferred_network") for t in self.queue.list(cid)):
            return
        self.enqueue(cid, "score", None, "final", task["priority"])
        self.enqueue(cid, "analysis", None, None, task["priority"])
        self.companies.set_processing_state(cid, "scored_partial")

    def _label(self, task: dict) -> str:
        try:
            return self.ticker(task["company_id"]) if task["company_id"] else "-"
        except Exception:   # noqa: BLE001
            return str(task["company_id"])

    def _next(self, rep: RunReport) -> Optional[dict]:
        for t in self.queue.runnable(self._turns):
            if getattr(self, "only", None) and self._label(t) not in self.only:
                continue
            if t["job_type"] in AI_JOBS and t.get("skill") != "render" and not self.ai_allowed():       # a render-only background task needs no model budget
                continue                                      # AI work waits (queued) while there is no budget
            if self.queue.open_before(t):
                rep.skipped_blocked += 1
                continue
            return t
        return None

    # ------------------------------------------------------------ data jobs
    def exec_import(self, task: dict) -> dict:
        if self.pipeline_factory is None:
            raise RuntimeError("no pipeline configured for data jobs")
        p = self.pipeline_factory()
        p.router_fallback = bool((task.get("payload") or {}).get("router_fallback"))
        res = p.load(self.ticker(task["company_id"]), task["job_type"])
        return self.after_load(res, task["company_id"], task["priority"])

    def after_load(self, res, company_id: int, priority: int) -> dict:
        """What follows a data job: the first score, or - when the router needs extraction that does not exist - the extraction request."""
        if res.status == "failed":
            raise RuntimeError(res.error or "load failed")
        if res.state == "unsupported":
            return {"status": res.status, "state": res.state}
        why = self.short_history(company_id)
        if why:
            # a final state of its own, not `unsupported`: the company gets its score when the third annual report arrives (the SEC daily index queues a new_report load, priority 3)
            self.companies.set_processing_state(company_id, "insufficient_history", why)
            for t in self.queue.list(company_id):
                if t["state"] in ("queued", "running", "deferred_quota", "deferred_network") and t["job_type"] not in DATA_JOBS:
                    self.queue.done(t, {"skipped": "not relevant: " + why})
            return {"status": res.status, "state": "insufficient_history", "reason": why}
        task = {"company_id": company_id, "priority": priority}
        if res.router_needs:
            # provisional profile: the router needs the extraction of the engine first; the score waits until the profile is confirmed (a `repair` job re-routes from the cache)
            profile = {"bank": "BANK", "insurance": "INSURANCE", "realestate": "INCOME_REAL_ESTATE"}[res.router_needs]
            ran = [t for t in self.queue.list(company_id) if t["job_type"] == "ai_extract" and t["state"] == "done" and (t.get("payload") or {}).get("purpose") == "router"
                   and (t["payload"] or {}).get("engine") == res.router_needs]
            if ran:                                   # K6d-2: the extraction ran once and the router still has no rows to decide with: no second request (the DLR loop) - the profile is set by the SIC code
                self.enqueue(task["company_id"], "repair", None, None, PRIORITY["completion"], {"router_fallback": True})
                return {"status": res.status, "provisional_profile": res.profile, "router_fallback": res.router_needs}
            self.enqueue(task["company_id"], "ai_extract", None, None, PRIORITY["completion"], {"blocks": BLOCKS_OF[profile], "purpose": "router", "engine": res.router_needs, "priority_reason": "router"})
            return {"status": res.status, "rows": res.rows_written, "years": res.years, "provisional_profile": res.profile, "extraction_requested": res.router_needs}
        self.enqueue(task["company_id"], "score", None, "first", task["priority"])
        return {"status": res.status, "rows": res.rows_written, "years": res.years}

    def short_history(self, company_id: int) -> Optional[str]:
        """The reason when the company has fewer than ``MIN_SCORE_YEARS`` loaded fiscal years (a new registrant after a merger: PNFP has one), else None."""
        n = len({p["fiscal_year"] for p in self.client.table("filing_periods").select("fiscal_year").eq("company_id", company_id).execute().data})
        return f"היסטוריה קצרה מדי לציון ({n} שנים; נדרשות {MIN_SCORE_YEARS})" if 0 < n < MIN_SCORE_YEARS else None                       # no period rows at all = nothing is known yet (the load did not write periods): no verdict

    def not_relevant(self, task: dict) -> Optional[str]:
        """A score / analysis / AI task of a company in `insufficient_history` does not run and does not fail: it ends as not relevant. The data jobs (a new annual report) still run."""
        if not task.get("company_id") or task["job_type"] in DATA_JOBS:
            return None
        co = self.companies.get_by_id(task["company_id"]) or {}
        return co.get("unsupported_reason") if co.get("processing_state") == "insufficient_history" else None

    def d1_facts(self, ticker: str) -> tuple:
        """-> (D1 facts, competitors of the stored English text) of a company, for the checks of a corrected Hebrew text."""
        S._paths()
        from src.scoring import peer_source as PS
        co = self.companies.get_by_symbol(ticker, "US")
        res = self.load_result(ticker)
        if not co or res is None:
            raise RuntimeError(f"no score result for {ticker}")
        self._meta_context(co, res)
        import run_ai_k5c as K5C
        rec = next(r for r in PS.load_records(self.results_dir, self.companies.industry_overrides()) if r["ticker"] == ticker)
        facts, _moat, _missing = K5C.d1_inputs(rec, self.ai_store)
        from src.ai import content as C
        en = self.texts.get(ticker, int(rec["fiscal_year"][2:]), "background", str(C.content_cfg()["d1"]["version"]), "", "en") or {}
        return facts, en.get("competitors", [])

    # ------------------------------------------------------------ scoring
    def exec_score(self, task: dict) -> dict:
        cid = task["company_id"]
        stage = task.get("skill") or "first"
        co = self.company(cid)
        ticker = co["symbol"]
        if not co.get("profile"):
            raise RuntimeError(f"{ticker} has no profile yet: load it first")
        from src.etl.db_io import FactSetDb
        out = S.score_company(ticker, co["profile"], FactSetDb(self.client), self.ai_store, self.item_store, self.results_dir)
        if out.status in ("needs_config", "not_scored"):
            return {"status": out.status, "detail": out.detail}
        if out.status != "scored":
            raise RuntimeError(f"scoring failed: {out.detail}")
        out.result = self.priced_result(cid, ticker, out)
        run_id, w = self.scores.write_result(cid, out.result)
        gaps = self.gap_review(cid)
        self.enqueue_peer_renders(co)
        if stage == "first":
            self.companies.set_processing_state(cid, "scored_partial")
            planned = self.plan_ai(co, out, task["priority"])
            self.enqueue(cid, "score", None, "final", task["priority"])
            self.enqueue(cid, "analysis", None, None, task["priority"])
            return {"run_id": run_id, "write": w, "ai_pending": out.ai_pending, "planned": planned, "gaps": gaps}
        self.companies.set_processing_state(cid, "complete" if out.ai_pending == 0 else "scored_partial")
        return {"run_id": run_id, "write": w, "ai_pending": out.ai_pending, "gaps": gaps}

    def gap_review(self, company_id: int) -> dict:
        """K6d-2 fixes: the criteria that stay Missing after this score go to the review list (``data_gap_review``); no model call, and a failure here never fails the score."""
        try:
            from src.ai import gap_review as GR
            out = GR.refresh(self.client, company_id)
            co = self.companies.get_by_id(company_id) or {}
            out["core"] = GR.record_core(self.client, company_id, co.get("profile"), alert=self.alert)          # a core figure that is missing: an administrator alert and a top-priority row
            return out
        except Exception as e:   # noqa: BLE001
            return {"error": f"{type(e).__name__}: {e}"}

    def priced_result(self, company_id: int, ticker: str, out) -> dict:
        """The result priced at the latest stored price (``market_snapshot``): the engines read the price file of the earlier stages, which is not refreshed (K6d-1). A stale price (E1) gives no price
        score. The result file that D2 and the peer groups read is rewritten with the same prices."""
        snap = self.client.table("market_snapshot").select("current_price,market_date,is_stale").eq("company_id", company_id).limit(1).execute().data
        if not snap or snap[0].get("current_price") is None:
            return out.result
        from src.pipeline.reprice import reprice_result
        res = reprice_result(out.result, float(snap[0]["current_price"]), snap[0].get("market_date"), bool(snap[0].get("is_stale")))
        path = self.results_dir / out.engine / f"{ticker}.json"
        path.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        return res

    def enqueue_peer_renders(self, co: dict) -> list:
        """A company of this database was scored: the companies of the same profile and industry that already have a business profile get their background rendered again (the 'similar companies'
        sentence may change). A render-only task (``ai_background`` with skill ``render``): no model, no translation."""
        from src.bp.pipeline import group_tickers
        from src.bp.stores import ProfileStore
        S._paths()
        from src.scoring import peer_source as PS
        records = PS.load_records(self.results_dir, self.companies.industry_overrides())
        rec = next((r for r in records if r["ticker"] == co["symbol"]), None)
        if rec is None:
            return []
        queued = []
        profiles = ProfileStore(self.client)
        for t in group_tickers(self.client, rec, records):
            peer = self.companies.get_by_symbol(t, "US")
            if peer and profiles.latest(peer["id"]):
                task, _state = self.enqueue(peer["id"], "ai_background", None, "render", 3, {"reason": f"{co['symbol']} was loaded", "no_ai": True})
                queued.append(t)
        return queued

    def plan_ai(self, co: dict, out, priority: int) -> list:
        """The AI tasks a scored company still needs; a stored answer or text is not asked again."""
        cid, t, res = co["id"], co["symbol"], out.result
        fy = int(sorted(res.get("fiscal_years") or {k: 0 for k in (res.get("inputs") or {}).get("fy", [])})[-1][2:])
        planned = []
        if ((res.get("profile_router") or {}).get("classification") or {}).get("status") == "classification_pending" and not self.ai_store.get(t, fy, "CLS-1", 1):
            planned.append(self.enqueue(cid, "ai_classify", fy, "C1", priority)[0]["id"])
        miss = self.missing_extraction(co, res, fy)
        if miss:
            planned.append(self.enqueue(cid, "ai_extract", fy, None, priority, {"blocks": miss})[0]["id"])
        skills = self.missing_assessments(t, res, fy)
        if skills:
            planned.append(self.enqueue(cid, "ai_assess", fy, None, priority, {"skills": skills})[0]["id"])
        if not self.has_background(t, fy):
            planned.append(self.enqueue(cid, "ai_background", fy, None, priority)[0]["id"])
        return planned

    def plan_completion(self, co: dict, priority: int = 2) -> list:
        """The weekly audit (K6d-1): the tasks a loaded company still needs - the first score when it has none, otherwise the AI answers, extraction items and background text that are missing
        (``plan_ai``; a stored answer or text is not asked again). Priority 2 (data completion). Nothing is planned without the company's result file."""
        cid = co["id"]
        if co.get("processing_state") in ("unsupported", "resolved", "failed") or not co.get("profile") or str(co.get("profile_reason") or "").startswith("provisional"):
            return []                                         # a provisional profile waits for its extraction (the router), it is not scored on the wrong engine
        if not self.scores.latest_run(cid):
            return [self.enqueue(cid, "score", None, "first", priority)[0]["id"]]
        res = self.load_result(co["symbol"])
        if res is None:
            return []

        class _Out:                                          # plan_ai reads only .result
            result = res
        return self.plan_ai(co, _Out, priority)

    def missing_assessments(self, ticker: str, res: dict, fy: int) -> list:
        S._paths()
        from src.scoring.ai_items import PENDING_TO_SKILL
        want = set()
        for kind, key in (("buffett", "buffett_quality"), ("graham", "graham_quality")):
            for c in (res.get(key) or {}).get("criteria", []):
                for i in c["items"]:
                    if i["state"] == "ai_pending":
                        want.add(PENDING_TO_SKILL[(kind, c["id"], i["id"])])
        have = {r["question_id"] for r in self.ai_store.rows(ticker) if r["fiscal_year"] == fy}
        profile = res.get("profile")
        if profile:                                    # a skill with its own version for the profile (REIT wording, 2026-11-05): only an answer of THAT version counts, an older answer is asked again
            from src.ai.assess import prompt_version_of
            from src.ai.prompt import scoring_skills
            rows = [r for r in self.ai_store.rows(ticker) if r["fiscal_year"] == fy]
            for q, sk in scoring_skills().items():
                if (sk.get("profile_versions") or {}).get(profile):
                    want.add(q)
                    cur = prompt_version_of(sk, "3.1", profile)
                    if any(r["question_id"] == q and str(r["prompt_version"]) == cur for r in rows):
                        have.add(q)
                    else:
                        have.discard(q)
        return sorted(want - have)

    def missing_extraction(self, co: dict, res: dict, fy: int) -> list:
        """The extraction blocks of the profile that have no item yet; for a general company B14 when the report has profile items without a tag value."""
        have = {r.get("skill_id") for r in self.item_store.rows_for(co["symbol"])}
        blocks = BLOCKS_OF.get(co.get("profile") or "", [])
        if not blocks and "EXT-GENERAL" not in have:
            try:
                K5 = self._meta_context(co, res)
                import run_ai_k5b_extract as K5B
                K5B.ENGINE_OF[co["symbol"]] = K5.ENGINE_OF[co["symbol"]]
                items, _secs, _counts = K5B.b14_items(co["symbol"], K5.meta(co["symbol"]))
                blocks = ["EXT-GENERAL"] if items else []
            except Exception:   # noqa: BLE001 - B14 detection needs the dictionary and the result; without them nothing is planned
                blocks = []
        return [b for b in blocks if b not in have]

    def has_background(self, ticker: str, fy: int) -> bool:
        """A template-rendered background (BP) of this fiscal year exists, in either language and whatever its state (a Hebrew text that waits for a translation is re-rendered by `render`, not re-planned)."""
        return any(r["fiscal_year"] == fy and r["kind"] == "background" and r.get("template_version") for r in self.texts.rows(ticker))

    # ------------------------------------------------------------ D2 (code, no model call)
    def exec_analysis(self, task: dict) -> dict:
        S._paths()
        from src.ai import d2 as D2, d2_template as T
        from src.scoring import peer_source as PS, peers as P
        cid = task["company_id"]
        co = self.company(cid)
        t = co["symbol"]
        res = self.load_result(t)
        if res is None:
            raise RuntimeError(f"no score result for {t}: score it first")
        records = PS.load_records(self.results_dir, self.companies.industry_overrides())
        rec = next(r for r in records if r["ticker"] == t)
        run = self.scores.latest_run(cid)
        run_label = f"run:{run['id']}"
        g = P.peer_group(rec, records)
        pc = P.peer_percentiles(rec, g, records)
        inputs = D2.build_d2_inputs(res, rec, run_label, pc)
        inputs["changes"] = (run or {}).get("changes")           # K6d-1: the "what changed" line is computed when the run is written and kept in the run (the previous run is deleted)
        if inputs.get("ai_pending"):
            return {"state": "skipped_ai_pending", "ai_pending": inputs["ai_pending"]}
        if any(m.get("score") is None for m in inputs["results"]["models"].values()):         # K6d-2: no quality score (coverage below 60%) = nothing to analyse; the analysis waits for data
            return {"state": "skipped_no_score"}
        row = T.generate_analysis_template(t, int(rec["fiscal_year"][2:]), inputs, self.texts)
        if run:
            self.client.table("score_runs").update({"peer_group": {"ids": g["ids"], "definition": g["definition"], "n": g["n"], "fallback": g["fallback"]}}).eq("id", run["id"]).execute()
            if row.get("id"):
                self.texts.update(row["id"], run_id=run["id"])
        return {"state": row.get("state"), "peers": g["n"], "text_id": row.get("id")}

    # ------------------------------------------------------------ AI tasks
    def _meta_context(self, co: dict, res: dict):
        """Point the K5 helpers (which read golden files) at this company's current result."""
        S._paths()
        import run_ai_k5a as K5
        eng = S.runner_engine(co["profile"], co["symbol"])
        K5.ENGINE_OF[co["symbol"]] = eng                      # K6d-2 fixes: assigned, not setdefault - the router's extraction pass of the same process had set "realestate" for VTR, which stayed after the router chose STANDARD
        K5.golden = lambda t, _r=res: _r
        return K5

    def d1_context(self, ticker: str) -> dict:
        """What D1 is checked against, without a model call: the facts, the report sections that were sent and the prompt text. Used to re-run the checks on stored texts."""
        S._paths()
        from src.ai import assess, content as C
        from src.ai.sections import find_filing
        from src.scoring import peer_source as PS
        co = self.companies.get_by_symbol(ticker, "US")
        res = self.load_result(ticker)
        if not co or res is None:
            raise RuntimeError(f"no score result for {ticker}")
        K5 = self._meta_context(co, res)
        import run_ai_k5c as K5C
        rec = next(r for r in PS.load_records(self.results_dir, self.companies.industry_overrides()) if r["ticker"] == ticker)
        facts, _moat, _missing = K5C.d1_inputs(rec, self.ai_store)
        m = K5.meta(ticker)
        filing = find_filing(ticker, str(m["end"][-1])[:10])
        if filing is None:
            raise RuntimeError(f"the 10-K of {ticker} is not in the local filings cache")
        a = assess.Company(ticker, m["name"], m["profile"], int(rec["fiscal_year"][2:]), filing)
        secs = {k: v.text for k, v in a.sections().items() if k in ("TXT-001", "TXT-003", "TXT-005") and v.found}
        secs, _trimmed = C.trim_d1_sections(facts, filing.accession, secs)
        _prompt, text_sent, sent = C.build_d1_prompt(facts, filing.accession, secs)
        return {"facts": facts, "text_sent": text_sent, "sent": sent, "fiscal_year": a.fiscal_year}

    def background_builder(self, translator=None):
        """The business-profile background (BP, 2026-10-26): XBRL axes + BP-1 -> profile -> phrase translation -> template rendering. Replaces D1 + T1 (``content.generate_background``, deprecated)."""
        from src.bp.pipeline import BackgroundBuilder
        sec = self.pipeline_factory().sec if self.pipeline_factory else None
        return BackgroundBuilder(self.client, self.ai_store, self.texts, gemini=self.gemini, translator=translator, results_dir=self.results_dir, sec=sec, ensure_filing=self.ensure_filing,
                                 companies=self.companies)

    def exec_background(self, task: dict) -> dict:
        """BP-1 (one call, only when the profile of this annual report does not exist) -> profile -> translation of new phrases (Google, if the key exists) -> rendering of the English and the Hebrew text."""
        S._paths()
        t = self.ticker(task["company_id"])
        if task.get("skill") == "render":                     # a company of the same profile and industry was loaded: render again from the stored profile, no model, no translation
            return self.background_builder().render_only(t)
        before = self.gemini.attempts if self.gemini else 0
        try:
            out = self.background_builder().run(t)
        except BudgetExceeded as e:
            raise QuotaSpent(str(e)) from e
        out["attempts"] = (self.gemini.attempts - before) if self.gemini else 0
        return out

    def exec_assess(self, task: dict) -> dict:
        if self.gemini is None:
            raise QuotaSpent("no model budget")
        S._paths()
        from src.ai import assess
        from src.ai.facts import discontinued_facts, facts_for
        from src.ai.prompt import scoring_skills
        from src.ai.sections import find_filing
        co = self.company(task["company_id"])
        t = co["symbol"]
        res = self.load_result(t)
        self.ensure_filing(t, co.get("cik"), self.latest_period_end(task["company_id"]))
        K5 = self._meta_context(co, res)
        import run_ai_k5a2 as K5A2
        K5A2.golden = K5.golden
        m = K5.meta(t)
        filing = find_filing(t, str(m["end"][-1])[:10])
        if filing is None:
            raise RuntimeError(f"the 10-K of {t} is not in the local filings cache")
        a = assess.Company(t, m["name"], m["profile"], int(m["fy"][-1][2:]), filing)
        fd = K5A2.facts_data(t, m)
        note = a.sections().get("NOTE-ACQ")
        fd["discontinued"] = discontinued_facts(getattr(note, "text", note) or "", max_year=2000 + int(m["fy"][-1][2:]))
        a.code_facts = {s: facts_for(s, fd) for s in m["pending"] if facts_for(s, fd)}
        sk = scoring_skills()
        done = 0
        for s in (task.get("payload") or {}).get("skills") or m["pending"]:
            assess.ask(a, sk[s], self.gemini, self.ai_store, assess.Stats(), variant="3.1")
            done += 1
        return {"asked": done, "attempts": self.gemini.attempts}

    def result_from_db(self, co: dict, engine: str, profile: str) -> dict:
        """A result-shaped dict for a company that is not scored yet (the extraction helpers read the fiscal years and the financials from it)."""
        from src.etl import field_map as fm
        from src.repositories.financial_repository import FinancialRepository
        fin = FinancialRepository(self.client)
        periods = fin.get_filing_periods(co["id"])
        labels = [f"FY{p['fiscal_year']}" for p in periods]
        ends = [p["fiscal_year_end"] for p in periods]
        by_field = {key: fld for fld, key in fm.FIELDS[engine].items()}
        f: dict = {}
        for d in fin.get_history(co["id"]):
            fld = by_field.get(d["item_key"])
            if fld:
                f.setdefault(fld, {})[f"FY{d['fiscal_year']}"] = d["value"]
        if engine == "realestate":
            from src.etl.extraction_store import reg_from_rows
            from src.repositories.extraction_repository import ExtractionRepository
            reg = reg_from_rows("realestate", ExtractionRepository(self.client).get_rows(co["id"], co["symbol"]))
            return {"ticker": co["symbol"], "name": co["company_name"], "profile": profile, "buffett_quality": {"criteria": []}, "graham_quality": {"criteria": []},
                    "inputs": {"fy": labels, "end": ends, "f": {k: [v.get(l) for l in labels] for k, v in f.items()}, "reg": reg, "asset_type": None, "noi_method": None}}
        return {"ticker": co["symbol"], "name": co["company_name"], "profile": profile, "fiscal_years": dict(zip(labels, ends)), "financials": f,
                "buffett_quality": {"criteria": []}, "graham_quality": {"criteria": []}}

    def latest_period_end(self, company_id: int) -> Optional[str]:
        """The fiscal year end (YYYY-MM-DD) of the latest annual report whose data is loaded (``filing_periods``): the year the engine scores and the extraction reads."""
        rows = self.client.table("filing_periods").select("fiscal_year,fiscal_year_end").eq("company_id", company_id).order("fiscal_year", desc=True).limit(1).execute().data
        return str(rows[0]["fiscal_year_end"]) if rows and rows[0].get("fiscal_year_end") else None

    def ensure_filing(self, ticker: str, cik: Optional[str], end_date: Optional[str] = None) -> None:
        """The 10-K of the engine's latest fiscal year in the local filings cache (downloaded through the rate-limited SEC client when it is not there). K6d-2 fixes (CLX, a June year end): the latest
        10-K on the SEC list can be of a year that companyfacts does not carry yet; the report read is the one of ``end_date`` (the latest loaded fiscal year end), within 20 days."""
        from src.ai.sections import find_filing
        if find_filing(ticker, end_date) is not None and not (end_date and self.pipeline_factory is not None and cik):
            return
        if end_date and self.pipeline_factory is not None and cik:                # also completes the documents of the filing (companion document with the statements): cached files are not downloaded again
            from datetime import date as _d
            from src.providers.sec_filings import _get_raw, filing_documents
            from src.providers.sec_ixbrl import tenk_filings
            sec = self.pipeline_factory().sec
            want = _d.fromisoformat(end_date)
            k = next((x for x in tenk_filings(sec, cik) if abs((x["report_date"] - want).days) <= 20), None)
            if k is not None:
                acc = k["accession"].replace("-", "")
                for d in filing_documents(sec, cik, {"accession": k["accession"], "primary": k["primary"]}):
                    _get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{d}", f"{acc}_{d}")
                if find_filing(ticker, end_date) is not None:
                    return
            raise RuntimeError(f"the 10-K of {ticker} for the fiscal year ending {end_date} was not found in the cache or on the SEC list")
        if self.pipeline_factory is None or not cik:
            raise RuntimeError(f"the 10-K of {ticker} is not in the local filings cache")
        from src.providers.sec_filings import fetch_filing_text
        fetch_filing_text(self.pipeline_factory().sec, ticker, cik)

    def exec_classify(self, task: dict) -> dict:
        raise RuntimeError("C1 (industry classification) for a new company is not wired to the queue yet: needs the router's SIC / provider industry inputs of the company")

    def retire_old_skill_rows(self, company_id: int) -> int:
        """K6d-2 fixes: a skill whose version was raised is asked again; the rows of the older version for a period that has a row of the current version are rejected (``superseded``), so the
        engine never reads a stale value next to the new one (AFG: two mortgage-loan rows of version 1 beside the one of version 5). Rows approved by a person are left alone."""
        from src.ai.approval_rules import HUMAN_SOURCES
        from src.ai.prompt import extraction_blocks
        current = {b["skill_id"]: str(b["version"]) for b in extraction_blocks().values()}
        rows = [r for r in self.client.table("extraction_items").select("id,skill_id,skill_version,period,approval_status,approval_source").eq("company_id", company_id).execute().data if r.get("skill_id")]
        fresh = {(r["skill_id"], r["period"]) for r in rows if r["skill_version"] == current.get(r["skill_id"])}
        n = 0
        for r in rows:
            cur = current.get(r["skill_id"])
            if cur and r["skill_version"] != cur and (r["skill_id"], r["period"]) in fresh and r["approval_status"] != "rejected" and r.get("approval_source") not in HUMAN_SOURCES:
                self.client.table("extraction_items").update({"approval_status": "rejected", "approval_source": None, "note": f"superseded by skill version {cur}"}).eq("id", r["id"]).execute()
                n += 1
        return n

    def exec_extract(self, task: dict) -> dict:
        if self.gemini is None:
            raise QuotaSpent("no model budget")
        S._paths()
        co = self.company(task["company_id"])
        t = co["symbol"]
        res = self.load_result(t)
        if (task.get("payload") or {}).get("purpose") == "router":      # K6d-2 (the DLR loop): a result file of the provisional profile (a score that ran on the general engine) must not decide which blocks are asked
            eng = (task["payload"] or {}).get("engine")
            profile = {"bank": "BANK", "insurance": "INSURANCE", "realestate": "INCOME_REAL_ESTATE"}[eng]
            res = self.result_from_db(co, eng, profile)
            co = {**co, "profile": profile}
        self.ensure_filing(t, co.get("cik"), self.latest_period_end(task["company_id"]))
        K5 = self._meta_context(co, res)
        import run_ai_k5b_extract as K5B
        K5B.golden, K5B.meta = K5.golden, K5.meta
        K5B.ENGINE_OF[t] = K5.ENGINE_OF[t]
        out_root = ROOT / "scripts" / "ai_store" / "k6c" / "extraction"
        before = self.gemini.attempts
        K5B.main(["--companies", t, "--out-root", str(out_root)], client=self.gemini)
        rows = [json.loads(ln) for ln in (out_root / "items.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()] if (out_root / "items.jsonl").exists() else []
        rows = [r for r in rows if r["ticker"] == t]
        n = self.item_store.upsert_rows(rows, "ai_controls") if rows else {}
        n["superseded"] = self.retire_old_skill_rows(task["company_id"])
        if rows:                                                      # K6d-2: the approval rules (AI skills 2.3) judge the new rows before the score reads them
            from src.ai import recheck as RC
            n["approval_rules"] = RC.recheck(self.client, t, apply=True)["applied"]
            if any(r.get("skill_id") == "EXT-GENERAL" and r.get("state") == "value" and r.get("approval_status") == "approved" for r in self.item_store.rows_for(t)):
                # an approved B14 value is an engine input only once it is a fact (K6 spec 2.3, step 5): a `repair` job rebuilds the facts from the cache with the approved rows, before the score
                n["repair_queued"] = self.enqueue(task["company_id"], "repair", None, None, task["priority"], {"reason": "approved B14 values become facts"})[1]
        if co.get("profile") == "INCOME_REAL_ESTATE" and self.pipeline_factory is not None:
            # K6d-2 fixes: the depth items of a REIT by keyword search (no model): occupancy of the last annual reports, same-property NOI growth from the stated levels, the unencumbered-assets backup
            from src.ai import keyword_depth as KD
            n["depth"] = KD.run(self.client, self.item_store, self.pipeline_factory().sec, t)
            if n["depth"]["rows"]:
                from src.ai import recheck as RC
                RC.recheck(self.client, t, apply=True)
        if co.get("profile") == "INSURANCE" and self.pipeline_factory is not None:
            from src.ai import keyword_depth as KD
            n["depth"] = KD.run_insurer(self.client, self.item_store, self.pipeline_factory().sec, t)
            if n["depth"]["rows"]:
                from src.ai import recheck as RC
                RC.recheck(self.client, t, apply=True)
        if (task.get("payload") or {}).get("purpose") == "router":
            self.enqueue(task["company_id"], "repair", None, None, 1)               # re-route from the cache now that the extraction exists; the score follows
        return {"items": n, "attempts": self.gemini.attempts - before}

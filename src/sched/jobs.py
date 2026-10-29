"""The scheduled jobs (K6 spec 3.1, K6d-1). ``JobRunner.run(name)`` runs one job, records it in ``data_update_log`` (``update_scope`` = ``sched:<job>``) and never raises: a failure is logged with its
error and the scheduler goes on. Connection errors wait 30, 60, 120, 120 s between five attempts (``src/net.py``, the whole job is repeated: every job is idempotent).

  close_prices      all stocks, one batch request, after the close           -> market_snapshot + the price part of the score in place
  intraday_prices   the "hot" stocks only, one batch request                 -> the same; no hot stock = no request
  new_reports       the SEC daily form index of the previous trading day(s)  -> new_report / amendment tasks (priority 3)
  ai_queue          the work queue with the daily budget                      -> data tasks and AI tasks, by priority
  audit             every company against the SEC list                        -> backfill / amendment / missing AI tasks (priority 2)
  yields, fx        reference tables                                          -> gov_yields, fx_rates
  cleanup           the retention rules                                       -> a plan, or (apply) the deletions
"""
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from src.net import NETWORK_WAITS, retry_network
from src.pipeline import prices as P
from src.pipeline.reprice import PriceUpdater
from src.repositories.work_queue_repository import PRIORITY, WorkQueueRepository
from src.sched import cleanup as CL
from src.sched import refdata, sec_daily
from src.sched.hot import hot_stocks
from src.sched.schedule import NO_CATCH_UP, Config

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "scripts" / "state"
FILINGS_DIR = ROOT / "scripts" / "cache" / "filings"
OK = ("success", "partial_success", "no_change")
OPERATION = {"close_prices": "refresh_market_snapshot", "intraday_prices": "refresh_market_snapshot", "new_reports": "refresh_financials", "ai_queue": "calculate_scores",
             "audit": "full_refresh", "yields": "full_refresh", "fx": "full_refresh", "cleanup": "purge_data"}
TARGET = {"close_prices": "market_snapshot", "intraday_prices": "market_snapshot", "new_reports": "work_queue", "ai_queue": "work_queue", "audit": "work_queue", "yields": "gov_yields",
          "fx": "fx_rates", "cleanup": "multiple"}
MAX_SEC_DAYS = 20
LOADED_STATES = ("data_loaded", "scored_partial", "ai_in_progress", "complete")       # a company the pipeline loaded (a legacy row without a CIK or a state is not part of the daily jobs)


@dataclass
class Outcome:
    status: str = "success"                         # success | partial_success | no_change | failed
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    detail: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    error: Optional[str] = None
    skipped: bool = False                           # the job had nothing to do at this moment (the intraday gate): not logged


class JobRunner:
    def __init__(self, client, cfg: Config, now: Optional[Callable] = None, make_pipeline: Optional[Callable] = None, make_runner: Optional[Callable] = None,
                 fetch_batch: Optional[Callable] = None, sec_factory: Optional[Callable] = None, fx_get: Optional[Callable] = None, filings_dir: Path = FILINGS_DIR,
                 state_dir: Path = STATE_DIR, sleep: Optional[Callable] = None, yield_runners: Optional[dict] = None):
        self.client, self.cfg = client, cfg
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._make_pipeline, self._make_runner = make_pipeline, make_runner
        self.fetch_batch = fetch_batch or P.fetch_prices_batch
        self._sec_factory, self.fx_get = sec_factory, fx_get
        self.filings_dir, self.state_dir, self.sleep = filings_dir, state_dir, sleep
        self.yield_runners = yield_runners or {}
        self.queue = WorkQueueRepository(client, now=self.now)
        self._job_locks = {n: threading.Lock() for n in OPERATION}      # a job never runs twice at the same time (a catch-up and the scheduled run)
        self.functions ={"close_prices": self.close_prices, "intraday_prices": self.intraday_prices, "new_reports": self.new_reports, "ai_queue": self.ai_queue, "audit": self.audit,
                          "yields": self.yields, "fx": self.fx, "cleanup": self.cleanup}

    # ------------------------------------------------------------ plumbing
    def pipeline(self, dry_run: bool = False):
        if self._make_pipeline:
            return self._make_pipeline(dry_run)
        from src.pipeline.factory import make_pipeline
        return make_pipeline(dry_run, client=self.client)

    def runner(self, budget: int = 0, rpm: int = 12):
        if self._make_runner:
            return self._make_runner(budget, rpm)
        from src.pipeline.factory import make_runner
        return make_runner(budget, rpm=rpm, client=self.client)

    def sec(self):
        if self._sec_factory:
            return self._sec_factory()
        from src.pipeline.sec_source import PipelineSec
        return PipelineSec(max_age_hours=20.0)

    def run(self, name: str, **opts) -> Outcome:
        """Run one job and record it. Never raises. A job that is already running is not started again (the call returns a skipped outcome)."""
        lock = self._job_locks[name]
        if not lock.acquire(blocking=False):
            return Outcome(skipped=True, detail={"reason": "already running"})
        started = self.now()
        try:
            out = retry_network(lambda: self.functions[name](**opts), NETWORK_WAITS, self.sleep,
                                on_retry=lambda n, w, e: print(f"[{name}] network error {type(e).__name__}: attempt {n} failed, waiting {w}s", flush=True))
        except Exception as e:   # noqa: BLE001 - a failed job is logged, never dropped, and never stops the scheduler
            out = Outcome("failed", error=f"{type(e).__name__}: {e}", detail={"trace": traceback.format_exc()[-600:]})
        finally:
            lock.release()
        if out.skipped:
            return out
        out.detail = {**out.detail, "job": name, "started": started.isoformat(), "seconds": round((self.now() - started).total_seconds(), 2)}
        try:
            self.client.table("data_update_log").insert({
                "created_at": started.isoformat(), "operation_type": OPERATION[name], "target_table": TARGET[name], "update_scope": f"sched:{name}", "data_source": "scheduler", "status": out.status,
                "records_inserted": out.inserted, "records_updated": out.updated, "records_deleted": out.deleted, "error_message": (out.error or None) and out.error[:2000],
                "warning_message": ("; ".join(out.warnings)[:2000] or None), "source_details": [out.detail]}).execute()
        except Exception as e:   # noqa: BLE001 - the log itself failed: say so, do not stop
            print(f"[{name}] could not write data_update_log: {type(e).__name__}: {e}", flush=True)
        return out

    def last_rows(self, name: str, n: int = 10) -> list:
        return self.client.table("data_update_log").select("*").eq("update_scope", f"sched:{name}").order("created_at", desc=True).limit(n).execute().data

    def last_ok(self, name: str) -> Optional[datetime]:
        """When the job last finished without failing (None: never)."""
        for r in self.last_rows(name):
            if r["status"] in OK:
                return datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
        return None

    def missed(self, now: Optional[datetime] = None) -> list:
        """The jobs whose last due time passed without a successful run since, in the catch-up order (an intraday run is never caught up)."""
        now = now or self.now()
        out = []
        order = [j for j in self.cfg.catch_up_order if j in self.functions] + [j for j in self.functions if j not in self.cfg.catch_up_order]
        for name in order:
            if name in NO_CATCH_UP or not self.cfg.enabled(name):
                continue
            due = self.cfg.last_due(name, now)
            if due is None:
                continue
            ok = self.last_ok(name)
            if ok is None or ok < due:
                out.append(name)
        return out

    # ------------------------------------------------------------ prices
    def active_companies(self) -> list:
        rows = self.client.table("companies").select("id,symbol,exchange,processing_state,is_active,cik").eq("exchange", "US").execute().data
        return [r for r in rows if r.get("is_active", True) and r.get("cik") and r.get("processing_state") in LOADED_STATES]

    def apply_prices(self, companies: list, prices: dict) -> Outcome:
        """Each fetched price -> ``market_snapshot`` and, in place, the price part of the latest run (never a new run)."""
        updater = PriceUpdater(self.client, ratio=float(self.cfg.get("intraday_prices", "hot_ratio", 1.10)), now=self.now)
        out = Outcome()
        n_price = n_score = n_none = 0
        for c in companies:
            try:
                p = prices.get(c["symbol"])
                snap = P.apply_snapshot(self.client, c["id"], p, self.now())
                if snap["status"] == "no_price":
                    n_none += 1
                    out.warnings.append(f"{c['symbol']}: no price")
                    continue
                n_price += 1
                r = updater.update_company(c["id"], snap["price"], snap["market_date"], snap["snapshot_at"], snap["is_stale"])
                if r["status"] == "updated":
                    n_score += 1
                elif r["status"] == "no_run":
                    out.detail.setdefault("no_score_run", []).append(c["symbol"])
            except Exception as e:   # noqa: BLE001 - one stock does not stop the others
                out.warnings.append(f"{c['symbol']}: {type(e).__name__}: {e}"[:200])
        out.updated = n_price
        out.detail.update({"stocks": len(companies), "prices": n_price, "no_price": n_none, "scores_updated_in_place": n_score})
        if not companies:
            out.status = "no_change"
        elif n_price == 0:
            out.status, out.error = "failed", "no price was returned for any stock"
        elif n_none or len(out.warnings) > n_none:
            out.status = "partial_success"
        return out

    def close_prices(self) -> Outcome:
        companies = self.active_companies()
        if not companies:
            return Outcome("no_change", detail={"stocks": 0})
        prices = self.fetch_batch([c["symbol"] for c in companies], intraday=True)          # K6d-2: the last price traded, not the daily close row; one request, no second attempt
        out = self.apply_prices(companies, prices)
        out.detail["price_kind"] = "last_price"
        return out

    def intraday_prices(self) -> Outcome:
        if not self.cfg.intraday_open(self.now()):
            return Outcome(skipped=True)
        hot = hot_stocks(self.client, float(self.cfg.get("intraday_prices", "hot_ratio", 1.10)))
        if not hot:
            return Outcome("no_change", detail={"hot": 0, "requests": 0})
        companies = [{"id": h["company_id"], "symbol": h["symbol"]} for h in hot]
        prices = self.fetch_batch([c["symbol"] for c in companies], intraday=True)
        out = self.apply_prices(companies, prices)
        out.detail.update({"hot": [h["symbol"] for h in hot], "requests": 1})
        return out

    # ------------------------------------------------------------ SEC daily index
    def new_reports(self) -> Outcome:
        cal, now = self.cfg.calendar, self.now()
        upper = cal.prev_trading_day(self.cfg.ny_today(now))        # the index of a day is complete only after that day: the last day to read is the one before New York's today
        last = None
        for r in self.last_rows("new_reports"):
            d = ((r.get("source_details") or [{}])[0]).get("last_day")
            if r["status"] in OK and d:
                last = date.fromisoformat(d)
                break
        if last:
            days = cal.trading_days(last + timedelta(days=1), upper)
        else:                                                         # the first run ever: the last few trading days, in case the system was not running
            first = int(self.cfg.get("new_reports", "first_run_days", 5))
            days = cal.trading_days(upper - timedelta(days=first * 2 + 4), upper)[-first:]
        days = days[-MAX_SEC_DAYS:]
        out = Outcome("no_change", detail={"last_day": last.isoformat() if last else None, "days": [], "missing_days": []})
        if not days:
            return out
        sec = self.sec()
        companies = self.client.table("companies").select("id,symbol,cik").execute().data
        done_day = last
        scanned = 0
        queued = []
        pending = []                                                  # days whose index is not there: skipped for good only when a LATER day's index exists, otherwise tried again next time
        for d in days:
            text = sec_daily.fetch_index(sec, d)
            if text is None:
                pending.append(d)
                continue
            out.warnings += [f"the index of {m.isoformat()} is not on the SEC site; skipped" for m in pending]
            pending = []
            filings = sec_daily.parse_form_index(text)
            scanned += len(filings)
            for f, c in sec_daily.ours(filings, companies):
                job = sec_daily.job_of(f["form"])
                task, state = self.queue.enqueue(c["id"], job, None, None, PRIORITY["new_report"], {"accession": f["accession"], "form": f["form"], "filed": f["filed"], "source": "sec_daily_index"})
                queued.append({"ticker": c["symbol"], "form": f["form"], "accession": f["accession"], "job": job, "task": task["id"], "state": state})
            out.detail["days"].append(d.isoformat())
            done_day = d
        out.detail["missing_days"] = [m.isoformat() for m in pending]
        out.detail.update({"last_day": done_day.isoformat() if done_day else None, "annual_reports_in_index": scanned, "queued": queued, "sec_requests": getattr(sec, "requests_made", None)})
        out.inserted = sum(1 for q in queued if q["state"] == "queued")
        if out.detail["missing_days"] and not out.detail["days"]:
            out.status, out.warnings = "no_change", [f"the index of {out.detail['missing_days'][0]} is not published yet"]
        else:
            out.status = "success" if out.inserted else "no_change"
        return out

    # ------------------------------------------------------------ queue and audit
    def ai_queue(self) -> Outcome:
        budget = int(self.cfg.get("ai_queue", "budget", 450))
        runner = self.runner(budget, int(self.cfg.get("ai_queue", "rpm", 12)))
        rep = runner.run()
        out = Outcome(detail={"done": [list(map(str, t)) for t in rep.done], "failed": [list(map(str, t)) for t in rep.failed], "deferred": [list(map(str, t)) for t in rep.deferred],
                              "attempts": rep.attempts, "budget": budget})
        out.updated = len(rep.done)
        out.status = "partial_success" if rep.failed else ("success" if rep.done else "no_change")
        out.warnings = [f"failed {t[1]} {t[2]}: {t[3]}" for t in rep.failed][:10]
        return out

    def audit(self) -> Outcome:
        pipe = self.pipeline(True)
        runner = self.runner(0)
        out = Outcome("no_change", detail={"companies": 0, "backfill": [], "amendment": [], "completion": {}})
        rows = [r for r in self.client.table("companies").select("*").eq("exchange", "US").execute().data
                if r.get("processing_state") in ("data_loaded", "scored_partial", "ai_in_progress", "complete") and r.get("cik")]
        for co in rows:
            out.detail["companies"] += 1
            try:
                _resolved, plans = pipe.audit(co["symbol"])
                missing = [p.fiscal_year for p in plans if p.status == "missing"]
                superseded = [p.fiscal_year for p in plans if p.status == "superseded"]
                if missing:
                    _t, st = self.queue.enqueue(co["id"], "backfill", None, None, PRIORITY["completion"], {"years": missing, "source": "weekly_audit"})
                    out.detail["backfill"].append({"ticker": co["symbol"], "years": missing, "state": st})
                    out.inserted += st == "queued"
                if superseded:
                    _t, st = self.queue.enqueue(co["id"], "amendment", None, None, PRIORITY["completion"], {"years": superseded, "source": "weekly_audit"})
                    out.detail["amendment"].append({"ticker": co["symbol"], "years": superseded, "state": st})
                    out.inserted += st == "queued"
                planned = runner.plan_completion(co, PRIORITY["completion"])
                if planned:
                    out.detail["completion"][co["symbol"]] = planned
            except Exception as e:   # noqa: BLE001 - one company does not stop the audit
                out.warnings.append(f"{co['symbol']}: {type(e).__name__}: {e}"[:200])
        planned_n = sum(len(v) for v in out.detail["completion"].values())
        out.inserted += planned_n
        out.status = "partial_success" if out.warnings else ("success" if out.inserted else "no_change")
        return out

    # ------------------------------------------------------------ reference data
    def yields(self) -> Outcome:
        r = refdata.refresh_yield_csv(self.now().date(), self.yield_runners.get("monthly"), self.yield_runners.get("annual"))
        s = refdata.sync_yields_to_db(self.client)
        return Outcome("success" if s["written"] else "no_change", inserted=s["written"], detail={"builders": r, **s})

    def fx(self) -> Outcome:
        r = refdata.update_fx(self.client, self.fx_get, self.now())
        out = Outcome("success" if r["written"] else "no_change", inserted=r["written"], detail=r)
        if r["missing"]:
            out.status, out.warnings = "partial_success", [f"no rate for {', '.join(r['missing'])}"]
        return out

    # ------------------------------------------------------------ retention
    def cleanup(self, apply: Optional[bool] = None) -> Outcome:
        apply = bool(self.cfg.get("cleanup", "apply", False)) if apply is None else apply
        plan = CL.plan_cleanup(self.client, self.now(), self.filings_dir)
        tickers = {r["id"]: r["symbol"] for r in self.client.table("companies").select("id,symbol").execute().data}
        text = CL.render_plan(plan, tickers)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        stamp = self.now().strftime("%Y%m%d_%H%M%S")
        path = self.state_dir / f"cleanup_plan_{stamp}.txt"
        path.write_text(text + "\n", encoding="utf-8")
        out = Outcome("no_change", detail={"apply": apply, "counts": plan.counts(), "bytes": plan.total_bytes(), "plan_file": str(path)})
        if not apply:
            return out
        done = CL.apply_plan(self.client, plan)
        out.deleted = sum(done.values())
        out.detail["deleted"] = done
        out.status = "success" if out.deleted else "no_change"
        return out

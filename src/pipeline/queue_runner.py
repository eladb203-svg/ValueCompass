"""The work queue runner (K6c, K6 spec 2.8 and section 3): picks tasks from ``work_queue`` and runs them, one at a time.

Order: priority (1 a user asked, 2 a new annual report, 3 backfill), then inside one company: the data job, the first score (without AI), C1, B extraction, A questions, D1 + T1, the score
with the AI answers (``final``), D2. A task waits for the earlier open tasks of its company. A model call is made only through ``self.gemini`` (a ``CappedGemini``): every request attempt
counts against the run's budget and the shared daily counter (cap 450); when the budget is spent the task that needed a call becomes ``deferred_quota`` until the next reset
(midnight Pacific = 10:00 Israel) and no further AI task starts. Data tasks (import, score, D2) need no budget and keep running. A stored answer is never asked again (R18).
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
from src.repositories.work_queue_repository import SCORING_AI, WorkQueueRepository

ROOT = Path(__file__).resolve().parents[2]
ISRAEL = ZoneInfo("Asia/Jerusalem")
AI_JOBS = ("ai_classify", "ai_extract", "ai_assess", "ai_background")
BLOCKS_OF = {"BANK": ["EXT-BANK-CAP", "EXT-BANK-LOANS"], "INSURANCE": ["EXT-INS-CAP", "EXT-INS-INV"],
             "INCOME_REAL_ESTATE": ["EXT-RE-OPS", "EXT-RE-MAINT", "EXT-RE-VALUE", "EXT-RE-LIQ", "EXT-RE-UNENC", "EXT-RE-NAV", "EXT-RE-OPU", "EXT-RE-FFO", "EXT-PROFILE"]}


class QuotaSpent(Exception):
    """The run's budget or the shared daily cap is spent."""


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

    @property
    def calls(self) -> int:
        return self.attempts

    def generate(self, prompt: str, seed_offset: int = 0, **kw):
        if self.attempts >= self.cap:
            raise BudgetExceeded(f"run budget of {self.cap} request attempts reached")
        inner_guard = getattr(self.inner, "_shared_guard", None)
        if inner_guard is not None:                         # count every attempt (also the retries inside one call)
            def guard():
                if self.attempts >= self.cap:
                    raise BudgetExceeded(f"run budget of {self.cap} request attempts reached")
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


class QueueRunner:
    def __init__(self, client, gemini=None, budget: int = 0, pipeline_factory: Optional[Callable] = None, results_dir: Path = S.RESULTS_DIR, now: Optional[Callable] = None,
                 executors: Optional[dict] = None):
        self.client, self.budget = client, budget
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
        for eng in S.ENGINE_KEYS:
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
        for _ in range(max_tasks):
            task = self._next(rep)
            if task is None:
                break
            task = self.queue.claim(task)
            if task["job_type"] in SCORING_AI and task["company_id"]:
                self.companies.set_processing_state(task["company_id"], "ai_in_progress")
            try:
                payload = self.executors[task["job_type"]](task) or {}
                self.queue.done(task, payload)
                rep.done.append((task["id"], task["job_type"], task.get("skill"), self._label(task)))
                if task["job_type"] in SCORING_AI and task["company_id"]:
                    self.after_ai(task)
            except (BudgetExceeded, QuotaSpent) as e:
                self.queue.defer(task, next_reset(self.now()), str(e)[:200])
                rep.deferred.append((task["id"], task["job_type"], self._label(task), str(e)[:120]))
            except RuntimeError as e:
                if "shared daily request cap" in str(e):
                    self.queue.defer(task, next_reset(self.now()), str(e)[:200])
                    rep.deferred.append((task["id"], task["job_type"], self._label(task), "shared daily cap"))
                else:
                    self.queue.fail(task, f"{type(e).__name__}: {e}")
                    rep.failed.append((task["id"], task["job_type"], self._label(task), str(e)[:160]))
            except Exception as e:   # noqa: BLE001 - a failed task is recorded, never dropped
                self.queue.fail(task, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-300:]}")
                rep.failed.append((task["id"], task["job_type"], self._label(task), f"{type(e).__name__}: {e}"[:160]))
        rep.attempts = self.gemini.attempts if self.gemini else 0
        return rep

    def after_ai(self, task: dict) -> None:
        """When the last open scoring AI task (C1, B, A) of a company is done: the score with the AI answers and D2 follow (both are idempotent), and the state goes back to scored_partial until that
        score decides. The background text (D1 + T1) is not waited for."""
        cid = task["company_id"]
        if any(t["job_type"] in SCORING_AI and t["state"] in ("queued", "running", "deferred_quota") for t in self.queue.list(cid)):
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
        for t in self.queue.runnable():
            if getattr(self, "only", None) and self._label(t) not in self.only:
                continue
            if t["job_type"] in AI_JOBS and not self.ai_allowed():
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
        res = p.load(self.ticker(task["company_id"]), task["job_type"])
        return self.after_load(res, task["company_id"], task["priority"])

    def after_load(self, res, company_id: int, priority: int) -> dict:
        """What follows a data job: the first score, or - when the router needs extraction that does not exist - the extraction request."""
        if res.status == "failed":
            raise RuntimeError(res.error or "load failed")
        if res.state == "unsupported":
            return {"status": res.status, "state": res.state}
        task = {"company_id": company_id, "priority": priority}
        if res.router_needs:
            # provisional profile: the router needs the extraction of the engine first; the score waits until the profile is confirmed (a `repair` job re-routes from the cache)
            profile = {"bank": "BANK", "insurance": "INSURANCE", "realestate": "INCOME_REAL_ESTATE"}[res.router_needs]
            self.enqueue(task["company_id"], "ai_extract", None, None, 1, {"blocks": BLOCKS_OF[profile], "purpose": "router", "engine": res.router_needs, "priority_reason": "router"})
            return {"status": res.status, "rows": res.rows_written, "years": res.years, "provisional_profile": res.profile, "extraction_requested": res.router_needs}
        self.enqueue(task["company_id"], "score", None, "first", task["priority"])
        return {"status": res.status, "rows": res.rows_written, "years": res.years}

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
        rec = next(r for r in PS.load_records(self.results_dir) if r["ticker"] == ticker)
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
        run_id, w = self.scores.write_result(cid, out.result)
        if stage == "first":
            self.companies.set_processing_state(cid, "scored_partial")
            planned = self.plan_ai(co, out, task["priority"])
            self.enqueue(cid, "score", None, "final", task["priority"])
            self.enqueue(cid, "analysis", None, None, task["priority"])
            return {"run_id": run_id, "write": w, "ai_pending": out.ai_pending, "planned": planned}
        self.companies.set_processing_state(cid, "complete" if out.ai_pending == 0 else "scored_partial")
        return {"run_id": run_id, "write": w, "ai_pending": out.ai_pending}

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
        return sorted(want - have)

    def missing_extraction(self, co: dict, res: dict, fy: int) -> list:
        """The extraction blocks of the profile that have no item yet; for a general company B14 when the report has profile items without a tag value."""
        have = {r.get("skill_id") for r in self.item_store.rows_for(co["symbol"])}
        blocks = BLOCKS_OF.get(co.get("profile") or "", [])
        if not blocks and "EXT-GENERAL" not in have:
            try:
                K5 = self._meta_context(co, res)
                import run_ai_k5b_extract as K5B
                K5B.ENGINE_OF.setdefault(co["symbol"], K5.ENGINE_OF[co["symbol"]])
                items, _secs, _counts = K5B.b14_items(co["symbol"], K5.meta(co["symbol"]))
                blocks = ["EXT-GENERAL"] if items else []
            except Exception:   # noqa: BLE001 - B14 detection needs the dictionary and the result; without them nothing is planned
                blocks = []
        return [b for b in blocks if b not in have]

    def has_background(self, ticker: str, fy: int) -> bool:
        """An approved Hebrew background of this fiscal year exists (any prompt version: a text made under an older D1 version stays until the 'recompute all' job, K6d)."""
        return any(r["fiscal_year"] == fy and r["kind"] == "background" and r["language"] == "he" and r["approval_status"] == "approved" for r in self.texts.rows(ticker))

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
        records = PS.load_records(self.results_dir)
        rec = next(r for r in records if r["ticker"] == t)
        run = self.scores.latest_run(cid)
        run_label = f"run:{run['id']}"
        g = P.peer_group(rec, records)
        pc = P.peer_percentiles(rec, g, records)
        prev = None
        try:
            prev, _ = PS.load_json(S.GOLDEN_DIR, t)
        except KeyError:
            pass
        inputs = D2.build_d2_inputs(res, rec, run_label, pc, prev, S.GOLDEN_DIR.name if prev else None)
        if inputs.get("ai_pending"):
            return {"state": "skipped_ai_pending", "ai_pending": inputs["ai_pending"]}
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
        K5.ENGINE_OF.setdefault(co["symbol"], eng)
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
        rec = next(r for r in PS.load_records(self.results_dir) if r["ticker"] == ticker)
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

    def exec_background(self, task: dict) -> dict:
        """D1 in English, then T1 (the Hebrew translation); both checked in code; the passing Hebrew text is approved at once with human_reviewed = false."""
        if self.gemini is None:
            raise QuotaSpent("no model budget")
        S._paths()
        from src.ai import assess, content as C
        from src.ai.sections import find_filing
        from src.scoring import peer_source as PS
        co = self.company(task["company_id"])
        t = co["symbol"]
        res = self.load_result(t)
        if res is None:
            raise RuntimeError(f"no score result for {t}")
        self.ensure_filing(t, co.get("cik"))
        K5 = self._meta_context(co, res)
        import run_ai_k5c as K5C
        records = PS.load_records(self.results_dir)
        rec = next(r for r in records if r["ticker"] == t)
        facts, moat_source, missing = K5C.d1_inputs(rec, self.ai_store)
        m = K5.meta(t)
        filing = find_filing(t, str(m["end"][-1])[:10])
        if filing is None:
            raise RuntimeError(f"the 10-K of {t} is not in the local filings cache")
        a = assess.Company(t, m["name"], m["profile"], int(rec["fiscal_year"][2:]), filing)
        secs = {k: v.text for k, v in a.sections().items() if k in ("TXT-001", "TXT-003", "TXT-005") and v.found}
        import os
        C.SEED_SHIFT = int(os.environ.get("VC_D1_SEED_SHIFT", "0"))          # a later run of a failed text uses other seeds (the model is deterministic per seed)
        row = C.generate_background(a, facts, secs, self.gemini, self.texts)
        if row.get("state") == "skipped_budget":
            raise QuotaSpent("; ".join((row.get("checks") or {}).get("reasons") or ["budget"]))
        return {"state": row.get("state"), "approval_status": row.get("approval_status"), "reasons": (row.get("checks") or {}).get("reasons"), "missing_inputs": missing, "attempts": self.gemini.attempts}

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
        self.ensure_filing(t, co.get("cik"))
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

    def ensure_filing(self, ticker: str, cik: Optional[str]) -> None:
        """The latest 10-K in the local filings cache (downloaded through the rate-limited SEC client when it is not there)."""
        from src.ai.sections import find_filing
        if find_filing(ticker) is not None:
            return
        if self.pipeline_factory is None or not cik:
            raise RuntimeError(f"the 10-K of {ticker} is not in the local filings cache")
        from src.providers.sec_filings import fetch_filing_text
        fetch_filing_text(self.pipeline_factory().sec, ticker, cik)

    def exec_classify(self, task: dict) -> dict:
        raise RuntimeError("C1 (industry classification) for a new company is not wired to the queue yet: needs the router's SIC / provider industry inputs of the company")

    def exec_extract(self, task: dict) -> dict:
        if self.gemini is None:
            raise QuotaSpent("no model budget")
        S._paths()
        co = self.company(task["company_id"])
        t = co["symbol"]
        res = self.load_result(t)
        if res is None and (task.get("payload") or {}).get("purpose") == "router":
            eng = (task["payload"] or {}).get("engine")
            profile = {"bank": "BANK", "insurance": "INSURANCE", "realestate": "INCOME_REAL_ESTATE"}[eng]
            res = self.result_from_db(co, eng, profile)
            co = {**co, "profile": profile}
        self.ensure_filing(t, co.get("cik"))
        K5 = self._meta_context(co, res)
        import run_ai_k5b_extract as K5B
        K5B.golden, K5B.meta = K5.golden, K5.meta
        K5B.ENGINE_OF.setdefault(t, K5.ENGINE_OF[t])
        out_root = ROOT / "scripts" / "ai_store" / "k6c" / "extraction"
        before = self.gemini.attempts
        K5B.main(["--companies", t, "--out-root", str(out_root)], client=self.gemini)
        rows = [json.loads(ln) for ln in (out_root / "items.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()] if (out_root / "items.jsonl").exists() else []
        rows = [r for r in rows if r["ticker"] == t]
        n = self.item_store.upsert_rows(rows, "ai_controls") if rows else {}
        if (task.get("payload") or {}).get("purpose") == "router":
            self.enqueue(task["company_id"], "repair", None, None, 1)               # re-route from the cache now that the extraction exists; the score follows
        return {"items": n, "attempts": self.gemini.attempts - before}

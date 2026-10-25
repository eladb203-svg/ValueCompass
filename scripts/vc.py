"""Runner commands (K6 spec 7). The database is chosen by VC_DB_TARGET (default test); `prod` writes to production.

  Data
    vc.py load <ticker> [--job initial_import|backfill|new_report|amendment|repair] [--dry-run] [--budget N]
                       the whole pipeline up to data_loaded, then the first score (scored_partial) and the AI tasks go to the queue (priority 1 for a company that is new);
                       --budget N lets the queue make up to N model requests right away (default 0: the data and score tasks run, the AI tasks wait in the queue)
    vc.py audit <ticker>     the plan per fiscal year; writes nothing
    vc.py status <ticker>    state, years, sources, flags, last job, price, queue
  Queue
    vc.py score <ticker>             queue and run the first score
    vc.py ai-queue --budget N [--max-tasks M] [--tickers T ...]   run the queue; N = most model request attempts of this run (the shared daily cap of 450 applies too)
    vc.py queue status [ticker]
  Texts (D1 background; the Hebrew text is shown at once with the "automatic translation" marker until a person reviews it)
    vc.py texts review | confirm <id> | edit <id> --file <path> | sendback <id>
    vc.py glossary list | approve <n> --en "<english term>"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target, get_supabase_client  # noqa: E402
from src.pipeline import audit as A  # noqa: E402
from src.pipeline.runner import JOBS, Pipeline  # noqa: E402
from src.pipeline.sec_source import PipelineSec  # noqa: E402


def make_pipeline(dry_run: bool, offline: bool = False) -> Pipeline:
    sec = PipelineSec(max_age_hours=float("inf") if offline else 20.0)
    return Pipeline(sec, dry_run=dry_run)


def make_runner(budget: int = 0):
    from src.pipeline.queue_runner import QueueRunner
    client = get_supabase_client()
    gemini = None
    if budget > 0:
        from src.ai.client import GeminiClient, RateLimiter
        gemini = GeminiClient(limiter=RateLimiter(rpm=12, rpd=450))
    return QueueRunner(client, gemini=gemini, budget=budget, pipeline_factory=lambda: make_pipeline(False))


def print_result(r) -> None:
    mode = " (dry run: nothing written)" if r.dry_run else ""
    print(f"{r.ticker}  job={r.job}  status={r.status}{mode}  state={r.state}  profile={r.profile}  engine={r.engine}")
    if r.error:
        print("  ERROR:", r.error)
    print(f"  years: {r.years}")
    print(f"  facts: {r.facts}   filing_periods: {r.periods}")
    print(f"  sources: {r.sources}   missing years: {r.missing_years}   series without any value: {len(r.missing_series)}")
    for chk, out, y, item, detail in r.dq:
        print(f"  DQ {chk}/{out} {y or ''} {item or ''}: {detail}")
    if r.restated:
        print("  restated:", r.restated)
    if r.ai_required:
        print("  AI required:", r.ai_required)
    if r.router_needs:
        print(f"  provisional profile: extraction for the {r.router_needs} engine is requested before the first score")
    if r.price:
        print("  price:", r.price)
    for w in r.warnings[:8]:
        print("  warning:", w)
    print(f"  SEC requests: {r.requests}   seconds: {r.seconds}")


def print_report(rep) -> None:
    print(f"queue: {len(rep.done)} done, {len(rep.failed)} failed, {len(rep.deferred)} deferred, model request attempts {rep.attempts}")
    for t in rep.done:
        print("  done    ", t)
    for t in rep.failed:
        print("  FAILED  ", t)
    for t in rep.deferred:
        print("  deferred", t)


def queue_status(runner, ticker=None) -> None:
    cid = runner.ai_store.co.id(ticker.upper()) if ticker else None
    print("counts:", runner.queue.counts(cid))
    for t in runner.queue.list(cid):
        print(f"  #{t['id']:<4}{runner._label(t):<6}{t['job_type']:<14}{(t['skill'] or ''):<7}{t['state']:<15}prio {t['priority']}  attempts {t['attempts']}" + (f"  {t['last_error'][:70]}" if t.get("last_error") else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("load", "audit", "status", "score", "ai-queue", "queue", "texts", "glossary"))
    ap.add_argument("arg", nargs="?", help="ticker, or the sub-command of queue / texts / glossary")
    ap.add_argument("arg2", nargs="?", help="id of a text / number of a proposal / ticker for queue status")
    ap.add_argument("--job", choices=JOBS, default="initial_import")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--budget", type=int, default=0)
    ap.add_argument("--max-tasks", type=int, default=1000)
    ap.add_argument("--tickers", nargs="*", help="ai-queue: run only the tasks of these companies")
    ap.add_argument("--file")
    ap.add_argument("--en")
    a = ap.parse_args(argv)
    print(f"[database target: {db_target()}]")
    if a.command == "audit":
        resolved, plans = make_pipeline(True).audit(a.arg)
        print(A.render(resolved, plans))
        return 0
    if a.command == "status":
        print(json.dumps(make_pipeline(True).status(a.arg), indent=1, default=str, ensure_ascii=False))
        r = make_runner()
        if r.companies.get_by_symbol(a.arg.upper(), "US"):
            queue_status(r, a.arg)
        return 0
    if a.command == "load":
        p = make_pipeline(a.dry_run, offline=(a.job == "repair"))
        before = p.companies.get_by_symbol(a.arg.upper(), "US")
        res = p.load(a.arg, a.job)
        print_result(res)
        if a.dry_run or res.status == "failed":
            return 1 if res.status == "failed" else 0
        runner = make_runner(a.budget)
        row = runner.companies.get_by_symbol(a.arg.upper(), "US")
        print("after load:", runner.after_load(res, row["id"], 1 if before is None or not before.get("processing_state") else 3))
        print_report(runner.run(a.max_tasks))
        return 0
    if a.command == "score":
        runner = make_runner(a.budget)
        row = runner.companies.get_by_symbol(a.arg.upper(), "US")
        runner.enqueue(row["id"], "score", None, "first", 1)
        print_report(runner.run(a.max_tasks))
        return 0
    if a.command == "ai-queue":
        runner = make_runner(a.budget)
        print_report(runner.run(a.max_tasks, only=set(a.tickers) if a.tickers else None))
        return 0
    if a.command == "queue":
        queue_status(make_runner(), a.arg2 if a.arg == "status" else None)
        return 0
    runner = make_runner()
    from src.pipeline import texts as TX
    if a.command == "glossary":
        if a.arg == "list":
            for p in TX.read_proposals():
                print(f"  #{p['n']} {p['status']:<9}{p['old_he']} -> {p['new_he']}   ({p['ticker']}, text {p['text_id']})")
        elif a.arg == "approve":
            print(TX.glossary_approve(int(a.arg2), a.en or ""))
        return 0
    if a.arg == "review":
        for t in TX.pending_review(runner.texts):
            print(f"#{t['id']} {t['ticker']} FY{t['fiscal_year']} (prompt v{t['prompt_version']})\n  HE: {t['he']}\n  EN: {t['en']}\n")
    elif a.arg == "confirm":
        print("confirmed:", TX.confirm(runner.texts, int(a.arg2))["id"])
    elif a.arg == "sendback":
        print("pending_review:", TX.sendback(runner.texts, int(a.arg2))["approval_status"])
    elif a.arg == "edit":
        row = runner.texts.get_by_id(int(a.arg2))
        facts, comps = runner.d1_facts(row["ticker"])
        try:
            out = TX.edit(runner.texts, int(a.arg2), Path(a.file).read_text(encoding="utf-8").strip(), facts, comps)
            print("stored (edited_by human, human_reviewed true); glossary proposals:", out["glossary_proposals"])
        except TX.EditRejected as e:
            print("REJECTED by the checks (nothing stored):", "; ".join(e.reasons))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

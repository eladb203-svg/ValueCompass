"""Runner commands (K6 spec 7). The database is chosen by VC_DB_TARGET (default test); `prod` writes to production.

  Data
    vc.py load <ticker> [--job initial_import|backfill|new_report|amendment|repair] [--dry-run] [--no-score] [--budget N]
                       the whole pipeline up to data_loaded, then the first score (scored_partial) and the AI tasks go to the queue (priority 1 for a company that is new);
                       --budget N lets the queue make up to N model requests right away (default 0: the data and score tasks run, the AI tasks wait in the queue)
    vc.py audit <ticker>     the plan per fiscal year; writes nothing
    vc.py status <ticker>    state, years, sources, flags, last job, price, queue
  Queue
    vc.py score <ticker>             queue and run the first score
    vc.py ai-queue --budget N [--max-tasks M] [--tickers T ...]   run the queue; N = most model request attempts of this run (the shared daily cap of 450 applies too)
    vc.py queue status [ticker]
  Scheduler (K6d-1; times in config/schedule.yaml; no operating-system scheduler)
    vc.py scheduler [--config FILE]       run the scheduler in this window (one instance only; Ctrl+C stops it in order)
    vc.py scheduler --ensure              start it in the background if it is not running (does nothing when it is); the K7 app icon runs this
    vc.py scheduler --stop                orderly stop: a job in the middle finishes, the lock is released
    vc.py scheduler --status              per job: last run and result, next run, jobs missed while the PC was off
    vc.py scheduler --once <job>          run one job now: close_prices intraday_prices new_reports ai_queue audit yields fx cleanup
    vc.py approvals recheck [--ticker T] [--dry-run | --apply]   the extraction approval rules (AI skills 2.3) on the rows in the database; default only lists
    vc.py cleanup [--apply]               the retention cleanup (K6 spec 3.3): prints what would be deleted (default); --apply deletes it
  Background (business profile: XBRL + BP-1 -> closed vocabulary -> template; replaces D1 / T1)
    vc.py profile show <ticker>           the stored profile: field, value, source (xbrl / ai / code), quote or tag, status
    vc.py render <ticker> | --all         render the English and Hebrew texts again from the stored profiles and phrase translations (no model call, no translation call)
    vc.py terms review                    translated phrases that nobody approved yet
    vc.py terms approve <id>              approve a phrase; the texts that use it are rendered again
    vc.py terms apply-file <file>         corrections from a table (id | english | hebrew); like terms edit for each line
    vc.py terms edit <id> --he "..."      correct a phrase (stored as human / approved); the texts that use it are rendered again
  Texts of the OLD D1 / T1 background (deprecated; those texts are superseded and not shown)
    vc.py texts review | confirm <id> | edit <id> --file <path> | sendback <id>
    vc.py glossary list | approve <n> --en "<english term>"
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target  # noqa: E402
from src.pipeline import audit as A  # noqa: E402
from src.pipeline.factory import make_pipeline, make_runner  # noqa: E402
from src.pipeline.runner import JOBS  # noqa: E402


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


def show_profile(profile: dict, ticker: str) -> None:
    print(f"{ticker}  profile #{profile['id']}  FY{profile['fiscal_year']}  accession {profile['accession']}  skill {profile['skill_version']}  model {profile['model']}")
    for f in ("core_activity", "segments", "products_services", "customer_types", "revenue_models", "regions", "competitors", "competitor_types"):
        fld = profile[f] or {}
        print(f"  [{f}] status={fld.get('status')} source={fld.get('source')}" + (f" reasons={fld['reasons']}" if fld.get("reasons") else ""))
        for it in fld.get("items") or []:
            val = it.get("value") or it.get("name") or it.get("code") or it.get("industry")
            extra = f" share={it['share']:.1%}" if isinstance(it.get("share"), float) else ""
            ev = (it.get("quote") or it.get("tag") or "")[:110]
            print(f"      {str(val)[:70]}{extra}  | {it.get('source')} | {ev} | {it.get('status')}")


def companies_using_phrases(builder, ens: list) -> list:
    """Tickers (with a profile) whose Hebrew text uses any of these phrases (profiles are read once)."""
    from src.bp.pipeline import phrases_needed
    from src.bp.translate import phrase_key
    keys = {phrase_key(e) for e in ens}
    out = []
    for p in builder.client.table("company_business_profiles").select("*").execute().data:
        if any(phrase_key(x[0]) in keys for x in phrases_needed(p)):
            out.append(builder.companies.get_by_id(p["company_id"])["symbol"])
    return sorted(set(out))


def rerender_all(builder) -> list:
    """Every company that has a business profile is rendered again (no model, no translation call)."""
    done = []
    for co in builder.companies.client.table("companies").select("id,symbol").execute().data:
        if builder.profiles.latest(co["id"]):
            try:
                builder.render_only(co["symbol"])
                done.append(co["symbol"])
            except Exception as e:   # noqa: BLE001
                print(f"  could not render {co['symbol']}: {e}")
    return done


def rerender_for_phrase(builder, en: str) -> list:
    """The companies whose Hebrew text uses this phrase are rendered again."""
    from src.bp.pipeline import phrases_needed
    from src.bp.translate import phrase_key
    done = []
    for co in builder.companies.client.table("companies").select("id,symbol").execute().data:
        p = builder.profiles.latest(co["id"])
        if p and any(phrase_key(x[0]) == phrase_key(en) for x in phrases_needed(p)):
            try:
                builder.render_only(co["symbol"])
                done.append(co["symbol"])
            except Exception as e:   # noqa: BLE001
                print(f"  could not render {co['symbol']}: {e}")
    return done


def apply_terms_file(builder, path: Path) -> int:
    """`terms apply-file <file>`: corrections from a table `| company | en | he |` (or `| id | en | he |`, or `en | he`). The English phrase is matched as written, then without a trailing parenthetical note
    (\"North America (Segment)\"), then as the cleaned name the template shows (names.py). \"(להשאיר בלטינית)\" in the Hebrew column keeps the phrase as the English text. Each match is applied like
    `terms edit` (human / approved); the texts that use the phrase are rendered again; rows that match no phrase are listed."""
    import re
    from src.bp.names import clean_name
    from src.bp.translate import phrase_key
    rows = {r["id"]: r for r in builder.terms.rows()}
    by_en = {phrase_key(r["en"]): r for r in rows.values()}
    done, skipped = [], []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in ln.strip().strip("|").split("|")]
        if len(cells) < 2 or set("".join(cells)) <= set("-: ") or cells[-1] in ("he (תיקון)", "he", "hebrew"):
            continue
        he = cells[-1]
        if re.fullmatch(r"#?\d+", cells[0]) and int(cells[0].lstrip("#")) in rows and len(cells) >= 2:
            row = rows[int(cells[0].lstrip("#"))]
        else:
            en_raw = cells[-2]
            plain = re.sub(r"\s*\([^)]*\)\s*$", "", en_raw).strip()
            cands = [en_raw, plain, clean_name(plain, "segments"), clean_name(plain, "products_services")]
            row = next((by_en[phrase_key(c)] for c in cands if c and phrase_key(c) in by_en), None)
        keep_latin = "להשאיר בלטינית" in he
        he = re.sub(r"\s*\(להשאיר בלטינית\)\s*", "", he).strip()
        if row is None or not he:
            skipped.append(ln.strip())
            continue
        if keep_latin:
            he = row["en"]
        builder.terms.edit(row["id"], he)
        done.append((row["id"], row["en"], he))
    touched = set(companies_using_phrases(builder, [en for _i, en, _h in done]))      # every company whose text uses an edited phrase is rendered once, after all the edits
    for t in sorted(touched):
        builder.render_only(t)
    print("rendered again:", sorted(touched))
    for d in done:
        print("edited:", d)
    for sk in skipped:
        print("NOT FOUND:", sk)
    return 0


def background_command(runner, a) -> int:
    builder = runner.background_builder()
    if a.command == "profile" and a.arg == "add-fields":      # BP-1 v4 on a stored profile: ONE call per company, only `founded` and `listed_since`, then the texts are rendered again
        tickers = [t.upper() for t in (a.ticker or [])]
        if not tickers or runner.gemini is None:
            print("usage: vc.py profile add-fields --ticker T [T ...] --budget N")
            return 2
        for t in tickers:
            try:
                r = builder.add_new_fields(t)
                r["render"] = builder.render_only(t)
                print(t, r)
            except Exception as e:   # noqa: BLE001
                print(t, "NOT DONE:", type(e).__name__, e)
        print("model request attempts:", runner.gemini.attempts)
        return 0
    if a.command == "profile":
        if a.arg != "show" or not a.arg2:
            print("usage: vc.py profile show <ticker> | add-fields --ticker T ... --budget N")
            return 2
        co = runner.companies.get_by_symbol(a.arg2.upper(), "US")
        p = builder.profiles.latest(co["id"]) if co else None
        if not p:
            print("no business profile for", a.arg2)
            return 1
        show_profile(p, a.arg2.upper())
        return 0
    if a.command == "render":
        tickers = []
        if a.all:
            for co in runner.companies.client.table("companies").select("id,symbol").execute().data:
                if builder.profiles.latest(co["id"]):
                    tickers.append(co["symbol"])
        elif a.arg:
            tickers = [a.arg.upper()]
        else:
            print("usage: vc.py render <ticker> | --all")
            return 2
        for t in tickers:
            try:
                print(t, builder.render_only(t))
            except Exception as e:   # noqa: BLE001
                print(t, "NOT RENDERED:", e)
        return 0
    if a.arg == "seed-sectors":                           # the sector / product-line glossary as human / approved terms (K6d-2)
        r = builder.terms.seed_sectors(dry_run=a.dry_run)
        print(f"sector glossary: {r['inserted']} term(s) {'would be ' if a.dry_run else ''}added, {r['existing']} already there")
        if r["inserted"] and not a.dry_run:
            print("rendered again:", sorted(rerender_all(builder)))
        return 0
    if a.arg == "review":
        rows = builder.terms.unreviewed()
        for r in rows:
            print(f"#{r['id']:<4}[{r['source']}] {r['en']}  ->  {r['he']}")
        print(f"{len(rows)} phrases wait for review")
        return 0
    if a.arg == "apply-file" and a.arg2:
        return apply_terms_file(builder, Path(a.arg2))
    if a.arg in ("approve", "edit") and a.arg2:
        tid = int(a.arg2)
        row = builder.terms.get_by_id(tid)
        if not row:
            print("no such phrase", tid)
            return 1
        if a.arg == "approve":
            builder.terms.approve(tid)
        else:
            if not a.he or not a.he.strip():
                print('usage: vc.py terms edit <id> --he "..."')
                return 2
            from src.bp.translate import check_translation, auto_names
            reasons = [r for r in check_translation(row["en"], a.he.strip(), [n for n in auto_names(row["en"]) if n], []) if not r.startswith(("length", "no_hebrew"))]      # a person may keep a name in Latin letters
            if reasons:
                print("REJECTED by the checks (nothing stored):", "; ".join(reasons))
                return 1
            builder.terms.edit(tid, a.he.strip())
        print("rendered again:", rerender_for_phrase(builder, row["en"]))
        return 0
    print("usage: vc.py terms review | approve <id> | edit <id> --he \"...\"")
    return 2


def scheduler_command(a) -> int:
    from src.db import get_supabase_client
    from src.sched import service
    from src.sched.jobs import JobRunner
    from src.sched.schedule import JOB_NAMES, Config
    cfg = Config.load(Path(a.config) if a.config else None)
    if a.command == "cleanup":
        jr = JobRunner(get_supabase_client(), cfg)
        out = jr.run("cleanup", apply=True) if a.apply else jr.cleanup(apply=False)          # the plan alone reads only: nothing is written, not even a log row
        print(Path(out.detail["plan_file"]).read_text(encoding="utf-8") if out.detail.get("plan_file") else "")
        print(f"cleanup: {out.status}  apply={out.detail.get('apply')}  deleted={out.detail.get('deleted', 0)}" + (f"  ERROR {out.error}" if out.error else ""))
        return 1 if out.status == "failed" else 0
    if a.ensure:
        started, msg = service.ensure(Path(a.config) if a.config else None)
        print(msg)
        return 0
    if a.stop:
        ok, msg = service.stop()
        print(msg)
        return 0 if ok or "not running" in msg else 1
    if a.status:
        try:
            jobs = JobRunner(get_supabase_client(), cfg)
            jobs.last_rows("fx", 1)                                 # one read: is the database reachable?
        except Exception as e:   # noqa: BLE001 - the schedule can be shown without the database
            print(f"(database not reachable: {type(e).__name__}; showing the schedule only)")
            jobs = None
        print("\n".join(service.status(cfg, jobs)))
        return 0
    if a.once:
        if a.once not in JOB_NAMES:
            print(f"unknown job {a.once!r}; one of: {', '.join(JOB_NAMES)}")
            return 2
        if service.is_running():
            print("note: the scheduler is running; this run is separate from it")
        opts = {"apply": True} if (a.once == "cleanup" and a.apply) else {}
        out = JobRunner(get_supabase_client(), cfg).run(a.once, **opts)
        print(json.dumps({"job": a.once, "status": out.status, "inserted": out.inserted, "updated": out.updated, "deleted": out.deleted, "error": out.error, "warnings": out.warnings[:10],
                          "skipped": out.skipped, "detail": out.detail}, indent=1, ensure_ascii=False, default=str))
        return 1 if out.status == "failed" else 0
    return service.serve(cfg, get_supabase_client, log=lambda m: print(m, flush=True))


def approvals_command(a) -> int:
    """`vc.py approvals recheck [--ticker T] [--dry-run | --apply]`: the extraction approval rules (AI skills 2.3) on the rows in the database. Default: only the list."""
    from datetime import datetime
    from src.ai import recheck as RC
    from src.db import get_supabase_client
    if a.arg != "recheck":
        print("usage: vc.py approvals recheck [--ticker T] [--dry-run | --apply]")
        return 2
    client = get_supabase_client()
    tick = a.ticker[0] if a.ticker else None
    before = RC.status_table(client, [tick] if tick else None)
    res = RC.recheck(client, tick, apply=a.apply and not a.dry_run)
    ds = res["decisions"]
    out_dir = ROOT / "scripts" / "state"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"approvals_recheck_{db_target()}_{datetime.now():%Y%m%d_%H%M%S}.txt"
    lines = [f"{d.ticker:<6}{(d.skill or ''):<14}{d.item_key[:34]:<35}{d.period:<8}{d.before:<9}-> {d.after:<9}{d.rule:<22}{d.reason[:150]}" for d in ds if d.changed]
    kept = [d for d in ds if not d.changed]
    lines += ["", f"UNCHANGED ({len(kept)}):"] + [f"{d.ticker:<6}{(d.skill or ''):<14}{d.item_key[:34]:<35}{d.period:<8}{d.before:<9}   {d.rule:<22}{d.reason[:100]}" for d in kept if d.before == "pending"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(RC.table(ds))
    tot = Counter(f"{d.before}->{d.after}" for d in ds if d.changed)
    print(f"\nrows judged: {len(ds)}  changed: {res['changed']}  {dict(tot)}  (applied: {res['applied']})  full list: {path}")
    print("before (figure rows by status):", {t: {s: dict(c) for s, c in v.items()} for t, v in before.items()})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("load", "audit", "status", "score", "ai-queue", "queue", "texts", "glossary", "profile", "render", "terms", "scheduler", "cleanup", "approvals"))
    ap.add_argument("arg", nargs="?", help="ticker, or the sub-command of queue / texts / glossary")
    ap.add_argument("arg2", nargs="?", help="id of a text / number of a proposal / ticker for queue status")
    ap.add_argument("--job", choices=JOBS, default="initial_import")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-score", action="store_true", help="load: stop at data_loaded (no first score, nothing queued)")
    ap.add_argument("--budget", type=int, default=0)
    ap.add_argument("--max-tasks", type=int, default=1000)
    ap.add_argument("--tickers", nargs="*", help="ai-queue: run only the tasks of these companies")
    ap.add_argument("--file")
    ap.add_argument("--all", action="store_true", help="render: every company that has a profile")
    ap.add_argument("--he", help="terms edit: the corrected Hebrew phrase")
    ap.add_argument("--en")
    ap.add_argument("--config", help="scheduler: the schedule file (default config/schedule.yaml)")
    ap.add_argument("--ensure", action="store_true", help="scheduler: start in the background if not running")
    ap.add_argument("--stop", action="store_true", help="scheduler: orderly stop")
    ap.add_argument("--status", action="store_true", help="scheduler: last/next run of every job")
    ap.add_argument("--once", help="scheduler: run this job now")
    ap.add_argument("--apply", action="store_true", help="cleanup / scheduler --once cleanup / approvals recheck: really write (default: only list)")
    ap.add_argument("--ticker", nargs="*", help="approvals recheck: one company")
    a = ap.parse_args(argv)
    print(f"[database target: {db_target()}]", flush=True)
    if a.command in ("scheduler", "cleanup"):
        return scheduler_command(a)
    if a.command == "approvals":
        return approvals_command(a)
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
        if a.dry_run or res.status == "failed" or a.no_score:
            return 1 if res.status == "failed" else 0
        runner = make_runner(a.budget)
        row = runner.companies.get_by_symbol(a.arg.upper(), "US")
        from src.repositories.work_queue_repository import JOB_PRIORITY, PRIORITY
        prio = PRIORITY["user"] if before is None or not before.get("processing_state") else JOB_PRIORITY.get(a.job, PRIORITY["completion"])        # a new company = a user's request (1)
        print("after load:", runner.after_load(res, row["id"], prio))
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
    runner = make_runner(a.budget if (a.command == "profile" and a.arg == "add-fields") else 0)
    if a.command in ("profile", "render", "terms"):
        return background_command(runner, a)
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

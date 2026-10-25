"""Runner commands (K6 spec 7): ``load <ticker>``, ``audit <ticker>``, ``status <ticker>``. ``--dry-run`` computes and prints, writes nothing.

    .venv/Scripts/python scripts/vc.py load KO [--job initial_import|backfill|new_report|amendment|repair] [--dry-run]
    .venv/Scripts/python scripts/vc.py audit KO
    .venv/Scripts/python scripts/vc.py status KO

The database is chosen by VC_DB_TARGET (default test). The SEC cache is scripts/cache/sec_live; `repair` never downloads.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target  # noqa: E402
from src.pipeline import audit as A  # noqa: E402
from src.pipeline.runner import JOBS, Pipeline  # noqa: E402
from src.pipeline.sec_source import PipelineSec  # noqa: E402


def make_pipeline(dry_run: bool, offline: bool = False) -> Pipeline:
    sec = PipelineSec(max_age_hours=float("inf") if offline else 20.0)
    return Pipeline(sec, dry_run=dry_run)


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
    if r.price:
        print("  price:", r.price)
    for w in r.warnings[:8]:
        print("  warning:", w)
    print(f"  SEC requests: {r.requests}   seconds: {r.seconds}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("load", "audit", "status"))
    ap.add_argument("ticker")
    ap.add_argument("--job", choices=JOBS, default="initial_import")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    print(f"[database target: {db_target()}]")
    if a.command == "audit":
        p = make_pipeline(True)
        resolved, plans = p.audit(a.ticker)
        print(A.render(resolved, plans))
        return 0
    if a.command == "status":
        print(json.dumps(make_pipeline(True).status(a.ticker), indent=1, default=str, ensure_ascii=False))
        return 0
    p = make_pipeline(a.dry_run, offline=(a.job == "repair"))
    r = p.load(a.ticker, a.job)
    print_result(r)
    return 1 if r.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())

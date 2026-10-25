"""K6c section 2: load the extraction CSV files (bank, insurance, real estate) into ``extraction_items``, by the approval rule. Idempotent; works on test and on production (VC_DB_TARGET).

Rule (src/etl/db_io.approval_for): K5b matched the value -> approved + k5b_confirmed (also when the old process verified it); else the quote was verified in the earlier process -> approved +
legacy_verified; else pending. There is no approve-all option here.

    .venv/Scripts/python scripts/load_extraction.py [--tickers KO JPM ...] [--dry-run]
A company that is not in ``companies`` yet is created (symbol only; RESOLVE fills the name and CIK on its first ``load``).
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target, get_supabase_client  # noqa: E402
from src.etl.db_io import approval_for  # noqa: E402
from src.etl.extraction_store import load_rows  # noqa: E402
from src.etl.k5b_match import k5b_matched_keys  # noqa: E402
from src.repositories.company_repository import CompanyRepository  # noqa: E402
from src.repositories.extraction_repository import ExtractionRepository  # noqa: E402


def main(argv) -> int:
    dry = "--dry-run" in argv
    only = None
    if "--tickers" in argv:
        i = argv.index("--tickers") + 1
        only = {a.upper() for a in argv[i:] if not a.startswith("--")}
    client = get_supabase_client()
    companies, repo = CompanyRepository(client), ExtractionRepository(client)
    k5b = k5b_matched_keys()
    print(f"[database target: {db_target()}] K5b-matched keys: {len(k5b)}" + ("  (dry run: nothing written)" if dry else ""))
    total, by_source, stats = 0, Counter(), Counter()
    for engine in ("bank", "insurance", "realestate"):
        for ticker, rows in sorted(load_rows(engine).items()):
            if only and ticker not in only:
                continue
            out = []
            for r in rows:
                status, source = approval_for(r, False, (ticker, r.item_key, r.period) in k5b)
                out.append(replace(r, approval_status=status, approval_source=source))
                by_source[(status, source or "-")] += 1
            total += len(out)
            if dry:
                continue
            row = companies.get_by_symbol(ticker, "US") or companies.ensure(ticker, ticker)
            for k, v in repo.upsert_rows(row["id"], out).items():
                stats[k] += v
    print(f"rows: {total}")
    for (status, source), n in sorted(by_source.items()):
        print(f"  {status:<9}{source:<16}{n}")
    if not dry:
        print("written:", dict(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

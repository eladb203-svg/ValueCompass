"""Acceptance run preflight: a ticker is "new" only if it is in none of: the companies table of the database (test and prod), any CSV of the repository (bank / insurance / real-estate extraction,
provider industries, AI reference set, extracted-before), the golden sets, or the local caches (prices, SEC) of earlier stages.
Usage: python scripts/acceptance_preflight.py TICKER [TICKER ...]    (exit code 1 if any ticker is not new)"""
from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def csv_hits(ticker: str) -> list:
    hits = []
    for p in list(ROOT.glob("scripts/*.csv")) + list((ROOT / "docs").rglob("*.csv")):
        try:
            with open(p, encoding="utf-8", newline="") as f:
                for row in csv.reader(f):
                    if any(c.strip().upper() == ticker for c in row[:3]):
                        hits.append(str(p.relative_to(ROOT)))
                        break
        except (OSError, UnicodeDecodeError, csv.Error):
            continue
    return hits


def golden_hits(ticker: str) -> list:
    hits = []
    for base in [ROOT / "tests" / "golden", *ROOT.glob("scripts/output_k5*")]:
        for p in base.rglob("*"):
            if p.is_file() and re.fullmatch(rf"{ticker}(\..*)?", p.name, re.I):
                hits.append(str(p.relative_to(ROOT)))
    idx = ROOT / "tests" / "golden" / "2026-10-20" / "index.json"
    if idx.exists() and re.search(rf'"{ticker}"', idx.read_text(encoding="utf-8")):
        hits.append("tests/golden/2026-10-20/index.json")
    return hits


def cache_hits(ticker: str) -> list:
    return [str(p.relative_to(ROOT)) for p in (ROOT / "scripts" / "cache").rglob(f"*{ticker}*")][:5]


def db_hits(ticker: str) -> dict:
    from src.db import get_supabase_client
    out = {}
    for target in ("test", "prod"):
        os.environ["VC_DB_TARGET"] = target
        out[target] = bool(get_supabase_client(target).table("companies").select("id").eq("symbol", ticker).limit(1).execute().data)
    return out


def main(tickers: list) -> int:
    bad = 0
    print(f"{'ticker':8}{'test.companies':16}{'prod.companies':16}{'csv':6}{'golden':8}{'cache':7} verdict")
    for t in [x.upper() for x in tickers]:
        db, c, g, k = db_hits(t), csv_hits(t), golden_hits(t), cache_hits(t)
        new = not (db["test"] or db["prod"] or c or g or k)
        bad += 0 if new else 1
        print(f"{t:8}{('YES' if db['test'] else 'no'):16}{('YES' if db['prod'] else 'no'):16}{len(c):<6}{len(g):<8}{len(k):<7} {'NEW' if new else 'NOT NEW ' + str(c + g + k)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

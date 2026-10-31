"""Keyword search of the 10-K text (no model): completes an extraction item from the earlier annual reports (K6d-2 fixes, 2026-10-31).

    python scripts/keyword_backfill.py <TICKER> [--years 5] [--apply]

For the tickers in ``RULES`` the figure is searched in each of the last N annual reports with a fixed pattern. The report is downloaded when it is not in the cache (rate-limited SEC client).
A row is made only when the quote is found in the text as written (the same normalization as the model's quotes). Default: print what was found; ``--apply`` writes the rows (provenance model ``keyword-search``) with the status the block rule of
EXT-RE-OPS gives (automatic when the 0-100 control passes) and runs the approval rules on the company.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ticker -> item, pattern (group 1 = the figure), what the figure is
RULES = {
    "DLR": {"item": "occupancy", "rx": r"approximately ([\d.]+)% leased", "basis": "portfolio leased percentage (primary basis of the report)"},
    "MAA": {"item": "occupancy", "rx": r"Same Store \d+ [\d,]+ ([\d.]+) %", "basis": "Same Store average physical occupancy (primary basis of the report)"},
    "VICI": {"item": "occupancy", "rx": r"properties are (\d+)% leased", "basis": "percentage of properties leased"},
}


def filing_text(path: Path) -> str:
    from src.ai.checks import normalize
    from src.providers.sec_filings import html_to_text
    return normalize(html_to_text(path.read_text(encoding="utf-8", errors="ignore")))


def ensure_reports(ticker: str, n: int) -> list:
    """-> [(fiscal year, accession, path)] of the last n annual reports, downloaded when missing."""
    from src.pipeline.factory import make_pipeline
    from src.pipeline.resolve import resolve
    from src.providers.sec_filings import _get_raw
    p = make_pipeline(False)
    r = resolve(p.sec, ticker)
    out = []
    for f in r.annual[:n]:
        acc = f.accession.replace("-", "")
        name = f"{acc}_{f.primary_doc}"
        path = ROOT / "scripts" / "cache" / "filings" / name
        if not path.exists():
            _get_raw(p.sec, f"https://www.sec.gov/Archives/edgar/data/{int(r.cik)}/{acc}/{f.primary_doc}", name)
        out.append((f.fiscal_year, f.accession, path))
    return out


def find_rows(ticker: str, n: int) -> list:
    rule = RULES[ticker]
    rows = []
    for fy, acc, path in ensure_reports(ticker, n):
        text = filing_text(path)
        m = re.search(rule["rx"], text)
        if not m:
            print(f"  FY{fy} {acc}: no match")
            continue
        s = max(0, m.start() - 0)
        quote = text[m.start():m.end()]
        assert quote in text
        print(f"  FY{fy} {acc}: {m.group(1)}%  <- \"{quote}\"")
        rows.append({"ticker": ticker, "item_key": rule["item"], "year": fy, "fiscal_year": fy, "accession": acc, "skill_id": "EXT-RE-OPS", "block": "B5", "version": 1,
                     "prompt_version": "kw1", "model": "keyword-search", "state": "value", "stated_state": "value", "value": float(m.group(1)), "value_full": float(m.group(1)), "scale": 1,
                     "unit": "percent", "period": f"December 31, {fy}", "basis": rule["basis"], "quote": quote, "section": "keyword search of the annual report text", "flags": [],
                     "reasons": [], "control": "bounds_0_100", "control_result": "pass" if 0 <= float(m.group(1)) <= 100 else "fail", "control_detail": f"pattern {rule['rx']!r}",
                     "approval_status": "approved" if 0 <= float(m.group(1)) <= 100 else "pending", "approval_reason": "block rule EXT-RE-OPS: automatic when the bounds control passes (quote found as written in the report text)"})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    t = a.ticker.upper()
    if t not in RULES:
        print(f"no rule for {t}; known: {', '.join(RULES)}")
        return 2
    from src.db import db_target
    print(f"[database target: {db_target()}]")
    rows = find_rows(t, a.years)
    if not a.apply or not rows:
        print(f"{len(rows)} rows found (not written; use --apply)")
        return 0
    from src.ai import recheck as RC
    from src.ai.db_stores import DbAiItemStore
    from src.db import get_supabase_client
    client = get_supabase_client()
    print("written:", DbAiItemStore(client).upsert_rows(rows, "ai_controls"))
    print("approval rules applied to", RC.recheck(client, t, apply=True)["applied"], "rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())

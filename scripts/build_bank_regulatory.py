"""Build scripts/bank_regulatory.csv from scripts/bank_extraction_spec.py and the cached FY2025 10-K texts.

Every row carries the exact quote (taken from the converted 10-K text, whitespace collapsed) and is only marked
verified when the extracted number occurs inside that quote. Run: .venv/Scripts/python scripts/build_bank_regulatory.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from bank_extraction_spec import S as S1  # noqa: E402
from bank_extraction_spec_v2 import S2  # noqa: E402

# later rows override earlier ones with the same (ticker, item)
_merged: dict = {}
for _row in list(S1) + list(S2):
    _merged[(_row["t"], _row["item"])] = _row
S = list(_merged.values())
from src.providers.sec_filings import FILINGS  # noqa: E402

OUT = ROOT / "scripts" / "bank_regulatory.csv"


def _pattern(tokens):
    return r"[\s|$%]*".join(re.escape(t) for t in tokens)


def main():
    texts = {}
    rows, failures = [], []
    for row in S:
        t = row["t"]
        src = row.get("file")
        key = src or t
        if key not in texts:
            path = (FILINGS.parent / src) if src else (FILINGS / f"{t}_10K_text.txt")
            texts[key] = path.read_text(encoding="utf-8")
        text = texts[key]
        if row["tokens"] == ("liquidity",):  # absence check: the LCR is never mentioned
            n = len(re.findall(r"(?i)liquidity coverage|(?-i:LCR)", text))
            rows.append({**row, "quote": f"[no mention: {n} matches for /liquidity coverage|LCR/ in {len(text):,} characters of 10-K text]",
                         "verified": "YES" if n == 0 else "NO"})
            if n:
                failures.append((t, row["item"], f"expected absence but found {n} matches"))
            continue
        m = re.search(_pattern(row["tokens"]), text)
        if not m:
            failures.append((t, row["item"], "anchor not found"))
            rows.append({**row, "quote": "", "verified": "NO"})
            continue
        s, e = max(0, m.start() - row["pre"]), min(len(text), m.end() + row["post"])
        quote = re.sub(r"\s+", " ", text[s:e]).strip()
        ok = row["verify"] is None or row["verify"] in quote
        if not ok:
            failures.append((t, row["item"], f"value string {row['verify']!r} not in quote"))
        rows.append({**row, "quote": quote, "verified": "YES" if ok else "NO"})
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "item", "value", "unit", "10-K section", "exact quote", "verified", "note"])
        for r in rows:
            w.writerow([r["t"], r["item"], r["value"], r["unit"], r["section"], r["quote"], r["verified"], r["note"]])
    print(f"{len(rows)} rows, {len(failures)} failures")
    for f in failures:
        print("  FAIL", f)


if __name__ == "__main__":
    main()

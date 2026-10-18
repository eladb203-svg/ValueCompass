"""Build scripts/insurance_regulatory.csv from scripts/insurance_extraction_spec.py and the cached FY2025 10-K texts.

Every row carries the exact quote (converted 10-K text, whitespace collapsed), the location (nearest preceding heading is not available in the
converted text, so the character offset within the document and the section named in the spec are stored) and is only marked verified when
the extracted number occurs inside the quote (normal rows), when the absence regex has no match (absence rows) or when the presence regex
matches (presence rows).  Run: .venv/Scripts/python scripts/build_insurance_regulatory.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from insurance_extraction_spec import S as S1  # noqa: E402
from insurance_extraction_spec_v2 import S2  # noqa: E402

S = list(S1) + list(S2)
from src.providers.sec_filings import FILINGS  # noqa: E402

OUT = ROOT / "scripts" / "insurance_regulatory.csv"  # round 1 + round 2 rows (round-1 rows unchanged)
_merged: dict = {}
for _row in S:
    _merged[(_row["t"], _row["item"], _row.get("period", ""))] = _row
ROWS = list(_merged.values())


def _pattern(tokens):
    return r"[\s|$%]*".join(re.escape(t) for t in tokens)


def main():
    texts, rows, failures = {}, [], []
    for row in ROWS:
        t = row["t"]
        if t not in texts:
            texts[t] = (FILINGS / f"{t}_10K_text.txt").read_text(encoding="utf-8")
        text = texts[t]
        loc = ""
        if row.get("absence"):
            n = len(re.findall(row["absence"], text))
            quote = f"[no match: {n} matches for /{row['absence']}/ in {len(text):,} characters of 10-K text]"
            ok = n == 0
            if not ok:
                m = re.search(row["absence"], text)
                quote += " first match: " + re.sub(r"\s+", " ", text[max(0, m.start() - 80):m.end() + 80])
                failures.append((t, row["item"], f"expected absence but found {n} matches"))
        elif row.get("presence"):
            m = re.search(row["presence"], text)
            if m:
                quote = re.sub(r"\s+", " ", text[max(0, m.start() - row["pre"]):m.end() + row["post"]]).strip()
                loc, ok = f"char {m.start():,} of {len(text):,}", True
            else:
                quote, ok = "[no match]", False
                row = {**row, "value": "NO"}
        else:
            m = re.search(_pattern(row["tokens"]), text)
            if not m:
                failures.append((t, row["item"], "anchor not found"))
                rows.append({**row, "quote": "", "verified": "NO", "loc": ""})
                continue
            s, e = max(0, m.start() - row["pre"]), min(len(text), m.end() + row["post"])
            quote = re.sub(r"\s+", " ", text[s:e]).strip()
            ok = row["verify"] is None or row["verify"] in quote
            loc = f"char {m.start():,} of {len(text):,}"
            if not ok:
                failures.append((t, row["item"], f"value string {row['verify']!r} not in quote"))
        rows.append({**row, "quote": quote, "verified": "YES" if ok else "NO", "loc": loc})
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "item", "period", "value", "unit", "10-K section", "exact quote", "verified", "note"])
        for r in rows:
            sec = r["section"] + (f" [{r['loc']}]" if r.get("loc") else "")
            w.writerow([r["t"], r["item"], r.get("period", ""), r["value"], r["unit"], sec, r["quote"], r["verified"], r["note"]])
    print(f"{len(rows)} rows, {len(failures)} failures")
    for f in failures:
        print("  FAIL", f)


if __name__ == "__main__":
    main()

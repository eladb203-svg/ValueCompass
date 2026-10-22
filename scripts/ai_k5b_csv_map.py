"""Code stage K5b, section 4 (no model calls): map every item of the three extraction CSVs to the item_key and block of the AI extraction, and count what no block covers (B14 candidates).

Run: .venv/Scripts/python.exe scripts/ai_k5b_csv_map.py  -> scripts/ai_store/k5b/csv_map.md and csv_map.json
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.scoring.ext_items import map_csv_item  # noqa: E402

FILES = {"bank": "bank_regulatory.csv", "insurance": "insurance_regulatory.csv", "realestate": "realestate_extracted.csv"}


def rows_of(kind: str) -> list:
    p = ROOT / "scripts" / FILES[kind]
    return [r for r in csv.DictReader(l for l in p.open(encoding="utf-8") if not l.startswith("#")) if r.get("ticker") and not r["ticker"].startswith("#")]


def year_of(kind: str, r: dict) -> str:
    if kind == "bank":
        m = re.search(r"(20\d\d)$", r["item"])
        return m.group(1) if m else "2025"
    if kind == "insurance":
        return (r.get("period") or "FY2025").replace("FY", "") or "2025"
    return (r.get("year") or "").replace("FY", "") or "latest"


def main() -> None:
    out, md = {}, ["# CSV -> AI extraction block map (code stage K5b, section 4)", ""]
    for kind in FILES:
        R = rows_of(kind)
        cov, unc = Counter(), Counter()
        keys = defaultdict(set)
        yrs = defaultdict(set)
        items_all, items_cov = set(), set()
        for r in R:
            key, blk = map_csv_item(kind, r["item"])
            items_all.add(r["item"])
            y = year_of(kind, r)
            if blk:
                cov[blk] += 1
                keys[blk].add(key)
                items_cov.add(r["item"])
                yrs[blk].add(y)
            else:
                unc[re.sub(r"_(20\d\d)$", "_YYYY", re.sub(r"^(funding:[a-z_]+):.*", r"\1:*", r["item"]))] += 1
        tickers = sorted({r["ticker"] for r in R})
        n_cov = sum(cov.values())
        out[kind] = {"file": FILES[kind], "rows": len(R), "distinct_items": len(items_all), "tickers": len(tickers), "covered_rows": n_cov, "covered_items": len(items_cov),
                     "by_block": dict(cov), "keys": {b: sorted(v) for b, v in keys.items()}, "uncovered": dict(unc), "uncovered_rows": sum(unc.values()),
                     "years": {b: sorted(v) for b, v in yrs.items()}}
        md += [f"## {FILES[kind]} - {len(R)} item-year rows, {len(items_all)} distinct item names, {len(tickers)} companies", "",
               f"Covered by a block: {n_cov} rows ({len(items_cov)} item names); not covered by any block: {sum(unc.values())} rows ({len(unc)} item groups).", "",
               "| block | rows | AI item_keys | CSV years |", "|---|---|---|---|"]
        for b in sorted(cov, key=lambda x: int(x[1:])):
            md.append(f"| {b} | {cov[b]} | {', '.join(sorted(keys[b]))} | {', '.join(sorted(yrs[b]))} |")
        md += ["", "Not covered (B14 candidates / outside the blocks):", ""]
        md += [f"- `{k}`: {v} rows" for k, v in sorted(unc.items(), key=lambda kv: -kv[1])]
        md.append("")
    (ROOT / "scripts" / "ai_store" / "k5b").mkdir(parents=True, exist_ok=True)
    (ROOT / "scripts" / "ai_store" / "k5b" / "csv_map.md").write_text("\n".join(md), encoding="utf-8")
    (ROOT / "scripts" / "ai_store" / "k5b" / "csv_map.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for k, v in out.items():
        print(k, v["rows"], "rows;", v["covered_rows"], "covered;", v["uncovered_rows"], "uncovered;", "blocks", v["by_block"])


if __name__ == "__main__":
    main()

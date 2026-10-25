"""Which CSV extraction rows did K5b confirm? (K6b section 0)

K5b compared the AI extraction with the CSV rows (``scripts/ai_k5b_compare.py`` -> ``compare.json``, 7 development companies). A CSV row is *K5b-matched* when a ``match`` result exists for
its (ticker, item, year); balance-sheet lines (``bsa_*``) match by their CSV item name. The result is a set of ``(ticker, item_key, period)`` keys, the keys of ``ExtractionRow``.
The K5b results live in the (git-ignored) AI store: when the file is missing the set is empty.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from src.etl.extraction_store import load_rows
from src.scoring.ext_items import map_csv_item

ROOT = Path(__file__).resolve().parents[2]
COMPARE = ROOT / "scripts" / "ai_store" / "k5b" / "extraction" / "compare.json"
LATEST_YEAR = 2025


def _year(engine: str, row) -> int:
    m = re.search(r"(20\d\d)$", row.item_key) if engine == "bank" else re.search(r"FY(20\d\d)", row.item_key)
    if m:
        return int(m.group(1))
    m = re.search(r"(20\d\d)", row.period or "")
    return int(m.group(1)) if m else LATEST_YEAR


def k5b_matched_keys(path: Optional[Path] = None) -> set:
    path = Path(path) if path else COMPARE
    if not path.exists():
        return set()
    results = json.loads(path.read_text(encoding="utf-8"))
    match = {(x["ticker"], x["item"], x["year"]) for x in results if x.get("result") == "match"}
    lines = {(x["ticker"], x["csv_item"]) for x in results if x.get("result") == "match" and x.get("csv_item")}
    keys: set = set()
    for engine in ("bank", "insurance", "realestate"):
        for ticker, rows in load_rows(engine).items():
            for r in rows:
                key, _blk = map_csv_item(engine, r.item_key)
                if (ticker, key, _year(engine, r)) in match or (ticker, r.item_key) in lines:
                    keys.add((ticker, r.item_key, r.period))
    return keys

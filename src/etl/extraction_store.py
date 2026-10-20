"""Extraction store (extraction_items) in memory: rows <-> the ``reg`` dictionaries the engines read, and a loader for the three CSV files.

``reg`` shapes (unchanged, engine side):
  bank        item -> {value, unit, section, quote, verified, note}
  insurance   item -> {value, unit, period, section, quote, verified, note}
  realestate  item -> year label ('FY2024', quarter 'FY2024Q3' or '') -> {value, unit, quote, source, verified, note}
Rows keep the insertion order of the dictionaries (the engines sum extracted lines in that order). All CSV rows are loaded as ``approved``
(the engines never filtered by ``verified``); text values (YES / NA / MISSING / not disclosed) stay as text in the row.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from .facts import ExtractionRow

ROOT = Path(__file__).resolve().parents[2]
CSV_FILES = {"bank": ROOT / "scripts" / "bank_regulatory.csv", "insurance": ROOT / "scripts" / "insurance_regulatory.csv",
             "realestate": ROOT / "scripts" / "realestate_extracted.csv"}
QUARTER_ITEMS = {"maintenance_capex_q": "maintenance_capex", "ti_lc_income_preserving_q": "ti_lc_income_preserving",
                 "straight_line_x_q": "straight_line_x", "reported_affo_q": "reported_affo"}


def value_state(v) -> str:
    if isinstance(v, (int, float)):
        return "value"
    s = str(v).strip()
    if s == "NA":
        return "NA"
    if s == "MISSING":
        return "MISSING"
    if s.lower().startswith("not disclosed") or s.lower() == "not_disclosed":
        return "not_disclosed"
    return "value"


def rows_from_reg(engine: str, ticker: str, reg: dict) -> list:
    out: list = []
    for item, body in (reg or {}).items():
        if engine == "realestate":
            for year, r in body.items():
                out.append(ExtractionRow(ticker, item, year, r["value"], value_state(r["value"]), r.get("unit", ""), r.get("source", ""), "",
                                         r.get("quote", ""), bool(r.get("verified")), "", r.get("note", "")))
        else:
            r = body
            out.append(ExtractionRow(ticker, item, r.get("period", ""), r["value"], value_state(r["value"]), r.get("unit", ""), "",
                                     r.get("section", ""), r.get("quote", ""), bool(r.get("verified")), "", r.get("note", "")))
    return out


def reg_from_rows(engine: str, rows, sum_quarters: bool = False) -> dict:
    reg: dict = {}
    for r in rows:
        if r.approval_status != "approved":
            continue
        if engine == "realestate":
            reg.setdefault(r.item_key, {})[r.period] = {"value": r.value, "unit": r.unit, "quote": r.exact_quote, "source": r.document_ref,
                                                          "verified": r.quote_verified, "note": r.note}
        elif engine == "insurance":
            reg[r.item_key] = {"value": r.value, "unit": r.unit, "period": r.period, "section": r.section, "quote": r.exact_quote,
                               "verified": r.quote_verified, "note": r.note}
        else:
            reg[r.item_key] = {"value": r.value, "unit": r.unit, "section": r.section, "quote": r.exact_quote,
                               "verified": r.quote_verified, "note": r.note}
    if sum_quarters and engine == "realestate":
        _sum_quarters(reg)
    return reg


def _sum_quarters(items: dict) -> None:
    """Quarter rows ('FY2024Q3') of the *_q items are summed to the fiscal year when all four quarters exist (same rule as the provider loader)."""
    for qitem, item in QUARTER_ITEMS.items():
        rows = items.get(qitem)
        if not rows:
            continue
        years = {k[:-2] for k in rows if k[-2:-1] == "Q" and k[-1] in "1234"}
        for y in sorted(years):
            qs = [rows.get(f"{y}Q{i}") for i in (1, 2, 3, 4)]
            if any(q is None or not isinstance(q["value"], (int, float)) for q in qs):
                continue
            items.setdefault(item, {})[y] = {"value": sum(q["value"] for q in qs), "unit": qs[0]["unit"], "verified": all(q["verified"] for q in qs),
                                             "quote": " || ".join(f"{i + 1}Q: {q['quote']}" for i, q in enumerate(qs)),
                                             "source": " || ".join(sorted({q["source"] for q in qs})),
                                             "note": "sum of the four quarters (" + qs[0]["note"] + ")"}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def load_rows(engine: str, path: Optional[Path] = None) -> dict:
    """CSV -> {ticker: [ExtractionRow]} (all rows ``approved``). Comment rows (ticker starting with '#') are skipped."""
    path = Path(path) if path else CSV_FILES[engine]
    out: dict = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            tk = r.get("ticker")
            if not tk or tk.startswith("#"):
                continue
            v = _num(r["value"])
            if engine == "bank":
                row = ExtractionRow(tk, r["item"], "", v, value_state(v), r["unit"], "", r["10-K section"], r["exact quote"],
                                    r["verified"] == "YES", "", r["note"])
            elif engine == "insurance":
                row = ExtractionRow(tk, r["item"], r.get("period", ""), v, value_state(v), r["unit"], "", r["10-K section"], r["exact quote"],
                                    r["verified"] == "YES", "", r["note"])
            else:
                row = ExtractionRow(tk, r["item"], r.get("year", ""), v, value_state(v), r.get("unit", ""), r.get("source", ""), "",
                                    r.get("quote", ""), str(r.get("verified", "")).lower() in ("1", "true", "yes", "y"), "", r.get("note", ""))
            out.setdefault(tk, []).append(row)
    return out

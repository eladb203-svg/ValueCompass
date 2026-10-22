"""Code stage K5b, section 5: compare the AI extraction items with the verified CSVs (bank_regulatory, insurance_regulatory, realestate_extracted).

Match = the same value after scale (within 0.5%, or within 0.05 percentage points for percents); differ; missing in AI (the CSV has it, the AI did not return an accepted value);
missing in CSV (the AI returned an accepted value and the CSV has none). Multi-line items (loan lines, balance-sheet lines, debt maturities by instrument) are compared by sum and, for the
lines, line by line by value. Run: .venv/Scripts/python.exe scripts/ai_k5b_compare.py [--root scripts/ai_store/k5b/extraction] -> compare.json, compare.md next to items.jsonl
"""
from __future__ import annotations

import argparse
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
KIND_OF = {"B1": "bank", "B2": "bank", "B3": "insurance", "B4": "insurance"}
SUM_KEYS = ("debt_maturity_year1", "debt_maturity_year2", "re29a_nonre_inv", "re29_nonre_impairments", "op_units_book_value", "recon_nci_jv")
LINE_KEYS = ("loan_line",)


def csv_rows(kind: str) -> list:
    p = ROOT / "scripts" / FILES[kind]
    return [r for r in csv.DictReader(l for l in p.open(encoding="utf-8") if not l.startswith("#")) if r.get("ticker") and not r["ticker"].startswith("#")]


def csv_year(kind: str, r: dict, latest: int) -> int:
    m = re.search(r"(20\d\d)$", r["item"]) if kind == "bank" else re.search(r"FY(20\d\d)", r["item"])
    if m:
        return int(m.group(1))
    y = (r.get("year") or r.get("period") or "")
    m = re.search(r"(20\d\d)", y)
    return int(m.group(1)) if m else latest


def csv_value(kind: str, r: dict):
    """(value in comparison units, unit class): USD full dollars / percent points / count."""
    try:
        v = float(r["value"])
    except (TypeError, ValueError):
        return None, None
    u = r["unit"]
    if u == "USD mm":
        return v * 1e6, "USD"
    if u == "%":
        return v, "percent"
    if u == "fraction":
        return v * 100.0, "percent"
    if u in ("USD", "USD/share"):
        return v, "USD"
    return v, "count"


def same(a: float, b: float, unit: str) -> bool:
    if unit == "percent":
        return abs(a - b) <= 0.05 + 1e-9
    return abs(a - b) <= 0.005 * max(abs(a), abs(b)) + 1e-9


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT / "scripts" / "ai_store" / "k5b" / "extraction"))
    a = ap.parse_args()
    root = Path(a.root)
    ai = [json.loads(l) for l in (root / "items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    kinds = {"B1": "bank", "B2": "bank", "B3": "insurance", "B4": "insurance"}
    kinds.update({f"B{i}": "realestate" for i in range(5, 14)})
    cs = {k: csv_rows(k) for k in FILES}
    # CSV index: (kind, ticker, item_key, year) -> [(value, unit, csv_item, row)]
    idx = defaultdict(list)
    for k, rows in cs.items():
        for r in rows:
            key, blk = map_csv_item(k, r["item"])
            if not blk or re.search(r"_q$", r["item"]) or re.search(r"Q[1-4]$", r.get("year") or ""):
                continue
            v, u = csv_value(k, r)
            if v is not None:
                latest = 2025
                idx[(k, r["ticker"], key, csv_year(k, r, latest))].append((v, u, r["item"], r))
    ran = {(r["ticker"], r["block"]) for r in ai}
    acc = [r for r in ai if r["state"] == "value"]
    out, per_block = [], defaultdict(Counter)
    seen_csv = set()
    groups = defaultdict(list)
    for r in acc:
        groups[(r["ticker"], r["block"], r["item_key"], r["year"])].append(r)
    for (t, blk, key, y), rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        kind = kinds.get(blk)
        if kind is None:
            continue
        cands = idx.get((kind, t, key, y), [])
        unit = "percent" if rs[0]["unit"] == "percent" else "USD"
        if key.startswith("bsa_"):
            continue          # compared line by line below
        if key in LINE_KEYS:
            ai_sum = sum(x["value_full"] for x in rs if not re.match(r"\s*total\b", str(x.get("basis") or ""), re.I))
            cv = sum(c[0] for c in cands)
            matched = sum(1 for x in rs for c in cands if same(x["value_full"], c[0], "USD"))
            res = "match" if cands and same(ai_sum, cv, "USD") else ("differ" if cands else "missing_in_csv")
            out.append({"ticker": t, "block": blk, "item": key, "year": y, "result": res, "ai": ai_sum, "csv": cv if cands else None, "ai_lines": len(rs), "csv_lines": len(cands), "lines_matched_by_value": matched,
                        "quote": rs[0]["quote"], "approval": rs[0]["approval_status"]})
            seen_csv.add((kind, t, key, y))
            continue
        av = sum(x["value_full"] for x in rs) if key in SUM_KEYS else rs[0]["value_full"]
        if not cands:
            out.append({"ticker": t, "block": blk, "item": key, "year": y, "result": "missing_in_csv", "ai": av, "csv": None, "unit": unit, "quote": rs[0]["quote"], "approval": rs[0]["approval_status"]})
            continue
        cv = sum(c[0] for c in cands) if key in SUM_KEYS else cands[0][0]
        if key not in SUM_KEYS and len(cands) > 1:
            best = min(cands, key=lambda c: abs(c[0] - av))
            cv = best[0]
        seen_csv.add((kind, t, key, y))
        out.append({"ticker": t, "block": blk, "item": key, "year": y, "result": "match" if same(av, cv, unit) else "differ", "ai": av, "csv": cv, "unit": unit, "csv_items": [c[2] for c in cands][:4],
                    "quote": rs[0]["quote"], "approval": rs[0]["approval_status"]})
    # balance-sheet lines (B10): by value
    bsa = defaultdict(list)
    for r in acc:
        if r["item_key"].startswith("bsa_") and r["block"] == "B10":
            bsa[(r["ticker"], r["year"])].append(r)
    for (t, y), rs in bsa.items():
        csv_lines = [(c[0], key[4:], c[2]) for (kd, tt, key, yy), cl in idx.items() if kd == "realestate" and tt == t and yy == y and key.startswith("bsa_") for c in cl]
        used = set()
        for x in rs:
            hit = next((i for i, c in enumerate(csv_lines) if i not in used and same(x["value_full"], c[0], "USD")), None)
            if hit is None:
                out.append({"ticker": t, "block": "B10", "item": x["item_key"], "line": x.get("basis"), "year": y, "result": "missing_in_csv", "ai": x["value_full"], "csv": None, "quote": x["quote"], "approval": x["approval_status"]})
                continue
            used.add(hit)
            cls_csv = "bsa_" + csv_lines[hit][1]
            out.append({"ticker": t, "block": "B10", "item": x["item_key"], "line": x.get("basis"), "year": y, "result": "match" if cls_csv == x["item_key"] else "class_differs",
                        "ai": x["value_full"], "csv": csv_lines[hit][0], "csv_class": cls_csv, "csv_item": csv_lines[hit][2], "quote": x["quote"], "approval": x["approval_status"]})
        for i, c in enumerate(csv_lines):
            if i not in used:
                out.append({"ticker": t, "block": "B10", "item": "bsa_" + c[1], "line": c[2], "year": y, "result": "missing_in_ai", "ai": None, "csv": c[0], "quote": None, "approval": None})
    # missing in AI: CSV values of a block that ran for the company, in the year window, that the AI did not return as accepted
    ai_keys = {(r["ticker"], r["block"], r["item_key"], r["year"]) for r in acc}
    for (kind, t, key, y), cl in idx.items():
        blk = map_csv_item(kind, cl[0][2])[1]
        if (t, blk) not in ran or key.startswith("bsa_") or y < 2023 or (kind, t, key, y) in seen_csv or (t, blk, key, y) in ai_keys:
            continue
        stated = [r for r in ai if r["ticker"] == t and r["block"] == blk and r["item_key"] == key]
        why = ("rejected: " + "/".join(sorted({x for r in stated if r["state"] == "rejected" for x in r["reasons"]}))) if any(r["state"] == "rejected" for r in stated) else \
              ("not_disclosed/NA" if any(r["state"] in ("not_disclosed", "NA") for r in stated) else "not returned")
        out.append({"ticker": t, "block": blk, "item": key, "year": y, "result": "missing_in_ai", "ai": None, "csv": sum(c[0] for c in cl) if key in SUM_KEYS else cl[0][0], "why": why, "quote": None, "approval": None})
    for o in out:
        per_block[o["block"]][o["result"]] += 1
    (root / "compare.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    md = ["# AI extraction vs CSV (code stage K5b)", "", "| block | match | differ | class differs | missing in AI | missing in CSV |", "|---|---|---|---|---|---|"]
    for b in sorted(per_block, key=lambda x: int(x[1:])):
        c = per_block[b]
        md.append(f"| {b} | {c['match']} | {c['differ']} | {c['class_differs']} | {c['missing_in_ai']} | {c['missing_in_csv']} |")
    tot = sum(per_block.values(), Counter())
    md.append(f"| total | {tot['match']} | {tot['differ']} | {tot['class_differs']} | {tot['missing_in_ai']} | {tot['missing_in_csv']} |")
    md += ["", "## Differing items (AI value, CSV value, AI quote)", "", "| company | block | item | year | AI | CSV | AI quote |", "|---|---|---|---|---|---|---|"]
    for o in out:
        if o["result"] in ("differ", "class_differs"):
            q = (o.get("quote") or "").replace("|", "/").replace("\n", " ")
            q = q if len(q) <= 200 else q[:197] + "..."
            name = o["item"] + (f" [{o['line']}]" if o.get("line") else "")
            ai_v = f"{o['ai']:,.4g}" if isinstance(o["ai"], (int, float)) else o["ai"]
            csv_v = f"{o['csv']:,.4g}" if isinstance(o["csv"], (int, float)) else o["csv"]
            extra = f" (CSV class {o.get('csv_class')})" if o["result"] == "class_differs" else ""
            md.append(f"| {o['ticker']} | {o['block']} | {name}{extra} | {o['year']} | {ai_v} | {csv_v} | {q} |")
    (root / "compare.md").write_text("\n".join(md), encoding="utf-8")
    print(dict(tot))
    for b in sorted(per_block, key=lambda x: int(x[1:])):
        print(b, dict(per_block[b]))


if __name__ == "__main__":
    main()

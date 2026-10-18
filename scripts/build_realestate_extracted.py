"""Build scripts/realestate_extracted.csv from scripts/realestate_extraction_spec.py and the cached 10-K texts (scripts/cache/filings/RE_<T>_FY<yyyy>.txt).

Row types (see the spec file): normal rows carry anchor ``tokens`` (joined by a whitespace / | / $ / % tolerant regex) and ``verify`` (the number string that must appear in the
quote); ``absent`` rows record "not disclosed" with the search scope and are verified only when the absence regex has no match in the filing text. Every row stores the exact
quote (whitespace collapsed), the source document, section and character offset.  Run: .venv/Scripts/python -X utf8 scripts/build_realestate_extracted.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from realestate_extraction_spec import ROWS as _ROWS1  # noqa: E402
from realestate_extraction_spec_p2 import ROWS_P2  # noqa: E402
from realestate_extraction_spec_p3 import ROWS_P3  # noqa: E402
from realestate_extraction_spec_p4 import ROWS_P4  # noqa: E402
from realestate_extraction_spec_p5 import ROWS_P5  # noqa: E402
from realestate_extraction_spec_p6 import ROWS_P6  # noqa: E402

ROWS = list(_ROWS1) + list(ROWS_P2) + list(ROWS_P3) + list(ROWS_P4) + list(ROWS_P5) + list(ROWS_P6)

CACHE = ROOT / "scripts" / "cache" / "filings"
OUT = ROOT / "scripts" / "realestate_extracted.csv"
HEAD = ["ticker", "item", "year", "value", "unit", "quote", "source", "verified", "note"]


def _num(g: str) -> float:
    """Parse a table number: thousands separators, (negative), dash = 0."""
    g = g.strip()
    if g in ("-", "—", "–", "", "�", "—"):
        return 0.0
    neg = g.startswith("(") or g.startswith("-")
    return float(g.replace(",", "").strip("()- $")) * (-1 if neg else 1)


def _pattern(tokens):
    return r"[\s|$%<>]*".join(re.escape(t) for t in tokens)


def main():
    texts, out, fails = {}, [], []
    for r in ROWS:
        key = (r["t"], r["filing"])
        if key not in texts:
            if str(r["filing"]).startswith("SUP"):  # "SUP2025:tm263695d2" = the 8-K exhibit of fiscal year 2025 whose file name contains the fragment
                tag, frag = str(r["filing"]).split(":")
                fs = sorted(CACHE.glob(f"RE_{r['t']}_{tag}_*{frag}*.txt"))
                texts[key] = fs[0].read_text(encoding="utf-8").replace(chr(0x200b), "") if fs else ""
            else:
                p = CACHE / f"RE_{r['t']}_FY{r['filing']}.txt"
                texts[key] = p.read_text(encoding="utf-8").replace(chr(0x200b), "") if p.exists() else ""
        text = texts[key]
        src_head = text.split("\n", 1)[0] if text else "[filing not cached]"
        src = f"{src_head} | {r['section']}"
        if r.get("regex"):  # series row: regex groups map to the fiscal-year columns in ``cols``; numbers are parsed with thousands separators
            text = re.sub(r"[\s|]+", " ", text)  # series rows run on text with table cells collapsed to single spaces
            m = re.search(r["regex"], text, re.S | re.I) if text else None
            if not m or len(m.groups()) < len(r["cols"]):
                fails.append((r["t"], r["item"], r["cols"][0], "series regex not found"))
                continue
            s_, e_ = max(0, m.start() - r.get("pre", 0)), min(len(text), m.end() + r.get("post", 0))
            quote = re.sub(r"\s+", " ", text[s_:e_]).strip()
            if r.get("agg"):  # sum of selected groups (e.g. the four quarters of a fiscal year from a quarterly supplemental)
                col, idx = r["agg"]
                parts = []
                for k in idx:  # k = group index, or (group index, sign) to subtract a printed positive number
                    kk, sg = (k if isinstance(k, tuple) else (k, 1))
                    parts.append(sg * _num(m.group(kk + 1)))
                out.append([r["t"], r["item"], col, repr(round(sum(parts) * r.get("scale", 1.0), 10)), r["unit"], quote + " [value = sum of " + " + ".join(("-" if isinstance(k, tuple) and k[1] < 0 else "") + m.group((k[0] if isinstance(k, tuple) else k) + 1) for k in idx) + "]",
                            src + f" [char {m.start():,} of {len(text):,}]", "true" if all(m.group((k[0] if isinstance(k, tuple) else k) + 1).strip() in quote for k in idx) else "false", r.get("note", "")])
                continue
            for col, g in zip(r["cols"], m.groups()):
                if col is None:
                    continue
                num = _num(g) * r.get("scale", 1.0)
                out.append([r["t"], r["item"], col, repr(round(num, 10)), r["unit"], quote, src + f" [char {m.start():,} of {len(text):,}]", "true" if g.strip() in quote else "false", r.get("note", "")])
            continue
        if r.get("label"):  # line-item row: the first numbers after ``label`` inside the 9,000 characters that follow ``anchor`` (collapsed text); col 0 = current year, 1 = prior year
            ct = re.sub(r"[\s|]+", " ", text)
            num = r"(\(?\d[\d,]*(?:\.\d+)?\)?|[—–�-])"
            m, am = None, None
            for am in re.finditer(r["anchor"], ct):
                seg_end = am.end() + r.get("within", 9000)
                m = re.compile(r["label"] + r"\s*\$?\s*" + num + r"(?:\s*\$?\s*" + num + ")?").search(ct, am.end(), seg_end)
                if m:
                    break
            if not m:
                fails.append((r["t"], r["item"], r["year"], "line label not found after the anchor"))
                out.append([r["t"], r["item"], r["year"], "", r["unit"], "", src, "false", r.get("note", "")])
                continue
            g = m.group(1 + r.get("col", 0))
            quote = re.sub(r"\s+", " ", ct[max(0, m.start() - r.get("pre", 30)):m.end() + r.get("post", 30)]).strip()
            val = _num(g) * r.get("scale", 1.0)
            out.append([r["t"], r["item"], r["year"], repr(round(val, 10)), r["unit"], quote, src + f" [char {m.start():,} of {len(ct):,}]", "true" if (g.strip() in quote and g is not None) else "false", r.get("note", "")])
            continue
        if r.get("zero_absence"):  # numeric 0 backed by a verified absence (e.g. "no operating-partnership units outstanding")
            n = len(re.findall(r["zero_absence"], text, re.I))
            ok = n == 0 and bool(text)
            quote = f"[search scope: {r['scope']}; no match: {n} matches for /{r['zero_absence']}/ in {len(text):,} characters]"
            if not ok:
                fails.append((r["t"], r["item"], r["year"], f"expected absence but {n} matches"))
            out.append([r["t"], r["item"], r["year"], "0.0", r["unit"], quote, src, "true" if ok else "false", r.get("note", "")])
            continue
        if r.get("nomatch"):
            out.append([r["t"], r["item"], r["year"], r["value"], r.get("unit", ""), f"[not extracted this round: {r['scope']}]", src, "false", r.get("note", "")])
            continue
        if r.get("absence"):
            n = len(re.findall(r["absence"], text, re.I))
            quote = f"[search scope: {r['scope']}; no match: {n} matches for /{r['absence']}/ in {len(text):,} characters]"
            ok = n == 0 and bool(text)
            if not ok:
                fails.append((r["t"], r["item"], r["year"], f"expected absence but {n} matches"))
            out.append([r["t"], r["item"], r["year"], "not disclosed", r.get("unit", ""), quote, src, "true" if ok else "false", r.get("note", "")])
            continue
        m = re.search(_pattern(r["tokens"]), text, re.I) if text else None
        if not m:
            fails.append((r["t"], r["item"], r["year"], "anchor not found"))
            out.append([r["t"], r["item"], r["year"], r["value"], r["unit"], "", src, "false", r.get("note", "")])
            continue
        s, e = max(0, m.start() - r.get("pre", 40)), min(len(text), m.end() + r.get("post", 160))
        quote = re.sub(r"\s+", " ", text[s:e]).strip()
        ok = r.get("verify") is None or r["verify"] in quote
        if not ok:
            fails.append((r["t"], r["item"], r["year"], f"value string {r['verify']!r} not in quote"))
        out.append([r["t"], r["item"], r["year"], r["value"], r["unit"], quote, src + f" [char {m.start():,} of {len(text):,}]", "true" if ok else "false", r.get("note", "")])
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(HEAD)
        w.writerow(["# INCOME_REAL_ESTATE extracted items, round 2 (2026-10-14). value units: USD (full dollars), fractions (0.989 = 98.9%); 'not disclosed' rows carry the search scope; verified = the value string is in the quote / the absence regex has no match"] + [""] * 8)
        w.writerows(out)
    n_ok = sum(1 for x in out if x[7] == "true")
    print(f"{len(out)} rows, {n_ok} verified, {len(fails)} failures")
    for f in fails:
        print("  FAIL", f)


if __name__ == "__main__":
    main()

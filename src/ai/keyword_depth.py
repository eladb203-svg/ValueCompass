"""REIT depth items by keyword search of the annual-report text (no model) - an automatic step of the extraction task of a real-estate company (K6d-2 fixes, 2026-11-01).

Three families the model's single call per report does not give:
  * occupancy for several years: the same sentence / table row searched in the last N annual reports (the earlier ones are downloaded through the rate-limited SEC client);
  * same-property NOI growth: the filing states same-property NOI levels for two years of the same pool -> growth = current / prior - 1, flagged ``derived``, with the quote holding both numbers
    (rulebook CL22);
  * unencumbered assets share: "unencumbered asset value $A ... total asset value $B" -> the backup of the rulebook (the engine reads ``unencumbered_assets_share``) when the model returned
    ``not_disclosed`` for both unencumbered items.
A row is made only when the matched text is in the report as written; the status follows the block rule of EXT-RE-OPS / EXT-RE-UNENC (automatic when the 0-100 control passes).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .checks import normalize

ROOT = Path(__file__).resolve().parents[2]
FILINGS = ROOT / "scripts" / "cache" / "filings"

# occupancy: ordered by how specific the sentence is; the first pattern that matches the LATEST report is used for every report (one basis across the years)
OCCUPANCY = (
    ("average occupancy of the same-store pool", r"average (?:physical |square foot )?occupancy[^.%$]{0,80}?(?:was|were|of)\s*(\d{2,3}(?:\.\d)?)\s?%"),
    ("approximately N% leased", r"approximately (\d{2,3}(?:\.\d)?)\s?% (?:leased|occupied)"),
    ("properties are N% leased", r"(?:properties|portfolio|stores|communities|facilities|buildings)[^.%$]{0,40}? (?:are|were|was|is) (\d{2,3}(?:\.\d)?)\s?% (?:leased|occupied)"),
    ("Same Store table row", r"Same Store \d+ [\d,]+ (\d{2,3}\.\d) ?%"),
    ("N% occupancy / leased", r"(\d{2,3}(?:\.\d)?)\s?% (?:occupancy|occupied|leased)\b"),
)
SAME_NOI = (
    r"[Tt]otal same[- ]?(?:store|property) net operating income\s*\$?\s*([\d,]{5,})\s*\$?\s*([\d,]{5,})",
    r"[Ss]ame[- ]?[Ss]tore NOI\s*\$?\s*([\d,]{5,})\s*\$?\s*([\d,]{5,})",
    r"[Ss]ame[- ]?(?:store|property) (?:NOI|net operating income)[^0-9$]{0,40}\$\s?([\d,]{5,})\s*\$\s?([\d,]{5,})",
)
# insurers: the investment-grade share of the fixed income portfolio, from the sentence or the table line of the report (the first form that matches)
IG_SENTENCES = (
    (r"investment[- ]grade[^.%]{0,80}?(?:representing|represented|representing approximately|were|was|of)\s*(?:approximately )?(\d{2,3}(?:\.\d)?)\s?%", False),
    (r"(\d{2,3}(?:\.\d)?)\s?% of (?:our |the |AFG[’']s )?[^.%]{0,100}?(?:fixed (?:maturity|maturities|income)|portfolio)[^.%]{0,100}?(?:investment[- ]grade|rated investment grade)", False),
    (r"[Tt]otal investment grade\s+[\d,\.]+\s+[\d,\.]+\s+(\d{2,3})\s?%", False),
    (r"[Nn]on-investment[- ]grade [^.%]{0,100}?(?:represented|representing|was|were|of)\s*(?:approximately )?(\d{1,2}(?:\.\d)?)\s?%", True),     # the complement
)
UNENC = r"unencumbered (?:asset|property) value[^$]{0,120}\$\s?([\d,\.]+)[^$]{0,200}?total (?:asset|property) value[^$]{0,120}\$\s?([\d,\.]+)"


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def report_text(path: Path) -> str:
    from src.providers.sec_filings import html_to_text
    return normalize(html_to_text(Path(path).read_text(encoding="utf-8", errors="ignore")))


def occupancy_rows(texts: dict) -> list:
    """texts = {fiscal year: (accession, normalized text)} -> [(year, accession, value, quote, basis)]. One pattern for all years: the first that matches the latest report."""
    years = sorted(texts)
    if not years:
        return []
    pat = next(((b, p) for b, p in OCCUPANCY if re.search(p, texts[years[-1]][1])), None)
    if pat is None:
        return []
    out = []
    for y in years:
        m = re.search(pat[1], texts[y][1])
        if m and 0 < _num(m.group(1)) <= 100:
            out.append((y, texts[y][0], _num(m.group(1)), texts[y][1][m.start():m.end()], pat[0]))
    return out


def same_noi_rows(texts: dict) -> list:
    """[(year, accession, growth in percent, quote, basis)] - growth of the same pool, current over prior year, from the two levels in one quote."""
    out = []
    for y in sorted(texts):
        for p in SAME_NOI:
            m = re.search(p, texts[y][1])
            if m:
                cur, prior = _num(m.group(1)), _num(m.group(2))
                if prior > 0 and cur > 0 and abs(cur / prior - 1) <= 0.5:
                    out.append((y, texts[y][0], round((cur / prior - 1) * 100, 4), texts[y][1][m.start():m.end()], "same-property NOI growth derived: current / prior - 1 (both levels in the quote)"))
                break
    return out


def unencumbered_rows(texts: dict) -> list:
    out = []
    for y in sorted(texts):
        m = re.search(UNENC, texts[y][1], re.I)
        if m:
            a, b = _num(m.group(1)), _num(m.group(2))
            if b > 0 and 0 < a <= b * 1.0001:
                out.append((y, texts[y][0], round(a / b * 100, 4), texts[y][1][m.start():m.end()], "unencumbered asset value / total asset value, as defined by the public bonds (derived from both figures)"))
    return out


def _row(ticker: str, item: str, skill: str, block: str, y: int, acc: str, value: float, quote: str, basis: str, derived: bool) -> dict:
    ok = 0 <= value <= 100 if item != "same_property_noi_growth" else -50 <= value <= 50
    return {"ticker": ticker, "item_key": item, "year": y, "fiscal_year": y, "accession": acc, "skill_id": skill, "block": block, "version": 1, "prompt_version": "kw2", "model": "keyword-search",
            "state": "value", "stated_state": "value", "value": value, "value_full": value, "scale": 1, "unit": "percent", "period": f"December 31, {y}", "basis": basis, "quote": quote,
            "section": "keyword search of the annual report text", "flags": ["derived"] if derived else [], "reasons": [], "control": "bounds_0_100", "control_result": "pass" if ok else "fail",
            "control_detail": "keyword depth step (src/ai/keyword_depth.py)", "approval_status": "approved" if ok else "pending",
            "approval_reason": "block rule: automatic when the bounds control passes; the quote is found in the report text as written"}


def build_rows(ticker: str, texts: dict, have_unenc_value: bool, have_same_noi_years: set, have_occupancy_years: set) -> list:
    """The rows to add. An item/year the model already answered with a value is left alone; ``not_disclosed`` is replaced."""
    rows = []
    for y, acc, v, q, b in occupancy_rows(texts):
        if y not in have_occupancy_years:
            rows.append(_row(ticker, "occupancy", "EXT-RE-OPS", "B5", y, acc, v, q, b, False))
    for y, acc, v, q, b in same_noi_rows(texts):
        if y not in have_same_noi_years:
            rows.append(_row(ticker, "same_property_noi_growth", "EXT-RE-OPS", "B5", y, acc, v, q, b, True))
    if not have_unenc_value:
        for y, acc, v, q, b in unencumbered_rows(texts):
            rows.append(_row(ticker, "unencumbered_assets_share", "EXT-RE-UNENC", "B9", y, acc, v, q, b, True))
    return rows


def reports(sec, ticker: str, n: int = 5) -> dict:
    """{fiscal year: (accession, normalized text)} of the last n annual reports (downloaded when missing)."""
    from src.pipeline.resolve import resolve
    from src.providers.sec_filings import _get_raw
    r = resolve(sec, ticker)
    out = {}
    for f in r.annual[:n]:
        acc = f.accession.replace("-", "")
        name = f"{acc}_{f.primary_doc}"
        _get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(r.cik)}/{acc}/{f.primary_doc}", name)
        if f.fiscal_year:
            out[f.fiscal_year] = (f.accession, report_text(FILINGS / name))
    return out


def run(client, item_store, sec, ticker: str, n: int = 5) -> dict:
    """The step: search, write the rows, return a summary for the task result. Idempotent."""
    rows_db = item_store.rows_for(ticker)
    have = lambda key: {r["year"] for r in rows_db if r.get("item_key") == key and r.get("state") == "value" and r.get("model") != "keyword-search"}   # noqa: E731
    unenc_value = any(r.get("item_key") in ("unencumbered_noi_share", "unencumbered_assets_share") and r.get("state") == "value" and r.get("model") != "keyword-search" for r in rows_db)
    texts = reports(sec, ticker, n)
    rows = build_rows(ticker, texts, unenc_value, have("same_property_noi_growth"), have("occupancy"))
    stats = item_store.upsert_rows(rows, "ai_controls") if rows else {}
    return {"reports": sorted(texts), "rows": len(rows), "by_item": {k: sum(1 for r in rows if r["item_key"] == k) for k in {r["item_key"] for r in rows}}, "upsert": stats}


def ig_share_rows(texts: dict) -> list:
    """[(year, accession, investment-grade share in percent, quote, basis)] - one form for all years: the first that matches the latest report."""
    years = sorted(texts)
    if not years:
        return []
    form = next(((p, comp) for p, comp in IG_SENTENCES if re.search(p, texts[years[-1]][1])), None)
    if form is None:
        return []
    out = []
    for y in years:
        m = re.search(form[0], texts[y][1])
        if m:
            v = _num(m.group(1))
            v = 100.0 - v if form[1] else v
            if 0 < v <= 100:
                out.append((y, texts[y][0], v, texts[y][1][m.start():m.end()], "investment-grade share of the fixed income portfolio" + (" (100 - the stated non-investment-grade share)" if form[1] else "")))
    return out


def run_insurer(client, item_store, sec, ticker: str, n: int = 3) -> dict:
    """The insurer step: the investment-grade share where the model returned none for the year."""
    rows_db = item_store.rows_for(ticker)
    have = {r["year"] for r in rows_db if r.get("item_key") == "inv_ig_share" and r.get("state") == "value" and r.get("model") != "keyword-search"}      # the engine uses the share when no total fixed income was extracted
    texts = reports(sec, ticker, n)
    rows = [_row(ticker, "inv_ig_share", "EXT-INS-INV", "B4", y, acc, v, q, b, "100 -" in b) for y, acc, v, q, b in ig_share_rows(texts) if y not in have]
    stats = item_store.upsert_rows(rows, "ai_controls") if rows else {}
    return {"reports": sorted(texts), "rows": len(rows), "upsert": stats}

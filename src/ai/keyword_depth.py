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
# same-property table without an NOI line (REXR): revenues and property expenses of the same pool, current and prior year -> NOI = revenues - property expenses
SAME_ANCHOR = r"[Ss]ame[- ](?:[Pp]roperty|[Ss]tore)"
SAME_REV = r"(?:TOTAL REVENUES|Total revenues|Rental (?:income|revenues?)|Rental and other (?:income|revenues?))\s+\$?\s*([\d,]{5,})\s+\$?\s*([\d,]{5,})"
SAME_EXP = r"(?:Property|Real estate|Property operating) (?:operating )?expenses?\s+\$?\s*([\d,]{4,})\s+\$?\s*([\d,]{4,})"
# tenants: "no single tenant ... more than X%" is a ceiling (bound=max); "10 largest tenants ... Y%" is a separate item
TENANT_WORDS = r"(?:tenants?|operators?|lessees?|customers?)"           # a healthcare REIT calls its tenants operators
TENANT_CAP = r"no (?:single |one )?" + TENANT_WORDS + r"[^.%$]{0,100}?(?:more than|greater than|in excess of|exceeding|over) (\d{1,2}(?:\.\d+)?)\s?%"
# "one operator represented greater than 10% of our investments" is a floor (the largest is at least X): kept as its own item, never scored as the largest share
TENANT_FLOOR = r"(?:one|a single|an?) " + TENANT_WORDS + r"[^.%$]{0,60}?(?:represented|accounted for|accounting for|representing)[^.%$]{0,30}?(?:more than|greater than|in excess of|over) (\d{1,2}(?:\.\d+)?)\s?%"
TENANT_TOP10 = r"(?:10|ten) largest " + TENANT_WORDS + r"[^.%$]{0,120}?(\d{1,2}(?:\.\d+)?)\s?%"
# insurers: investment-grade share from amounts - "non-investment grade bonds totaled $148 million while non-rated ... $90 million"
NONIG = r"non-investment[- ]grade[^.$]{0,80}?\$\s?([\d,\.]+)\s+(million|billion)"
NONRATED = r"non-rated[^.$]{0,100}?\$\s?([\d,\.]+)\s+(million|billion)"
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
        else:
            t = same_table(texts[y][1])
            if t:
                out.append((y, texts[y][0], t[0], t[1], t[2]))
    return out


def same_table(text: str) -> Optional[tuple]:
    """The same-property table with revenues and property expenses but no NOI line -> (growth in percent, quote, basis) or None. NOI = revenues - property expenses for each of the two years;
    growth = current / prior - 1 (rulebook CL22). The quote runs from the revenue line to the end of the expense line, so both lines are in it."""
    for a in re.finditer(SAME_ANCHOR, text):
        win = text[a.start():a.start() + 3500]
        r = re.search(SAME_REV, win)
        if not r:
            continue
        e = re.search(SAME_EXP, win[r.end():r.end() + 900])
        if not e:
            continue
        rc, rp, ec, ep = _num(r.group(1)), _num(r.group(2)), _num(e.group(1)), _num(e.group(2))
        cur, prior = rc - ec, rp - ep
        if prior > 0 and cur > 0 and ec < rc and ep < rp and abs(cur / prior - 1) <= 0.5:
            quote = win[r.start():r.end() + e.end()]
            return (round((cur / prior - 1) * 100, 4), quote,
                    f"same-property NOI derived: NOI = revenues - property expenses = {rc:,.0f} - {ec:,.0f} = {cur:,.0f} and {rp:,.0f} - {ep:,.0f} = {prior:,.0f}; growth = current / prior - 1 (CL22)")
    return None


def tenant_rows(texts: dict) -> list:
    """[(item, year, accession, value, quote, basis, bound)] - the ceiling of the largest tenant and the share of the 10 largest tenants, from the sentence of the report."""
    out = []
    for y in sorted(texts):
        t = texts[y][1]
        m = re.search(TENANT_CAP, t, re.I)
        if m and 0 < _num(m.group(1)) <= 100:
            out.append(("largest_tenant_share", y, texts[y][0], _num(m.group(1)), t[m.start():m.end()], "upper bound (bound=max): no single tenant above this share of annualized base rent; the largest tenant is at or below it", True))
        m = re.search(TENANT_FLOOR, t, re.I)
        if m and 0 < _num(m.group(1)) <= 100 and not re.search(TENANT_CAP, t, re.I):
            out.append(("largest_tenant_floor", y, texts[y][0], _num(m.group(1)), t[m.start():m.end()], "lower bound (bound=min): the largest tenant / operator is at or above this share; not a scored value", False))
        m = re.search(TENANT_TOP10, t, re.I)
        if m and 0 < _num(m.group(1)) <= 100:
            out.append(("top10_tenants_share", y, texts[y][0], _num(m.group(1)), t[m.start():m.end()], "share of annualized base rent of the 10 largest tenants", False))
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


def build_rows(ticker: str, texts: dict, have_unenc_value: bool, have_same_noi_years: set, have_occupancy_years: set, have_tenant_years: Optional[dict] = None) -> list:
    """The rows to add. An item/year the model already answered with a value is left alone; ``not_disclosed`` is replaced."""
    rows = []
    for y, acc, v, q, b in occupancy_rows(texts):
        if y not in have_occupancy_years:
            rows.append(_row(ticker, "occupancy", "EXT-RE-OPS", "B5", y, acc, v, q, b, False))
    for y, acc, v, q, b in same_noi_rows(texts):
        if y not in have_same_noi_years:
            rows.append(_row(ticker, "same_property_noi_growth", "EXT-RE-OPS", "B5", y, acc, v, q, b, True))
    have_tenant_years = have_tenant_years or {}
    for item, y, acc, v, q, b, bound in tenant_rows(texts):
        if y not in have_tenant_years.get(item, set()):
            rows.append(_row(ticker, item, "EXT-RE-OPS", "B5", y, acc, v, q, b, False))
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
    rows = build_rows(ticker, texts, unenc_value, have("same_property_noi_growth"), have("occupancy"), {k: have(k) for k in ("largest_tenant_share", "top10_tenants_share")})
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


def _amount(num: str, unit: str) -> float:
    return _num(num.rstrip(".")) * (1e9 if unit.lower() == "billion" else 1e6)


def ig_amount_rows(texts: dict, totals: dict) -> list:
    """[(year, accession, investment-grade share in percent, quote, basis)] where the report gives only the amounts of non-investment-grade (and non-rated) bonds: share = 1 - (non-IG + non-rated) / total
    fixed income. ``totals`` = {year: (amount in USD, where it comes from)}; a year without a total gives no row (the item stays missing). The non-rated part is counted as not investment grade (the cautious reading)."""
    out = []
    for y in sorted(texts):
        if y not in totals:
            continue
        t = texts[y][1]
        a = re.search(NONIG, t, re.I)
        if not a:
            continue
        b = re.search(NONRATED, t[a.start():a.end() + 400], re.I)
        low = _amount(a.group(1), a.group(2)) + (_amount(b.group(1), b.group(2)) if b else 0.0)
        total, src = totals[y]
        if total > 0 and 0 <= low < total:
            end = a.start() + (b.end() if b else a.end() - a.start())
            share = round((1 - low / total) * 100, 4)
            out.append((y, texts[y][0], share, t[a.start():end], f"investment-grade share derived: 1 - (non-investment grade{' + non-rated' if b else ''} = {low / 1e6:,.0f} m) / fixed income {total / 1e6:,.0f} m ({src})"))
    return out


def fixed_income_totals(item_rows: list, facts_json: dict, years: list) -> dict:
    """{fiscal year: (USD, source)} - the fixed-income total of the report (an extracted row of the investments block), else the XBRL fair value of debt securities of the year."""
    out = {}
    for r in item_rows:
        if r.get("item_key") in ("inv_fixed_maturities", "inv_total_fixed_income") and r.get("state") == "value" and r.get("value_full") and r.get("year") in years and r.get("approval_status") != "rejected":
            out.setdefault(r["year"], (float(r["value_full"]), f"report: {r['item_key']} of the investments block"))
    from datetime import date
    gaap = (facts_json or {}).get("facts", {}).get("us-gaap", {})
    for tag in ("AvailableForSaleSecuritiesDebtSecurities", "DebtSecuritiesAvailableForSaleExcludingAccruedInterest"):
        for e in gaap.get(tag, {}).get("units", {}).get("USD", []):
            if e.get("form") in ("10-K", "10-K/A") and e.get("fp") == "FY" and "start" not in e:
                y = date.fromisoformat(e["end"]).year
                if y in years and y not in out:
                    out[y] = (float(e["val"]), f"XBRL {tag}")
    return out


def run_insurer(client, item_store, sec, ticker: str, n: int = 3) -> dict:
    """The insurer step: the investment-grade share where the model returned none for the year."""
    rows_db = item_store.rows_for(ticker)
    have = {r["year"] for r in rows_db if r.get("item_key") == "inv_ig_share" and r.get("state") == "value" and r.get("model") != "keyword-search"}      # the engine uses the share when no total fixed income was extracted
    texts = reports(sec, ticker, n)
    rows = [_row(ticker, "inv_ig_share", "EXT-INS-INV", "B4", y, acc, v, q, b, "100 -" in b) for y, acc, v, q, b in ig_share_rows(texts) if y not in have]
    done = {r["year"] for r in rows} | have
    if any(y not in done for y in texts):                                # K6d-2 fixes (RLI): only amounts of non-investment-grade bonds -> the share from the fixed-income total
        try:
            from src.pipeline.resolve import resolve
            facts_json = sec.companyfacts(resolve(sec, ticker).cik)
        except Exception:  # noqa: BLE001 - the XBRL total is a second source; the report's own total may be enough
            facts_json = {}
        totals = fixed_income_totals(rows_db, facts_json, list(texts))
        rows += [_row(ticker, "inv_ig_share", "EXT-INS-INV", "B4", y, acc, v, q, b, True) for y, acc, v, q, b in ig_amount_rows(texts, totals) if y not in done]
    stats = item_store.upsert_rows(rows, "ai_controls") if rows else {}
    return {"reports": sorted(texts), "rows": len(rows), "upsert": stats}

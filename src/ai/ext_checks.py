"""Code checks on extraction answers (AI spec section 4.4) and the block controls (AI skills document "Other", section 2). Pure.

Per item: the quote is found verbatim in the text sent; the number appears in the quote after scale conversion (millions / thousands, parentheses = negative, percents); the unit is allowed;
the period belongs to the report; value_state is consistent. Per block: a control over the accepted items (sum of lines = total, categories = total, bounds ...).
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Optional

from .checks import normalize, parse_json, MIN_QUOTE_CHARS

SCALES = (1, 1000, 1000000, 1000000000)
UNITS = ("USD", "percent", "count", "ratio", "sq_ft", "MW")
STATES = ("value", "NA", "not_disclosed")
# items that the report text rarely carries because the company publishes them in the supplemental package (an 8-K, not downloaded): not_disclosed is flagged
SUPPLEMENTAL_ITEMS = ("acquisition_yield", "development_yield", "acquisition_invested", "development_invested", "unencumbered_noi_share", "unencumbered_assets_share",
                      "same_property_noi_growth", "largest_tenant_share", "occupancy", "maint_capex", "ti_lc", "straight_line_rent_affo", "stabilized_noi", "stabilized_value",
                      "other_property_value", "committed_undrawn_facilities")

_NUM = re.compile(r"(\()?\s*(-|−|–)?\s*\$?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(\))?\s*(%|percent|pp|bp|bps|x|times|thousand|million|billion|trillion|bn|mm|mil)?", re.I)
_WORD = {"thousand": 1e3, "million": 1e6, "mil": 1e6, "mm": 1e6, "billion": 1e9, "bn": 1e9, "trillion": 1e12}


def quote_numbers(q: str) -> list:
    """[(abs value, word multiplier, negative?, followed by %?)] for every number in a quote."""
    out = []
    for m in _NUM.finditer(q or ""):
        try:
            v = float(m.group(3).replace(",", ""))
        except ValueError:
            continue
        suf = (m.group(5) or "").lower()
        neg = bool(m.group(1) and m.group(4)) or bool(m.group(2))
        out.append((v, _WORD.get(suf, 1.0), neg, suf in ("%", "percent")))
    return out


def _close(a: float, b: float, rel: float = 1e-6) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=1e-9)


def number_in_quote(value: float, scale: int, unit: str, quote: str) -> tuple:
    """-> (found, negative_in_quote). The value as stated (``value`` in units of ``scale``) must be one of the quote's numbers: as written, times the word multiplier ('1.2 billion'),
    in another table scale (x1000 steps), or for a percent as a fraction / percentage points."""
    av = abs(float(value))
    full = av * (scale or 1)
    for n, mult, neg, pct in quote_numbers(quote):
        cands = [n, n * mult]
        if unit in ("USD", "count", "sq_ft", "MW"):
            cands_full = [n * 10 ** k for k in (0, 3, 6, 9)] + [n * mult]
            if any(_close(full, c) for c in cands_full) or any(_close(av, c) for c in cands):
                return True, neg
        else:
            cands += [n / 100.0, n * 100.0]
            if any(_close(av, c) for c in cands):
                return True, neg
    return False, False


_YEAR = re.compile(r"(20\d\d)")


def period_year(period: str, fy: int) -> tuple:
    """-> (year, assumed). A period without a year ('Q4 average', 'year end') is the report's fiscal year (flagged)."""
    ys = [int(y) for y in _YEAR.findall(period or "")]
    if ys:
        return ys[-1] if len(ys) == 1 else max(ys), False
    return fy, True


@dataclass
class ItemResult:
    ok: bool
    item: dict
    reasons: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    year: Optional[int] = None
    value_full: Optional[float] = None


def check_item(it: dict, keys: dict, text_norm: str, fy: int, window: int = 2, rule: Optional[str] = None) -> ItemResult:
    """``keys`` = {item_key: expected unit}. One item of the model's answer."""
    res = ItemResult(False, it)
    if not isinstance(it, dict):
        res.reasons.append("item_malformed")
        return res
    key, state = it.get("item_key"), it.get("value_state")
    if key not in keys:
        res.reasons.append("item_key_unknown")
        return res
    if state not in STATES:
        res.reasons.append("value_state_invalid")
        return res
    res.year, assumed = period_year(str(it.get("period") or ""), fy)
    if assumed:
        res.flags.append("period_assumed_fiscal_year")
    if not (fy - window <= res.year <= fy):
        res.reasons.append("period_mismatch")
    v = it.get("value")
    if state != "value":
        if v is not None:
            res.reasons.append("value_state_inconsistent")                  # null only with NA / not_disclosed
        elif state == "not_disclosed" and key in SUPPLEMENTAL_ITEMS:
            res.flags.append("supplemental_only")
        res.ok = not res.reasons
        return res
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (isinstance(v, float) and math.isnan(v)):
        res.reasons.append("value_state_inconsistent")                      # state 'value' needs a number
        return res
    if it.get("unit") not in UNITS or it.get("unit") != keys[key]:
        res.reasons.append("unit_not_allowed")
    sc = it.get("scale")
    if isinstance(sc, bool) or sc not in SCALES:
        res.reasons.append("scale_not_allowed")
        sc = 1
    q = it.get("quote")
    qt = q.get("text") if isinstance(q, dict) else None
    if not isinstance(qt, str):
        res.reasons.append("no_quote")
        return res
    qn = normalize(qt)
    if len(qn) < MIN_QUOTE_CHARS or "..." in qn or "…" in qn:
        res.reasons.append("quote_not_found")
    elif qn not in text_norm:
        res.reasons.append("quote_not_found")
    else:
        found, neg = number_in_quote(float(v), int(sc), str(it.get("unit")), qt)
        if not found:
            res.reasons.append("number_not_in_quote")
        elif (v < 0) != neg and key not in ("loan_line",):
            res.flags.append("sign_not_verified")
    res.value_full = float(v) * int(sc) if it.get("unit") == "USD" else float(v)
    from . import ext_norm                                                   # year from the table columns, sign from the convention of the item (K5b-2)
    ext_norm.apply(res, it, text_norm, fy, rule, window)
    res.ok = not res.reasons
    return res


def salvage_items(raw: str) -> Optional[dict]:
    """A reply cut off at the output limit: the complete items before the cut are kept (flagged by the caller). -> {"skill_id"?, "items": [...]} or None."""
    t = (raw or "")
    i = t.find('"items"')
    j = t.find("[", i) if i >= 0 else -1
    if j < 0:
        return None
    dec, pos, items = json.JSONDecoder(), j + 1, []
    while True:
        m = re.compile(r"[\s,]*").match(t, pos)
        pos = m.end()
        if pos >= len(t) or t[pos] != "{":
            break
        try:
            obj, pos = dec.raw_decode(t, pos)
        except ValueError:
            break
        items.append(obj)
    sid = re.search(r'"skill_id"\s*:\s*"([^"]+)"', t)
    return {"skill_id": sid.group(1) if sid else None, "items": items} if items else None


def check_reply(raw: str, block: dict, text_sent: str, fy: int, items: Optional[list] = None) -> tuple:
    """-> (results, reasons): the item results of one block call, and call-level reasons (invalid_json, skill_id_mismatch)."""
    d = parse_json(raw)
    reasons = []
    if d is None:
        try:
            bare = json.loads((raw or "").strip().removeprefix("```json").removesuffix("```").strip())
        except ValueError:
            bare = None
        if isinstance(bare, list):                                           # the model returned the list of items without the wrapping object (USB B14)
            d = {"skill_id": block["skill_id"], "items": bare}
            reasons.append("bare_list_accepted")
    if d is None:
        d = salvage_items(raw)
        if d is None:
            return [], ["invalid_json"]
        reasons.append("truncated_salvaged")
    if d.get("skill_id") != block["skill_id"]:
        reasons.append("skill_id_mismatch")
    its = d.get("items")
    if not isinstance(its, list):
        return [], reasons + ["items_missing"]
    keys = {i["key"]: i["unit"] for i in (items if items is not None else block["items"])}
    tn = normalize(text_sent)
    from .prompt import extraction_signs
    signs, _ = extraction_signs()
    return [check_item(it, keys, tn, fy, rule=signs.get(it.get("item_key")) if isinstance(it, dict) else None) for it in its], reasons


# ---------------------------------------------------------------- block controls
def _by_year(rows: list, key: str) -> dict:
    return {r["year"]: r for r in rows if r["item_key"] == key and r.get("value_full") is not None}


def _fld(r: dict, k: str):
    """Field of an item row: flat in stored rows, nested under ``item`` in the older test rows."""
    return r[k] if k in r else (r.get("item") or {}).get(k)


def _group(rows: list, key: str) -> dict:
    out: dict = {}
    for r in rows:
        if r["item_key"] == key and r.get("value_full") is not None:
            out.setdefault(r["year"], []).append(r)
    return out


def ctl(name: str, result: str, detail: str = "", items: Optional[list] = None, years: Optional[dict] = None) -> dict:
    return {"name": name, "result": result, "detail": detail, "items": items or [], "years": years or {}}


def control_cet1_vs_rwa(rows: list) -> dict:
    cap = _by_year(rows, "cet1_capital")
    bad, ok, n = [], [], 0
    for ap in ("standardized", "advanced"):
        ratio, rwa = _by_year(rows, f"cet1_ratio_{ap}"), _by_year(rows, f"rwa_{ap}")
        for y in sorted(set(cap) & set(rwa) & set(ratio)):
            n += 1
            calc = cap[y]["value_full"] / rwa[y]["value_full"] * 100.0
            (ok if abs(calc - ratio[y]["value_full"]) <= 0.2 else bad).append(f"{ap} {y}: capital/RWA {calc:.2f}% vs ratio {ratio[y]['value_full']:.2f}%")
    if n == 0:
        return ctl("cet1_vs_rwa", "na", "CET1 capital, RWA and ratio not all disclosed", ["cet1_capital", "rwa_standardized", "cet1_ratio_standardized"])
    return ctl("cet1_vs_rwa", "fail" if bad else "pass", "; ".join(bad or ok), ["cet1_capital", "rwa_standardized", "rwa_advanced", "cet1_ratio_standardized", "cet1_ratio_advanced"])


def control_loans_sum(rows: list) -> dict:
    tot = _by_year(rows, "total_loans")
    lines = _group(rows, "loan_line")
    out, bad = [], []
    for y in sorted(set(tot) & set(lines)):
        ls = [r for r in lines[y] if not re.match(r"\s*total\b", str(_fld(r, "basis") or ""), re.I)]
        s = sum(r["value_full"] for r in ls)
        diff = abs(s - tot[y]["value_full"]) / abs(tot[y]["value_full"]) if tot[y]["value_full"] else 1.0
        (out if diff <= 0.01 else bad).append(f"{y}: sum of {len(ls)} lines {s:,.0f} vs total {tot[y]['value_full']:,.0f} ({diff:.2%})")
    if not out and not bad:
        return ctl("loans_sum", "na", "no total loans or no loan lines", ["loan_line", "total_loans"])
    return ctl("loans_sum", "fail" if bad else "pass", "; ".join(bad or out), ["loan_line", "total_loans"])


INV_PARTS = ("inv_cash", "inv_short_term", "inv_fixed_maturities", "inv_equity", "inv_illiquid_loans", "inv_real_estate", "inv_other")


def control_inv_sum(rows: list) -> dict:
    tot = _by_year(rows, "inv_total")
    out, bad = [], []
    for y in sorted(tot):
        s = sum((_by_year(rows, k).get(y) or {}).get("value_full", 0.0) for k in INV_PARTS)
        if s == 0:
            continue
        diff = abs(s - tot[y]["value_full"]) / abs(tot[y]["value_full"]) if tot[y]["value_full"] else 1.0
        (out if diff <= 0.02 else bad).append(f"{y}: categories {s:,.0f} vs total {tot[y]['value_full']:,.0f} ({diff:.2%})")
    if not out and not bad:
        return ctl("inv_sum", "na", "no total investments or no categories", list(INV_PARTS) + ["inv_total"])
    return ctl("inv_sum", "fail" if bad else "pass", "; ".join(bad or out), list(INV_PARTS) + ["inv_total"])


def control_bounds(rows: list) -> dict:
    bad = [f"{r['item_key']} {r['year']}: {r['value_full']}" for r in rows if _fld(r, "unit") == "percent" and r.get("value_full") is not None and not (0.0 <= r["value_full"] <= 100.0)]
    return ctl("bounds_0_100", "fail" if bad else "pass", "; ".join(bad) or "all percentages within 0-100", [])


def control_assets_sum(rows: list) -> dict:
    tot = _by_year(rows, "total_assets")
    classes = [k for k in {r["item_key"] for r in rows} if k.startswith("bsa_")]
    out, bad = [], []
    for y in sorted(tot):
        s = sum(r["value_full"] for r in rows if r["item_key"] in classes and r["year"] == y and r.get("value_full") is not None)
        other = sum(r["value_full"] for r in rows if r["item_key"] == "bsa_other" and r["year"] == y and r.get("value_full") is not None)
        diff = abs(s - tot[y]["value_full"]) / abs(tot[y]["value_full"]) if tot[y]["value_full"] else 1.0
        note = f"{y}: lines {s:,.0f} vs total assets {tot[y]['value_full']:,.0f} ({diff:.2%})"
        if tot[y]["value_full"] and other / tot[y]["value_full"] > 0.10:
            note += f"; unidentified {other / tot[y]['value_full']:.0%} > 10% -> no Graham price score (RP2a)"
            diff = 1.0
        (out if diff <= 0.005 else bad).append(note)
    if not out and not bad:
        return ctl("assets_sum", "na", "total assets or lines not disclosed", classes)
    return ctl("assets_sum", "fail" if bad else "pass", "; ".join(bad or out), classes + ["total_assets"])


def control_neighbours(rows: list, series: Optional[dict] = None) -> dict:
    """B14: a value more than 3x or less than 1/3 of both neighbouring years (neighbours from the extracted rows or the tag series) is flagged. Per item key: {year: flagged?}."""
    flagged, years = [], {}
    keys = {r["item_key"] for r in rows}
    for k in sorted(keys):
        vals = {r["year"]: r["value_full"] for r in rows if r["item_key"] == k and r.get("value_full") is not None}
        for src in ((series or {}).get(k) or {}).items():
            vals.setdefault(int(src[0]), src[1])
        for y, v in vals.items():
            nb = [vals[z] for z in (y - 1, y + 1) if z in vals and vals[z]]
            if v and nb and all(abs(v) > 3 * abs(n) or abs(v) < abs(n) / 3 for n in nb):
                flagged.append(f"{k} {y}: {v:,.0f} vs neighbours {', '.join(f'{n:,.0f}' for n in nb)}")
                years.setdefault(k, {})[y] = "flag"
    return ctl("neighbours_3x", "fail" if flagged else "pass", "; ".join(flagged) or "no value beyond 3x of both neighbours", [], years)


BLOCK_CONTROLS = {"cet1_vs_rwa": control_cet1_vs_rwa, "loans_sum": control_loans_sum, "inv_sum": control_inv_sum, "bounds_0_100": control_bounds, "assets_sum": control_assets_sum}

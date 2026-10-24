"""Normalisation of extraction items by code (K5b-2): the year of a table value from the column headers of the table, and the sign of an item from the convention of the item and the wording of
its table line - never from what the model decided. Pure over the text sent and the quote."""
from __future__ import annotations

import re
from typing import Optional

from .checks import normalize
from .ext_checks import number_in_quote

_MONTH_DAY = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\s*,?", re.I)
_YEAR = re.compile(r"\b(20\d\d)\b")
_TOKEN = re.compile(r"(\(?\s*(?:[-−](?=\$?\d))?\$?\s*\d[\d,]*(?:\.\d+)?\s*\)?)\s*(%)?|(?<=\s)(-)(?=\s|$)")
_FOOTNOTE = re.compile(r"^\(\s*\d\s*\)$")


def data_tokens(s: str) -> tuple:
    """-> (label, tokens): the line label (text before the first data number) and the data cells of the line in order: (text, negative?, is_percent, is_dash)."""
    label_end = None
    toks = []
    for m in _TOKEN.finditer(s):
        t = (m.group(1) or m.group(3) or "").strip()
        if m.group(1) and _FOOTNOTE.match(t):
            continue                                       # footnote reference "(1)"
        if m.group(1) and m.start() > 0 and m.group(1) == m.group(1).lstrip() and s[m.start() - 1].isalnum():
            continue                                       # digits glued to a word ("Intel4", "Q4")
        if label_end is None:
            label_end = m.start()
        if m.group(3):
            toks.append((t, False, False, True))
        else:
            toks.append((t, t.startswith("(") or "-" in t or "−" in t, bool(m.group(2)), False))
    return (s[:label_end] if label_end is not None else s).strip(), toks


def header_years(tn: str, idx: int, upto: int, span: int = 2500) -> Optional[list]:
    """The column years of the table that holds the quote: the last cluster of year numbers (gaps of up to 40 characters without digits) before the first data cell of the quote."""
    pre = _MONTH_DAY.sub(" ", tn[max(0, idx - span):upto])
    best = None
    cluster: list = []
    last_end = None
    for m in _YEAR.finditer(pre):
        if cluster and m.start() - last_end <= 40 and not re.search(r"\d", pre[last_end:m.start()]):
            cluster.append(int(m.group(1)))
        else:
            if len(cluster) >= 2:
                best = cluster
            cluster = [int(m.group(1))]
        last_end = m.end()
    if len(cluster) >= 2:
        best = cluster
    if best and len(set(best)) == len(best) and (best == sorted(best) or best == sorted(best, reverse=True)):
        return best
    return None


def assign_year(item: dict, value: float, scale: int, unit: str, quote: str, text_norm: str, fy: int, ai_year: Optional[int] = None) -> tuple:
    """-> (year or None, how, printed_negative). The year of the table column that holds ``value``; ``how``: 'header' (a year header with as many columns as cells), 'column_order'
    (no usable header: newest first, 2-3 cells), 'unresolved'."""
    qn = normalize(quote)
    idx = text_norm.find(qn)
    label, toks = data_tokens(qn)
    if idx < 0 or not toks:
        return None, "unresolved", None
    cells = [t for t in toks if unit == "percent" or not t[2]]            # percent cells are other columns (shares, changes) unless the item itself is a percent
    cands = [i for i, t in enumerate(cells) if not t[3] and number_in_quote(value, scale, unit, t[0])[0]]
    if not cands:
        return None, "unresolved", None
    col = cands[0]
    neg = cells[col][1]
    if len(cells) < 2:
        return None, "single", neg                                         # one cell: no column to assign
    upto = idx + len(label) + 1
    hdr = header_years(text_norm, idx, upto)
    if hdr and len(hdr) == len(cells):
        if len(cands) > 1:                                                 # the same number in several columns: keep the model's year when one of the columns is that year
            return (ai_year, "header", neg) if ai_year in {hdr[c] for c in cands} else (None, "unresolved", neg)
        return hdr[col], "header", neg
    if not hdr and len(cells) in (2, 3) and len(cands) == 1 and not any(t[3] for t in cells):
        return fy - col, "column_order", neg                               # no header: the usual 10-K order, newest first; only when the value is in one column and no cell is empty
    return None, "unresolved", neg


_LOSS_FIRST = re.compile(r"loss(?:es)?\s*\(\s*gains?\s*\)|\(\s*gains?\s*\)\s*loss", re.I)
_GAIN_FIRST = re.compile(r"gains?\s*\(\s*loss(?:es)?\s*\)|\(\s*loss(?:es)?\s*\)\s*gains?", re.I)


def signed(rule: Optional[str], full: float, label: str, printed_neg: Optional[bool], ai_neg: bool) -> float:
    """The value with the sign set by the convention of the item (see ``sign_rules`` in extraction.yaml). ``full`` = value in full units as the model gave it."""
    mag = abs(full)
    pneg = ai_neg if printed_neg is None else printed_neg
    if rule == "magnitude":
        return mag
    if rule == "deduction_positive":
        return mag if pneg else -mag
    if rule == "effect":
        if _LOSS_FIRST.search(label):
            return mag if pneg else -mag                                   # printed positive = loss
        if _GAIN_FIRST.search(label):
            return -mag if pneg else mag                                   # printed positive = gain
        has_gain, has_loss = re.search(r"\bgains?\b", label, re.I), re.search(r"\b(?:loss(?:es)?|impairments?|charges?|write-?downs?)\b", label, re.I)
        if has_gain and not has_loss:
            return mag
        if has_loss and not has_gain:
            return -mag
        return -mag if pneg else mag                                       # no wording to go by: the printed sign
    return full


def apply(res, it: dict, text_norm: str, fy: int, rule: Optional[str], window: int = 2) -> None:
    """Corrects ``res`` (an ext_checks.ItemResult of an accepted-so-far item) in place: year from the table columns, sign from the convention."""
    q = (it.get("quote") or {}).get("text")
    if not isinstance(q, str) or res.value_full is None or "number_not_in_quote" in res.reasons or "quote_not_found" in res.reasons:
        return
    v, sc, unit = float(it["value"]), int(it.get("scale") or 1), str(it.get("unit"))
    year, how, pneg = assign_year(it, v, sc, unit, q, text_norm, fy, res.year)
    if how == "unresolved" and year is None and res.year is not None:
        res.flags.append("period_unverified")
    elif year is not None:
        if how == "column_order":
            res.flags.append("period_by_column_order")
        if year != res.year:
            res.year = year
            res.flags.append("period_corrected")
            res.reasons = [r for r in res.reasons if r != "period_mismatch"]
            if not (fy - window <= year <= fy):
                res.reasons.append("period_mismatch")
    if rule and unit == "USD":
        label, _ = data_tokens(normalize(q))
        new = signed(rule, res.value_full, label, pneg, v < 0)
        if new != res.value_full:
            res.flags.append("sign_normalized")
            res.value_full = new

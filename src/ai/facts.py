"""Facts given to the AI by code (skills document, FACTS GIVEN BY CODE). Pure: formats numbers the engines already computed - the AI never computes them.

``data`` = {"labels": [5 fiscal-year labels], "revenue": [...], "eps": [...], "net_income": [...], "acquisitions": [...], "goodwill_impairment": [...],
            "margins": {name: [5 values]}, "first_annual_report": "YYYY-MM-DD" | None, "as_of": "YYYY-MM-DD", "currency": "USD"}
"""
from __future__ import annotations

import re

from datetime import date
from typing import Optional


def cagr(first, last, years: int) -> Optional[float]:
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def _num(v, scale=1e9, unit="bn") -> str:
    return "not reported" if v is None else f"{v / scale:,.2f}{unit}"


_DISC = re.compile(r"(goodwill impairment|impairment|loss on (?:the )?sale|gain on (?:the )?sale|loss on (?:the )?disposal|gain on (?:the )?disposal)[^.$]{0,160}?(?:of|was|totaling|totalled|:)\s*\$\s?([\d,]+(?:\.\d+)?)\s*(million|billion)", re.I)
_YEAR = re.compile(r"(?:year[s]? ended|fiscal year|during)[^.]{0,60}?(20\d\d)|\b(20\d\d)\b")


_DISC_TITLE = re.compile(r"^\s*(?:note\s*)?\d{0,2}[\.\):\-– ]*\s*discontinued\s+operations\s*$", re.I)
_ANY_TITLE = re.compile(r"^\s*(?:note\s*)?\d{1,2}[\.\):\-–]\s*[A-Za-z]", re.I)


def discontinued_facts(note_text: str, max_year: int = 2026) -> dict:
    """Impairments and gains / losses on sale that the notes place in DISCONTINUED operations: {year: [(description, USD)]}, year 0 = not stated in the sentence.
    Deterministic scan: a sentence counts when it mentions 'discontinued' or sits under a 'Discontinued operations' note title; amounts are taken as stated."""
    out: dict = {}
    in_disc = False
    for line in (note_text or "").split("\n"):
        if _DISC_TITLE.match(line):
            in_disc = True
            continue
        if _ANY_TITLE.match(line) and len(line.strip()) < 90:
            in_disc = False
        for sent in re.split(r"(?<=[.;])\s+", line):
            if not (in_disc or "discontinued" in sent.lower()):
                continue
            m = _DISC.search(sent)
            if not m:
                continue
            ys = [int(next(x for x in t if x)) for t in _YEAR.findall(sent)]
            ys = [y for y in ys if y <= max_year]
            amt = float(m.group(2).replace(",", "")) * (1e9 if m.group(3).lower() == "billion" else 1e6)
            item = (m.group(1).lower(), amt)
            if item not in out.setdefault(ys[-1] if ys else 0, []):
                out[ys[-1] if ys else 0].append(item)
    return out


def _series(labels, vals, scale=1e9, unit="bn") -> str:
    return "; ".join(f"{l}: {_num(v, scale, unit)}" for l, v in zip(labels, vals))


def _pct(v) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _margin_line(name, vals) -> str:
    return f"{name}: average of the first 2 years {_pct(_avg(vals[:2]))} -> average of the last 2 years {_pct(_avg(vals[-2:]))}"


def facts_for(skill_id: str, d: dict) -> Optional[str]:
    L = d["labels"]
    rev, eps = d.get("revenue") or [], d.get("eps") or []
    if skill_id == "B3.2-Q4":
        if not rev or all(x is None for x in rev):
            return None
        lines = [f"Revenue per fiscal year (USD): {_series(L, rev)}; 5-year CAGR: {_pct(cagr(rev[0], rev[-1], len(rev) - 1))}."]
        lines += [_margin_line(n, v) + "." for n, v in (d.get("margins") or {}).items()]
        lines.append("Segment revenue trend: not provided.")
        return "\n".join(lines)
    if skill_id == "B3.8-Q6":
        lines = []
        if rev:
            lines.append(f"Revenue per fiscal year (USD): {_series(L, rev)}; 5-year CAGR: {_pct(cagr(rev[0], rev[-1], len(rev) - 1))}.")
        if eps:
            lines.append("Diluted EPS per fiscal year: " + "; ".join(f"{l}: {'n/a' if v is None else f'{v:.2f}'}" for l, v in zip(L, eps)) +
                         f"; 5-year CAGR: {_pct(cagr(eps[0], eps[-1], len(eps) - 1))}.")
        acq = d.get("acquisitions")
        if acq:
            lines.append(f"Acquisitions (cash paid, USD) per fiscal year: {_series(L, acq)}.")
        return "\n".join(lines) or None
    if skill_id == "G3.1-Q4":
        far, asof = d.get("first_annual_report"), d.get("as_of")
        lines = []
        if far and asof:
            yrs = (date.fromisoformat(asof) - date.fromisoformat(far)).days / 365.25
            lines.append(f"Years since the first annual report: {yrs:.0f} (first annual report filed {far}).")
        if rev and rev[-1] is not None:
            lines.append(f"Latest-year revenue: USD {_num(rev[-1])}.")
        return "\n".join(lines) or None
    if skill_id == "G3.8-Q3":
        ni = d.get("net_income")
        return ("Net income per fiscal year (USD): " + _series(L, ni) + ".") if ni else None
    if skill_id == "B3.7-Q3":
        acq, imp = d.get("acquisitions"), d.get("goodwill_impairment")
        parts = []
        if acq:
            parts.append(f"Acquisitions (cash paid, USD) per fiscal year: {_series(L, acq)}.")
        if imp:
            parts.append(f"Goodwill impairment (USD) per fiscal year, continuing operations: {_series(L, imp)}.")
        disc = d.get("discontinued")
        if disc is not None:
            lines = [f"{y or 'year not stated'}: " + ", ".join(f"{k} {_num(v)}" for k, v in items) for y, items in sorted(disc.items())]
            parts.append("Recorded in DISCONTINUED operations (from the notes; not in the series above): " + ("; ".join(lines) if lines else "none found") + ".")
        return "\n".join(parts) or None
    return None

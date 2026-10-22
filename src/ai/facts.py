"""Facts given to the AI by code (skills document, FACTS GIVEN BY CODE). Pure: formats numbers the engines already computed - the AI never computes them.

``data`` = {"labels": [5 fiscal-year labels], "revenue": [...], "eps": [...], "net_income": [...], "acquisitions": [...], "goodwill_impairment": [...],
            "margins": {name: [5 values]}, "first_annual_report": "YYYY-MM-DD" | None, "as_of": "YYYY-MM-DD", "currency": "USD"}
"""
from __future__ import annotations

from datetime import date
from typing import Optional


def cagr(first, last, years: int) -> Optional[float]:
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def _num(v, scale=1e9, unit="bn") -> str:
    return "n/a" if v is None else f"{v / scale:,.2f}{unit}"


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
            parts.append(f"Goodwill impairment (USD) per fiscal year: {_series(L, imp)}.")
        return "\n".join(parts) or None
    return None

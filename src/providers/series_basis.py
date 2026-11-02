"""A flow series whose definition changed between the filings (K6d-2 fixes, 2026-11-01; LNC premiums: 5.6 bn for 2021 in the FY2021 10-K, 11.7 bn in the FY2023 10-K after the LDTI restatement).

SEC ``companyfacts`` keeps one value per fiscal year end per filing; the provider takes the latest. When a later filing restates a year by more than the threshold and the year before it is NOT restated by
that later filing (so no overlap proves that both years are on the same basis), the older years are on another basis: connecting them to the newer ones would show a jump that is a change of definition.
The overlap test: the year before the first restated year is covered by the restating filing and agrees with its older value -> the series is continuous. Otherwise the older years are dropped (missing, flagged).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

ANNUAL = ("10-K", "10-K/A", "10-KT")


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def values_by_end(facts: dict, tags: list, unit: str = "USD") -> dict:
    """{end: [(filed, value)]} of the first tag of ``tags`` that has annual flow data (the tag the provider uses)."""
    node_all = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        out: dict = {}
        for e in node_all.get(tag, {}).get("units", {}).get(unit, []):
            if e.get("form") not in ANNUAL or e.get("fp") != "FY" or "start" not in e:
                continue
            if not 340 <= (_d(e["end"]) - _d(e["start"])).days <= 380:
                continue
            out.setdefault(_d(e["end"]), set()).add((_d(e["filed"]), float(e["val"])))
        if out:
            return {k: sorted(v) for k, v in out.items()}
    return {}


def basis_break(facts: dict, tags: list, unit: str = "USD", threshold: float = 0.15) -> Optional[dict]:
    """-> {"end": first end on the new basis, "old": value, "new": value} when the older years are on another basis, else None."""
    vals = values_by_end(facts, tags, unit)
    ends = sorted(vals)
    for e in ends:
        v = vals[e]
        first = v[0][1]
        later = [(f, x) for f, x in v[1:] if first and abs(x / first - 1) > threshold]
        if not later:
            continue
        restated_on = later[0][0]
        prior = [p for p in ends if p < e]
        if not prior:
            return None
        pe = prior[-1]
        covered = [(f, x) for f, x in vals[pe] if f >= restated_on]
        if covered and vals[pe][0][1] and abs(covered[-1][1] / vals[pe][0][1] - 1) <= threshold:
            continue                                                 # the restating filing also shows the year before, and it agrees: one basis
        return {"end": e, "old": first, "new": later[-1][1], "restated_in_filing_of": str(restated_on)}
    return None


def drop_older(f: dict, log: dict, labels: list, ends: list, field: str, brk: dict, problems: list, flags: list) -> list:
    """Set the years before the break to missing; returns the labels."""
    gone = []
    for i, (end, lab) in enumerate(zip(ends, labels)):
        if end < brk["end"] and f[field][i] is not None:
            f[field][i] = None
            log.setdefault(field, {})[lab] = {"tag": None, "basis_break": f"{field} of {brk['end']} was restated from {brk['old']:,.0f} to {brk['new']:,.0f} by the filing of {brk['restated_in_filing_of']} and the year before is not shown on the new basis: older years are not comparable"}
            gone.append(lab)
    if gone:
        problems.append(f"{field}: basis break at {brk['end']} (a definition change, {brk['old']:,.0f} -> {brk['new']:,.0f}); {', '.join(gone)} set missing")
        flags.append(f"basis_break:{field}")
    return gone

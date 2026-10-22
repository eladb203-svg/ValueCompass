"""Peer group and percentiles (AI spec section 12 / skills document "Other" 3.2). Pure: computed by code, fixed per run, never by the AI.

A company record: {"ticker", "profile", "industry", "buffett": {"score", "range_min", "range_max", "status"}, "graham": {...}, "metrics": {name: value | None}}.
Peer group = same profile and same ValueCompass industry; fewer than ``MIN_PEERS`` (5) other companies -> same profile only (``fallback``). n and the definition are always kept.
Percentile = share of the group (the company included) below the company's value, ties counting half, in percent; for the metrics where lower is better (leverage) the percentile is of
goodness. A quality score that is a range (not final) enters with the middle of the range and is marked.
"""
from __future__ import annotations

from typing import Optional

MIN_PEERS = 5
METRICS = ("revenue", "net_income", "eps", "roe", "fcf", "leverage")      # the six key metrics of the display spec, section 1 (latest fiscal year)
LOWER_IS_BETTER = ("leverage",)
# the leverage metric is profile specific (display spec 1): STANDARD debt / equity; BANK CET1 ratio (higher is better); INSURANCE financial leverage; real estate net debt / EBITDAre
HIGHER_IS_BETTER_BY_PROFILE = {"BANK": ("leverage",)}
LABELS = {
    "STANDARD": {"revenue": "Revenue", "net_income": "Net income", "eps": "Diluted EPS", "roe": "ROE", "fcf": "Free cash flow", "leverage": "Debt / equity"},
    "BANK": {"revenue": "Bank revenue (NII + noninterest income)", "net_income": "Net income", "eps": "Diluted EPS", "roe": "ROTCE", "fcf": None, "leverage": "CET1 ratio"},
    "INSURANCE": {"revenue": "Operating revenue", "net_income": "Net income", "eps": "Diluted EPS", "roe": "Operating ROE", "fcf": None, "leverage": "Financial leverage"},
    "INCOME_REAL_ESTATE": {"revenue": "Total revenue", "net_income": "Net income", "eps": "Normalized FFO per share", "roe": "ROE (not shown for real estate)", "fcf": "Owner earnings",
                           "leverage": "Net debt / EBITDAre"},
}


def score_of(q: Optional[dict]) -> tuple:
    """-> (score used, is_range). A final score is used as is; a range (min != max) enters with its middle and is marked."""
    if not q or q.get("score") is None and q.get("range_min") is None:
        return None, False
    lo, hi = q.get("range_min"), q.get("range_max")
    if lo is not None and hi is not None and abs(hi - lo) > 1e-9:
        return (lo + hi) / 2.0, True
    return (q["score"] if q.get("score") is not None else lo), False


def peer_group(company: dict, records: list, min_peers: int = MIN_PEERS) -> dict:
    """The fixed group of one company for one run (the company itself is not a member)."""
    others = [r for r in records if r["ticker"] != company["ticker"]]
    same = [r for r in others if r["profile"] == company["profile"] and r.get("industry") == company.get("industry")]
    fallback = len(same) < min_peers
    members = [r for r in others if r["profile"] == company["profile"]] if fallback else same
    definition = (f"profile {company['profile']}" if fallback else f"profile {company['profile']} and industry {company.get('industry')}")
    if fallback:
        definition += f" (fewer than {min_peers} companies in industry {company.get('industry')}: profile only)"
    return {"ticker": company["ticker"], "ids": sorted(r["ticker"] for r in members), "definition": definition, "n": len(members), "fallback": fallback,
            "profile": company["profile"], "industry": company.get("industry")}


def percentile(value: Optional[float], group_values: list, lower_is_better: bool = False) -> Optional[float]:
    """Percentile of ``value`` among ``group_values`` (the other members) plus itself; None when the value or the group is missing."""
    vals = [v for v in group_values if v is not None]
    if value is None or not vals:
        return None
    sign = -1.0 if lower_is_better else 1.0
    x = sign * value
    ys = [sign * v for v in vals] + [x]
    below = sum(1 for y in ys if y < x)
    equal = sum(1 for y in ys if y == x)
    return round(100.0 * (below + 0.5 * equal) / len(ys), 1)


def peer_percentiles(company: dict, group: dict, records: list) -> dict:
    """Percentiles of the two quality scores and of the six key metrics of ``company`` within ``group``."""
    by = {r["ticker"]: r for r in records}
    members = [by[t] for t in group["ids"] if t in by]
    out: dict = {"group": {k: group[k] for k in ("definition", "n", "fallback")}, "quality": {}, "metrics": {}}
    for model in ("buffett", "graham"):
        s, rng = score_of(company.get(model))
        vals = [score_of(m.get(model))[0] for m in members]
        out["quality"][model] = {"score": None if s is None else round(s, 1), "range_midpoint": rng, "percentile": percentile(s, vals), "n": sum(1 for v in vals if v is not None)}
    higher = HIGHER_IS_BETTER_BY_PROFILE.get(company["profile"], ())
    for k in METRICS:
        v = company.get("metrics", {}).get(k)
        vals = [m.get("metrics", {}).get(k) for m in members]
        lower = k in LOWER_IS_BETTER and k not in higher
        out["metrics"][k] = {"label": LABELS.get(company["profile"], LABELS["STANDARD"]).get(k), "value": v, "percentile": percentile(v, vals, lower),
                             "n": sum(1 for x in vals if x is not None), "lower_is_better": lower}
    return out

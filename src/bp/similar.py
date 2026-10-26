"""'Similar companies in ValueCompass' (AI skills 2026-10-26_10-30, 3.2.3): code only.

Pool = the same profile and industry (the golden companies are in it too); the same market first; the 3 closest in size - total assets for banks and insurers, revenue for the rest. Fewer than 3: what
exists. Used only when the report names no competitor.
"""
from __future__ import annotations

import math
from typing import Optional

SIZE_BY_ASSETS = ("BANK", "INSURANCE")


def _last(x) -> Optional[float]:
    if isinstance(x, dict) and x:
        x = x[sorted(x)[-1]]
    elif isinstance(x, list) and x:
        x = x[-1]
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and not math.isnan(x) else None


def size_of(rec: dict, result_json: Optional[dict]) -> Optional[float]:
    """Total assets (banks, insurers) or revenue (the others) of the latest fiscal year of a company record; None when missing."""
    if rec.get("profile") in SIZE_BY_ASSETS and result_json:
        fin = result_json.get("financials") or (result_json.get("inputs") or {}).get("f") or {}
        v = _last(fin.get("assets"))
        if v:
            return v
    v = (rec.get("metrics") or {}).get("revenue")
    return float(v) if v else None


def pick_similar(target: dict, records: list, sizes: dict, markets: Optional[dict] = None, n: int = 3) -> list:
    """The ``n`` records closest in size to ``target`` among those with its profile and industry (the target itself excluded). -> list of records, nearest first."""
    markets = markets or {}
    own_market = markets.get(target["ticker"], "US")
    t_size = sizes.get(target["ticker"])
    pool = [r for r in records if r["ticker"] != target["ticker"] and r["profile"] == target["profile"] and r.get("industry") and r.get("industry") == target.get("industry")]

    def key(r: dict) -> tuple:
        s = sizes.get(r["ticker"])
        dist = abs(math.log(s / t_size)) if (s and t_size and s > 0 and t_size > 0) else float("inf")
        return (markets.get(r["ticker"], "US") != own_market, dist, r["ticker"])
    return sorted(pool, key=key)[:n]

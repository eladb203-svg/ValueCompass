"""Company records for the peer groups and the D2 RESULTS block, read from golden-format company JSON files (code stage K5c; from K6 on the same records come from the database).

``load_records(golden_dir)`` -> one record per company: profile, industry, the two quality results and the six key metrics of the latest fiscal year (display spec section 1).
``build_results(json, record)`` -> the RESULTS block of D2: scores, coverage, points per criterion against the maximum, key metrics, values, buy prices, states and flags. No share price.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Optional

from .peers import LABELS

ENGINES = ("general", "managed_care", "bank", "insurance", "realestate")


def _num(x) -> Optional[float]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return None if (math.isnan(x) or math.isinf(x)) else float(x)


def _last(x):
    if isinstance(x, list):
        return _num(x[-1]) if x else None
    if isinstance(x, dict):
        return _num(x[sorted(x)[-1]]) if x else None
    return _num(x)


def _at(series: dict, label: str) -> Optional[float]:
    return _num((series or {}).get(label))


def profile_of(j: dict, engine: str) -> str:
    r = j.get("profile_router") or {}
    p = r.get("computed_profile") or j.get("profile")
    if engine == "realestate" or p in (None, ""):
        return "INCOME_REAL_ESTATE" if engine == "realestate" else "STANDARD"
    return "STANDARD" if p in ("MANAGED_CARE", "TECH_ASSET_LIGHT") else p


def key_metrics(j: dict, engine: str) -> tuple:
    """-> (metrics {revenue, net_income, eps, roe, fcf, leverage}, fiscal year label). Definitions per profile as in the display spec section 1; a missing input is None."""
    if engine == "realestate":
        from .realestate import REInputs, derive_re
        inp = j["inputs"]
        ri = REInputs(ticker=j["ticker"], name=j["ticker"], fy=inp["fy"], end=[date.fromisoformat(e) for e in inp["end"]], f=inp["f"], reg=inp["reg"], asset_type=inp.get("asset_type"),
                      utilization=None, noi_method=inp.get("noi_method"))
        d = derive_re(ri)
        f = inp["f"]
        return {"revenue": _last(f.get("total_revenue")), "net_income": _last(f.get("net_income")), "eps": _last(d.get("nffo_ps")), "roe": None, "fcf": _last(d.get("oe")),
                "leverage": _last(d.get("nd_ebitdare"))}, inp["fy"][-1]
    labels = sorted(j["fiscal_years"])
    L = labels[-1]
    fin, der = j["financials"], j.get("derived") or {}
    ni, eps = _at(fin.get("net_income"), L), _at(fin.get("eps"), L)
    if engine == "bank":
        return {"revenue": _at(der.get("revenue"), L), "net_income": ni, "eps": eps, "roe": _at(der.get("rotce"), L), "fcf": None,
                "leverage": _num((j.get("latest") or {}).get("cet1_ratio"))}, L
    if engine == "insurance":
        return {"revenue": _at(der.get("operating_revenue"), L), "net_income": ni, "eps": eps, "roe": _at(der.get("operating_roe"), L), "fcf": None,
                "leverage": _at(der.get("financial_leverage"), L)}, L
    eq1, eq0 = _at(fin.get("equity"), L), _at(fin.get("equity"), labels[-2]) if len(labels) > 1 else None
    roe = (ni / ((eq1 + eq0) / 2.0)) if (ni is not None and eq1 and eq0 and eq1 > 0 and eq0 > 0) else None     # not meaningful when an end point is <= 0 (display spec)
    debt, eq = _at(der.get("fin_debt"), L), eq1
    return {"revenue": _at(fin.get("revenue"), L), "net_income": ni, "eps": eps, "roe": roe, "fcf": _at(der.get("fcf"), L),
            "leverage": (debt / eq) if (debt is not None and eq and eq > 0) else None}, L


def record_of(j: dict, engine: str) -> dict:
    q = lambda m: {k: j[m].get(k) for k in ("score", "range_min", "range_max", "status", "coverage")}   # noqa: E731
    metrics, label = key_metrics(j, engine)
    return {"ticker": j["ticker"], "name": j.get("name") or j["ticker"], "engine": engine, "profile": profile_of(j, engine),
            "industry": (j.get("profile_router") or {}).get("classification", {}).get("industry") or (j.get("profile_router") or {}).get("industry"),
            "buffett": q("buffett_quality"), "graham": q("graham_quality"), "metrics": metrics, "fiscal_year": label}


def load_records(golden_dir) -> list:
    root, out = Path(golden_dir), []
    for eng in ENGINES:
        for p in sorted((root / eng).glob("*.json")):
            j = json.loads(p.read_text(encoding="utf-8"))
            out.append(record_of(j, eng))
    return out


def load_json(golden_dir, ticker: str) -> tuple:
    for eng in ENGINES:
        p = Path(golden_dir) / eng / f"{ticker}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")), eng
    raise KeyError(ticker)


def _r(x, nd=2):
    return None if x is None else round(x, nd)


def _price(j: dict, key: str) -> dict:
    p = j.get(key) or (j.get("pricing_file") or {}).get(key) or {}
    bp = p.get("buy_price") if isinstance(p.get("buy_price"), dict) else {}
    fv = p.get("fair_value")
    if fv is None and isinstance(p.get("graham_number"), dict):
        fv = p["graham_number"].get("graham_number")
    if fv is None:
        fv = (p.get("economic_value") or {}).get("value") if isinstance(p.get("economic_value"), dict) else None
    return {"buy_price": _r(_num(bp.get("buy_price"))), "buy_price_state": bp.get("state") or p.get("state"), "margin_of_safety": _r(_num(bp.get("margin_of_safety")), 3),
            "value_per_share": _r(_num(fv)), "flags": [str(f)[:90] for f in (p.get("flags") or [])][:6]}


def build_results(j: dict, rec: dict, run_id: str) -> dict:
    """The RESULTS block of D2. Criteria carry ids ``B-<id>`` / ``G-<id>`` so that ``criteria_cited`` is unambiguous."""
    out: dict = {"run_id": run_id, "profile": rec["profile"], "industry": rec["industry"], "fiscal_year": rec["fiscal_year"], "quality": {}, "price": {}, "key_metrics": {}}
    for model, key, pre in (("buffett", "buffett_quality", "B"), ("graham", "graham_quality", "G")):
        q = j[key]
        out["quality"][model] = {"score": _r(q.get("score"), 1), "range": [_r(q.get("range_min"), 1), _r(q.get("range_max"), 1)], "status": q.get("status"), "coverage": q.get("coverage"),
                                 "criteria": [{"id": f"{pre}-{c['id']}", "name": c["name"], "points": _r(c.get("observed_points"), 1), "range": [_r(c.get("range_min"), 1), _r(c.get("range_max"), 1)],
                                               "max": c.get("weight")} for c in q.get("criteria", [])]}
        out["price"][model] = _price(j, key.replace("quality", "price"))
    labels = LABELS.get(rec["profile"], {})
    for k, v in rec["metrics"].items():
        if labels.get(k):
            out["key_metrics"][labels[k]] = _r(v, 4)
    return out

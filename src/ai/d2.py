"""Inputs of D2 (results analysis) with uniform wording (skills document "Other" 2026-10-23_15-00, section 3.3). Pure: code prepares the words, the model only composes.

RESULTS carries the Hebrew glossary names exactly as the screen shows them, a strength word per criterion (>=70% of the maximum strong, 40-69% medium, below 40% weak), the quality
labels, the values and buy prices and the required margin of safety - nothing that changes with the daily price. PEERS carries the position among peers in words (percentile >=75 top
quarter, 50-74 above the median, 25-49 below the median, below 25 bottom quarter). CHANGES (only when a previous run exists) is computed by code.
"""
from __future__ import annotations

import math
from typing import Optional

from .content import content_cfg
from ..scoring.peers import score_of

PRICE_FLAG_WORDS = ("current", "discount", "upside", "price_score", "price_above", "price_below")


def glossary() -> dict:
    return content_cfg()["glossary"]


def strength_word(points: Optional[float], mx: Optional[float]) -> Optional[str]:
    if points is None or not mx:
        return None
    share = points / mx
    g = glossary()["strength"]
    return g["strong"] if share >= 0.70 - 1e-9 else (g["medium"] if share >= 0.40 - 1e-9 else g["weak"])


def position_word(percentile: Optional[float]) -> Optional[str]:
    if percentile is None:
        return None
    g = glossary()["position"]
    return g["top"] if percentile >= 75 else (g["above"] if percentile >= 50 else (g["below"] if percentile >= 25 else g["bottom"]))


def quality_label(model: str, score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    for floor, label in glossary()["quality_labels"][model]:
        if score >= floor:
            return label
    return None


def _r(x, nd=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), nd)


def _pts(c: dict) -> tuple:
    lo, hi = c.get("range_min"), c.get("range_max")
    if lo is not None and hi is not None and abs(hi - lo) > 1e-9:
        return (lo + hi) / 2.0, True
    return (c.get("observed_points") if c.get("observed_points") is not None else lo), False


def _price_block(j: dict, key: str) -> dict:
    return j.get(key) or (j.get("pricing_file") or {}).get(key) or {}


def model_block(j: dict, model: str) -> dict:
    g = glossary()
    q = j[f"{model}_quality"]
    pre = "B" if model == "buffett" else "G"
    score, rng = score_of(q)
    crit = []
    for c in q.get("criteria", []):
        pts, is_range = _pts(c)
        crit.append({"id": f"{pre}-{c['id']}", "name_he": g["criteria"][f"{pre}-{c['id']}"], "points": _r(pts, 1), "max": c.get("weight"), "strength_he": strength_word(pts, c.get("weight")),
                     **({"range": True} if is_range else {})})
    ranked = sorted((c for c in crit if c["points"] is not None and c["max"]), key=lambda c: c["points"] / c["max"])
    strongest = [c["name_he"] for c in reversed(ranked) if c["strength_he"] == g["strength"]["strong"]][:2]
    weakest = [c["name_he"] for c in ranked if c["strength_he"] == g["strength"]["weak"]][:2]
    p = _price_block(j, f"{model}_price")
    bp = p.get("buy_price") if isinstance(p.get("buy_price"), dict) else {}
    value = p.get("fair_value") if model == "buffett" else p.get("value")
    method = p.get("method") or ("dcf" if "dcf" in p else "default")
    state = bp.get("state")
    st_he = None
    if state and state != "computed":
        st_he = g["states"].get(state) or g["states"]["cannot_price"]
    flags = [str(f)[:80] for f in (p.get("flags") or []) if not any(w in str(f).lower() for w in PRICE_FLAG_WORDS)][:3]
    return {"score": _r(score, 1), "label_he": quality_label(model, score), "range_midpoint": rng, "coverage": q.get("coverage"), "criteria": crit,
            "strongest_he": strongest or "אין", "weakest_he": weakest or "אין", "value": _r(value), "method_he": g["methods"].get(method, g["methods"]["default"]),
            "buy_price": _r(bp.get("buy_price")), "required_mos_pct": _r(bp.get("margin_of_safety") * 100, 1) if isinstance(bp.get("margin_of_safety"), (int, float)) else None,
            "state_he": st_he, "flags": flags}


def forbidden_numbers(j: dict) -> list:
    """Numbers that change with the daily price (current price, price score points, discount, upside, current margin): they must not appear in the text."""
    out = []
    for key in ("buffett_price", "graham_price"):
        p = _price_block(j, key)
        if isinstance(p.get("price_current"), (int, float)):
            out.append(float(p["price_current"]))
        ps = p.get("price_score") if isinstance(p.get("price_score"), dict) else {}
        for k in ("points", "discount"):
            if isinstance(ps.get(k), (int, float)):
                out.append(float(ps[k]))
        v = p.get("fair_value") if key.startswith("buffett") else p.get("value")
        if isinstance(v, (int, float)) and v and isinstance(p.get("price_current"), (int, float)):
            out.append(round(p["price_current"] / v - 1, 4) * 100)
    return out


def peers_view(pc: dict, profile: str) -> dict:
    g = glossary()
    mn = g["metrics"].get(profile, g["metrics"]["STANDARD"])
    q = {m: {"score": v["score"], "percentile": v["percentile"], "position_he": position_word(v["percentile"]), "range_midpoint": v["range_midpoint"]} for m, v in pc["quality"].items()}
    he = {"buffett": g["models"]["buffett"], "graham": g["models"]["graham"]}
    return {"group": {"definition": g["group"]["fallback" if pc["group"]["fallback"] else "full"], "n": pc["group"]["n"], "fallback": pc["group"]["fallback"]},
            "quality": {he[m]: v for m, v in q.items()},
            "metrics": [{"name_he": mn[k], "percentile": v["percentile"], "position_he": position_word(v["percentile"])} for k, v in pc["metrics"].items() if mn.get(k) and v["percentile"] is not None]}


def compute_changes(cur: dict, prev: Optional[dict], prev_date: Optional[str]) -> Optional[dict]:
    """The score changes between the previous run of the company and this run, and their reason - computed by code (None when there is no previous run)."""
    if not prev:
        return None
    g = glossary()
    items = []
    for model, he in (("buffett", g["models"]["buffett"]), ("graham", g["models"]["graham"])):
        a, b = model_block(prev, model), model_block(cur, model)
        if a["score"] is not None and b["score"] is not None and abs(b["score"] - a["score"]) >= 1.0:
            items.append({"name_he": f"ציון האיכות לפי {he}", "direction_he": g["change"]["up" if b["score"] > a["score"] else "down"], "from": a["score"], "to": b["score"]})
        pa = {c["id"]: c for c in a["criteria"]}
        for c in b["criteria"]:
            x = pa.get(c["id"])
            if x and x["points"] is not None and c["points"] is not None and abs(c["points"] - x["points"]) >= 1.0:
                items.append({"name_he": c["name_he"], "model_he": he, "direction_he": g["change"]["up" if c["points"] > x["points"] else "down"], "from": x["points"], "to": c["points"],
                              "_d": abs(c["points"] - x["points"])})
    items.sort(key=lambda i: -(i.get("_d") or 99))
    for i in items:
        i.pop("_d", None)
    if str(cur.get("fiscal_years") and sorted(cur["fiscal_years"])[-1]) != str(prev.get("fiscal_years") and sorted(prev["fiscal_years"])[-1]):
        why = "new_report"
    elif cur.get("scoring_model_version") != prev.get("scoring_model_version"):
        why = "rules"
    elif prev["buffett_quality"].get("pending_criteria") or prev["graham_quality"].get("pending_criteria"):
        why = "ai"
    else:
        why = "data"
    return {"previous_run": prev_date, "reason_he": g["change"]["reasons"][why], "changes": items[:3]}


def build_d2_inputs(j: dict, rec: dict, run_id: str, pc: dict, prev: Optional[dict] = None, prev_date: Optional[str] = None) -> dict:
    g = glossary()
    mn = g["metrics"].get(rec["profile"], g["metrics"]["STANDARD"])
    results = {"run_id": run_id, "profile": rec["profile"], "fiscal_year": rec["fiscal_year"], "score_scale_max": 100,
               "models": {g["models"][m]: model_block(j, m) for m in ("buffett", "graham")},
               "key_metrics": {mn[k]: (None if v is None else float(f"{v:.4g}")) for k, v in rec["metrics"].items() if mn.get(k)}}
    return {"results": results, "peers": peers_view(pc, rec["profile"]), "changes": compute_changes(j, prev, prev_date), "forbidden_numbers": forbidden_numbers(j)}

"""Inputs of D2 (results analysis) with uniform wording (skills document "Other" 2026-10-23_15-00, section 3.3; decisions of 2026-10-24). Pure: code prepares the words and the numbers,
the model only composes.

RESULTS carries the Hebrew glossary names exactly as the screen shows them, a strength word per criterion (>=70% of the maximum strong, 40-69% medium, below 40% weak), the quality labels,
the lowest criterion of each model with its strength word, the values / buy prices / required margin of safety as ready formatted text ("$33.16", "331.8 מיליארד $", "21.0%"), and a score
that is still a range as a range ("65.2–67.2/100, משוער"). Nothing that changes with the daily price. PEERS carries the position among peers in words, and ``compare`` = whether the comparison
may be written at all (every one of the two models: this company's score final and at least 5 peers with a final score). CHANGES (only when a previous run exists) is computed by code.
D2 is generated only after every AI question of the company was handled (no ``ai_pending`` item).
"""
from __future__ import annotations

import math
from typing import Optional

from .content import content_cfg
from ..scoring.peers import score_of

PRICE_FLAG_WORDS = ("current", "discount", "upside", "price_score", "price_above", "price_below")
MIN_FINAL_PEERS = 5


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


# ---------------------------------------------------------------- number formatting (the model copies, never formats)
def money(v: Optional[float]) -> Optional[str]:
    """Amounts: billions / millions with $ ("331.8 מיליארד $", "267 מיליון $"), per-share values "$33.16"; a negative has a leading minus."""
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    sign, a = ("-" if v < 0 else ""), abs(v)
    if a >= 1e9:
        return f"{sign}{a / 1e9:.1f} מיליארד $"
    if a >= 1e6:
        return f"{sign}{a / 1e6:.0f} מיליון $"
    return f"{sign}${a:,.2f}"


def pct(v: Optional[float], nd: int = 1, fraction: bool = True) -> Optional[str]:
    return None if v is None else f"{v * 100 if fraction else v:.{nd}f}%"


def _pts(c: dict) -> tuple:
    lo, hi = c.get("range_min"), c.get("range_max")
    if lo is not None and hi is not None and abs(hi - lo) > 1e-9:
        return (lo + hi) / 2.0, True
    return (c.get("observed_points") if c.get("observed_points") is not None else lo), False


def _price_block(j: dict, key: str) -> dict:
    return j.get(key) or (j.get("pricing_file") or {}).get(key) or {}


def ai_pending_count(j: dict) -> int:
    """Items still waiting for an AI answer (state ``ai_pending``): D2 is not generated while there are any."""
    return sum(1 for m in ("buffett", "graham") for c in j[f"{m}_quality"].get("criteria", []) for i in c.get("items", []) if i.get("state") == "ai_pending")


def score_display(model: str, q: dict) -> dict:
    score, is_range = score_of(q)
    if score is None:
        return {"score": None, "score_display": None, "label_he": None, "is_range": False}
    if is_range:
        lo, hi = q["range_min"], q["range_max"]
        la, lb = quality_label(model, lo), quality_label(model, hi)
        return {"score": round(score, 1), "range": [round(lo, 1), round(hi, 1)], "score_display": f"{lo:.1f}–{hi:.1f}/100, משוער", "label_he": la if la == lb else None, "is_range": True}
    return {"score": round(score, 1), "score_display": f"{score:.1f}/100", "label_he": quality_label(model, score), "is_range": False}


def method_he(p: dict) -> str:
    key = p.get("method") or ("dcf" if "dcf" in p else None)
    return glossary()["methods"][key]                    # an unknown method fails loudly: every profile has its own named method


def model_block(j: dict, model: str) -> dict:
    g = glossary()
    q = j[f"{model}_quality"]
    pre = "B" if model == "buffett" else "G"
    sd = score_display(model, q)
    crit = []
    for c in q.get("criteria", []):
        pts, is_range = _pts(c)
        crit.append({"id": f"{pre}-{c['id']}", "name_he": g["criteria"][f"{pre}-{c['id']}"], "points": round(pts, 1) if pts is not None else None, "max": c.get("weight"),
                     "strength_he": strength_word(pts, c.get("weight")), **({"range": True} if is_range else {})})
    ranked = sorted((c for c in crit if c["points"] is not None and c["max"]), key=lambda c: c["points"] / c["max"])
    strong = g["strength"]["strong"]
    strongest = [c["name_he"] for c in reversed(ranked) if c["strength_he"] == strong][:2]
    lowest = {"name_he": ranked[0]["name_he"], "strength_he": ranked[0]["strength_he"]} if ranked else None      # always the lowest criterion, with its strength word
    p = _price_block(j, f"{model}_price")
    bp = p.get("buy_price") if isinstance(p.get("buy_price"), dict) else {}
    value = p.get("fair_value") if model == "buffett" else p.get("value")
    state = bp.get("state")
    st_he = None
    if state and state != "computed":
        st_he = g["states"].get(state) or g["states"]["cannot_price"]
    mos = bp.get("margin_of_safety")
    flags = [str(f)[:80] for f in (p.get("flags") or []) if not any(w in str(f).lower() for w in PRICE_FLAG_WORDS)][:3]
    return {**sd, "coverage": q.get("coverage"), "criteria": crit, "strongest_he": strongest or "אין", "lowest_he": lowest, "value_text": money(value), "method_he": method_he(p),
            "buy_price_text": money(bp.get("buy_price")), "required_mos_text": pct(mos) if isinstance(mos, (int, float)) else None, "state_he": st_he, "flags": flags}


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
    he = {"buffett": g["models"]["buffett"], "graham": g["models"]["graham"]}
    compare = all((not v["range_midpoint"]) and v.get("n_final", 0) >= MIN_FINAL_PEERS and v["percentile"] is not None for v in pc["quality"].values())
    q = {he[m]: {"score": v["score"], "range_midpoint": v["range_midpoint"], "peers_with_final_score": v.get("n_final", 0),
                 "position_he": position_word(v["percentile"]) if compare else None} for m, v in pc["quality"].items()}
    return {"group": {"definition": g["group"]["fallback" if pc["group"]["fallback"] else "full"], "n": pc["group"]["n"], "fallback": pc["group"]["fallback"], "compare": compare},
            "quality": q}


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
    elif prev["buffett_quality"].get("pending_criteria") or prev["graham_quality"].get("pending_criteria") or ai_pending_count(prev):
        why = "ai"
    else:
        why = "data"
    return {"previous_run": prev_date, "reason_he": g["change"]["reasons"][why], "changes": items[:3]}


def key_metrics_text(rec: dict) -> dict:
    """The six key metrics of the latest year as ready formatted text (display spec, Appendix A); a missing or not-shown metric is left out."""
    g = glossary()
    mn = g["metrics"].get(rec["profile"], g["metrics"]["STANDARD"])
    m, prof, out = rec["metrics"], rec["profile"], {}
    fmt = {"revenue": money, "net_income": money, "eps": money, "fcf": money}
    for k, name in mn.items():
        v = m.get(k)
        if not name or v is None:
            continue
        if k in fmt:
            out[name] = fmt[k](v)
        elif k == "roe":
            out[name] = pct(v)
        elif k == "leverage":
            out[name] = pct(v, fraction=False) if prof == "BANK" else (pct(v) if prof == "INSURANCE" else (f"{v:.1f}x" if prof == "INCOME_REAL_ESTATE" else f"{v:.2f}"))
    return out


def build_d2_inputs(j: dict, rec: dict, run_id: str, pc: dict, prev: Optional[dict] = None, prev_date: Optional[str] = None) -> dict:
    g = glossary()
    results = {"run_id": run_id, "profile": rec["profile"], "fiscal_year": rec["fiscal_year"], "score_scale_max": 100,
               "models": {g["models"][m]: model_block(j, m) for m in ("buffett", "graham")}, "key_metrics": key_metrics_text(rec)}
    return {"results": results, "peers": peers_view(pc, rec["profile"]), "changes": compute_changes(j, prev, prev_date), "forbidden_numbers": forbidden_numbers(j),
            "ai_pending": ai_pending_count(j)}

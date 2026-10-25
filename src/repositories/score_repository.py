"""Score outputs in the database (K6c, K6 spec 2.7): ``score_runs``, ``score_details``, ``valuations`` and ``company_score_summary`` (the current state).

``write_result`` takes the result dict of an engine run (the structure the runners save as <ticker>.json: ``buffett_quality`` / ``graham_quality`` with ``criteria`` and ``items``,
``buffett_price`` / ``graham_price`` with ``price_score`` and ``buy_price``) and writes one run. The same result is not written twice: a fingerprint of the content is kept in the run's
``flags`` and an unchanged result returns the existing run. ``read_latest`` rebuilds a comparable view from the tables (used by the identity test against the golden files).
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from typing import Optional

from src.db import get_supabase_client

QUALITY = (("buffett", "buffett_quality"), ("graham", "graham_quality"))
PRICE = (("buffett", "buffett_price"), ("graham", "graham_price"))
ITEM_STATUS = {"score": "calculated", "true_zero": "calculated", "ai_pending": "ai_pending", "not_applicable": "not_applicable", "missing": "missing_data"}
PROFILES = ("STANDARD", "TECH_ASSET_LIGHT", "BANK", "INSURANCE", "INCOME_REAL_ESTATE")
CALCULATION_VERSION = "k6c-1"


def clean(o):
    """JSON-safe copy: dates -> iso text, non-finite floats -> None."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return o


def price_model(result: dict, key: str):
    """The price result of a model: in the result itself, or (insurance) in the separate pricing file the runner writes next to it."""
    p = result.get(key)
    return p if isinstance(p, dict) else ((result.get("pricing_file") or {}).get(key) if isinstance((result.get("pricing_file") or {}).get(key), dict) else None)


def fingerprint(result: dict) -> str:
    keep = {k: result.get(k) for k in ("profile", "buffett_quality", "graham_quality", "buffett_price", "graham_price", "price", "flags", "pricing_file")}
    return hashlib.sha256(json.dumps(clean(keep), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


class ScoreRepository:
    def __init__(self, client=None):
        self.client = client or get_supabase_client()

    # ------------------------------------------------------------ mapping helpers
    @staticmethod
    def profile_of(result: dict) -> str:
        p = result.get("profile") or (result.get("profile_router") or {}).get("profile")
        if p not in PROFILES:
            raise ValueError(f"result has no usable profile ({p!r})")
        return p

    @staticmethod
    def price_state(p: Optional[dict]) -> str:
        if not p:
            return "not_applicable"
        if p.get("state") == "cannot_be_valued":
            return "cannot_be_valued"
        s = (p.get("price_score") or {}).get("state")
        return {"score": "scored", "blocked": "blocked", "cannot_be_priced": "cannot_be_priced", "not_applicable": "not_applicable", "stale": "stale"}.get(s, "not_applicable")

    @staticmethod
    def buy_state(p: Optional[dict]) -> str:
        b = (p or {}).get("buy_price") or {}
        s = b.get("state")
        if s == "computed" and b.get("buy_price") is not None:
            return "allowed"
        if s == "not_suitable":
            return "not_suitable"
        if s == "not_computed" and (b.get("quality_coverage") is not None and b["quality_coverage"] < 0.8):
            return "coverage_below_80"
        return "not_applicable"

    def _quality_rows(self, run_id: int, company_id: int, model: str, q: dict) -> list:
        rows = [{"run_id": run_id, "company_id": company_id, "model": model, "score_type": "quality", "criterion_key": "total", "criterion_name": "Total quality score", "detail_level": "criterion",
                 "sub_criterion_key": "main", "criterion_score": _num(q.get("score")), "max_score": 100, "score_status": "calculated" if q.get("score") is not None else "missing_data",
                 "coverage": _num(q.get("coverage")), "range_min": _num(q.get("range_min")), "range_max": _num(q.get("range_max")),
                 "evidence": clean({**{k: q.get(k) for k in ("observed_points", "status", "buy_price_allowed", "pending_criteria", "invalid_criteria", "unknown_items", "range_error", "model")},
                                    "exact": {k: q.get(k) for k in ("score", "range_min", "range_max", "coverage")}}),
                 "calculation_version": CALCULATION_VERSION}]
        for c in q.get("criteria", []):
            weight = c.get("weight") or 0
            items = c.get("items", [])
            status = "ai_pending" if any(i.get("state") == "ai_pending" for i in items) else ("calculated" if c.get("valid", True) else "missing_data")
            rows.append({"run_id": run_id, "company_id": company_id, "model": model, "score_type": "quality", "criterion_key": c["id"], "criterion_name": c.get("name") or c["id"], "detail_level": "criterion",
                         "sub_criterion_key": "main", "criterion_score": _num(c.get("observed_points")), "max_score": weight, "score_status": status,
                         "coverage": (min(1.0, c["covered_points"] / weight) if weight and _num(c.get("covered_points")) is not None else None),
                         "range_min": _num(c.get("range_min")), "range_max": _num(c.get("range_max")),
                         "missing_fields": [str(i["id"]) for i in items if i.get("state") == "missing"],
                         "evidence": clean({k: c.get(k) for k in ("computed_share", "covered_points", "normalized", "observed_points", "valid", "weight", "range_min", "range_max")}),
                         "calculation_version": CALCULATION_VERSION})
            for it in items:
                rows.append({"run_id": run_id, "company_id": company_id, "model": model, "score_type": "quality", "criterion_key": c["id"], "criterion_name": c.get("name") or c["id"],
                             "detail_level": "sub_criterion", "sub_criterion_key": str(it["id"]), "sub_criterion_name": it.get("name"), "criterion_score": _num(it.get("points")),
                             "max_score": it.get("max_pts") or 0, "score_status": ITEM_STATUS.get(it.get("state"), "calculated" if it.get("points") is not None else "missing_data"),
                             "metric_value": _num(it.get("metric")), "inputs": clean(it.get("inputs")) if it.get("inputs") else None,
                             "evidence": clean({"state": it.get("state"), "flags": it.get("flags"), "note": it.get("note"), "metric_label": it.get("metric_label"), "thresholds": it.get("thresholds"),
                                                "metric": it.get("metric"), "points": it.get("points"), "max_pts": it.get("max_pts")}), "calculation_version": CALCULATION_VERSION})
        return rows

    # ------------------------------------------------------------ write
    def latest_run(self, company_id: int) -> Optional[dict]:
        r = self.client.table("score_runs").select("*").eq("company_id", company_id).order("id", desc=True).limit(1).execute().data
        return r[0] if r else None

    def write_result(self, company_id: int, result: dict, rulebook_version: Optional[str] = None, peer_group: Optional[dict] = None, force: bool = False) -> tuple:
        """-> (run_id, "inserted" | "unchanged"). An unchanged result (same fingerprint as the latest run) writes nothing."""
        fp = fingerprint(result)
        last = self.latest_run(company_id)
        if last and not force and (last.get("flags") or {}).get("fingerprint") == fp:
            return last["id"], "unchanged"
        profile = self.profile_of(result)
        pr = result.get("price") or {}
        run = self.client.table("score_runs").insert({
            "company_id": company_id, "profile": profile, "rulebook_version": rulebook_version or str(result.get("scoring_model_version") or "rulebook-2026-10-21"),
            "calculation_version": CALCULATION_VERSION, "price": _num(pr.get("current")), "price_date": clean(pr.get("current_date") or pr.get("date")),
            "flags": clean({"fingerprint": fp, "engine_flags": result.get("flags") or []}), "peer_group": clean(peer_group)}).execute().data[0]
        run_id = run["id"]
        bq, gq = result.get("buffett_quality") or {}, result.get("graham_quality") or {}
        bp, gp = price_model(result, "buffett_price"), price_model(result, "graham_price")
        labels = list((result.get("fiscal_years") or {}).keys()) or list((result.get("inputs") or {}).get("fy") or [])
        fy_list = sorted(int(str(k)[2:]) for k in labels)
        as_of = fy_list[-1] if fy_list else (int(str(pr["current_date"])[:4]) if pr.get("current_date") else None)
        overall = ("missing_data" if bq.get("score") is None else "partial" if (bq.get("pending_criteria") or bq.get("status") != "full") else "calculated")
        summary = {"company_id": company_id, "as_of_fiscal_year": as_of, "years_available": min(len(fy_list), 20) if fy_list else None,
                   "buffett_quality_score": _num(bq.get("score")), "buffett_price_score": _num(((bp or {}).get("price_score") or {}).get("points")),
                   "graham_quality_score": _num(gq.get("score")), "graham_price_score": _num(((gp or {}).get("price_score") or {}).get("points")), "overall_status": overall,
                   "calculation_version": CALCULATION_VERSION, "updated_at": datetime.now(timezone.utc).isoformat(), "profile": profile if profile in PROFILES else None,
                   "rulebook_version": rulebook_version or str(result.get("scoring_model_version") or "rulebook-2026-10-21"),
                   "buffett_quality_coverage": _num(bq.get("coverage")), "graham_quality_coverage": _num(gq.get("coverage")),
                   "buffett_fair_value": _num((bp or {}).get("fair_value", (bp or {}).get("value"))), "graham_fair_value": _num((gp or {}).get("fair_value", (gp or {}).get("value"))),
                   "buffett_buy_price": _num(((bp or {}).get("buy_price") or {}).get("buy_price")), "graham_buy_price": _num(((gp or {}).get("buy_price") or {}).get("buy_price")),
                   "latest_run_id": run_id}
        self.client.table("company_score_summary").upsert(summary, on_conflict="company_id").execute()
        rows = []
        for model, key in QUALITY:
            if result.get(key):
                rows += self._quality_rows(run_id, company_id, model, result[key])
        for r in rows:                                   # one batch needs the same keys in every row
            r.setdefault("missing_fields", [])
            for k in ("sub_criterion_name", "metric_value", "inputs", "coverage", "range_min", "range_max"):
                r.setdefault(k, None)
        try:
            for i in range(0, len(rows), 200):
                self.client.table("score_details").insert(rows[i:i + 200]).execute()
        except Exception:
            self.client.table("score_runs").delete().eq("id", run_id).execute()        # no half-written run stays (details cascade)
            raise
        vals = []
        for model, key in PRICE:
            p = price_model(result, key)
            if not isinstance(p, dict):
                continue
            b = p.get("buy_price") or {}
            vals.append({"run_id": run_id, "model": model, "method": str(p.get("method") or p.get("model") or "n/a"), "fair_value": _num(p.get("fair_value", p.get("value"))),
                         "price_score": _num((p.get("price_score") or {}).get("points")) if self.price_state(p) == "scored" else None, "price_state": self.price_state(p),
                         "margin_of_safety": _num(b.get("margin_of_safety")), "buy_price": _num(b.get("buy_price")) if self.buy_state(p) == "allowed" else None,
                         "buy_price_state": self.buy_state(p), "details": clean(p)})
        if vals:
            self.client.table("valuations").insert(vals).execute()
        return run_id, "inserted"

    # ------------------------------------------------------------ read
    def read_latest(self, company_id: int) -> Optional[dict]:
        """A view of the latest run rebuilt from the tables: {"run", "summary", "quality": {model: {...}}, "price": {model: {...}}}."""
        run = self.latest_run(company_id)
        if not run:
            return None
        rows, start = [], 0
        while True:
            page = self.client.table("score_details").select("*").eq("run_id", run["id"]).order("id").range(start, start + 999).execute().data
            rows += page
            if len(page) < 1000:
                break
            start += 1000
        quality: dict = {}
        for r in rows:
            m = quality.setdefault(r["model"], {"criteria": {}})
            if r["criterion_key"] == "total":
                ev = r["evidence"] or {}
                m.update({"score": r["criterion_score"], "range_min": r["range_min"], "range_max": r["range_max"], "coverage": r["coverage"], "status": ev.get("status"),
                          "observed_points": ev.get("observed_points"), "exact": ev.get("exact") or {}})
            elif r["detail_level"] == "criterion":
                ev = r["evidence"] or {}
                m["criteria"].setdefault(r["criterion_key"], {"items": {}}).update({"observed_points": r["criterion_score"], "range_min": r["range_min"], "range_max": r["range_max"],
                                                                                  "weight": r["max_score"], "computed_share": ev.get("computed_share"), "covered_points": ev.get("covered_points"),
                                                                                  "normalized": ev.get("normalized"), "valid": ev.get("valid"), "status": r["score_status"], "ev": ev})
            else:
                ev = r["evidence"] or {}
                m["criteria"].setdefault(r["criterion_key"], {"items": {}})["items"][r["sub_criterion_key"]] = {"points": r["criterion_score"], "max_pts": r["max_score"], "state": ev.get("state"),
                                                                                                               "metric": ev.get("metric"), "status": r["score_status"],
                                                                                                               "points_exact": ev.get("points"), "max_pts_exact": ev.get("max_pts")}
        vals = {v["model"]: v for v in self.client.table("valuations").select("*").eq("run_id", run["id"]).execute().data}
        summary = self.client.table("company_score_summary").select("*").eq("company_id", company_id).limit(1).execute().data
        return {"run": run, "summary": summary[0] if summary else None, "quality": quality, "price": vals}


SCALE = {"score": 2, "range_min": 2, "range_max": 2, "coverage": 4, "observed_points": 2, "weight": 2, "points": 2, "fair_value": 4, "price_score": 2, "buy_price": 4, "margin_of_safety": 4}


def rnd(v, scale):
    """The value as a numeric column stores it (rounded half away from zero)."""
    from decimal import ROUND_HALF_UP, Decimal
    return None if v is None else float(Decimal(repr(float(v))).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP))


def compare_with_golden(view: dict, golden: dict) -> list:
    """Differences between ``read_latest`` and a golden result file. A column is compared with the golden value rounded to the column's scale (the tables keep display precision: scores 2
    decimals, prices 4); the full-precision values kept in the jsonb columns (``evidence``, ``valuations.details``) are compared exactly."""
    diffs: list = []

    def chk(path, a, b):
        if not (a == b or (a is None and b is None)):
            diffs.append(f"{path}: db={a!r} golden={b!r}")

    def col(path, db, gv, name):
        chk(path, None if db is None else float(db), rnd(gv, SCALE[name]) if _num(gv) is not None else gv)

    for model, key in QUALITY:
        g, d = golden.get(key), view["quality"].get(model)
        if not isinstance(g, dict):
            if d:
                diffs.append(f"{key}: in the database but not in golden")
            continue
        if not d:
            diffs.append(f"{key}: missing in the database")
            continue
        for f in ("score", "range_min", "range_max", "coverage"):
            col(f"{key}.{f}", d.get(f), g.get(f), f)
            chk(f"{key}.{f} (exact)", d["exact"].get(f), clean(g.get(f)))
        chk(f"{key}.status", d.get("status"), g.get("status"))
        chk(f"{key}.observed_points (exact)", d.get("observed_points"), clean(g.get("observed_points")))
        gc = {c["id"]: c for c in g["criteria"]}
        chk(f"{key}.criteria ids", sorted(d["criteria"]), sorted(gc))
        for cid, c in gc.items():
            dc = d["criteria"].get(cid, {"items": {}, "ev": {}})
            for f in ("observed_points", "range_min", "range_max", "weight"):
                col(f"{key}.{cid}.{f}", dc.get(f), c.get(f), f)
            for f in ("computed_share", "covered_points", "normalized", "valid", "observed_points", "range_min", "range_max", "weight"):
                chk(f"{key}.{cid}.{f} (exact)", dc.get("ev", {}).get(f), clean(c.get(f)))
            gi = {str(i["id"]): i for i in c["items"]}
            chk(f"{key}.{cid}.item ids", sorted(dc["items"]), sorted(gi))
            for iid, i in gi.items():
                di = dc["items"].get(iid, {})
                col(f"{key}.{cid}.{iid}.points", di.get("points"), i.get("points"), "points")
                chk(f"{key}.{cid}.{iid}.points (exact)", di.get("points_exact"), clean(i.get("points")))
                chk(f"{key}.{cid}.{iid}.state", di.get("state"), i.get("state"))
                chk(f"{key}.{cid}.{iid}.max_pts (exact)", di.get("max_pts_exact"), clean(i.get("max_pts")))
    for model, key in PRICE:
        g, d = price_model(golden, key), view["price"].get(model)
        if not isinstance(g, dict):
            if d:
                diffs.append(f"{key}: in the database but not in golden")
            continue
        if not d:
            diffs.append(f"{key}: missing in the database")
            continue
        b = g.get("buy_price") or {}
        col(f"{key}.fair_value", d["fair_value"], g.get("fair_value", g.get("value")), "fair_value")
        col(f"{key}.price_score", d["price_score"], (g.get("price_score") or {}).get("points") if ScoreRepository.price_state(g) == "scored" else None, "price_score")
        col(f"{key}.buy_price", d["buy_price"], b.get("buy_price") if ScoreRepository.buy_state(g) == "allowed" else None, "buy_price")
        col(f"{key}.margin_of_safety", d["margin_of_safety"], b.get("margin_of_safety"), "margin_of_safety")
        chk(f"{key}.price_state", d["price_state"], ScoreRepository.price_state(g))
        chk(f"{key}.details (exact)", d["details"], clean(g))
    return diffs

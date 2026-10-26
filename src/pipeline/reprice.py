"""A new price changes the price part of the score in place (K6 spec 3.3, K6d-1): the price score, the distance from the buy price and the conclusion. It never creates a score run.

The price score is the engines' own rule: discount = (fair value - price) / fair value, points = piecewise-linear interpolation of the discount on the anchors of the model (the anchors the run stored
in ``price_score.anchors``, or the engine constants when the run had no price). The quality score, the fair value and the buy price do not depend on the price and are not touched.

Pure functions (``reprice_block``, ``reprice_result``, ``vs_buy``) and ``PriceUpdater`` (the database part: ``valuations`` + ``company_score_summary`` + ``score_runs.price`` of the company's latest run).
``reprice_result`` is also used when a new run is written, so a run is always priced at the latest stored price and not at the price file of an older stage.

Display extras that are computed from the price by the engine (the reverse DCF, the implied return, price/TBV) are kept as the run computed them; ``extras_price`` records the price they belong to.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Optional

from src.repositories.score_repository import SCORE_WRITE, ScoreRepository, rnd
from src.scoring import buffett as B
from src.scoring import graham as G
from src.scoring.interpolate import describe, interpolate

HOT_RATIO = 1.10
PRICE_EXTRAS = ("reverse_dcf", "implied_return", "price_to_tbv")
CONCLUSIONS = ("at_or_below_buy_price", "near_buy_price", "above_buy_price", "no_buy_price")


def parse_anchors(text: str) -> list:
    """``"-0.25->0 | -0.2->0.5 | 0->2.5"`` (``describe`` output) -> [(-0.25, 0.0), ...]."""
    out = []
    for part in str(text).split("|"):
        x, y = part.strip().rsplit("->", 1)
        out.append((float(x), float(y)))
    return out


def anchors_for(model: str, block: dict) -> list:
    stored = (block.get("price_score") or {}).get("anchors")
    if stored:
        return parse_anchors(stored)
    if model == "buffett":
        return B.PRICE_ANCHORS
    return G.TECH_PRICE if block.get("method") == "graham_tech" else G.CLASSIC_PRICE


def fair_value_of(model: str, block: dict) -> Optional[float]:
    v = block.get("fair_value", block.get("value"))                      # the same lookup as ScoreRepository.write_result
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def vs_buy(price: Optional[float], buy_block: Optional[dict], ratio: float = HOT_RATIO) -> dict:
    """Distance of the price from the buy price (price / buy price - 1: above 0 = the price is above the buy price) and the conclusion."""
    buy = (buy_block or {}).get("buy_price") if (buy_block or {}).get("state") == "computed" else None
    if price is None or not isinstance(buy, (int, float)) or buy <= 0:
        return {"price": price, "buy_price": None, "distance": None, "conclusion": "no_buy_price"}
    concl = "at_or_below_buy_price" if price <= buy else ("near_buy_price" if price <= buy * ratio else "above_buy_price")
    return {"price": price, "buy_price": buy, "distance": price / buy - 1, "conclusion": concl}


def reprice_block(model: str, block: dict, price: Optional[float], stale: bool = False, ratio: float = HOT_RATIO) -> dict:
    """A copy of a price block (``buffett_price`` / ``graham_price`` of a result, or ``valuations.details``) priced at ``price``. A block that cannot be priced is returned as it is."""
    if not isinstance(block, dict) or price is None:
        return block
    fv = fair_value_of(model, block)
    if block.get("state") == "cannot_be_valued" or fv is None:
        return block
    b = copy.deepcopy(block)
    if "extras_price" not in b and any(k in b for k in PRICE_EXTRAS):
        b["extras_price"] = block.get("price_current")
    b["price_current"] = price
    if stale:
        b["price_score"] = {"state": "stale", "points": None, "reason": "the price was not updated for more than 3 trading days (E1)"}
    else:
        anchors = anchors_for(model, block)
        disc = (fv - price) / fv
        b["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, anchors), "anchors": describe(anchors)}
    b["price_vs_buy"] = vs_buy(price, b.get("buy_price"), ratio)
    return b


def reprice_result(result: dict, price: Optional[float], price_date=None, stale: bool = False, ratio: float = HOT_RATIO) -> dict:
    """A copy of an engine result with the price part priced at ``price`` (the quality part is untouched)."""
    if price is None:
        return result
    out = copy.deepcopy(result)
    out["price"] = {**(out.get("price") or {}), "current": price, "current_date": str(price_date) if price_date else (out.get("price") or {}).get("current_date")}
    for model in ("buffett", "graham"):
        key = f"{model}_price"
        if isinstance(out.get(key), dict):
            out[key] = reprice_block(model, out[key], price, stale, ratio)
        pf = out.get("pricing_file")
        if isinstance(pf, dict) and isinstance(pf.get(key), dict):
            pf[key] = reprice_block(model, pf[key], price, stale, ratio)
    return out


class PriceUpdater:
    """Applies a price to the latest score run of a company, in place."""

    def __init__(self, client, ratio: float = HOT_RATIO, now=None):
        self.client, self.ratio = client, ratio
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.scores = ScoreRepository(client)

    def update_company(self, company_id: int, price: float, price_date=None, snapshot_at: Optional[str] = None, stale: bool = False) -> dict:
        """-> {"status": "updated" | "unchanged" | "no_run", "valuations": n changed}."""
        with SCORE_WRITE:
            run = self.scores.latest_run(company_id)
            if not run:
                return {"status": "no_run", "valuations": 0}
            vals = self.client.table("valuations").select("*").eq("run_id", run["id"]).execute().data
            changed, points = 0, {}
            for v in vals:
                new = reprice_block(v["model"], v["details"], price, stale, self.ratio)
                state = ScoreRepository.price_state(new)
                score = rnd((new.get("price_score") or {}).get("points"), 2) if state == "scored" and (new.get("price_score") or {}).get("points") is not None else None
                points[v["model"]] = score
                if new != v["details"] or v["price_state"] != state or (None if v["price_score"] is None else float(v["price_score"])) != score:
                    self.client.table("valuations").update({"details": new, "price_state": state, "price_score": score}).eq("id", v["id"]).execute()
                    changed += 1
            summary = self.client.table("company_score_summary").select("*").eq("company_id", company_id).limit(1).execute().data
            fields = {}
            if summary:
                for model in ("buffett", "graham"):
                    if model in points:
                        old = summary[0].get(f"{model}_price_score")
                        if (None if old is None else float(old)) != points[model]:
                            fields[f"{model}_price_score"] = points[model]
                if snapshot_at and summary[0].get("market_snapshot_at") != snapshot_at:
                    fields["market_snapshot_at"] = snapshot_at
                if fields:
                    fields["updated_at"] = self.now().isoformat()
                    self.client.table("company_score_summary").update(fields).eq("company_id", company_id).execute()
            run_fields = {}
            if run.get("price") is None or float(run["price"]) != rnd(price, 4):
                run_fields["price"] = rnd(price, 4)
            if price_date and str(run.get("price_date")) != str(price_date):
                run_fields["price_date"] = str(price_date)
            if run_fields:
                self.client.table("score_runs").update(run_fields).eq("id", run["id"]).execute()
            return {"status": "updated" if (changed or fields or run_fields) else "unchanged", "valuations": changed}

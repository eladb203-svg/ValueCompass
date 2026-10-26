"""The "what changed" line of a company (K6 spec 3.3): only the latest score run of a company is kept, so before the previous run is deleted the code compares it with the new result and keeps the
line in the NEW run (``score_runs.changes``). D2 reads the line from there (``exec_analysis``).

The comparison itself is ``d2.compute_changes`` (the same wording and rules as before); this module rebuilds the previous run as a result-shaped dict from the tables.
A previous run that still waited for AI answers is not "a state the user saw": the new run then inherits the line of the previous run (the change since the last complete run).
"""
from __future__ import annotations

from typing import Optional


def view_to_result(view: dict, as_of_fiscal_year: Optional[int], rulebook_version: str) -> dict:
    """``ScoreRepository.read_latest`` -> the structure ``d2.compute_changes`` reads."""
    out = {"fiscal_years": {f"FY{as_of_fiscal_year}": None} if as_of_fiscal_year else {}, "scoring_model_version": rulebook_version}
    for model in ("buffett", "graham"):
        q = (view.get("quality") or {}).get(model)
        if q:
            crit = [{"id": cid, "weight": c.get("weight"), "observed_points": c.get("observed_points"), "range_min": c.get("range_min"), "range_max": c.get("range_max"),
                     "items": [{"id": iid, "state": i.get("state"), "points": i.get("points")} for iid, i in c["items"].items()]} for cid, c in q["criteria"].items()]
            out[f"{model}_quality"] = {"score": q.get("score"), "range_min": q.get("range_min"), "range_max": q.get("range_max"), "coverage": q.get("coverage"),
                                       "status": q.get("status"), "pending_criteria": q.get("pending_criteria") or [], "criteria": crit}
        v = (view.get("price") or {}).get(model)
        if v:
            out[f"{model}_price"] = v["details"]
    return out


def change_line(prev_view: dict, prev_fiscal_year: Optional[int], result: dict, rulebook_version: str, prev_date: str) -> Optional[dict]:
    """The change line between the previous run (``prev_view``) and ``result`` (None when the model finds nothing to say, or when a part is missing)."""
    from src.ai import d2 as D2
    prev = view_to_result(prev_view, prev_fiscal_year, str(prev_view["run"].get("rulebook_version") or rulebook_version))
    if "buffett_quality" not in prev or "graham_quality" not in prev or "buffett_quality" not in result or "graham_quality" not in result:
        return None
    cur = {**result, "scoring_model_version": rulebook_version}
    if prev["buffett_quality"].get("pending_criteria") or prev["graham_quality"].get("pending_criteria") or D2.ai_pending_count(prev):
        return (prev_view["run"].get("changes"))                       # inherit: the previous run was only a partial score
    return D2.compute_changes(cur, prev, prev_date)

"""AI answers inside the quality criteria (code stage K5a): an ``ai_pending`` sub-item becomes a scored (or missing) sub-item when a stored answer exists.

Pure. ``inp.ai_answers`` maps a skill id to ``{"state": "answered" | "insufficient_evidence", "answer": 0|1|2|None, "version": int, "flags": [...]}``; the engines'
input objects carry it (default empty = no change in any result). Points are computed here by code, never by the AI (R1, R13):
A1-A6, A8-A13 answer x 1; A7 (B3.2-Q5) answer x 0.5; A14 (G3.3B-Q4) 2 -> 3, 1 -> 1.5, 0 -> 0.
"""
from __future__ import annotations

from .coverage import ai_pending, missing, scored

POINTS = {  # skill id -> function(answer) -> points
    "B3.1-Q1": lambda a: a * 1.0, "B3.1-Q2": lambda a: a * 1.0, "B3.1-Q3": lambda a: a * 1.0, "B3.1-Q4": lambda a: a * 1.0, "B3.1-Q5": lambda a: a * 1.0,
    "B3.2-Q4": lambda a: a * 1.0, "B3.2-Q5": lambda a: a * 0.5, "B3.7-Q3": lambda a: a * 1.0, "B3.7-Q5": lambda a: a * 1.0, "B3.8-Q6": lambda a: a * 1.0,
    "G3.1-Q3": lambda a: a * 1.0, "G3.1-Q4": lambda a: a * 1.0, "G3.8-Q3": lambda a: a * 1.0, "G3.3B-Q4": lambda a: {2: 3.0, 1: 1.5, 0: 0.0}[a],
}
# quality model kind + criterion id + item id -> skill (used by the AI runner to find what to ask)
PENDING_TO_SKILL = {
    ("buffett", "3.1", "1"): "B3.1-Q1", ("buffett", "3.1", "2"): "B3.1-Q2", ("buffett", "3.1", "3"): "B3.1-Q3", ("buffett", "3.1", "4"): "B3.1-Q4",
    ("buffett", "3.1", "5"): "B3.1-Q5", ("buffett", "3.2", "4"): "B3.2-Q4", ("buffett", "3.2", "5"): "B3.2-Q5", ("buffett", "3.7", "3"): "B3.7-Q3",
    ("buffett", "3.7", "5"): "B3.7-Q5", ("buffett", "3.8", "6"): "B3.8-Q6",
    ("graham", "3.1", "3"): "G3.1-Q3", ("graham", "3.1", "4"): "G3.1-Q4", ("graham", "3.8", "3"): "G3.8-Q3", ("graham", "3.3", "4"): "G3.3B-Q4",
}


def ai_item(inp, skill: str, id, name, max_pts, **kw):
    rec = (getattr(inp, "ai_answers", None) or {}).get(skill)
    if not rec:
        return ai_pending(id, name, max_pts, **kw)
    base_inputs = dict(kw.pop("inputs", None) or {})
    base_inputs.update({"ai_skill": skill, "ai_version": rec.get("version")})
    kw.pop("note", None)
    if rec.get("state") != "answered" or rec.get("answer") is None:
        return missing(id, name, max_pts, inputs=base_inputs, flags=["ai_insufficient_evidence"] + list(rec.get("flags", [])),
                       note="AI: insufficient evidence (counted as missing, R16)", **{k: v for k, v in kw.items() if k in ("metric", "metric_label", "thresholds")})
    answer = int(rec["answer"])
    flags = ["ai_answer"] + list(rec.get("flags", []))
    return scored(id, name, max_pts, POINTS[skill](answer), inputs={**base_inputs, "ai_answer": answer}, flags=flags, note=f"AI answer {answer} ({skill})",
                  **{k: v for k, v in kw.items() if k in ("metric", "metric_label", "thresholds")})

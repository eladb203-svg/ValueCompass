"""Missing-data policy (M1-M9): sub-item states, criterion and model aggregation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("valuecompass.coverage")

SCORE = "score"
NOT_APPLICABLE = "not_applicable"
MISSING = "missing"
AI_PENDING = "ai_pending"
TRUE_ZERO = "true_zero"

COMPUTED_STATES = (SCORE, TRUE_ZERO)
UNKNOWN_STATES = (MISSING, AI_PENDING)  # widen the min-max range
# Round-specific ruling: ai_pending is temporary; it is ignored by the M2 validity check and by
# coverage (treated like not_applicable there) and shows up only in the min-max range.

CRITERION_VALID_SHARE = 0.70  # M2
COVERAGE_FULL = 0.80  # M5
COVERAGE_PARTIAL = 0.60  # M5
_EPS = 1e-9


@dataclass
class SubItem:
    id: str
    name: str
    max_pts: float
    state: str
    points: Optional[float] = None
    metric: Any = None
    metric_label: str = ""
    thresholds: str = ""
    inputs: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)
    note: str = ""


def scored(id, name, max_pts, points, **kw) -> SubItem:
    return SubItem(id, name, max_pts, SCORE, round(float(points), 6), **kw)


def true_zero(id, name, max_pts, **kw) -> SubItem:
    return SubItem(id, name, max_pts, TRUE_ZERO, 0.0, **kw)


def not_applicable(id, name, max_pts, **kw) -> SubItem:
    return SubItem(id, name, max_pts, NOT_APPLICABLE, None, **kw)


def missing(id, name, max_pts, **kw) -> SubItem:
    return SubItem(id, name, max_pts, MISSING, None, **kw)


def ai_pending(id, name, max_pts, **kw) -> SubItem:
    return SubItem(id, name, max_pts, AI_PENDING, None, **kw)


@dataclass
class CriterionResult:
    id: str
    name: str
    weight: float  # full weight = sum of sub-item maximums
    items: list
    observed: float  # points actually earned by computed sub-items
    computed_max: float
    na_max: float
    unknown_max: float  # missing + ai_pending
    applicable_max: float  # weight - na_max
    computed_share: float  # computed_max / applicable_max
    valid: bool
    normalized: Optional[float]  # M1, None when invalid / not applicable
    min_score: Optional[float]  # M9: unknown = 0
    max_score: Optional[float]  # M9: unknown = full
    covered_pts: float  # M4 contribution (0 when criterion invalid)
    unknown_items: list


def evaluate_criterion(id: str, name: str, items: list) -> CriterionResult:
    weight = sum(i.max_pts for i in items)
    computed = [i for i in items if i.state in COMPUTED_STATES]
    na = [i for i in items if i.state == NOT_APPLICABLE]
    unknown = [i for i in items if i.state in UNKNOWN_STATES]
    observed = sum(i.points or 0.0 for i in computed)
    computed_max = sum(i.max_pts for i in computed)
    na_max = sum(i.max_pts for i in na)
    unknown_max = sum(i.max_pts for i in unknown)
    ai_max = sum(i.max_pts for i in items if i.state == AI_PENDING)
    applicable = weight - na_max
    if applicable <= _EPS:  # whole criterion not applicable: neutral
        return CriterionResult(id, name, weight, items, 0.0, 0.0, na_max, 0.0, 0.0, 0.0, True,
                               None, None, None, weight, [])
    # K6d-2: a sub-item computed from a documented default (flag "default") counts in the score but not in the certain part: the range runs from 0 to its full points for that item
    dflt = [i for i in computed if "default" in (i.flags or [])]
    d_pts, d_max = sum(i.points or 0.0 for i in dflt), sum(i.max_pts for i in dflt)
    mn = (observed - d_pts) / applicable * weight
    mx = (observed - d_pts + d_max + unknown_max) / applicable * weight
    unk = [{"id": i.id, "name": i.name, "state": i.state, "max_pts": i.max_pts, "note": i.note}
           for i in items if i.state in UNKNOWN_STATES]
    basis = applicable - ai_max  # points that can be judged by code
    if basis <= _EPS:  # only AI items left: pending criterion, neutral for score and coverage
        return CriterionResult(id, name, weight, items, 0.0, 0.0, na_max, unknown_max, applicable, 0.0, True,
                               None, mn, mx, weight, unk)
    share = computed_max / basis
    valid = share + _EPS >= CRITERION_VALID_SHARE
    normalized = (observed / computed_max * weight) if (valid and computed_max > _EPS) else None
    covered = (computed_max + na_max + ai_max) if valid else 0.0
    return CriterionResult(
        id, name, weight, items, observed, computed_max, na_max, unknown_max, applicable,
        share, valid, normalized, mn, mx, covered, unk,
    )


@dataclass
class ModelResult:
    name: str
    criteria: list
    score: Optional[float]  # M3 (None when status == missing or no valid criteria)
    coverage: float  # M4, share 0..1
    status: str  # full / partial / missing   (M5)
    observed_points: float
    min_score: Optional[float]  # D14: None when the range check fails (range not published)
    max_score: Optional[float]
    invalid_criteria: list
    unknown_items: list
    pending_criteria: list
    buy_price_allowed: bool  # M7 (quality part)
    range_error: Optional[str] = None


def evaluate_model(name: str, criteria: list) -> ModelResult:
    total_w = sum(c.weight for c in criteria if c.applicable_max > _EPS) or 1.0
    valid = [c for c in criteria if c.valid and c.normalized is not None]
    valid_w = sum(c.weight for c in valid)
    score = (sum(c.normalized for c in valid) / valid_w * 100.0) if valid_w > _EPS else None
    covered = sum(c.covered_pts for c in criteria)
    coverage = covered / total_w
    if coverage + _EPS >= COVERAGE_FULL:
        status = "full"
    elif coverage + _EPS >= COVERAGE_PARTIAL:
        status = "partial"
    else:
        status = "missing"
        score = None
    # D14: score and range use the same set V of valid criteria (pending all-AI criteria included in the range only,
    # as their score is undefined); invalid criteria enter neither; not-applicable items create no uncertainty.
    in_v = [c for c in criteria if c.valid and c.applicable_max > _EPS]
    wv = sum(c.weight for c in in_v)
    mn = mx = None
    range_error = None
    if score is not None and wv > _EPS:
        mn = sum(c.min_score for c in in_v) / wv * 100.0
        mx = sum(c.max_score for c in in_v) / wv * 100.0
        if not (mn - 1e-6 <= score <= mx + 1e-6):
            range_error = f"{name}: range check failed (min {mn:.2f} <= score {score:.2f} <= max {mx:.2f}); range not published"
            log.error(range_error)
            mn = mx = None
    invalid = [{"id": c.id, "name": c.name, "computed_share": round(c.computed_share, 4)}
               for c in criteria if not c.valid]
    pending = [c.id for c in criteria if c.valid and c.normalized is None and c.applicable_max > _EPS]
    unknown = []
    for c in criteria:
        for u in c.unknown_items:
            unknown.append({"criterion": c.id, **u})
    return ModelResult(name, criteria, score, coverage, status,
                       sum(c.observed for c in criteria), mn, mx, invalid, unknown, pending,
                       status == "full" and score is not None, range_error)

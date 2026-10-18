"""Small helpers shared by the Buffett and Graham sub-item builders."""
from __future__ import annotations

from .coverage import SubItem, missing, scored, true_zero
from .interpolate import describe, interpolate
from .metrics import INF, last_n, clean


def L(xs, n=5):
    """Fiscal-year-aligned trailing window (None padded on the left)."""
    return last_n(xs, n)


def tail(xs, n=10):
    """Trailing window without padding (for 10-year criteria with partial history)."""
    return list(xs)[-n:]


def thresholded(id, name, mx, value, anchors, unit="", label="", inputs=None, flags=None, note="") -> SubItem:
    pts = interpolate(value, anchors)
    return scored(id, name, mx, pts, metric=value, metric_label=label,
                  thresholds=describe(anchors, unit), inputs=inputs or {}, flags=list(flags or []), note=note)


def zero(id, name, mx, value=None, anchors=None, unit="", label="", inputs=None, flags=None, note="") -> SubItem:
    return true_zero(id, name, mx, metric=value, metric_label=label,
                     thresholds=describe(anchors, unit) if anchors else "", inputs=inputs or {},
                     flags=list(flags or []), note=note)


def miss(id, name, mx, reason, anchors=None, unit="", inputs=None, flags=None) -> SubItem:
    return missing(id, name, mx, thresholds=describe(anchors, unit) if anchors else "",
                   inputs=inputs or {}, flags=list(flags or []), note=reason)


def paired_totals(a, b, k=5, min_n=3):
    """Sums of two series over the trailing k years, using only years where both exist.

    Returns (sum_a, sum_b, n_used) or (None, None, n_used) when fewer than min_n years.
    """
    A, B = L(a, k), L(b, k)
    pairs = [(x, y) for x, y in zip(A, B) if x is not None and y is not None]
    if len(pairs) < min_n:
        return None, None, len(pairs)
    return sum(p[0] for p in pairs), sum(p[1] for p in pairs), len(pairs)


def fmt(x, nd=4):
    if x is None:
        return None
    if x in (INF, -INF):
        return "inf" if x > 0 else "-inf"
    return round(x, nd)


def window_values(xs):
    return clean(xs)


def growth_item(id, name, mx, g, anchors, label, turnaround_half=True, start_nonpos_zero=False):
    """Score a smoothed-growth dict (R14): growth / turnaround / negative end."""
    inputs = {"start_avg": g.get("start_avg"), "end_avg": g.get("end_avg")}
    k = g["kind"]
    if k == "insufficient":
        return miss(id, name, mx, "need first-2 and last-2 values of the 5-year window", anchors)
    if k == "negative_end":
        return zero(id, name, mx, None, anchors, "", label, inputs, ["ending_average_nonpositive"],
                    "ending average <= 0 -> 0 points")
    if k == "turnaround":
        if start_nonpos_zero:
            return zero(id, name, mx, None, anchors, "", label, inputs, ["start_nonpositive"],
                        "starting average <= 0 -> 0 (Graham: failed test)")
        if turnaround_half:
            return scored(id, name, mx, mx / 2, metric=None, metric_label=label,
                          inputs=inputs, flags=["turnaround"],
                          note="loss-to-profit: half points (R14)")
    return thresholded(id, name, mx, g["value"], anchors, "", label, inputs)

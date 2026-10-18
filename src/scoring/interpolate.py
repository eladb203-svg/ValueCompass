"""Piecewise-linear scoring helper (rule R4)."""
from __future__ import annotations

import math
from typing import Sequence


def interpolate(x: float, anchors: Sequence[tuple[float, float]]) -> float:
    """Score ``x`` by linear interpolation between ``(threshold, points)`` anchors.

    Below the lowest threshold the first anchor's points apply, above the highest
    threshold the last anchor's points apply. Anchors may rise or fall (higher-is-worse
    metrics simply list falling points). Two or more anchors are allowed.
    """
    if x is None or (isinstance(x, float) and math.isnan(x)):
        raise ValueError("interpolate() needs a real number")
    pts = sorted((float(a), float(b)) for a, b in anchors)
    if len(pts) < 2:
        raise ValueError("at least two anchors are required")
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise AssertionError("unreachable")  # pragma: no cover


def describe(anchors: Sequence[tuple[float, float]], unit: str = "") -> str:
    """Human-readable anchor list for reports, e.g. ``0.0->0 | 0.05->3``."""
    pts = sorted((float(a), float(b)) for a, b in anchors)
    return " | ".join(f"{a:g}{unit}->{b:g}" for a, b in pts)

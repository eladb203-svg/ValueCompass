"""S3a (all profiles): a quantitative profile-assignment test whose value lies within 5 percentage points of its threshold raises a `borderline_assignment`
flag and enters the admin review list; the code still decides (the assignment follows the threshold)."""
from __future__ import annotations

BORDERLINE_MARGIN = 0.05  # 5 percentage points, on ratios expressed as fractions


def borderline_tests(tests: dict, margin: float = BORDERLINE_MARGIN) -> list:
    """tests: name -> (value, threshold), both as fractions. Returns the names of the tests within `margin` of their threshold (either side)."""
    return [name for name, (value, threshold) in tests.items() if value is not None and abs(value - threshold) <= margin + 1e-12]


def borderline_flag(tests: dict) -> dict:
    names = borderline_tests(tests)
    return {"borderline_assignment": bool(names), "borderline_tests": {k: {"value": tests[k][0], "threshold": tests[k][1], "distance_pp": None if tests[k][0] is None else round((tests[k][0] - tests[k][1]) * 100, 2)} for k in names}}

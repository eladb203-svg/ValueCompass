import math

import pytest

from src.scoring.interpolate import interpolate

ROIC = [(0, 0), (0.06, 4.5), (0.10, 8.5), (0.15, 12.5), (0.20, 15)]


def test_clamps_below_and_above():
    a = [(0.20, 0), (0.40, 1.0)]
    assert interpolate(0.10, a) == 0
    assert interpolate(0.20, a) == 0
    assert interpolate(0.50, a) == 1.0


def test_linear_midpoint():
    assert interpolate(0.30, [(0.20, 0), (0.40, 1.0)]) == pytest.approx(0.5)


def test_falling_scale():
    a = [(0.03, 1.5), (0.10, 0)]  # lower is better
    assert interpolate(0.02, a) == 1.5
    assert interpolate(0.065, a) == pytest.approx(0.75)
    assert interpolate(0.20, a) == 0


def test_multi_anchor_piecewise():
    assert interpolate(0.08, ROIC) == pytest.approx(6.5)  # between 6%->4.5 and 10%->8.5
    assert interpolate(0.12, ROIC) == pytest.approx(10.1)
    assert interpolate(-0.05, ROIC) == 0
    assert interpolate(0.35, ROIC) == 15


def test_integer_count_anchors():
    a = [(2, 0), (3, 2), (4, 4), (5, 6)]
    assert [interpolate(c, a) for c in (0, 2, 3, 4, 5)] == [0, 0, 2, 4, 6]


def test_unsorted_anchors_and_infinity():
    assert interpolate(float("inf"), [(10, 3), (1.5, 0), (5, 2.25)]) == 3
    assert interpolate(float("-inf"), [(10, 3), (1.5, 0)]) == 0


def test_nan_and_too_few_anchors_rejected():
    with pytest.raises(ValueError):
        interpolate(math.nan, ROIC)
    with pytest.raises(ValueError):
        interpolate(1, [(0, 0)])

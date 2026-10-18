import pytest

from src.scoring.coverage import (ai_pending, evaluate_criterion, evaluate_model, missing, not_applicable,
                                  scored, true_zero)


def test_spec_example_m9_missing_item_rescaled_with_range():
    items = [scored("a", "a", 3, 2.5), scored("b", "b", 3, 3), missing("c", "c", 2), scored("d", "d", 2, 1.5)]
    c = evaluate_criterion("x", "x", items)
    assert c.valid
    assert c.normalized == pytest.approx(8.75)
    assert (c.min_score, c.max_score) == (pytest.approx(7.0), pytest.approx(9.0))
    assert c.covered_pts == 8


def test_criterion_invalid_below_70_percent():
    items = [scored("a", "a", 3, 3), missing("b", "b", 2), missing("c", "c", 2), scored("d", "d", 3, 3)]
    c = evaluate_criterion("x", "x", items)  # 6/10 computed
    assert not c.valid and c.normalized is None and c.covered_pts == 0
    assert c.max_score == pytest.approx(10.0)


def test_ai_pending_ignored_by_validity_and_coverage_but_in_range():
    items = [scored("a", "a", 3, 3), ai_pending("b", "b", 2), ai_pending("c", "c", 2), scored("d", "d", 3, 3)]
    c = evaluate_criterion("x", "x", items)  # 6 of 6 code-decidable points computed
    assert c.valid and c.normalized == pytest.approx(10.0)
    assert c.covered_pts == 10
    assert (c.min_score, c.max_score) == (pytest.approx(6.0), pytest.approx(10.0))


def test_all_ai_criterion_is_pending_and_neutral():
    c = evaluate_criterion("x", "x", [ai_pending("a", "a", 10)])
    assert c.valid and c.normalized is None and c.covered_pts == 10
    assert (c.min_score, c.max_score) == (0, 10)
    good = evaluate_criterion("g", "g", [scored("a", "a", 90, 45)])
    m = evaluate_model("m", [c, good])
    assert m.pending_criteria == ["x"] and m.score == pytest.approx(50.0)
    assert m.coverage == pytest.approx(1.0)
    assert m.min_score == pytest.approx(45.0) and m.max_score == pytest.approx(55.0)


def test_criterion_exactly_70_percent_is_valid():
    items = [scored("a", "a", 7, 7), missing("b", "b", 3)]
    assert evaluate_criterion("x", "x", items).valid


def test_not_applicable_excluded_without_coverage_penalty():
    items = [scored("a", "a", 5, 5), not_applicable("b", "b", 5)]
    c = evaluate_criterion("x", "x", items)
    assert c.normalized == pytest.approx(10.0)  # 5/5 -> full weight
    assert c.covered_pts == 10  # N/A counts as covered
    assert c.computed_share == pytest.approx(1.0)


def test_true_zero_counts_as_computed():
    c = evaluate_criterion("x", "x", [true_zero("a", "a", 4), scored("b", "b", 6, 6)])
    assert c.normalized == pytest.approx(6.0)
    assert c.computed_share == 1.0


def test_all_not_applicable_is_neutral():
    c = evaluate_criterion("x", "x", [not_applicable("a", "a", 10)])
    assert c.valid and c.normalized is None and c.applicable_max == 0


def _crit(pts_of, weight, name):
    return evaluate_criterion(name, name, [scored("a", "a", weight, pts_of)])


def test_model_scales_valid_criteria_to_100_and_status_full():
    m = evaluate_model("m", [_crit(10, 10, "c1"), _crit(15, 15, "c2"),
                             evaluate_criterion("c3", "c3", [scored("a", "a", 75, 37.5)])])
    assert m.coverage == pytest.approx(1.0) and m.status == "full"
    assert m.score == pytest.approx(62.5)  # (10+15+37.5)/100


def test_model_excludes_invalid_criterion_from_score_and_coverage():
    bad = evaluate_criterion("bad", "bad", [missing("a", "a", 10)])
    good = evaluate_criterion("good", "good", [scored("a", "a", 90, 45)])
    m = evaluate_model("m", [bad, good])
    assert m.coverage == pytest.approx(0.9)
    assert m.status == "full"
    assert m.score == pytest.approx(50.0)  # only the valid criterion counts, rescaled
    # D14: the invalid criterion enters neither the score nor the range
    assert m.min_score == pytest.approx(50.0) and m.max_score == pytest.approx(50.0)
    assert m.invalid_criteria[0]["id"] == "bad"


def test_model_status_partial_and_missing():
    def model(computed_pts):
        a = evaluate_criterion("a", "a", [scored("a", "a", computed_pts, computed_pts / 2),
                                          missing("b", "b", 100 - computed_pts)])
        return evaluate_model("m", [a])
    # a single criterion with <70% computed is invalid -> coverage 0 -> missing
    assert model(60).status == "missing" and model(60).score is None
    # 75% computed: criterion valid, coverage 75% -> partial
    assert model(75).status == "partial" and model(75).score is not None
    assert model(85).status == "full"


def test_d14_range_uses_the_same_criteria_as_the_score_and_contains_it():
    bad = evaluate_criterion("bad", "bad", [missing("a", "a", 30)])  # invalid (0% computed)
    good = evaluate_criterion("good", "good", [scored("a", "a", 60, 54), missing("b", "b", 10)])  # 6/7 -> valid
    m = evaluate_model("m", [bad, good])
    assert m.score is not None and m.min_score is not None
    assert m.min_score <= m.score <= m.max_score
    # score: 54/60 * 70 = 63 of 70 -> 90; min: 54/70 -> 77.1; max: (54+10)/70 -> 91.4
    assert m.score == pytest.approx(90.0)
    assert m.min_score == pytest.approx(54 / 70 * 100)
    assert m.max_score == pytest.approx(64 / 70 * 100)


def test_d14_failed_check_withholds_the_range_and_logs_an_error(caplog):
    good = evaluate_criterion("good", "good", [scored("a", "a", 60, 54), missing("b", "b", 10)])
    good.min_score = 95.0  # corrupt the criterion bounds so that min > score
    with caplog.at_level("ERROR", logger="valuecompass.coverage"):
        m = evaluate_model("m", [good])
    assert m.min_score is None and m.max_score is None
    assert m.range_error and "range check failed" in m.range_error
    assert any("range check failed" in r.message for r in caplog.records)


def test_d14_pending_ai_criteria_widen_the_range_but_not_the_score():
    ai = evaluate_criterion("ai", "ai", [ai_pending("a", "a", 10)])
    good = evaluate_criterion("good", "good", [scored("a", "a", 90, 81)])
    m = evaluate_model("m", [ai, good])
    assert m.score == pytest.approx(90.0)
    assert m.min_score == pytest.approx(81.0) and m.max_score == pytest.approx(91.0)

"""K6b section 0: the K5b-matched CSV rows (89 rows of the 7 development companies) from the K5b compare results."""
import json

from src.etl.k5b_match import k5b_matched_keys


def test_missing_compare_file_gives_an_empty_set(tmp_path):
    assert k5b_matched_keys(tmp_path / "nope.json") == set()


def test_only_match_results_count_and_keys_are_extraction_row_keys(tmp_path):
    p = tmp_path / "compare.json"
    p.write_text(json.dumps([{"ticker": "JPM", "item": "cet1_ratio_standardized", "year": 2025, "result": "match"},
                             {"ticker": "BAC", "item": "cet1_ratio_standardized", "year": 2025, "result": "differ"}]), encoding="utf-8")
    keys = k5b_matched_keys(p)
    assert ("JPM", "cet1_ratio_standardized", "") in keys and not any(t == "BAC" for t, _, _ in keys)

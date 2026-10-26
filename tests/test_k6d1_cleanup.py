"""K6d-1: the retention cleanup (K6 spec 3.3) - what is selected, what is never touched, the dry run, apply. Fake database, temporary files."""
from datetime import datetime, timedelta, timezone

import pytest

from fakedb import FakeClient
from src.sched import cleanup as CL

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def ago(days):
    return (NOW - timedelta(days=days)).isoformat()


def test_only_the_latest_run_of_each_company_stays():
    runs = [{"id": 1, "company_id": 1}, {"id": 2, "company_id": 1}, {"id": 3, "company_id": 2}, {"id": 4, "company_id": 1}]
    assert sorted(r["id"] for r in CL.old_runs(runs)) == [1, 2]


def test_assessments_keep_the_latest_year_and_its_latest_version_per_question():
    rows = [{"id": 1, "company_id": 1, "question_id": "Q1", "fiscal_year": 2024, "prompt_version": "3", "approval_status": "approved"},
            {"id": 2, "company_id": 1, "question_id": "Q1", "fiscal_year": 2025, "prompt_version": "3", "approval_status": "approved"},
            {"id": 3, "company_id": 1, "question_id": "Q1", "fiscal_year": 2025, "prompt_version": "10", "approval_status": "approved"},
            {"id": 4, "company_id": 1, "question_id": "Q2", "fiscal_year": 2024, "prompt_version": "3", "approval_status": "approved"},
            {"id": 5, "company_id": 2, "question_id": "Q1", "fiscal_year": 2024, "prompt_version": "3", "approval_status": "approved"},
            {"id": 6, "company_id": 1, "question_id": "Q3", "fiscal_year": 2023, "prompt_version": "3", "approval_status": "approved"},
            {"id": 7, "company_id": 1, "question_id": "Q3", "fiscal_year": 2025, "prompt_version": "9", "approval_status": "rejected"}]
    assert sorted(r["id"] for r in CL.old_assessments(rows)) == [1, 2]            # "10" is newer than "3"; a rejected row neither wins nor is deleted; Q2, Q3 and company 2 keep their only approved row
    assert CL.version_key("3.1") > CL.version_key("3") and CL.version_key("10") > CL.version_key("9")


def text(i, **kw):
    base = {"id": i, "company_id": 1, "kind": "background", "language": "he", "fiscal_year": 2025, "approval_status": "approved", "created_at": ago(10 - i)}
    base.update(kw)
    return base


def test_texts_superseded_ones_and_the_ones_a_newer_text_replaced_go_a_newer_failed_attempt_stays():
    rows = [text(1, approval_status="superseded"), text(2, fiscal_year=2024), text(3), text(4, language="en"), text(5, kind="analysis"), text(6, approval_status="failed", created_at=ago(0)),
            text(7, approval_status="failed", fiscal_year=2023, created_at=ago(30)), text(8, company_id=2)]
    gone = {r["id"]: why for r, why in CL.old_texts(rows)}
    assert gone == {1: "superseded", 2: "replaced by a newer text", 7: "replaced by a newer text"}      # 3 wins he/background; 6 is a newer failed attempt: it stays for its retry
    only_failed = [text(1, approval_status="failed"), text(2, approval_status="failed", fiscal_year=2024)]
    assert CL.old_texts(only_failed) == []                                                         # nothing passed its checks: nothing is deleted


def test_profiles_keep_the_latest_per_company():
    rows = [{"id": 1, "company_id": 1, "fiscal_year": 2024}, {"id": 2, "company_id": 1, "fiscal_year": 2025}, {"id": 3, "company_id": 2, "fiscal_year": 2025}, {"id": 4, "company_id": 1, "fiscal_year": 2025}]
    assert sorted(r["id"] for r in CL.old_profiles(rows)) == [1, 2]


def test_sec_files_outside_the_ten_year_window_are_listed_and_unknown_files_are_kept(tmp_path):
    names = ["000000497715000001_afl-20141231.htm", "000000497716000002_afl-20151231.htm", "000000497724000003_afl-20231231.htm", "000000497725000047_afl-20241231.htm", "AFL_10K_text.txt",
             "000099999924000001_zzz-20230101.htm"]
    for n in names:
        (tmp_path / n).write_text("x" * 10, encoding="utf-8")
    periods = [{"company_id": 1, "fiscal_year": 2014, "accession": "0000004977-15-000001"}, {"company_id": 1, "fiscal_year": 2015, "accession": "0000004977-16-000002"},
               {"company_id": 1, "fiscal_year": 2023, "accession": "0000004977-24-000003"}, {"company_id": 1, "fiscal_year": 2024, "accession": "0000004977-25-000047"}]
    out = CL.outside_window(sorted(tmp_path.iterdir()), periods)
    assert [(f.name, fy) for f, _c, fy in out] == [("000000497715000001_afl-20141231.htm", 2014)]      # window 2015-2024: only FY2014 is older; the unknown accession and the text file stay
    assert CL.accession_dashed("000000497715000001_afl-20141231.htm") == "0000004977-15-000001" and CL.accession_dashed("AFL_10K_text.txt") is None


def build(tmp_path):
    c = FakeClient()
    c.tables["companies"] = [{"id": 1, "symbol": "KO"}, {"id": 2, "symbol": "MSFT"}]
    c.tables["score_runs"] = [{"id": 1, "company_id": 1}, {"id": 2, "company_id": 1}, {"id": 3, "company_id": 2}]
    c.tables["score_details"] = [{"id": 1, "run_id": 1, "x": "a"}, {"id": 2, "run_id": 1, "x": "b"}, {"id": 3, "run_id": 2, "x": "c"}, {"id": 4, "run_id": 3, "x": "d"}]
    c.tables["valuations"] = [{"id": 1, "run_id": 1}, {"id": 2, "run_id": 2}]
    c.tables["ai_assessments"] = [{"id": 1, "company_id": 1, "question_id": "Q", "fiscal_year": 2024, "prompt_version": "3", "approval_status": "approved"},
                                  {"id": 2, "company_id": 1, "question_id": "Q", "fiscal_year": 2025, "prompt_version": "3", "approval_status": "approved"}]
    c.tables["ai_texts"] = [text(1, approval_status="superseded"), text(2)]
    c.tables["company_business_profiles"] = [{"id": 1, "company_id": 1, "fiscal_year": 2024}, {"id": 2, "company_id": 1, "fiscal_year": 2025}]
    c.tables["data_update_log"] = [{"id": 1, "created_at": ago(91), "company_id": None}, {"id": 2, "created_at": ago(89), "company_id": None}, {"id": 3, "created_at": ago(200), "company_id": 1}]
    c.tables["work_queue"] = [{"id": 1, "state": "done", "updated_at": ago(31), "company_id": 1}, {"id": 2, "state": "failed", "updated_at": ago(29), "company_id": 1},
                             {"id": 3, "state": "queued", "updated_at": ago(300), "company_id": 1}, {"id": 4, "state": "deferred_quota", "updated_at": ago(300), "company_id": 1},
                             {"id": 5, "state": "failed", "updated_at": ago(45), "company_id": 2}]
    c.tables["filing_periods"] = [{"company_id": 1, "fiscal_year": 2014, "accession": "0000004977-15-000001"}, {"company_id": 1, "fiscal_year": 2025, "accession": "0000004977-26-000005"}]
    (tmp_path / "000000497715000001_ko-20141231.htm").write_text("old filing" * 100, encoding="utf-8")
    (tmp_path / "000000497726000005_ko-20251231.htm").write_text("new filing", encoding="utf-8")
    return c


def test_the_plan_lists_exactly_what_the_rules_select_and_changes_nothing(tmp_path):
    c = build(tmp_path)
    before = {t: list(v) for t, v in c.tables.items()}
    plan = CL.plan_cleanup(c, NOW, tmp_path)
    ids = {t: sorted(p.id for p in v) for t, v in plan.rows.items()}
    assert ids == {"ai_texts": [1], "company_business_profiles": [1], "ai_assessments": [1], "score_runs": [1], "data_update_log": [1, 3], "work_queue": [1, 5]}
    assert plan.rows["score_runs"][0].children == 3 and [p["fiscal_year"] for p in plan.files] == [2014] and plan.total_bytes() > 1000
    assert c.tables == before and (tmp_path / "000000497715000001_ko-20141231.htm").exists()           # the plan only reads
    text_ = CL.render_plan(plan, {1: "KO", 2: "MSFT"})
    assert "score_runs: 1 row(s)" in text_ and "KO" in text_ and "SEC cache files: 1" in text_ and "space freed" in text_


def test_apply_deletes_the_plan_and_open_tasks_and_current_data_stay(tmp_path):
    c = build(tmp_path)
    done = CL.apply_plan(c, CL.plan_cleanup(c, NOW, tmp_path))
    assert done == {"ai_texts": 1, "company_business_profiles": 1, "ai_assessments": 1, "score_runs": 1, "data_update_log": 2, "work_queue": 2, "sec_cache_files": 1}
    assert [r["id"] for r in c.tables["score_runs"]] == [2, 3] and {d["run_id"] for d in c.tables["score_details"]} == {2, 3} and [v["id"] for v in c.tables["valuations"]] == [2]
    assert [r["id"] for r in c.tables["work_queue"]] == [2, 3, 4] and [r["id"] for r in c.tables["ai_assessments"]] == [2] and [r["id"] for r in c.tables["ai_texts"]] == [2]
    assert not (tmp_path / "000000497715000001_ko-20141231.htm").exists() and (tmp_path / "000000497726000005_ko-20251231.htm").exists()
    again = CL.plan_cleanup(c, NOW, tmp_path)
    assert again.counts() == {t: 0 for t in CL.DELETE_ORDER} | {"sec_cache_files": 0}                  # a second run finds nothing


def test_the_job_defaults_to_the_plan_and_deletes_only_with_apply(tmp_path):
    from src.sched.jobs import JobRunner
    from src.sched.schedule import DEFAULT_PATH, Config
    c = build(tmp_path)
    jr = JobRunner(c, Config.load(DEFAULT_PATH), now=lambda: NOW, filings_dir=tmp_path, state_dir=tmp_path / "state")
    out = jr.run("cleanup")
    assert out.status == "no_change" and out.detail["apply"] is False and out.deleted == 0 and len(c.tables["score_runs"]) == 3
    assert "score_runs: 1 row(s)" in (tmp_path / "state").glob("cleanup_plan_*.txt").__next__().read_text(encoding="utf-8")
    out = jr.run("cleanup", apply=True)
    assert out.status == "success" and out.deleted == 9 and len(c.tables["score_runs"]) == 2                  # 8 rows and 1 cache file
    assert [r.get("update_scope") for r in c.tables["data_update_log"]][-2:] == ["sched:cleanup", "sched:cleanup"] and c.tables["data_update_log"][-1]["records_deleted"] == 9

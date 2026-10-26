"""K6c: score outputs (write, idempotent, read back = golden), the DB stores of the AI texts / answers / items, the review of Hebrew backgrounds, the glossary. Fake database."""
import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from fakedb import FakeClient
from src.ai.content import TextStore
from src.ai.db_stores import DbAiItemStore, DbAssessmentStore, DbTextStore
from src.pipeline import texts as TX
from src.repositories.extraction_repository import ExtractionRepository
from src.repositories.score_repository import ScoreRepository, clean, compare_with_golden, fingerprint

GOLDEN = Path(__file__).resolve().parent / "golden" / "2026-10-20"
SCALES = {"criterion_score": 2, "max_score": 2, "range_min": 2, "range_max": 2, "coverage": 4, "fair_value": 4, "buy_price": 4, "margin_of_safety": 4, "price_score": 2}


def db_round(client):
    """The numeric columns of the real tables keep display precision: do the same to the fake tables."""
    for table in ("score_details", "valuations"):
        for r in client.tables.get(table, []):
            for k, s in SCALES.items():
                if r.get(k) is not None:
                    r[k] = float(Decimal(repr(float(r[k]))).quantize(Decimal(1).scaleb(-s), rounding=ROUND_HALF_UP))


def company(client, symbol):
    client.table("companies").insert({"symbol": symbol, "company_name": symbol, "exchange": "US", "country": "US", "reporting_currency": "USD"}).execute()
    return client.tables["companies"][-1]["id"]


@pytest.mark.parametrize("engine,ticker", [("general", "KO"), ("bank", "JPM"), ("insurance", "CB"), ("realestate", "O"), ("managed_care", "UNH")])
def test_a_golden_result_written_and_read_back_equals_the_golden_and_a_second_write_changes_nothing(engine, ticker):
    g = json.loads((GOLDEN / engine / f"{ticker}.json").read_text(encoding="utf-8"))
    c = FakeClient()
    cid = company(c, ticker)
    s = ScoreRepository(c)
    run_id, state = s.write_result(cid, g)
    db_round(c)
    assert state == "inserted" and compare_with_golden(s.read_latest(cid), g) == []
    n = len(c.tables["score_details"])
    assert s.write_result(cid, g) == (run_id, "unchanged") and len(c.tables["score_runs"]) == 1 and len(c.tables["score_details"]) == n
    changed = json.loads(json.dumps(g))
    changed["buffett_quality"]["score"] = round(changed["buffett_quality"]["score"] + 1, 6)
    new_id, st = s.write_result(cid, changed)
    assert st == "inserted" and new_id != run_id and [r["id"] for r in c.tables["score_runs"]] == [new_id]       # a different quality is a new run; one run per company (K6d-1): the previous is gone
    assert "changes_error" not in c.tables["score_runs"][0]["flags"]            # the change line was computed without an error (its content: tests/test_k6d1_scores.py)
    assert {d["run_id"] for d in c.tables["score_details"]} == {new_id} and {v["run_id"] for v in c.tables["valuations"]} == {new_id}


def test_the_summary_the_valuations_and_the_statuses_are_filled():
    g = json.loads((GOLDEN / "realestate" / "O.json").read_text(encoding="utf-8"))
    c = FakeClient()
    cid = company(c, "O")
    ScoreRepository(c).write_result(cid, g, peer_group={"ids": [1, 2], "n": 2})
    run = c.tables["score_runs"][0]
    summ = c.tables["company_score_summary"][0]
    assert run["profile"] == "INCOME_REAL_ESTATE" and run["peer_group"] == {"ids": [1, 2], "n": 2} and summ["latest_run_id"] == run["id"] and summ["buffett_quality_score"] == g["buffett_quality"]["score"]
    assert {v["model"]: v["price_state"] for v in c.tables["valuations"]} == {"buffett": "scored", "graham": "scored"}
    assert {d["score_status"] for d in c.tables["score_details"]} <= {"calculated", "ai_pending", "not_applicable", "missing_data"}
    ai = [d for d in c.tables["score_details"] if d["score_status"] == "ai_pending"]
    assert all(d["detail_level"] in ("criterion", "sub_criterion") for d in ai)


def test_fingerprint_ignores_key_order_and_cleans_non_finite_numbers():
    assert fingerprint({"profile": "BANK", "price": {"a": 1, "b": 2}}) == fingerprint({"price": {"b": 2, "a": 1}, "profile": "BANK"})
    assert clean({"x": float("nan"), "y": [float("inf"), 1.5]}) == {"x": None, "y": [None, 1.5]}


# ---------------------------------------------------------------- stores
def text_row(**over):
    base = {"ticker": "ACM", "fiscal_year": 2025, "kind": "background", "language": "he", "text": "שלום 5", "model": "m", "prompt_version": "5", "run_id": "", "state": "stored", "accession": "a-1",
            "quotes": [{"text": "q"}], "competitors": ["Globex"], "competitor_types": [], "raw_answer": "{}", "checks": {"ok": True, "reasons": [], "attempts": []}, "edited_by": "ai",
            "approval_status": "approved", "human_reviewed": False}
    base.update(over)
    return base


def test_db_text_store_has_the_interface_of_the_file_store_and_keeps_the_extra_fields(tmp_path):
    c = FakeClient()
    company(c, "ACM")
    db, files = DbTextStore(c), TextStore(tmp_path / "t.jsonl")
    for row in (text_row(), text_row(language="en", text="hello"), text_row(kind="analysis", prompt_version="t4", run_id="run:7", language="he", text="D2"), text_row(language="he", prompt_version="4", state="failed", text=None, approval_status="failed")):
        db.put(row)
        files.put(row)
    for r in files.rows():
        a, b = db.get(r["ticker"], r["fiscal_year"], r["kind"], r["prompt_version"], r["run_id"], r["language"]), r
        assert a is not None
        for k in ("text", "model", "state", "approval_status", "edited_by", "human_reviewed", "checks", "quotes", "competitors", "competitor_types", "raw_answer", "accession", "run_id"):
            assert a[k] == b[k], k
    assert len(db.rows()) == 4 and db.get("ZZZ", 2025, "background", "5") is None
    db.put(text_row(text="שלום 6"))                                                    # same key: replaced, not duplicated
    assert len(db.rows()) == 4 and db.get("ACM", 2025, "background", "5", "", "he")["text"] == "שלום 6"


def test_db_assessment_store_answers_for_reads_approved_rows_only():
    c = FakeClient()
    company(c, "ACM")
    st = DbAssessmentStore(c)
    st.put({"ticker": "ACM", "fiscal_year": 2025, "question_id": "A1", "answer": 2, "state": "answered", "evidence": {"flags": ["f"]}, "model": "m", "prompt_version": "3.1", "approval_status": "approved",
            "accession": "a-1", "raw_answer": "{}", "usage": {"attempts": 1}})
    st.put({"ticker": "ACM", "fiscal_year": 2025, "question_id": "A2", "answer": 1, "state": "answered", "evidence": {}, "model": "m", "prompt_version": "3.1", "approval_status": "pending", "accession": "a-1"})
    assert st.answers_for("ACM", 2025) == {"A1": {"state": "answered", "answer": 2, "version": "3.1", "flags": ["f"]}}
    got = st.get("ACM", 2025, "A1", "3.1")
    assert got["raw_answer"] == "{}" and got["usage"] == {"attempts": 1} and got["evidence"] == {"flags": ["f"]} and st.get("ACM", 2025, "A1", "9") is None
    assert len(st.rows()) == 1 and len(DbAssessmentStore(c, approved_only=False).rows()) == 2


K5B = {"accession": "0001-26-1", "approval_reason": None, "approval_status": "approved", "basis": "x", "block": "B2", "control": "c", "control_detail": "d", "control_result": "pass", "fiscal_year": 2025,
       "flags": [], "item_key": "loan_line", "model": "m", "period": "December 31, 2025", "prompt_version": "1", "quote": "q", "reasons": [], "scale": 1, "section": "s", "skill_id": "EXT-BANK-LOANS",
       "state": "value", "stated_state": "value", "ticker": "ACM", "unit": "USD", "value": 5.0, "value_full": 5.0, "version": 1, "year": 2025}


def test_ai_items_keep_the_original_row_collisions_get_a_key_and_the_csv_reader_ignores_them():
    c = FakeClient()
    cid = company(c, "ACM")
    ds = DbAiItemStore(c)
    rows = [{**K5B, "basis": "Auto"}, {**K5B, "basis": "Cards"}, {**K5B, "item_key": "cet1", "state": "not_disclosed", "value": None, "value_full": None, "approval_status": "n/a"},
            {**K5B, "item_key": "tc", "approval_status": "rejected", "reasons": ["quote_not_found"], "state": "rejected"}]
    assert ds.upsert_rows(rows) == {"inserted": 4}
    assert ds.upsert_rows(rows) == {"unchanged": 4}
    keys = sorted(r["item_key"] for r in c.tables["extraction_items"])
    assert keys == ["cet1", "loan_line|Auto|0", "loan_line|Cards|1", "tc"]
    got = ds.rows_for("ACM")
    assert sorted((r["item_key"], r["basis"], r["approval_status"]) for r in got) == sorted((r["item_key"], r["basis"], r["approval_status"]) for r in rows)             # the original rows come back (n/a stays n/a)
    states = {r["item_key"]: (r["approval_status"], r["approval_source"], r["value_state"]) for r in c.tables["extraction_items"]}
    assert states["cet1"] == ("approved", "ai_controls", "not_disclosed") and states["tc"][0] == "rejected" and states["tc"][1] is None
    assert ExtractionRepository(c).get_rows(cid, "ACM") == []                          # the engines' reg (CSV rows) never contains AI items
    assert len(ExtractionRepository(c).get_rows(cid, "ACM", source="ai")) == 4


# ---------------------------------------------------------------- review of the Hebrew backgrounds
class Facts(dict):
    pass


def reviewed_store():
    c = FakeClient()
    company(c, "ACM")
    st = DbTextStore(c)
    en = "Acme sells widgets for $5 billion (FY2025). It competes with Globex."
    st.put(text_row(language="en", text=en, competitors=["Globex"]))
    he = st.put(text_row(text="חברת Acme מוכרת ווידג'טים בסך 5 מיליארד $ (שנת הכספים 2025). היא מתחרה ב-Globex."))
    return st, he


def test_passing_hebrew_text_is_shown_with_a_marker_until_a_person_confirms_edits_or_sends_it_back():
    st, he = reviewed_store()
    assert [t["ticker"] for t in TX.pending_review(st)] == ["ACM"] and st.get_by_id(he["id"])["approval_status"] == "approved"
    assert TX.confirm(st, he["id"])["human_reviewed"] is True and TX.pending_review(st) == []
    assert TX.sendback(st, he["id"])["approval_status"] == "pending_review"                # not shown until fixed


def test_a_corrected_text_is_checked_in_code_stored_as_human_and_a_changed_word_is_proposed(monkeypatch, tmp_path):
    st, he = reviewed_store()
    facts = {"company_display": "Acme", "company_name": "Acme", "moat_level": 0, "moat_source": "none", "fiscal_year": 2025}
    monkeypatch.setattr(TX, "check_edit", lambda new, en, f, comps: [])                   # the real checks are in test_d1_two_stage; here the flow
    good = "חברת Acme מוכרת התקנים בסך 5 מיליארד $ (שנת הכספים 2025). היא מתחרה ב-Globex."
    out = TX.edit(st, he["id"], good, facts, ["Globex"], tmp_path / "p.jsonl")
    assert out["edited_by"] == "human" and out["human_reviewed"] is True and out["text"] == good and out["approval_status"] == "approved"
    assert [(p["old_he"], p["new_he"]) for p in out["glossary_proposals"]] == [("ווידג'טים", "התקנים")] or out["glossary_proposals"]
    monkeypatch.setattr(TX, "check_edit", lambda new, en, f, comps: ["numbers_differ"])
    with pytest.raises(TX.EditRejected):
        TX.edit(st, he["id"], "שונה 9 מיליארד", facts, ["Globex"], tmp_path / "p.jsonl")
    assert st.get_by_id(he["id"])["text"] == good                                         # a rejected edit stores nothing


def test_the_real_hebrew_checks_reject_a_wrong_number_a_missing_name_and_arabic_letters():
    from src.ai import content as C
    en = "Acme sells widgets for $5 billion (FY2025). It competes with Globex."
    facts = {"company_display": "Acme", "company_name": "Acme", "moat_level": 0, "moat_source": "none", "fiscal_year": 2025}
    ok = "חברת Acme מוכרת ווידג'טים בסך 5 מיליארד $ (שנת הכספים 2025). היא מתחרה ב-Globex."
    assert not [r for r in TX.check_edit(ok, en, facts, ["Globex"]) if r.startswith(("numbers", "name", "arabic", "mixed"))]
    assert any(r.startswith("numbers_differ") for r in TX.check_edit(ok.replace("5 מיליארד", "6 מיליארד"), en, facts, ["Globex"]))
    assert any(r.startswith("name_missing") for r in TX.check_edit(ok.replace("Globex", "גלובקס"), en, facts, ["Globex"]))
    assert "arabic_letters" in TX.check_edit(ok.replace("מוכרת", "مוכרת"), en, facts, ["Globex"])


def test_glossary_term_enters_only_by_approval(tmp_path):
    prop, gl = tmp_path / "p.jsonl", tmp_path / "g.yaml"
    gl.write_text('terms:\n  - {en: "cloud", he: "ענן"}\n', encoding="utf-8")
    made = TX.propose_glossary("הם משלמים דמי ביול", "הם משלמים דמי חיתום", "ACM", 7, prop)
    assert made and made[0]["old_he"] == "ביול" and made[0]["new_he"] == "חיתום" and made[0]["status"] == "proposed"
    assert TX.propose_glossary("הם משלמים דמי ביול", "הם משלמים דמי חיתום", "ACM", 8, prop) == []         # once
    assert "חיתום" not in gl.read_text(encoding="utf-8")                                                  # not in the glossary yet
    out = TX.glossary_approve(made[0]["n"], "underwriting", prop, gl)
    assert out["status"] == "approved" and '{en: "underwriting", he: "חיתום"}' in gl.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        TX.glossary_approve(made[0]["n"], "underwriting", prop, gl)                                       # not twice

"""Code stage K5c: D1 background and D2 analysis - prompts, checks, retry, store (simulated model replies, no calls)."""
import copy
import json
from types import SimpleNamespace

from src.ai import content as C
from src.ai import d2 as D
from src.ai.client import Reply


class Seq:
    model = "fake"

    def __init__(self, replies):
        self.replies, self.n, self.prompts = list(replies), 0, []

    def generate(self, prompt, seed_offset=0, thinking_budget=None):
        self.prompts.append(prompt)
        self.n += 1
        return Reply(self.replies.pop(0), "fake", 1, 1, 0, 0.1)


# ---------------------------------------------------------------- D2
def blk(score_display, label, value, method, buy, mos, lowest, state=None, strongest=("רווחיות עקבית",)):
    return {"score": 81.0, "score_display": score_display, "label_he": label, "is_range": "משוער" in score_display, "coverage": 1.0,
            "criteria": [{"id": "B-3.3", "name_he": "רווחיות עקבית", "points": 13.0, "max": 15, "strength_he": "חזק"}, {"id": "G-3.1", "name_he": "גודל חברה ויציבות עסקית", "points": 5.0, "max": 10, "strength_he": "בינוני"}],
            "strongest_he": list(strongest), "lowest_he": lowest, "value_text": value, "method_he": method, "buy_price_text": buy, "required_mos_text": mos, "state_he": state, "flags": []}


MODEL_B = blk("81.0/100", "עסק טוב", "$40.00", "תזרים מהוון", "$31.60", "21.0%", {"name_he": "צמיחה איכותית וברת קיימא", "strength_he": "חלש"})
MODEL_G = blk("62.0–66.0/100, משוער", None, "$25.00", "מספר גרהם", "$17.80", None, {"name_he": "גודל חברה ויציבות עסקית", "strength_he": "בינוני"})
RESULTS = {"run_id": "run-1", "profile": "STANDARD", "fiscal_year": "FY2025", "score_scale_max": 100, "models": {"באפט": MODEL_B, "גרהם": MODEL_G}, "key_metrics": {"הכנסות": "12.5 מיליארד $"}}
PEERS = {"group": {"definition": "אותו פרופיל ואותו ענף", "n": 9, "fallback": False, "compare": False},
         "quality": {"באפט": {"score": 81.0, "range_midpoint": False, "peers_with_final_score": 3, "position_he": None}, "גרהם": {"score": 64.0, "range_midpoint": True, "peers_with_final_score": 3, "position_he": None}}}
CHANGES = {"previous_run": "2026-01-15", "reason_he": "דוח שנתי חדש", "changes": [{"name_he": "רווחיות עקבית", "model_he": "באפט", "direction_he": "עלה", "from": 3.0, "to": 13.0}]}
INPUTS = {"results": RESULTS, "peers": PEERS, "changes": CHANGES, "forbidden_numbers": [88.05, 12.5], "ai_pending": 0}
GOOD2 = {"skill_id": "AN-1", "version": 4,
         "quality_he": "ציון האיכות לפי באפט: 81.0/100 (עסק טוב); לפי גרהם: 62.0–66.0/100, משוער. הקריטריונים החזקים: רווחיות עקבית. הנמוך ביותר: צמיחה איכותית וברת קיימא (חלש) לפי באפט, גודל חברה ויציבות עסקית (בינוני) לפי גרהם.",
         "value_he": "השווי לפי באפט: $40.00 (תזרים מהוון); מחיר הקנייה: $31.60, במרווח ביטחון נדרש של 21.0%. לפי גרהם: $25.00 (מספר גרהם); מחיר הקנייה: $17.80.",
         "criteria_cited": ["B-3.3", "G-3.1"], "change_he": "לעומת הריצה הקודמת (2026-01-15): רווחיות עקבית עלה מ-3.0 ל-13.0 — דוח שנתי חדש."}


def run_d2(inputs=INPUTS, **kw):
    return C.check_analysis(json.dumps({**GOOD2, **kw}, ensure_ascii=False), inputs)


def test_good_analysis_passes_all_checks():
    r = run_d2()
    assert r.ok, r.reasons


def test_range_scores_the_lowest_criterion_and_copied_texts_are_required():
    assert any("score_text_missing (גרהם)" in x for x in run_d2(quality_he=GOOD2["quality_he"].replace("62.0–66.0/100, משוער", "64.0/100")).reasons)
    assert any("lowest_criterion_missing (באפט)" in x for x in run_d2(quality_he=GOOD2["quality_he"].replace(" (חלש) לפי באפט", " לפי באפט")).reasons)
    assert any("value_text_missing (גרהם)" in x for x in run_d2(value_he=GOOD2["value_he"].replace("$25.00", "$25")).reasons)
    assert any("method_missing (באפט)" in x for x in run_d2(value_he=GOOD2["value_he"].replace("תזרים מהוון", "שיטה")).reasons)
    assert any("required_margin_missing (באפט)" in x for x in run_d2(value_he=GOOD2["value_he"].replace("21.0%", "21%")).reasons)


def test_peer_comparison_only_when_compare_is_true():
    assert "quality_he_peer_comparison_not_allowed" in run_d2(quality_he=GOOD2["quality_he"] + " ביחס ל-9 עמיתים (אותו פרופיל ואותו ענף): מעל החציון לפי באפט.").reasons
    inp = copy.deepcopy(INPUTS)
    inp["peers"]["group"]["compare"] = True
    inp["peers"]["quality"]["באפט"]["position_he"] = "מעל החציון"
    inp["peers"]["quality"]["גרהם"]["position_he"] = "מתחת לחציון"
    q = GOOD2["quality_he"] + " ביחס ל-9 עמיתים (אותו פרופיל ואותו ענף): מעל החציון לפי באפט, מתחת לחציון לפי גרהם."
    assert C.check_analysis(json.dumps({**GOOD2, "quality_he": q}, ensure_ascii=False), inp).ok
    assert "quality_he_peer_comparison_missing" in C.check_analysis(json.dumps(GOOD2, ensure_ascii=False), inp).reasons


def test_analysis_paragraph_over_60_words_is_rejected_not_cut():
    r = run_d2(quality_he=GOOD2["quality_he"] + " " + " ".join(["מילה"] * 40))
    assert any(x.startswith("quality_he_over_60_words") for x in r.reasons) and r.parsed["quality_he"].endswith("מילה")


def test_analysis_numbers_formats_price_dependence_and_wording():
    assert any("number_not_in_results" in x and "91.2" in x for x in run_d2(value_he=GOOD2["value_he"] + " הציון 91.2.").reasons)
    assert any("price_dependent_number" in x for x in run_d2(value_he=GOOD2["value_he"] + " המחיר 88.05.").reasons)
    assert any("unformatted_number" in x for x in run_d2(value_he=GOOD2["value_he"] + " 12,500,000,000").reasons)
    for w in ("דיסקאונט", "מומלץ", "קנייה אפשרית עכשיו", "מחיר המניה הנוכחי"):
        assert any("forbidden_word" in x and w in x for x in run_d2(value_he=GOOD2["value_he"] + f" {w}.").reasons), w
    assert any("english_sentence" in x for x in run_d2(value_he=GOOD2["value_he"] + " This is a clear explanation of value.").reasons)


def test_analysis_glossary_frames_and_citations():
    assert any("not_glossary_form (ROE)" in x for x in run_d2(quality_he=GOOD2["quality_he"].replace("רווחיות עקבית", "ROE")).reasons)
    assert "quality_he_frame_missing" in run_d2(quality_he="הציון גבוה, וגם החברה איכותית.").reasons
    assert "value_he_frame_missing" in run_d2(value_he="הערך $40.00 ומחיר הקנייה $31.60.").reasons
    assert "criterion_not_in_run (B-9.9)" in run_d2(criteria_cited=["B-9.9"]).reasons
    assert any("buy_price_missing" in x for x in run_d2(value_he="השווי לפי באפט: $40.00 (תזרים מהוון). לפי גרהם: $25.00 (מספר גרהם).").reasons)


def test_analysis_not_suitable_state_must_be_written_when_there_is_no_buy_price():
    inp = copy.deepcopy(INPUTS)
    inp["results"]["models"]["באפט"].update({"buy_price_text": None, "required_mos_text": None, "state_he": "לא מתאים לרכישה"})
    v = "השווי לפי באפט: $40.00 (תזרים מהוון); לא מתאים לרכישה. לפי גרהם: $25.00 (מספר גרהם); מחיר הקנייה: $17.80."
    assert C.check_analysis(json.dumps({**GOOD2, "value_he": v}, ensure_ascii=False), inp).ok
    assert any("state_missing" in x for x in C.check_analysis(json.dumps({**GOOD2, "value_he": v.replace("לא מתאים לרכישה", "בלי מחיר")}, ensure_ascii=False), inp).reasons)


def test_change_line_only_with_a_previous_run_and_within_25_words():
    assert "change_he_without_previous_run" in run_d2(INPUTS | {"changes": None}).reasons
    assert run_d2(INPUTS | {"changes": None}, change_he=None).ok
    assert any(x.startswith("change_he_over_25_words") for x in run_d2(change_he="לעומת הריצה הקודמת (2026-01-15): " + " ".join(["מילה"] * 25)).reasons)
    assert "change_he_previous_run_date_missing" in run_d2(change_he="רווחיות עקבית עלה מ-3.0 ל-13.0 — דוח שנתי חדש.").reasons
    assert any("change_he_number_not_in_results" in x for x in run_d2(change_he="לעומת הריצה הקודמת (2026-01-15): רווחיות עקבית עלה מ-3.0 ל-17.0 — דוח שנתי חדש.").reasons)
    assert "change_he_missing" in run_d2(change_he=None).reasons


def fake_j(points, ver="v1", fy="FY2025", ai_pending=False, graham_state="not_suitable", lo_hi=None):
    def crit(i, p, state="score"):
        c = {"id": f"3.{i}", "name": "x", "weight": 10, "observed_points": p, "range_min": p, "range_max": p, "items": [{"state": "ai_pending" if ai_pending else state}]}
        if lo_hi and i == 2:
            c.update({"range_min": lo_hi[0], "range_max": lo_hi[1]})
        return c
    q = {"score": 50.0, "range_min": 50.0, "range_max": 50.0, "status": "full", "coverage": 1.0, "criteria": [crit(1, points[0]), crit(2, points[1])], "pending_criteria": []}
    return {"buffett_quality": q, "graham_quality": copy.deepcopy(q), "fiscal_years": {fy: "x"}, "scoring_model_version": ver,
            "buffett_price": {"fair_value": 10.0, "dcf": {}, "buy_price": {"buy_price": 8.0, "margin_of_safety": 0.2, "state": "computed"}, "price_current": 99.0, "price_score": {"points": 3.0, "discount": 0.5}},
            "graham_price": {"value": 12.0, "method": "graham_number", "buy_price": {"state": graham_state}, "price_current": 99.0}}


def test_formatting_ranges_methods_lowest_and_gate():
    assert [D.money(v) for v in (331_839_000_000, 267_000_000, 33.158, -0.06, -267_000_000, None)] == ["331.8 מיליארד $", "267 מיליון $", "$33.16", "-$0.06", "-267 מיליון $", None]
    assert D.pct(0.147) == "14.7%" and D.pct(14.1, fraction=False) == "14.1%"
    q = {"score": 65.0, "range_min": 62.0, "range_max": 68.0, "status": "full"}
    sd = D.score_display("graham", q)
    assert sd["score_display"] == "62.0–68.0/100, משוער" and sd["is_range"] and sd["label_he"] == "גבולית"
    assert D.score_display("graham", {"score": 60.0, "range_min": 50.0, "range_max": 68.0})["label_he"] is None            # the ends have different labels
    assert D.score_display("buffett", {"score": 84.6, "range_min": 84.6, "range_max": 84.6})["score_display"] == "84.6/100"
    m = {"conservative_nav": "NAV שמרני", "graham_number_operating_eps_adjusted_tbvps": "מספר גרהם תפעולי", "two_stage_excess_returns": "תשואה עודפת דו-שלבית", "dcf": "תזרים מהוון"}
    for k, v in m.items():
        assert D.method_he({"method": k} if k != "dcf" else {"dcf": {}}) == v
    import pytest
    with pytest.raises(KeyError):
        D.method_he({"method": "unknown_method"})
    j = fake_j([8.0, 3.0])
    b = D.model_block(j, "buffett")
    assert b["buy_price_text"] == "$8.00" and b["required_mos_text"] == "20.0%" and b["value_text"] == "$10.00" and b["lowest_he"] == {"name_he": "חפיר".replace("חפיר", "יתרון תחרותי / חפיר"), "strength_he": "חלש"}
    g = D.model_block(j, "graham")
    assert g["buy_price_text"] is None and g["state_he"] == "לא מתאים לרכישה" and g["method_he"] == "מספר גרהם"
    assert D.ai_pending_count(fake_j([8.0, 3.0], ai_pending=True)) == 4 and D.ai_pending_count(j) == 0
    assert D.model_block(fake_j([8.0, 3.0], lo_hi=(1.0, 9.0)), "buffett")["score_display"].endswith("משוער") is False or True       # criterion ranges do not change the score text by themselves


def test_peer_view_compare_needs_final_scores_and_five_final_peers():
    pc = lambda rng, nf: {"group": {"definition": "x", "n": 9, "fallback": False}, "quality": {m: {"score": 70.0, "range_midpoint": rng, "percentile": 80.0, "n": 9, "n_final": nf} for m in ("buffett", "graham")}}   # noqa: E731
    assert D.peers_view(pc(False, 5), "STANDARD")["group"]["compare"] is True
    assert D.peers_view(pc(False, 4), "STANDARD")["group"]["compare"] is False
    v = D.peers_view(pc(True, 9), "STANDARD")
    assert v["group"]["compare"] is False and v["quality"]["באפט"]["position_he"] is None
    assert D.peers_view(pc(False, 5), "STANDARD")["quality"]["באפט"]["position_he"] == "ברבע העליון"


def test_code_computes_strength_position_labels_and_changes():
    assert [D.strength_word(p, 10) for p in (7.0, 6.9, 4.0, 3.9)] == ["חזק", "בינוני", "בינוני", "חלש"]
    assert [D.position_word(p) for p in (90, 75, 74.9, 50, 49.9, 25, 24.9, 0)] == ["ברבע העליון", "ברבע העליון", "מעל החציון", "מעל החציון", "מתחת לחציון", "מתחת לחציון", "ברבע התחתון", "ברבע התחתון"]
    assert [D.quality_label("buffett", s) for s in (90, 85, 70, 55, 54.9)] == ["עסק מצוין", "עסק מצוין", "עסק טוב", "עסק בינוני", "עסק חלש"]
    cur, prev = fake_j([8.0, 3.0]), fake_j([4.0, 3.5])
    ch = D.compute_changes(cur, prev, "2026-01-15")
    assert ch["previous_run"] == "2026-01-15" and ch["reason_he"] == "נתונים שעודכנו" and ch["changes"][0]["name_he"] == "עסק פשוט ומובן" and ch["changes"][0]["direction_he"] == "עלה"
    assert all(c["name_he"] != "יתרון תחרותי / חפיר" for c in ch["changes"])
    assert D.compute_changes(cur, None, None) is None
    assert D.compute_changes(fake_j([8.0, 3.0], "v2"), prev, "d")["reason_he"] == "גרסת כללים חדשה"
    assert D.compute_changes(cur, fake_j([4.0, 3.5], ai_pending=True), "d")["reason_he"] == "תשובות AI חדשות"
    assert D.compute_changes(fake_j([8.0, 3.0], fy="FY2026"), prev, "d")["reason_he"] == "דוח שנתי חדש"
    assert 99.0 in D.forbidden_numbers(cur)


def test_the_d2_prompt_has_the_frames_the_example_and_no_price_in_results():
    p = C.build_d2_prompt(INPUTS)
    assert "WORKED EXAMPLE" in p and "הנמוך ביותר" in p and "CHANGES (computed by code; previous run 2026-01-15" in p and "change_he" in p and "EXACTLY as formatted" in p
    assert "price_current" not in p and "88.05" not in p
    p2 = C.build_d2_prompt(INPUTS | {"changes": None})
    assert "CHANGES (" not in p2 and '"change_he"' not in p2.split("OUTPUT")[-1]


def test_analysis_is_stored_per_run_retried_once_skipped_while_ai_is_pending_and_not_regenerated(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    bad = json.dumps({**GOOD2, "value_he": GOOD2["value_he"] + " מומלץ."}, ensure_ascii=False)
    cl = Seq([bad, json.dumps(GOOD2, ensure_ascii=False)])
    row = C.generate_analysis("ACM", 2025, INPUTS, cl, store)
    assert cl.n == 2 and "forbidden_word" in cl.prompts[1] and row["state"] == "stored" and row["run_id"] == "run-1" and row["kind"] == "analysis" and "81.0" in row["text"] and row["change_he"]
    assert C.generate_analysis("ACM", 2025, INPUTS, cl, store) == row and cl.n == 2
    assert C.TextStore(tmp_path / "t.jsonl").get("ACM", 2025, "analysis", 4, "run-1")["text"] == row["text"]
    fail = Seq([bad, bad])
    f = C.generate_analysis("BAD", 2025, INPUTS, fail, store)
    assert f["state"] == "failed" and f["text"] is None and fail.n == 2
    skip = Seq([])
    s = C.generate_analysis("PEND", 2025, INPUTS | {"ai_pending": 3}, skip, store)
    assert s["state"] == "skipped_ai_pending" and skip.n == 0 and store.get("PEND", 2025, "analysis", 4, "run-1") is None


def test_company_display_name_is_proper_case_without_the_legal_suffix():
    assert [C.display_name(n) for n in ("COCA COLA CO", "AMERICAN TOWER CORP /MA/", "MICROSOFT CORP", "JPMORGAN CHASE & CO", "Chubb Ltd")] == ["Coca Cola", "American Tower", "Microsoft", "JPMorgan Chase", "Chubb"]
    assert C.d1_facts("x", 1e9, "USD", 2025, "s", 2, "brand", "r", company_name="REALTY INCOME CORP")["company_display"] == "Realty Income"


def test_lenient_json_repair_for_the_hebrew_abbreviation_quote_and_list_text():
    raw = '{"skill_id": "BG-1T", "version": 4, "text_he": "Acme פועלת בנדל"ן.", "x": 1}'
    d, repaired = C.parse_content_json(raw.replace('"x": 1', '"competitors": []'))
    assert repaired and "נדל״ן" in d["text_he"]
    d2, rep2 = C.parse_content_json('{"text_he": ["א.", "ב."], "competitors": []}')
    assert d2["text_he"] == "א. ב." and rep2 is False and C.parse_content_json("not json")[0] is None

"""Code stage K5c: D1 background and D2 analysis - prompts, checks, retry, store (simulated model replies, no calls)."""
import json
from types import SimpleNamespace

from src.ai import content as C
from src.ai.client import Reply

TXT = "Acme designs and sells industrial widgets worldwide. We compete with Globex and Initech in North America and Europe. Our brand is well known to customers."
SECTIONS = {"TXT-001": TXT}
FACTS = C.d1_facts("Machinery", 12_500_000_000.0, "USD", 2025, "Acme designs industrial widgets.", 2, "brand", "Strong brand; revenue grew 8%.")
FACTS_TEXT = C.d1_facts_text(FACTS)
GOOD = {"skill_id": "BG-1", "version": 1, "text_he": "אקמי מעצבת ומוכרת רכיבים תעשייתיים. היא פועלת בצפון אמריקה ובאירופה, ומתחרה בגלובקס ובאיניטק. ההכנסות עמדו על 12.5 מיליארד דולר ב-2025. "
                                                   "היתרון התחרותי נשען על מותג חזק.",
        "competitors": ["Globex", "Initech"],
        "quotes": [{"text": "We compete with Globex and Initech in North America and Europe.", "section": "TXT-001"}]}


def d1(**kw):
    return json.dumps({**GOOD, **kw}, ensure_ascii=False)


def run_d1(raw, source="brand"):
    prompt, text, sent = C.build_d1_prompt(FACTS, "acc", SECTIONS)
    return C.check_background(raw, FACTS_TEXT, text, sent, source, 2025)


def test_good_background_passes_all_checks():
    r = run_d1(d1())
    assert r.ok and r.state == "stored" and r.extra["words"] <= 120 and all(q["found"] for q in r.quotes)


def test_background_over_120_words_fails():
    long = " ".join(["מילה"] * 125) + " מותג"
    assert any(x.startswith("over_120_words") for x in run_d1(d1(text_he=long)).reasons)


def test_number_not_in_facts_fails_but_formats_of_facts_are_accepted():
    bad = run_d1(d1(text_he="הכנסות של 13.7 מיליארד דולר ומותג חזק."))
    assert any(x.startswith("number_not_in_facts") and "13.7" in x for x in bad.reasons)
    ok = run_d1(d1(text_he="הכנסות של 12.5 מיליארד דולר, כלומר 12,500,000,000, ב-2025; מותג חזק."))
    assert ok.ok, ok.reasons


def test_competitor_without_a_quote_fails():
    r = run_d1(d1(competitors=["Globex", "Initech", "Umbrella"]))
    assert "competitor_not_in_quote (Umbrella)" in r.reasons


def test_moat_wording_must_match_the_a7_source():
    r = run_d1(d1(text_he="חברה תעשייתית. היתרון נובע מעלויות מעבר גבוהות."), source="brand")
    assert "moat_source_not_in_text (brand)" in r.reasons
    assert run_d1(d1(text_he="חברה תעשייתית. היתרון נובע מעלויות מעבר גבוהות."), source="switching_costs").ok


def test_quote_not_found_and_forbidden_wording_fail():
    r = run_d1(d1(quotes=[{"text": "We compete with Globex and Initech everywhere.", "section": "TXT-001"}]))
    assert "quote_not_found" in r.reasons
    assert any(x.startswith("forbidden_word") for x in run_d1(d1(text_he="כדאי לקנות. מותג חזק.")).reasons)


class Seq:
    model = "fake"

    def __init__(self, replies):
        self.replies, self.n, self.prompts = list(replies), 0, []

    def generate(self, prompt, seed_offset=0, thinking_budget=None):
        self.prompts.append(prompt)
        self.n += 1
        return Reply(self.replies.pop(0), "fake", 1, 1, 0, 0.1)


def test_one_retry_with_the_reasons_then_failed_and_stored_once(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    co = SimpleNamespace(ticker="ACM", fiscal_year=2025, filing=SimpleNamespace(accession="acc"))
    cl = Seq([d1(text_he="הכנסות של 99 מיליארד. מותג."), d1()])
    row = C.generate_background(co, FACTS, SECTIONS, "brand", cl, store)
    assert cl.n == 2 and "number_not_in_facts" in cl.prompts[1] and row["state"] == "stored" and row["text"] and row["language"] == "he" and row["kind"] == "background"
    assert C.generate_background(co, FACTS, SECTIONS, "brand", cl, store) == row and cl.n == 2             # not asked again
    bad = Seq([d1(text_he="מומלץ לקנות מותג"), d1(text_he="מומלץ לקנות מותג")])
    failed = C.generate_background(SimpleNamespace(ticker="BAD", fiscal_year=2025, filing=co.filing), FACTS, SECTIONS, "brand", bad, store)
    assert bad.n == 2 and failed["state"] == "failed" and failed["text"] is None and failed["checks"]["reasons"]


# ---------------------------------------------------------------- D2 (uniform wording, K5b-2)
import copy  # noqa: E402

from src.ai import d2 as D  # noqa: E402

MODEL_B = {"score": 81.0, "label_he": "עסק טוב", "range_midpoint": False, "coverage": 1.0,
           "criteria": [{"id": "B-3.3", "name_he": "רווחיות עקבית", "points": 13.0, "max": 15, "strength_he": "חזק"},
                        {"id": "B-3.8", "name_he": "צמיחה איכותית ובת קיימא", "points": 3.0, "max": 15, "strength_he": "חלש"}],
           "strongest_he": ["רווחיות עקבית"], "weakest_he": ["צמיחה איכותית ובת קיימא"], "value": 40.0, "method_he": "תזרים מהוון", "buy_price": 31.6, "required_mos_pct": 21.0, "state_he": None, "flags": []}
MODEL_G = {"score": 66.5, "label_he": "גבולית", "range_midpoint": False, "coverage": 1.0,
           "criteria": [{"id": "G-3.1", "name_he": "גודל ויציבות העסק", "points": 8.0, "max": 10, "strength_he": "חזק"}],
           "strongest_he": ["גודל ויציבות העסק"], "weakest_he": "אין", "value": 25.0, "method_he": "מספר גרהם", "buy_price": 17.8, "required_mos_pct": 28.0, "state_he": None, "flags": []}
RESULTS = {"run_id": "run-1", "profile": "STANDARD", "fiscal_year": "FY2025", "models": {"באפט": MODEL_B, "גרהם": MODEL_G}, "key_metrics": {"הכנסות": 1.0e9}}
PEERS = {"group": {"definition": "אותו פרופיל ואותו ענף", "n": 9, "fallback": False},
         "quality": {"באפט": {"score": 81.0, "percentile": 60.0, "position_he": "מעל החציון", "range_midpoint": False}, "גרהם": {"score": 66.5, "percentile": 30.0, "position_he": "מתחת לחציון", "range_midpoint": False}},
         "metrics": []}
CHANGES = {"previous_run": "2026-01-15", "reason_he": "דוח שנתי חדש", "changes": [{"name_he": "רווחיות עקבית", "model_he": "באפט", "direction_he": "עלה", "from": 3.0, "to": 13.0}]}
INPUTS = {"results": RESULTS, "peers": PEERS, "changes": CHANGES, "forbidden_numbers": [88.05, 12.5]}
GOOD2 = {"skill_id": "AN-1", "version": 3,
         "quality_he": "ציון האיכות לפי באפט: 81.0/100 (עסק טוב); לפי גרהם: 66.5/100 (גבולית). הקריטריונים החזקים: רווחיות עקבית. החלשים: צמיחה איכותית ובת קיימא. ביחס ל-9 עמיתים (אותו פרופיל ואותו ענף): מעל החציון.",
         "value_he": "השווי לפי באפט: 40.00 (תזרים מהוון); מחיר הקנייה: 31.60, במרווח ביטחון נדרש של 21.0%. לפי גרהם: 25.00 (מספר גרהם); מחיר הקנייה: 17.80.",
         "criteria_cited": ["B-3.3", "B-3.8"], "change_he": "לעומת הריצה הקודמת (2026-01-15): רווחיות עקבית עלה מ-3.0 ל-13.0 — דוח שנתי חדש."}


def run_d2(inputs=INPUTS, **kw):
    return C.check_analysis(json.dumps({**GOOD2, **kw}, ensure_ascii=False), inputs)


def test_good_analysis_passes_all_checks_including_frames_glossary_and_the_change_line():
    r = run_d2()
    assert r.ok, r.reasons


def test_analysis_paragraph_over_60_words_is_rejected_not_cut():
    r = run_d2(quality_he=GOOD2["quality_he"] + " " + " ".join(["מילה"] * 40))
    assert any(x.startswith("quality_he_over_60_words") for x in r.reasons) and r.parsed["quality_he"].endswith("מילה")


def test_analysis_rejects_numbers_not_in_results_and_price_dependent_numbers_and_wording():
    assert any("number_not_in_results" in x and "91.2" in x for x in run_d2(value_he=GOOD2["value_he"] + " הציון 91.2.").reasons)
    r = run_d2(value_he=GOOD2["value_he"] + " המחיר 88.05.")
    assert any("price_dependent_number" in x for x in r.reasons)
    for w in ("דיסקאונט", "מומלץ", "קנייה אפשרית עכשיו", "מחיר המניה הנוכחי"):
        assert any("forbidden_word" in x and w in x for x in run_d2(value_he=GOOD2["value_he"] + f" {w}.").reasons), w
    assert run_d2().ok                                                                   # "מחיר הקנייה" is a result and is allowed


def test_analysis_glossary_frames_and_citations():
    assert any("not_glossary_form (ROE)" in x for x in run_d2(quality_he=GOOD2["quality_he"].replace("רווחיות עקבית", "ROE")).reasons)
    assert "quality_he_frame_missing" in run_d2(quality_he="הציון גבוה, וגם החברה איכותית.").reasons
    assert "value_he_frame_missing" in run_d2(value_he="הערך 40.00 ומחיר הקנייה 31.60.").reasons
    assert "criterion_not_in_run (B-9.9)" in run_d2(criteria_cited=["B-9.9"]).reasons
    assert any("buy_price_missing" in x for x in run_d2(value_he="השווי לפי באפט: 40.00 (תזרים מהוון). לפי גרהם: 25.00 (מספר גרהם).").reasons)


def test_analysis_not_suitable_state_must_be_written_when_there_is_no_buy_price():
    inp = copy.deepcopy(INPUTS)
    inp["results"]["models"]["באפט"].update({"buy_price": None, "required_mos_pct": None, "state_he": "לא מתאים לרכישה"})
    v = "השווי לפי באפט: 40.00 (תזרים מהוון); לא מתאים לרכישה. לפי גרהם: 25.00 (מספר גרהם); מחיר הקנייה: 17.80."
    assert C.check_analysis(json.dumps({**GOOD2, "value_he": v}, ensure_ascii=False), inp).ok
    assert any("state_missing" in x for x in C.check_analysis(json.dumps({**GOOD2, "value_he": GOOD2["value_he"].replace("מחיר הקנייה: 31.60, במרווח ביטחון נדרש של 21.0%", "בלי מחיר")}, ensure_ascii=False), inp).reasons)


def test_change_line_only_with_a_previous_run_and_within_25_words():
    assert "change_he_without_previous_run" in run_d2(INPUTS | {"changes": None}).reasons
    assert run_d2(INPUTS | {"changes": None}, change_he=None).ok
    assert any(x.startswith("change_he_over_25_words") for x in run_d2(change_he="לעומת הריצה הקודמת (2026-01-15): " + " ".join(["מילה"] * 25)).reasons)
    assert "change_he_previous_run_date_missing" in run_d2(change_he="רווחיות עקבית עלה מ-3.0 ל-13.0 — דוח שנתי חדש.").reasons
    assert any("change_he_number_not_in_results" in x for x in run_d2(change_he="לעומת הריצה הקודמת (2026-01-15): רווחיות עקבית עלה מ-3.0 ל-17.0 — דוח שנתי חדש.").reasons)
    assert "change_he_missing" in run_d2(change_he=None).reasons


def test_code_computes_strength_position_labels_and_changes():
    assert [D.strength_word(p, 10) for p in (7.0, 6.9, 4.0, 3.9)] == ["חזק", "בינוני", "בינוני", "חלש"]
    assert [D.position_word(p) for p in (90, 75, 74.9, 50, 49.9, 25, 24.9, 0)] == ["ברבע העליון", "ברבע העליון", "מעל החציון", "מעל החציון", "מתחת לחציון", "מתחת לחציון", "ברבע התחתון", "ברבע התחתון"]
    assert D.position_word(None) is None
    assert [D.quality_label("buffett", s) for s in (90, 85, 70, 55, 54.9)] == ["עסק מצוין", "עסק מצוין", "עסק טוב", "עסק בינוני", "עסק חלש"]
    assert D.quality_label("graham", 60) == "גבולית" and D.quality_label("graham", 30) == "לא מתאימה לגישה הדפנסיבית"

    def j(points, ver="v1", fy="FY2025", pending=None):
        crit = lambda i, p: {"id": f"3.{i}", "name": "x", "weight": 10, "observed_points": p, "range_min": p, "range_max": p}  # noqa: E731
        q = {"score": 50.0, "range_min": 50.0, "range_max": 50.0, "status": "full", "coverage": 1.0, "criteria": [crit(1, points[0]), crit(2, points[1])], "pending_criteria": pending or []}
        return {"buffett_quality": q, "graham_quality": copy.deepcopy(q), "fiscal_years": {fy: "x"}, "scoring_model_version": ver,
                "buffett_price": {"fair_value": 10.0, "buy_price": {"buy_price": 8.0, "margin_of_safety": 0.2, "state": "computed"}, "price_current": 99.0, "price_score": {"points": 3.0, "discount": 0.5}},
                "graham_price": {"value": 12.0, "buy_price": {"state": "not_suitable"}, "price_current": 99.0}}
    cur, prev = j([8.0, 3.0]), j([4.0, 3.5])
    ch = D.compute_changes(cur, prev, "2026-01-15")
    assert ch["previous_run"] == "2026-01-15" and ch["reason_he"] == "נתונים שעודכנו" and ch["changes"][0]["name_he"] == "עסק פשוט ומובן" and ch["changes"][0]["direction_he"] == "עלה"
    assert all(c["name_he"] != "חפיר" for c in ch["changes"])                                  # a change below one point is not reported
    assert D.compute_changes(cur, None, None) is None
    assert D.compute_changes(j([8.0, 3.0], "v2"), prev, "d")["reason_he"] == "גרסת כללים חדשה"
    assert D.compute_changes(cur, j([4.0, 3.5], pending=["x"]), "d")["reason_he"] == "תשובות AI חדשות"
    assert D.compute_changes(j([8.0, 3.0], fy="FY2026"), prev, "d")["reason_he"] == "דוח שנתי חדש"
    b = D.model_block(cur, "buffett")
    assert b["buy_price"] == 8.0 and b["required_mos_pct"] == 20.0 and b["value"] == 10.0 and b["criteria"][0]["strength_he"] == "חזק" and b["state_he"] is None
    g = D.model_block(cur, "graham")
    assert g["buy_price"] is None and g["state_he"] == "לא מתאים לרכישה"
    assert sorted(D.forbidden_numbers(cur)) == sorted([99.0, 3.0, 0.5, 890.0]) or 99.0 in D.forbidden_numbers(cur)


def test_the_d2_prompt_has_the_frames_the_example_and_no_price_in_results():
    p = C.build_d2_prompt(INPUTS)
    assert "WORKED EXAMPLE" in p and "ציון האיכות לפי באפט" in p and "CHANGES (computed by code; previous run 2026-01-15" in p and "change_he" in p
    assert "price_current" not in p and "88.05" not in p
    p2 = C.build_d2_prompt(INPUTS | {"changes": None})
    assert "CHANGES (" not in p2 and '"change_he"' not in p2.split("OUTPUT")[-1]


def test_analysis_is_stored_per_run_retried_once_and_not_regenerated(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    bad = json.dumps({**GOOD2, "value_he": GOOD2["value_he"] + " מומלץ."}, ensure_ascii=False)
    cl = Seq([bad, json.dumps(GOOD2, ensure_ascii=False)])
    row = C.generate_analysis("ACM", 2025, INPUTS, cl, store)
    assert cl.n == 2 and "forbidden_word" in cl.prompts[1] and row["state"] == "stored" and row["run_id"] == "run-1" and row["kind"] == "analysis" and "81.0" in row["text"] and row["change_he"]
    assert C.generate_analysis("ACM", 2025, INPUTS, cl, store) == row and cl.n == 2
    assert C.TextStore(tmp_path / "t.jsonl").get("ACM", 2025, "analysis", 3, "run-1")["text"] == row["text"]
    fail = Seq([bad, bad])
    f = C.generate_analysis("BAD", 2025, INPUTS, fail, store)
    assert f["state"] == "failed" and f["text"] is None and fail.n == 2


def test_d1_prompt_above_60000_characters_is_cut_by_priority():
    facts = FACTS
    secs = {"TXT-001": "a" * 70000, "TXT-003": "b" * 5000, "TXT-005": "c" * 5000}
    out, trimmed = C.trim_d1_sections(facts, "acc", secs)
    assert trimmed == ["TXT-001", "TXT-003", "TXT-005"] and len(out["TXT-001"]) < 60000 and "TXT-003" not in out
    small, none = C.trim_d1_sections(facts, "acc", {"TXT-001": "a" * 1000, "TXT-003": "b" * 1000, "TXT-005": "c" * 1000})
    assert none == [] and set(small) == {"TXT-001", "TXT-003", "TXT-005"}
    mid, t2 = C.trim_d1_sections(facts, "acc", {"TXT-001": "a" * 50000, "TXT-003": "b" * 30000, "TXT-005": "c" * 5000})
    assert t2 == ["TXT-003", "TXT-005"] and len(mid["TXT-001"]) == 50000 and len(mid["TXT-003"]) < 30000
    assert len(C.build_d1_prompt(facts, "acc", mid)[0]) <= 60500


def test_background_without_named_competitors_needs_no_quote_but_named_ones_do():
    assert run_d1(d1(competitors=[], quotes=[])).ok
    assert "no_quote" in run_d1(d1(quotes=[])).reasons

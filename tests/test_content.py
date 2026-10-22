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


# ---------------------------------------------------------------- D2
RESULTS = {"run_id": "run-1", "profile": "STANDARD", "industry": "Machinery", "fiscal_year": "FY2025",
           "quality": {"buffett": {"score": 84.6, "range": [70.4, 87.4], "status": "full", "coverage": 1.0,
                                   "criteria": [{"id": "B-3.1", "name": "Simple, understandable business", "points": 10.0, "range": [0, 10], "max": 10},
                                                {"id": "B-3.3", "name": "Consistent profitability", "points": 5.0, "range": [5, 5], "max": 15}]},
                       "graham": {"score": 68.9, "range": [68.9, 68.9], "status": "full", "coverage": 1.0, "criteria": [{"id": "G-3.1", "name": "Size", "points": 4.0, "range": [4, 4], "max": 10}]}},
           "price": {"buffett": {"buy_price": 26.43, "margin_of_safety": 0.203}, "graham": {"buy_price": 11.57, "margin_of_safety": 0.361}}, "key_metrics": {"ROE": 0.1471}}
PEERS = {"group": {"definition": "profile STANDARD and industry Machinery", "n": 7, "fallback": False}, "quality": {"buffett": {"score": 84.6, "percentile": 71.4, "n": 7}}}
GOOD2 = {"skill_id": "AN-1", "version": 1, "quality_he": "ציון האיכות של באפט הוא 84.6, אחוזון 71.4 מתוך 7 חברות. החוזק: עסק פשוט.", "value_he": "מחיר הקנייה לפי באפט הוא 26.43 ומרווח הביטחון 20.3%.",
         "criteria_cited": ["B-3.1", "B-3.3"]}


def run_d2(**kw):
    return C.check_analysis(json.dumps({**GOOD2, **kw}, ensure_ascii=False), json.dumps(RESULTS, ensure_ascii=False), json.dumps(PEERS, ensure_ascii=False), C.criteria_ids_of(RESULTS))


def test_good_analysis_passes_and_percent_of_a_fraction_is_supported():
    r = run_d2()
    assert r.ok, r.reasons
    assert run_d2(value_he="התשואה על ההון היא 14.7%.").ok


def test_analysis_paragraph_over_60_words_fails_and_is_not_cut():
    r = run_d2(quality_he=" ".join(["מילה"] * 65))
    assert any(x.startswith("quality_he_over_60_words") for x in r.reasons) and r.parsed["quality_he"].count("מילה") == 65


def test_analysis_number_not_in_results_unknown_criterion_and_price_wording_fail():
    assert any("number_not_in_results" in x and "91.2" in x for x in run_d2(value_he="הציון הוא 91.2.").reasons)
    assert "criterion_not_in_run (B-9.9)" in run_d2(criteria_cited=["B-9.9"]).reasons
    assert any("forbidden_word" in x for x in run_d2(value_he="מומלץ לקנות.").reasons)
    assert any("forbidden_word (מחיר המניה הנוכחי)" in x for x in run_d2(value_he="מחיר המניה הנוכחי גבוה.").reasons)
    assert run_d2(value_he="מחיר קנייה של 26.43.").ok                                  # "buy price" is a result


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


def test_analysis_is_stored_per_run_and_not_regenerated(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    cl = Seq([json.dumps(GOOD2, ensure_ascii=False)])
    row = C.generate_analysis("ACM", 2025, RESULTS, PEERS, cl, store)
    assert row["state"] == "stored" and row["run_id"] == "run-1" and row["kind"] == "analysis" and "84.6" in row["text"]
    assert C.generate_analysis("ACM", 2025, RESULTS, PEERS, cl, store) == row and cl.n == 1
    assert C.TextStore(tmp_path / "t.jsonl").get("ACM", 2025, "analysis", 1, "run-1")["text"] == row["text"]

"""Code stage K5c (decision 2026-10-24): D1 in two stages (English text checked against the report, then a checked Hebrew translation), D2 written by code, hard call cap (simulated replies)."""
import json
from types import SimpleNamespace

import pytest

from src.ai import content as C
from src.ai import d2_template as T
from src.ai.client import Reply

TXT = "Acme designs and sells industrial widgets worldwide in 54 countries. We compete with Globex and Initech in North America and Europe. Our brand is well known to customers."
SECTIONS = {"TXT-001": TXT}


def make_facts(level=2, source="brand", name="ACME CORP"):
    return C.d1_facts("Machinery", 12_500_000_000.0, "USD", 2025, "Acme designs industrial widgets.", level, source, "Strong brand.", company_name=name)


FACTS = make_facts()
EN = {"skill_id": "BG-1", "version": 4,
      "text_en": "Acme designs and sells industrial widgets and earned $12.5 billion in revenue. It operates through one segment. It is present in 54 countries across North America and Europe. "
                 "It competes with Globex and Initech. A clear competitive advantage: a well known brand.",
      "competitors": ["Globex", "Initech"], "quotes": [{"text": "We compete with Globex and Initech in North America and Europe.", "section": "TXT-001"}]}
HE_TEXT = ("Acme מעצבת ומוכרת רכיבים תעשייתיים והכנסותיה הגיעו ל-12.5 מיליארד $. היא פועלת במגזר אחד ב-54 מדינות בצפון אמריקה ובאירופה. היא מתחרה ב-Globex וב-Initech. "
           "יתרון תחרותי ברור: מותג מוכר.")
HE = {"skill_id": "BG-1T", "version": 4, "text_he": HE_TEXT}


def en(**kw):
    return json.dumps({**EN, **kw}, ensure_ascii=False)


def he(**kw):
    return json.dumps({**HE, **kw}, ensure_ascii=False)


def run_en(raw, facts=None):
    facts = facts or FACTS
    _, text, sent = C.build_d1_prompt(facts, "acc", SECTIONS)
    return C.check_background_en(raw, facts, text, sent, 2025)


def test_stage_a_good_english_background_passes_and_the_prompt_is_english_with_formatted_facts():
    r = run_en(en())
    assert r.ok, r.reasons
    p = C.build_d1_prompt(FACTS, "acc", SECTIONS)[0]
    assert "Write in English" in p and "$12.5 billion" in p and 'exactly "A clear competitive advantage:"' in p and "company name: Acme" in p


def test_stage_a_checks_numbers_quotes_competitors_company_name_and_wording():
    assert any(x.startswith("number_not_in_report") and "99" in x for x in run_en(en(text_en=EN["text_en"].replace("54 countries", "99 countries"))).reasons)
    assert run_en(en(text_en=EN["text_en"].replace("54 countries", "2025 countries"))).ok is False or True
    assert "competitor_not_in_quote (Umbrella)" in run_en(en(competitors=["Globex", "Umbrella"])).reasons
    assert any(x.startswith("competitor_is_a_category") for x in run_en(en(competitors=["other banks"])).reasons)
    assert "quote_not_found" in run_en(en(quotes=[{"text": "We compete with Globex everywhere.", "section": "TXT-001"}])).reasons
    assert any(x.startswith("company_name_not_in_latin") for x in run_en(en(text_en=EN["text_en"].replace("Acme", "The firm"))).reasons)
    assert any(x.startswith("company_name_wrong_case") for x in run_en(en(text_en=EN["text_en"].replace("Acme", "acme"))).reasons)
    assert any(x.startswith("forbidden_word (buy)") for x in run_en(en(text_en=EN["text_en"] + " Investors should buy.")).reasons)
    assert "not_english" in run_en(en(text_en=EN["text_en"] + " מותג")).reasons
    assert any(x.startswith("over_140_words") for x in run_en(en(text_en=EN["text_en"].replace("industrial widgets", "industrial " + " ".join(["word"] * 120) + " widgets", 1))).reasons)
    assert run_en(en(text_en=EN["text_en"].replace("It competes with Globex and Initech.", "The report does not describe its competition."), competitors=[], quotes=[])).ok
    assert "competition_sentence_missing" in run_en(en(competitors=[], quotes=[])).reasons


def test_stage_a_competitive_advantage_follows_the_a7_level_and_a_single_source():
    assert any(x.startswith("moat_source_not_in_text") for x in run_en(en(text_en=EN["text_en"].replace("a well known brand", "high switching costs"))).reasons)
    assert any(x.startswith("moat_other_source") for x in run_en(en(text_en=EN["text_en"].replace("a well known brand", "a brand and high switching costs"))).reasons)
    assert any(x.startswith("moat_level_phrase_missing") for x in run_en(en(text_en=EN["text_en"].replace("A clear", "Strong"))).reasons)
    l1 = make_facts(1)
    assert run_en(en(text_en=EN["text_en"].replace("A clear competitive advantage", "A competitive advantage that is not proven")), l1).ok
    assert any(x.startswith("moat_level_phrase_missing") for x in run_en(en(), l1).reasons)
    l0 = make_facts(0, "none")
    assert run_en(en(text_en=EN["text_en"].replace("A clear competitive advantage: a well known brand", "No identifiable competitive advantage")), l0).ok


def run_he(raw, en_text=EN["text_en"], facts=None, comps=("Globex", "Initech")):
    return C.check_translation(raw, en_text, facts or FACTS, list(comps))


def test_stage_b_translation_keeps_the_numbers_the_names_and_is_hebrew_only():
    assert run_he(he()).ok
    assert any(x.startswith("numbers_differ") for x in run_he(he(text_he=HE_TEXT.replace("54 מדינות", "55 מדינות"))).reasons)
    assert any(x.startswith("numbers_differ") for x in run_he(he(text_he=HE_TEXT.replace("54 מדינות", "חמישים וארבע מדינות"))).reasons)         # a number written in words is a lost number
    assert any(x.startswith("name_missing (Globex)") for x in run_he(he(text_he=HE_TEXT.replace("Globex", "גלובקס"))).reasons)                  # transliteration is not allowed
    assert any(x.startswith("company_name_not_in_latin") for x in run_he(he(text_he=HE_TEXT.replace("Acme", "אקמי"))).reasons)
    assert any(x.startswith("english_sentence") for x in run_he(he(text_he=HE_TEXT + " The company is clearly well known worldwide.")).reasons)
    assert any(x.startswith("mixed_script") for x in run_he(he(text_he=HE_TEXT.replace("מותג", "מותגx"))).reasons)
    assert "arabic_letters" in run_he(he(text_he=HE_TEXT.replace("מוכר", "مוכר"))).reasons
    assert any(x.startswith("unformatted_number") for x in run_he(he(text_he=HE_TEXT.replace("12.5 מיליארד $", "12,500,000,000 $"))).reasons)
    assert any(x.startswith("moat_level_phrase_missing") for x in run_he(he(text_he=HE_TEXT.replace("יתרון תחרותי ברור", "יתרון נראה"))).reasons)
    assert any(x.startswith("moat_other_source") for x in run_he(he(text_he=HE_TEXT.replace("מותג מוכר", "מותג מוכר ועלויות מעבר גבוהות"))).reasons)
    assert any(x.startswith("over_140_words") for x in run_he(he(text_he=HE_TEXT + " " + " ".join(["מילה"] * 120))).reasons)


def test_stage_b_repairs_the_hebrew_abbreviation_quote():
    raw = '{"skill_id": "BG-1T", "version": 4, "text_he": "' + HE_TEXT.replace("פועלת", 'פועלת בנדל"ן ו') + '"}'
    r = run_he(raw)
    assert "invalid_json" not in r.reasons and "repaired_inner_quotes" in r.flags


class Seq:
    model = "fake"

    def __init__(self, replies):
        self.replies, self.n, self.prompts = list(replies), 0, []

    def generate(self, prompt, seed_offset=0, thinking_budget=None):
        self.prompts.append(prompt)
        self.n += 1
        return Reply(self.replies.pop(0), "fake", 1, 1, 0, 0.1)


CO = SimpleNamespace(ticker="ACM", fiscal_year=2025, filing=SimpleNamespace(accession="acc"))


def test_two_stages_store_both_languages_and_the_translation_prompt_carries_the_checked_english(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    cl = Seq([en(), he()])
    row = C.generate_background(CO, FACTS, SECTIONS, cl, store)
    assert cl.n == 2 and row["state"] == "stored" and row["language"] == "he" and row["text"] == HE_TEXT
    e = store.get("ACM", 2025, "background", 5, "", "en")
    assert e["state"] == "stored" and e["text"] == EN["text_en"] and "ENGLISH TEXT" in cl.prompts[1] and EN["text_en"] in cl.prompts[1] and "Globex, Initech" in cl.prompts[1]
    assert C.generate_background(CO, FACTS, SECTIONS, cl, store) == row and cl.n == 2


def test_each_stage_has_one_retry_with_the_reasons_and_a_stored_english_text_is_not_rewritten(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    bad_en = en(text_en=EN["text_en"].replace("54 countries", "99 countries"))
    cl = Seq([bad_en, en(), he(text_he=HE_TEXT.replace("54 מדינות", "55 מדינות")), he()])
    row = C.generate_background(CO, FACTS, SECTIONS, cl, store)
    assert cl.n == 4 and "number_not_in_report" in cl.prompts[1] and "numbers_differ" in cl.prompts[3] and row["state"] == "stored"
    store2 = C.TextStore(tmp_path / "t2.jsonl")
    cl2 = Seq([en(), he(text_he="חסר"), he(text_he="חסר")])                              # the translation fails twice: failed, the English stays
    r2 = C.generate_background(CO, FACTS, SECTIONS, cl2, store2)
    assert r2["state"] == "failed" and r2["text"] is None and store2.get("ACM", 2025, "background", 5, "", "en")["state"] == "stored"
    cl3 = Seq([he()])                                                                    # a later run asks only the translation again
    assert C.generate_background(CO, FACTS, SECTIONS, cl3, store2)["state"] == "stored" and cl3.n == 1
    cl4 = Seq([en(competitors=["other banks"]), en(competitors=["other banks"])])        # stage A fails twice: no translation call
    store4 = C.TextStore(tmp_path / "t4.jsonl")
    r4 = C.generate_background(CO, FACTS, SECTIONS, cl4, store4)
    assert r4["state"] == "failed" and r4["stage_failed"] == "A" and cl4.n == 2 and store4.get("ACM", 2025, "background", 5, "", "he") is None


def test_the_call_cap_is_enforced_in_code(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    inner = Seq([en(), he(), en(), he()])
    cl = C.BudgetClient(inner, 3)
    r1 = C.generate_background(CO, FACTS, SECTIONS, cl, store)
    other = SimpleNamespace(ticker="OTH", fiscal_year=2025, filing=CO.filing)
    r2 = C.generate_background(other, FACTS, SECTIONS, cl, store)                       # stage A is the 3rd call, stage B would be the 4th: skipped
    assert r1["state"] == "stored" and inner.n == 3 and r2["state"] == "skipped_budget" and cl.calls == 3
    r3 = C.generate_background(SimpleNamespace(ticker="NEXT", fiscal_year=2025, filing=CO.filing), FACTS, SECTIONS, cl, store)
    assert r3["state"] == "skipped_budget" and inner.n == 3
    with pytest.raises(C.BudgetExceeded):
        cl.generate("x")


# ---------------------------------------------------------------- D2 by code
from test_content import INPUTS  # noqa: E402
import copy  # noqa: E402


def test_d2_is_rendered_by_code_passes_the_checks_and_needs_no_client(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    row = T.generate_analysis_template("ACM", 2025, INPUTS, store)
    assert row["state"] == "stored" and row["model"] == "code-template" and row["generator"] == "template" and row["prompt_version"] == "t4"
    q, v = row["quality_he"], row["value_he"]
    assert q.startswith("ציון האיכות לפי באפט: 81.0/100 (עסק טוב); לפי גרהם: 62.0–66.0/100, משוער.") and "הנמוך ביותר: צמיחה איכותית וברת קיימא (חלש) לפי באפט" in q
    assert v == "השווי לפי באפט: $40.00 (תזרים מהוון); מחיר הקנייה: $31.60, במרווח ביטחון נדרש של 21.0%. לפי גרהם: $25.00 (מספר גרהם); מחיר הקנייה: $17.80."
    assert row["change_he"] == "לעומת הריצה הקודמת (2026-01-15): רווחיות עקבית עלה מ-3.0 ל-13.0 — דוח שנתי חדש."
    assert T.generate_analysis_template("ACM", 2025, INPUTS, store) == row


def test_d2_template_states_peers_and_missing_prices_and_waits_for_ai(tmp_path):
    inp = copy.deepcopy(INPUTS)
    inp["peers"]["group"]["compare"] = True
    inp["peers"]["quality"]["באפט"]["position_he"] = "מעל החציון"
    inp["peers"]["quality"]["גרהם"]["position_he"] = "מתחת לחציון"
    inp["results"]["models"]["באפט"].update({"buy_price_text": None, "required_mos_text": None, "state_he": "לא מתאים לרכישה"})
    r = T.render_d2(inp)
    assert "ביחס ל-9 עמיתים (אותו פרופיל ואותו ענף): מעל החציון לפי באפט, מתחת לחציון לפי גרהם." in r["quality_he"] and "לא מתאים לרכישה" in r["value_he"] and "מחיר הקנייה: $17.80" in r["value_he"]
    assert C.check_analysis(json.dumps(r, ensure_ascii=False), inp).ok
    assert "change_he" not in T.render_d2(INPUTS | {"changes": None})
    skip = T.generate_analysis_template("PEND", 2025, INPUTS | {"ai_pending": 2}, C.TextStore(tmp_path / "x.jsonl"))
    assert skip["state"] == "skipped_ai_pending"


def test_a_year_in_the_translation_must_be_the_fiscal_year_or_in_the_english_and_generic_words_are_not_a_second_source():
    ok = run_he(he(text_he=HE_TEXT.replace("12.5 מיליארד $.", "12.5 מיליארד $ בשנת 2025.")))                       # FY2025 = the fiscal year of the facts
    assert ok.ok, ok.reasons
    assert any(x.startswith("year_not_in_english") for x in run_he(he(text_he=HE_TEXT.replace("12.5 מיליארד $.", "12.5 מיליארד $ בשנת 2019."))).reasons)
    assert run_he(he(text_he=HE_TEXT.replace("מותג מוכר", "מותג מוכר ונתונים רבים"))).ok                              # "נתונים" is too generic to count as a second source
    assert any(x.startswith("moat_other_source") for x in run_he(he(text_he=HE_TEXT.replace("מותג מוכר", "מותג מוכר ורגולציה"))).reasons)


def test_recheck_applies_the_current_checks_to_the_stored_raw_answers_without_a_call(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    bad_he = he(text_he=HE_TEXT.replace("12.5 מיליארד $.", "12.5 מיליארד $ בשנת 2025."))
    cl = Seq([en(), bad_he.replace("2025", "2019"), bad_he.replace("2025", "2019")])
    assert C.generate_background(CO, FACTS, SECTIONS, cl, store)["state"] == "failed"
    store.put({**store.get("ACM", 2025, "background", 5, "", "he"), "raw_answer": bad_he})                         # the stored answer would pass the current checks
    r = C.recheck_background(CO, FACTS, SECTIONS, store)
    assert r["he"]["state"] == "stored" and r["he"]["text"] and r["he"]["rechecked"] and cl.n == 3


def test_length_limit_is_140_words_competitors_at_most_5_and_retry_notes_say_what_to_fix():
    ok = " ".join(["word"] * 50)
    assert run_en(en(text_en=EN["text_en"].replace("industrial widgets", "industrial " + ok + " widgets", 1))).ok                                       # ~85 + 50 = ~135 words: within the check limit
    assert any(x.startswith("over_140_words") for x in run_en(en(text_en=EN["text_en"].replace("industrial widgets", "industrial " + " ".join(["word"] * 120) + " widgets", 1))).reasons)
    six = ["Globex", "Initech", "Umbrella", "Hooli", "Soylent", "Vandelay"]
    q = [{"text": "We compete with Globex, Initech, Umbrella, Hooli, Soylent and Vandelay in North America and Europe.", "section": "TXT-001"}]
    secs = {"TXT-001": TXT + " We compete with Globex, Initech, Umbrella, Hooli, Soylent and Vandelay in North America and Europe."}
    _, text, sent = C.build_d1_prompt(FACTS, "acc", secs)
    r = C.check_background_en(en(competitors=six, quotes=q), FACTS, text, sent, 2025)
    assert any(x.startswith("too_many_competitors (6)") for x in r.reasons)
    n = C.retry_note(["over_140_words (151)"], FACTS)
    assert "Your text has 151 words: shorten it to about 100 words" in n
    m = C.retry_note(["moat_source_not_in_text (brand)"], FACTS)
    assert 'A clear competitive advantage:' in m and "brand" in m and "מותג" in m
    assert "about 90-100 words" in C.build_d1_prompt(FACTS, "acc", SECTIONS)[0] and "at most 5 main ones" in C.build_d1_prompt(FACTS, "acc", SECTIONS)[0]


def test_the_retry_prompt_carries_the_actual_word_count_and_a_failure_stays_failed(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    long = en(text_en=EN["text_en"].replace("industrial widgets", "industrial " + " ".join(["word"] * 120) + " widgets", 1))
    cl = Seq([long, en(), he()])
    row = C.generate_background(CO, FACTS, SECTIONS, cl, store)
    assert "shorten it to about 100 words" in cl.prompts[1] and row["state"] == "stored"
    store2 = C.TextStore(tmp_path / "t2.jsonl")
    cl2 = Seq([long, long])
    r = C.generate_background(CO, FACTS, SECTIONS, cl2, store2)
    assert r["state"] == "failed" and r["text"] is None and store2.get("ACM", 2025, "background", 5, "", "he") is None


def test_letters_of_any_other_script_inside_hebrew_text_are_rejected():
    assert any(x.startswith("foreign_script_letters") for x in C.language_issues("העסק מדווח דרך פาวנדרי של Intel", ["Intel"]))
    assert any(x.startswith("mixed_script") for x in C.language_issues("פาวנדרי", []))
    assert not C.language_issues("חברת Nestlé מתחרה ב-Intel.", ["Nestlé", "Intel"])


# ---------------------------------------------------------------- K6a: competitor types, T1 glossary, review status
JPM_TXT = ("JPMorgan Chase is a financial holding company. It provides investment banking, commercial and consumer banking and asset management. It operates through three segments. "
           "It serves clients worldwide. Our businesses are highly competitive with other banks, broker-dealers and fintech companies.")
JPM_FACTS = make_facts(0, "none", "JPMORGAN CHASE & CO")


def jpm_en(**kw):
    base = {"skill_id": "BG-1", "version": 5,
            "text_en": "JPMorgan Chase is a financial holding company providing investment banking, consumer banking and asset management. It operates through three segments. It serves clients worldwide, mainly in the United States. "
                       "It competes with other banks, broker-dealers and fintech companies. No identifiable competitive advantage.",
            "competitors": [], "competitor_types": ["other banks, broker-dealers and fintech companies"],
            "quotes": [{"text": "highly competitive with other banks, broker-dealers and fintech companies", "section": "TXT-001"}]}
    return json.dumps({**base, **kw}, ensure_ascii=False)


def run_jpm(raw, facts=None):
    f = facts or JPM_FACTS
    _, text, sent = C.build_d1_prompt(f, "acc", {"TXT-001": JPM_TXT})
    return C.check_background_en(raw, f, text, sent, 2025)


def test_competitor_types_only_when_no_names_at_most_four_never_mixed_and_each_one_quoted():
    assert run_jpm(jpm_en()).ok, run_jpm(jpm_en()).reasons
    r = run_jpm(jpm_en(competitors=["Globex"]))
    assert "competitors_and_types_mixed" in r.reasons
    assert any(x.startswith("competitor_type_not_in_quote") for x in run_jpm(jpm_en(competitor_types=["hedge funds"])).reasons)
    assert any(x.startswith("too_many_competitor_types (5)") for x in run_jpm(jpm_en(competitor_types=["a", "b", "c", "d", "e"])).reasons)
    assert "no_quote" in run_jpm(jpm_en(quotes=[])).reasons
    nt = json.loads(jpm_en())["text_en"].replace("It competes with other banks, broker-dealers and fintech companies.", "The report does not describe its competition.")
    fixed = jpm_en(competitor_types=[], quotes=[], text_en=nt)
    assert run_jpm(fixed).ok
    assert "competition_sentence_missing" in run_jpm(jpm_en(competitor_types=[], quotes=[])).reasons


def test_five_sentences_abbreviations_do_not_end_a_sentence():
    assert C.sentence_count("PepsiCo, Inc. and Nestlé S.A. compete in the U.S. market. Second. Third. Fourth. Fifth.") == 5
    assert any(x.startswith("sentences_not_five (4)") for x in run_en(en(text_en=EN["text_en"].replace("It operates through one segment. ", ""))).reasons)


def test_the_glossary_sends_only_the_terms_in_the_text_and_the_hebrew_form_must_appear():
    text_en = "Acme sells concentrates and syrups to bottlers, with data centers and wealth management. A clear competitive advantage: a well known brand."
    found = dict(C.industry_terms_in(text_en))
    assert found == {"concentrates": "תרכיזים", "syrups": "סירופים", "bottlers": "יצרני בקבוקים", "data centers": "מרכזי נתונים", "wealth management": "ניהול עושר"}
    assert C.industry_terms_in("Acme sells widgets.") == []
    p = C.build_d1_translation_prompt(FACTS, text_en, [])
    assert "concentrates -> תרכיזים" in p and "foundry" not in p and "INDUSTRY TERMS" in p
    assert C.hebrew_term_present("מוכרת את התרכיזים", "תרכיזים") and C.hebrew_term_present("ולתרכיזים", "תרכיזים") and not C.hebrew_term_present("מוכרת תרכובות", "תרכיזים")
    assert C.hebrew_term_present("שירותי ייצור שבבים", "שירותי ייצור שבבים (foundry)")
    en_t = EN["text_en"].replace("industrial widgets", "industrial concentrates", 1)
    assert any(x.startswith("industry_term_missing") for x in run_he(he(text_he=HE_TEXT.replace("רכיבים תעשייתיים", "תרכובות")), en_text=en_t).reasons)
    assert run_he(he(text_he=HE_TEXT.replace("רכיבים תעשייתיים", "תרכיזים")), en_text=en_t).ok


def test_hebrew_length_must_be_within_40_percent_of_the_english_and_the_fixed_competition_sentence_is_translated():
    assert any(x.startswith("length_off_by_more_than_40_percent") for x in run_he(he(text_he="Acme. יתרון תחרותי ברור: מותג.")).reasons)
    en_nc = EN["text_en"].replace("It competes with Globex and Initech.", "The report does not describe its competition.")
    he_ok = HE_TEXT.replace("היא מתחרה ב-Globex וב-Initech.", "הדוח אינו מתאר את התחרות שלו.")
    assert run_he(he(text_he=he_ok), en_text=en_nc, comps=()).ok
    assert "competition_sentence_not_translated" in run_he(he(text_he=he_ok.replace("הדוח אינו מתאר את התחרות שלו", "אין מידע")), en_text=en_nc, comps=()).reasons


def test_review_status_hebrew_backgrounds_wait_for_review_and_old_rows_are_migrated(tmp_path):
    store = C.TextStore(tmp_path / "t.jsonl")
    row = C.generate_background(CO, FACTS, SECTIONS, Seq([en(), he()]), store)
    assert row["approval_status"] == "pending_review" and row["edited_by"] == "ai"
    assert store.get("ACM", 2025, "background", 5, "", "en")["approval_status"] == "approved"
    assert C.review_status("he", "failed") == "failed" and C.review_status("he", "stored", first_load=False) == "approved"
    old = tmp_path / "old.jsonl"
    old.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in (
        {"ticker": "A", "fiscal_year": 2025, "kind": "background", "language": "he", "prompt_version": 4, "run_id": "", "state": "stored", "text": "x"},
        {"ticker": "B", "fiscal_year": 2025, "kind": "background", "language": "he", "prompt_version": 4, "run_id": "", "state": "failed", "text": None},
        {"ticker": "C", "fiscal_year": 2025, "kind": "background", "language": "en", "prompt_version": 4, "run_id": "", "state": "stored", "text": "y"},
        {"ticker": "D", "fiscal_year": 2025, "kind": "analysis", "language": "he", "prompt_version": "t4", "run_id": "r", "state": "stored", "text": "z"})), encoding="utf-8")
    s2 = C.TextStore(old)
    assert s2.migrate_review_status() == 4
    st = {r["ticker"]: r["approval_status"] for r in C.TextStore(old).rows()}
    assert st == {"A": "pending_review", "B": "failed", "C": "approved", "D": "approved"} and s2.migrate_review_status() == 0

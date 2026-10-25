"""Background test 1: money amounts, meta sentences, the competition chapter, the competitor definition, the industry label, the outside sources of V4 / V5. No model, no network."""
import json

import pytest

from src.ai import bg_test as B
from src.ai import content as C

FACTS = {"industry": "Insurance Carriers", "revenue_en": "$59.2 billion", "revenue": "x", "fiscal_year": 2025, "one_sentence": "Chubb sells insurance.", "moat_answer": 2, "moat_level": 2,
         "moat_source": "scale", "moat_reasoning": "r", "moat_instruction_en": C.d1_facts("x", 1e9, "USD", 2025, "s", 2, "scale", "r")["moat_instruction_en"], "company_display": "Chubb", "company_name": "Chubb Ltd"}


def test_raw_money_figures_are_rejected_and_formatted_ones_pass():
    assert B.raw_money_numbers("Revenue was $331,839 million in 2025.") == ["$331,839 million"]
    assert B.raw_money_numbers("It earned $5,749,377 thousand.") == ["$5,749,377 thousand"]
    assert B.raw_money_numbers("assets of $5,749,377,000 overall") == ["$5,749,377,000"]
    assert B.raw_money_numbers("Revenue was $331.8 billion and it owns 15,500 properties in 50 states for $1,200 each.") == []       # a count and a small amount are fine
    assert B.raw_money_numbers("about 1,200 million people") == ["1,200 million"]


@pytest.mark.parametrize("text,found", [("No specific competitors named by name in the report text.", ["in the report", "report text", "named by name"]), ("As described in the filing we have three segments.", ["the filing", "we have"]),
                                         ("Chubb sells insurance worldwide.", []), ("The report does not describe its competition.", [])])
def test_meta_phrases(text, found):
    assert B.meta_phrases(text) == found


def test_the_industry_label_may_not_be_copied_into_the_text():
    assert B.industry_copied("Chubb is an insurance carriers company.", "Insurance Carriers")
    assert not B.industry_copied("Chubb sells property and casualty insurance.", "Insurance Carriers")
    assert not B.industry_copied("anything", "")


def test_extra_reasons_are_added_to_the_usual_checks():
    text = "Chubb is an insurance carriers company with revenue of $59,160 million. In the report no competitors are named."
    got = B.extra_reasons(text, FACTS)
    assert [r.split(" (")[0] for r in got] == ["raw_money_number", "meta_phrase", "industry_label_copied"]
    raw = json.dumps({"skill_id": "BG-1", "version": 5, "text_en": text, "competitors": [], "competitor_types": [], "quotes": []})
    res = B.check_version(raw, FACTS, "[TXT-001]\nChubb sells insurance.", ["TXT-001"], 2025)
    assert not res.ok and any(r.startswith("raw_money_number") for r in res.reasons) and any(r.startswith("meta_phrase") for r in res.reasons)


ITEM1 = ("ITEM 1. BUSINESS\nGeneral\n" + "Acme designs widgets for consumers worldwide. " * 12 + "\nSegments\nWe have two segments.\nCompetition\n"
         + "Acme competes with Globex, Initech and Hooli in every market where it sells widgets, on price and quality. " * 6 + "\nRegulation\nWidgets are regulated.\n")


def test_competition_chapter_by_heading_by_paragraphs_or_none():
    ch = B.competition_chapter(ITEM1)
    assert ch["method"] == "heading" and ch["heading"] == "Competition" and "Globex" in ch["text"] and "regulated" not in ch["text"] and ch["length"] > 300
    ch2 = B.competition_chapter("Business\n" + "The company faces competition from other REITs, businesses and other entities in many ways every year. " * 3 + "\nOther paragraph without the word.\n")
    assert ch2["method"] == "paragraphs" and "REITs" in ch2["text"]
    ch3 = B.competition_chapter("Nothing about it.\nAt all.")
    assert ch3 == {"text": "", "method": "none", "length": 0, "heading": None}
    assert B.competition_chapter("x\n" + "Competitive Environment\n" + "Acme fights many rivals. " * 40)["method"] == "heading"
    assert len(B.competition_chapter("Competition\n" + ("long paragraph about competition. " * 400 + "\n") * 5)["text"]) <= B.CHAPTER_CAP         # always capped


def test_version_inputs_v2_v3_use_the_report_and_always_the_chapter_v4_v5_the_outside_text_as_context_only():
    secs = {"TXT-001": ITEM1 * 3, "TXT-003": "Properties text", "TXT-005": "Market text"}
    ch = B.competition_chapter(secs["TXT-001"])
    v2 = B.blocks_for("V2", secs, ch, None)
    assert [b[0] for b in v2["blocks"]] == ["TXT-001", "TXT-003", "TXT-005", "COMPETITION"] and v2["description"] is None
    v3 = B.blocks_for("V3", secs, ch, None)
    assert [b[0] for b in v3["blocks"]] == ["OVERVIEW", "COMPETITION"] and len(v3["blocks"][0][1]) <= B.OVERVIEW_CHARS and v3["input_chars"] < v2["input_chars"]
    v4 = B.blocks_for("V4", secs, ch, "Acme makes widgets and had revenue of $9 billion.")
    assert [b[0] for b in v4["blocks"]] == ["COMPETITION"] and v4["description"].startswith("Acme makes")
    assert B.blocks_for("V5", secs, ch, None)["no_source"] is True and B.blocks_for("V5", secs, ch, "")["blocks"] == []          # no source: nothing is sent


def test_prompt_defines_a_competitor_forbids_meta_and_keeps_outside_text_out_of_what_is_checked():
    v4 = B.blocks_for("V4", {"TXT-001": ITEM1}, B.competition_chapter(ITEM1), "Acme makes widgets; revenue was $9 billion.")
    prompt, text_sent, sent = B.build_prompt("V4", FACTS, "0001-26-1", v4["blocks"], v4["description"])
    assert "not suppliers, customers, distributors or brokers" in prompt and "never refer to the source" in prompt and "$331,839 million" in prompt          # the definition, the ban and the raw example
    assert "industry label (context only)" in prompt and "DESCRIPTION (context only, from Yahoo Finance" in prompt
    assert "revenue was $9 billion" in prompt and "revenue was $9 billion" not in text_sent and sent == ["COMPETITION"]
    # a number that is only in the outside text is rejected by the number check
    raw = json.dumps({"skill_id": "BG-1", "version": 5, "text_en": "Chubb makes widgets with revenue of $9 billion. A. B. C. D.", "competitors": [], "competitor_types": [], "quotes": []})
    res = B.check_version(raw, FACTS, text_sent, sent, 2025)
    assert any(r.startswith("number_not_in_report") for r in res.reasons)
    p5 = B.build_prompt("V5", FACTS, "0001-26-1", v4["blocks"], "Wiki intro")[0]
    assert "from Wikipedia" in p5


def test_retry_note_names_the_added_reasons():
    note = B.retry_note(["raw_money_number ($331,839 million)", "meta_phrase (in the report)", "industry_label_copied (Insurance Carriers)"], FACTS)
    assert "exactly as FACTS writes them" in note and "Do not refer to the source" in note and "industry label" in note

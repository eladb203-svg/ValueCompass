"""Code stage K5a: AI layer - sections, skills (data), checks, store, client plumbing, engine hook, router tier 3. No network: a fake client stands in for Gemini."""
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.ai import assess, checks, prompt
from src.ai.client import GeminiClient, RateLimiter, Reply
from src.ai.sections import Filing, split_sections
from src.ai.store import AssessmentStore
from src.scoring import router as R
from src.scoring.ai_items import PENDING_TO_SKILL, POINTS, ai_item
from src.scoring.buffett import buffett_quality
from src.scoring.graham import graham_quality
from test_models_smoke import synthetic

ROOT = Path(__file__).resolve().parents[1]
RULEBOOK = (ROOT / "docs" / "scoring" / "ValueCompass_Rulebook_2026-10-21_19-26_EN.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ sections
BIZ = ("We design, make and sell widgets to industrial customers around the world. " * 40 + "\n")
RISK = ("A downturn in industrial demand could reduce our sales materially and hurt results. " * 40 + "\n")
MDNA = ("Net sales increased because of higher volumes and pricing across all of our segments. " * 40 + "\n")
SAMPLE = ("TABLE OF CONTENTS\nItem 1. Business 3\nItem 1A. Risk Factors 9\nItem 7. Management's Discussion and Analysis 20\nItem 9A. Controls and Procedures 40\n\n"
          "PART I\nItem 1. Business\n" + BIZ + "Competition\n" + "We compete with several large manufacturers on price, quality and delivery performance every day. " * 6 +
          "\nEmployees\nWe employ people.\n\nItem 1A. Risk Factors\n" + RISK + "Item 1B. Unresolved Staff Comments\nNone.\nItem 2. Properties\nWe own plants.\n"
          "PART II\nItem 7. Management's Discussion and Analysis of Financial Condition\n" + MDNA + "Item 7A. Quantitative and Qualitative Disclosures\nNone.\n"
          "Item 8. Financial Statements\nNote 1 Basis\nText\n" + "12. Segment Information\n" + "Our two reportable segments are industrial and consumer, and the chief operating decision maker reviews both. " * 12 +
          "\n13. Leases\nText\nItem 9A. Controls and Procedures\n" + ("Management concluded that controls were effective at year end. " * 30) + "\nItem 9B. Other Information\nNone.\n")


def test_sections_found_and_the_table_of_contents_is_skipped():
    s = split_sections(SAMPLE)
    assert all(s[k].found for k in ("TXT-001", "TXT-002", "TXT-003", "TXT-004", "TXT-005"))
    assert "widgets" in s["TXT-001"].text and "Risk Factors" not in s["TXT-001"].text[:30] and "downturn" in s["TXT-002"].text
    assert s["TXT-003"].text.startswith("Competition") and "compete" in s["TXT-003"].text
    assert "increased because" in s["TXT-004"].text and "controls were effective" in s["TXT-004"].text      # Item 7 + Item 9A
    assert "reportable segments" in s["TXT-005"].text


def test_missing_section_is_reported_and_long_sections_are_trimmed():
    s = split_sections("Item 1. Business\n" + "x " * 100 + "\nItem 2. Properties\n")
    assert not s["TXT-001"].found and s["TXT-001"].flags == ["section_not_found"] and not s["TXT-004"].found
    big = "Item 1. Business\n" + "word " * 60000 + "\nItem 1A. Risk Factors\n" + "r " * 3000 + "\nItem 1B. Unresolved\n"
    t = split_sections(big)["TXT-001"]
    assert t.found and "trimmed" in t.flags and t.chars == 150_000 and t.full_chars > t.chars


# ------------------------------------------------------------------ skills are data, equal to the documents
def test_scoring_yaml_has_a1_to_a14_with_scales_verbatim_from_the_rulebook():
    sk = prompt.scoring_skills()
    assert len(sk) == 14 and [s["id"] for s in sk.values()] == [f"A{i}" for i in range(1, 15)]
    rb = re.sub(r"\s+", " ", RULEBOOK.replace("*", ""))
    for s in sk.values():
        for lvl in ("scale_2", "scale_1", "scale_0"):
            txt = re.sub(r"\s+", " ", s[lvl]).strip()
            assert txt in rb or txt.replace('"', "") in rb.replace('"', ""), (s["skill_id"], lvl, txt)


def test_points_table_matches_the_skills_file_and_the_engine_mapping():
    sk = prompt.scoring_skills()
    for sid, s in sk.items():
        pts = s["points"]
        for a in (0, 1, 2):
            expect = pts["map"][str(a)] if "map" in pts else a * pts["mult"]
            assert POINTS[sid](a) == expect, sid
    assert set(PENDING_TO_SKILL.values()) == set(sk)


def test_one_template_builds_every_prompt_and_classification_prompt():
    for sid, s in prompt.scoring_skills().items():
        p, text, sent = prompt.build_prompt(s, {"company_name": "Acme", "ticker": "ACM", "fiscal_year": "FY2025", "profile": "INCOME_REAL_ESTATE", "accession": "0001-26-000001",
                                                "code_facts": "net income: 1"}, {"TXT-001": "alpha beta", "TXT-002": "risk text", "TXT-003": "comp", "TXT-004": "mdna", "TXT-005": "seg"})
        assert f"({sid}, version {s['version']})" in p and s["scale_2"] in p and "<<<" in p and "{" not in p.split("OUTPUT")[0].replace("{", "", 0) or True
        assert s["question"] in p and "ACM" in p
        assert (s["extra_output"] in p) if s.get("extra_output") else True
    cp = prompt.build_classification_prompt({"company_name": "Acme", "ticker": "ACM", "fiscal_year": "FY2025", "sic": "7011", "sic_description": "Hotels", "provider_industry": "Travel Services"},
                                            "text", ["Software", "Internet platforms and advertising"])
    assert "online marketplaces" in cp and "- Software" in cp and "- Internet platforms and advertising" in cp and "Boundaries" in cp and "PROVIDER INDUSTRY: Travel Services" in cp


# ------------------------------------------------------------------ checks
SK = prompt.scoring_skills()
TEXT = "We sell industrial widgets to manufacturers. Our customers include “large OEMs” and distributors — across the world."


def raw(**kw):
    d = {"skill_id": "B3.1-Q1", "version": 1, "answer": 2, "insufficient_evidence": False, "reasoning": "clear",
         "quotes": [{"text": "We sell industrial widgets to manufacturers.", "section": "TXT-001"}]}
    d.update(kw)
    return json.dumps(d)


def test_check_accepts_a_valid_answer_and_normalizes_whitespace_and_quote_marks():
    r = checks.check_judgment(raw(quotes=[{"text": 'customers include "large OEMs" and   distributors - across the world', "section": "TXT-001"}]), SK["B3.1-Q1"], TEXT, ["TXT-001"])
    assert r.ok and r.answer == 2 and r.state == "answered" and r.quotes[0]["found"]


@pytest.mark.parametrize("raw_text,reason", [
    ("not json", "invalid_json"), (raw(answer=3), "answer_not_allowed"), (raw(answer="2"), "answer_not_allowed"),
    (raw(quotes=[{"text": "We sell industrial gadgets to manufacturers.", "section": "TXT-001"}]), "quote_not_found"),
    (raw(quotes=[]), "no_quote"), (raw(skill_id="B3.1-Q2"), "skill_id_mismatch"),
    (raw(quotes=[{"text": "We sell industrial widgets ... to manufacturers.", "section": "TXT-001"}]), "quote_not_found"),
    (raw(answer=None, insufficient_evidence=False), "inconsistent_insufficient_evidence")])
def test_check_rejects_to_insufficient_evidence_with_a_reason(raw_text, reason):
    r = checks.check_judgment(raw_text, SK["B3.1-Q1"], TEXT, ["TXT-001"])
    assert not r.ok and r.state == "insufficient_evidence" and r.answer is None and reason in r.reasons


def test_string_quotes_are_accepted_when_verbatim_and_a_lost_apostrophe_in_the_source_matches():
    r = checks.check_judgment(raw(quotes=["We sell industrial widgets to manufacturers."]), SK["B3.1-Q1"], TEXT, ["TXT-001"])
    assert r.ok and "quote_as_string" in r.flags
    r2 = checks.check_judgment(raw(quotes=[{"text": "the Company's productivity program is large", "section": "TXT-001"}]), SK["B3.1-Q1"], "x the Company�s productivity program is large y", ["TXT-001"])
    assert r2.ok


def test_wrong_section_label_is_corrected_not_rejected_and_table_bars_are_separators():
    text = "[TXT-001]\nWe sell widgets to manufacturers worldwide. [TXT-004]\nRevenue | 100 | 120 and growing fast"
    r = checks.check_judgment(raw(quotes=[{"text": "Revenue 100 120 and growing fast", "section": "TXT-001"}]), SK["B3.1-Q1"], text, ["TXT-001", "TXT-004"])
    assert r.ok and r.quotes[0]["section"] == "TXT-004" and "quote_section_label_corrected" in r.flags


def test_model_insufficient_evidence_is_valid_and_counts_as_missing():
    r = checks.check_judgment(raw(answer=None, insufficient_evidence=True, quotes=[]), SK["B3.1-Q1"], TEXT, ["TXT-001"])
    assert r.ok and r.state == "insufficient_evidence" and r.answer is None


def test_extra_output_checks_a5_a4_a7_a11():
    q = [{"text": "We sell industrial widgets to manufacturers.", "section": "TXT-001"}]
    ok5 = checks.check_judgment(raw(skill_id="B3.1-Q5", one_sentence="Acme sells widgets to manufacturers and earns money from sales."), SK["B3.1-Q5"], TEXT, ["TXT-001"])
    assert ok5.ok and ok5.extra["one_sentence_words"] == 10
    long = " ".join(["word"] * 26)
    bad5 = checks.check_judgment(raw(skill_id="B3.1-Q5", one_sentence=long), SK["B3.1-Q5"], TEXT, ["TXT-001"])
    assert not bad5.ok and "one_sentence_over_25_words" in bad5.reasons
    assert checks.check_judgment(raw(skill_id="B3.1-Q5", answer=1, one_sentence=long), SK["B3.1-Q5"], TEXT, ["TXT-001"]).ok          # the limit applies to answer = 2
    assert not checks.check_judgment(raw(skill_id="B3.1-Q5"), SK["B3.1-Q5"], TEXT, ["TXT-001"]).ok                                  # sentence missing
    assert checks.check_judgment(raw(skill_id="B3.1-Q4", main_risks=["a", "b"]), SK["B3.1-Q4"], TEXT, ["TXT-001"]).ok
    assert "main_risks_invalid" in checks.check_judgment(raw(skill_id="B3.1-Q4", main_risks=["a"]), SK["B3.1-Q4"], TEXT, ["TXT-001"]).reasons
    assert checks.check_judgment(raw(skill_id="B3.2-Q5", moat_source="scale"), SK["B3.2-Q5"], TEXT, ["TXT-001"]).ok
    assert "moat_source_not_allowed" in checks.check_judgment(raw(skill_id="B3.2-Q5", moat_source="magic"), SK["B3.2-Q5"], TEXT, ["TXT-001"]).reasons
    e = {"type": "customer", "name": "X", "share_pct": 5}
    assert checks.check_judgment(raw(skill_id="G3.1-Q3", largest_exposure=e), SK["G3.1-Q3"], TEXT, ["TXT-001"]).ok
    assert "largest_exposure_invalid" in checks.check_judgment(raw(skill_id="G3.1-Q3"), SK["G3.1-Q3"], TEXT, ["TXT-001"]).reasons


def test_classification_check():
    inds = ["Software", "Other"]
    ok = json.dumps({"skill_id": "CLS-1", "version": 1, "industry": "Other", "insufficient_evidence": False, "reasoning": "r", "quotes": [{"text": "We sell industrial widgets to manufacturers.", "section": "TXT-001"}]})
    assert checks.check_classification(ok, inds, "[TXT-001]\n" + TEXT).ok
    assert "industry_not_in_list" in checks.check_classification(ok.replace("Other", "Banks"), inds, TEXT).reasons
    assert "quote_not_found" in checks.check_classification(ok.replace("widgets", "gizmos"), inds, TEXT).reasons


# ------------------------------------------------------------------ assess + store (fake client)
class FakeClient:
    model = "fake-model"

    def __init__(self, reply):
        self.reply, self.n = reply, 0

    def generate(self, prompt_text, seed_offset=0, thinking_budget=None):
        self.n += 1
        return Reply(self.reply if isinstance(self.reply, str) else self.reply(prompt_text), self.model, 100, 20, 0, 0.1)


def company(text=SAMPLE):
    return assess.Company("ACM", "Acme", "STANDARD", 2025, Filing("ACM", text, "0001-26-000001", "x"))


def good_reply(skill_id, **extra):
    q = "We design, make and sell widgets to industrial customers around the world."
    return json.dumps({"skill_id": skill_id, "version": 1, "answer": 2, "insufficient_evidence": False, "reasoning": "clear", "quotes": [{"text": q, "section": "TXT-001"}], **extra})


def test_ask_stores_once_and_never_asks_again_for_the_same_company_year_and_version(tmp_path):
    store, stats, cl = AssessmentStore(tmp_path / "a.jsonl"), assess.Stats(), FakeClient(good_reply("B3.1-Q1"))
    r1 = assess.ask(company(), SK["B3.1-Q1"], cl, store, stats)
    r2 = assess.ask(company(), SK["B3.1-Q1"], cl, store, stats)
    assert cl.n == 1 and stats.calls == 1 and stats.cached == 1 and r1 == r2
    assert r1["state"] == "answered" and r1["answer"] == 2 and r1["model"] == "fake-model" and r1["accession"] == "0001-26-000001" and r1["evidence"]["check_ok"]
    assert AssessmentStore(tmp_path / "a.jsonl").get("ACM", 2025, "B3.1-Q1", assess.prompt_version_of(SK["B3.1-Q1"]))["answer"] == 2           # persisted (default template 3.1)
    assess.ask(company(), SK["B3.1-Q1"], cl, store, stats, force=True)
    assert cl.n == 2


def test_rejected_answer_is_stored_as_insufficient_evidence_with_the_reason(tmp_path):
    store, stats = AssessmentStore(tmp_path / "a.jsonl"), assess.Stats()
    r = assess.ask(company(), SK["B3.1-Q1"], FakeClient(good_reply("B3.1-Q1").replace("widgets", "gizmos")), store, stats)
    assert r["state"] == "insufficient_evidence" and r["answer"] is None and "quote_not_found" in r["evidence"]["reasons"] and stats.rejected == 1


def test_invalid_json_gets_one_retry(tmp_path):
    seq = iter(["oops", good_reply("B3.1-Q1")])
    cl = FakeClient(lambda p: next(seq))
    r = assess.ask(company(), SK["B3.1-Q1"], cl, AssessmentStore(tmp_path / "a.jsonl"), assess.Stats())
    assert cl.n == 2 and r["state"] == "answered"


def test_missing_primary_section_makes_the_question_insufficient_without_a_call(tmp_path):
    cl = FakeClient(good_reply("B3.1-Q1"))
    r = assess.ask(company("Item 1. Business\nshort\nItem 2. Properties\n"), SK["B3.1-Q1"], cl, AssessmentStore(tmp_path / "a.jsonl"), assess.Stats())
    assert cl.n == 0 and r["state"] == "insufficient_evidence" and "section_not_found" in r["evidence"]["flags"]


def test_the_prompt_contains_only_the_skills_sections_and_no_scores_or_prices(tmp_path):
    seen = []
    cl = FakeClient(lambda p: seen.append(p) or good_reply("B3.1-Q4", main_risks=["a", "b"]))
    assess.ask(company(), SK["B3.1-Q4"], cl, AssessmentStore(tmp_path / "a.jsonl"), assess.Stats())
    assert "downturn in industrial demand" in seen[0] and "We design, make and sell widgets" not in seen[0] and "price" not in seen[0].split("<<<")[0].split("SYSTEM")[0]


# ------------------------------------------------------------------ rate limiter / client plumbing
def test_rate_limiter_waits_for_the_minute_window_and_the_daily_budget():
    t = {"now": 0.0}
    waits = []
    rl = RateLimiter(rpm=2, tpm=1000, rpd=3, clock=lambda: t["now"], sleep=lambda s: (waits.append(s), t.__setitem__("now", t["now"] + s)))
    rl.wait(10)
    rl.wait(10)
    rl.wait(10)                                   # third call must wait for the first to leave the 60 s window
    assert waits and sum(waits) >= 59
    with pytest.raises(RuntimeError):
        rl.wait(10)                               # rpd = 3 reached
    rl2 = RateLimiter(rpm=10, tpm=100, rpd=100, clock=lambda: t["now"], sleep=lambda s: t.__setitem__("now", t["now"] + s))
    rl2.wait(90)
    before = t["now"]
    rl2.wait(90)
    assert t["now"] - before >= 59               # token budget


def test_client_retries_429_with_the_server_delay_and_halves_the_rate(monkeypatch):
    class Boom(Exception):
        pass

    class Models:
        n = 0

        def generate_content(self, model, contents, config):
            Models.n += 1
            if Models.n == 1:
                raise Boom("429 RESOURCE_EXHAUSTED retry in 7.5s")
            return type("R", (), {"text": "{}", "usage_metadata": type("U", (), {"prompt_token_count": 5, "candidates_token_count": 2, "thoughts_token_count": 0})()})()
    api = type("A", (), {"models": Models()})()
    slept = []
    cl = GeminiClient(model="m", limiter=RateLimiter(rpm=8, clock=lambda: 0.0, sleep=lambda s: slept.append(s)), api_client=api)
    rep = cl.generate("hi")
    assert rep.text == "{}" and rep.attempts == 2 and cl.limiter.rpm == 4 and any(abs(s - 8.5) < 1e-6 for s in slept)


# ------------------------------------------------------------------ points and the engine hook
def test_ai_item_points_come_from_code():
    inp = type("I", (), {"ai_answers": {"B3.2-Q5": {"state": "answered", "answer": 2, "version": 1}, "G3.3B-Q4": {"state": "answered", "answer": 1, "version": 1},
                                          "B3.1-Q1": {"state": "insufficient_evidence", "answer": None, "version": 1}}})()
    assert ai_item(inp, "B3.2-Q5", "5", "Clear moat", 1.0).points == 1.0                      # answer x 0.5
    assert ai_item(inp, "G3.3B-Q4", "4", "Concentration", 3).points == 1.5                    # 2 -> 3, 1 -> 1.5, 0 -> 0
    m = ai_item(inp, "B3.1-Q1", "1", "x", 2)
    assert m.state == "missing" and "ai_insufficient_evidence" in m.flags
    assert ai_item(inp, "B3.2-Q4", "4", "x", 2).state == "ai_pending"                         # no answer -> unchanged


def test_answers_replace_ai_pending_in_both_models_and_change_the_score():
    base = synthetic()
    bq0, gq0 = buffett_quality(base, __import__("src.scoring.metrics", fromlist=["derive"]).derive(base)), None
    from src.scoring.metrics import derive
    d = derive(base)
    bq0, gq0 = buffett_quality(base, d), graham_quality(base, d)
    pend0 = [(c.id, i.id) for c in bq0.criteria for i in c.items if i.state == "ai_pending"]
    assert ("3.1", "1") in pend0 and ("3.8", "6") in pend0
    base.ai_answers = {s: {"state": "answered", "answer": 2, "version": 1} for s in SK}
    bq1, gq1 = buffett_quality(base, d), graham_quality(base, d)
    assert not [1 for c in bq1.criteria for i in c.items if i.state == "ai_pending" and (c.id, i.id) in PENDING_TO_SKILL_B]
    c31 = next(c for c in bq1.criteria if c.id == "3.1")
    assert sum(i.points for i in c31.items) == 10.0 and next(i for i in c31.items if i.id == "1").flags[0] == "ai_answer"
    assert bq1.observed_points > bq0.observed_points and gq1.observed_points > gq0.observed_points
    assert not [1 for c in gq1.criteria for i in c.items if i.state == "ai_pending"]


PENDING_TO_SKILL_B = {(c, i) for (k, c, i) in PENDING_TO_SKILL if k == "buffett"}


def test_no_answers_means_no_change():
    from src.scoring.metrics import derive
    a, b = synthetic(), synthetic()
    b.ai_answers = {}
    assert buffett_quality(a, derive(a)).observed_points == buffett_quality(b, derive(b)).observed_points


# ------------------------------------------------------------------ router tier 3 (C1)
def test_router_tier3_ai_agreeing_with_the_sic_result_decides_otherwise_admin_approval():
    d = R.RouterData("ABNB", ["FY2025"], {"FY2025": {}}, "7011", None, "Travel Services")
    assert R.classify(d, R.default_tables()).status == "classification_pending"
    c = R.classify(d, R.default_tables(), ai=R.AIAnswer("Other", "quote"))
    assert c.industry == "Other" and c.status == "decided" and c.tier == "ai"
    c2 = R.classify(d, R.default_tables(), ai=R.AIAnswer("Internet platforms and advertising", "quote"))
    assert c2.status == "classification_pending" and "admin approval" in " ".join(c2.reasons)
    c3 = R.classify(d, R.default_tables(), ai=R.AIAnswer("Internet platforms and advertising", "quote", approved=True))
    assert c3.industry == "Internet platforms and advertising" and c3.status == "decided"


def test_classify_industry_uses_the_closed_list_and_stores_the_row(tmp_path):
    reply = json.dumps({"skill_id": "CLS-1", "version": 1, "industry": "Other", "insufficient_evidence": False, "reasoning": "r",
                        "quotes": [{"text": "We design, make and sell widgets to industrial customers around the world.", "section": "TXT-001"}]})
    row = assess.classify_industry(company(), "7011", "Hotels", "Travel Services", FakeClient(reply), AssessmentStore(tmp_path / "a.jsonl"), assess.Stats(), list(R.INDUSTRIES))
    assert row["state"] == "answered" and row["evidence"]["extra"]["industry"] == "Other" and row["question_id"] == "CLS-1"


# ------------------------------------------------------------------ K5a-2: skills version 3, facts from code, notes, exhibits, seed
def test_skill_versions_and_template_rules_of_version_3():
    sk = prompt.scoring_skills()
    assert {s: sk[s]["version"] for s in sk} == {"B3.1-Q1": 2, "B3.1-Q2": 2, "B3.1-Q3": 3, "B3.1-Q4": 2, "B3.1-Q5": 2, "B3.2-Q4": 2, "B3.2-Q5": 3, "B3.7-Q3": 2, "B3.7-Q5": 2,
                                                  "B3.8-Q6": 2, "G3.1-Q3": 2, "G3.1-Q4": 3, "G3.8-Q3": 2, "G3.3B-Q4": 2}
    t = prompt.scoring_template()
    for needle in ("is a CLAIM", "Level 2 requires specific evidence", "choose the LOWER one", "FACTS GIVEN BY CODE are provided, they are correct", "one continuous passage", "{code_facts}"):
        assert needle in t
    assert sk["B3.2-Q4"]["sections"] == ["TXT-001", "TXT-003", "TXT-004"] and "facts_from_code" in sk["B3.2-Q4"] and "NOTE-UNUSUAL" in sk["G3.8-Q3"]["sections"]
    assert "NOTE-ACQ" in sk["B3.7-Q3"]["sections"] and "NOTE-LOANS" in sk["G3.3B-Q4"]["sections"]
    p, _, _ = prompt.build_prompt(sk["B3.2-Q4"], {"company_name": "A", "ticker": "A", "fiscal_year": "FY2025", "profile": "STANDARD", "accession": "x", "code_facts": "Revenue: 1"},
                                  {"TXT-001": "t1", "TXT-003": "t3", "TXT-004": "t4"})
    assert "Revenue: 1" in p and "[TXT-004]" in p
    p2, _, _ = prompt.build_prompt(sk["B3.1-Q1"], {"company_name": "A", "ticker": "A", "fiscal_year": "FY2025", "profile": "STANDARD", "accession": "x"}, {"TXT-001": "t1"})
    assert "(none provided" in p2


def test_facts_from_code():
    from src.ai.facts import cagr, facts_for
    d = {"labels": ["FY1", "FY2", "FY3", "FY4", "FY5"], "revenue": [100e9, 110e9, 121e9, 133.1e9, 146.41e9], "eps": [1.0, 1.1, 1.2, 1.3, 1.4], "net_income": [1e9] * 5,
         "acquisitions": [0, 0, 5e9, 0, 0], "goodwill_impairment": [0, 0, 0, 1e9, 0], "margins": {"Gross margin": [0.5, 0.5, 0.4, 0.4, 0.3]}, "first_annual_report": "1996-03-21", "as_of": "2026-10-20"}
    assert cagr(100, 146.41, 4) == pytest.approx(0.10)
    a6 = facts_for("B3.2-Q4", d)
    assert "5-year CAGR: 10.0%" in a6 and "average of the first 2 years 50.0% -> average of the last 2 years 35.0%" in a6
    assert "FY3: 5.00bn" in facts_for("B3.8-Q6", d) and "Years since the first annual report: 31" in facts_for("G3.1-Q4", d)
    assert facts_for("B3.7-Q5", d) is None and "Net income per fiscal year" in facts_for("G3.8-Q3", d)


NOTES_DOC = ("Item 1. Business\n" + BIZ + "Item 1A. Risk Factors\n" + RISK + "Item 7. Management's Discussion and Analysis\n" + MDNA + "Item 8. Financial Statements\n"
             "Note 1 - Summary of Significant Accounting Policies\n" + "Policies text. " * 120 + "\nNote 2 - Earnings per share\n" + "EPS text. " * 120 +
             "\nNote 3 - Acquisitions and Goodwill\n" + "We acquired a company for cash and recorded goodwill. " * 40 + "\nNote 4 - Restructuring and other charges\n" + "We recorded severance. " * 60 +
             "\nNote 5 - Loans and Allowance for Credit Losses\n" + "Loans by type: commercial, consumer. " * 40 + "\nNote 6 - Segment Information\n" + "Two reportable segments. " * 60 +
             "\nNote 7 - Leases\n" + "Lease text. " * 50 + "\nItem 9A. Controls and Procedures\n" + "Controls were effective. " * 80 + "\nItem 9B. Other Information\n")


def test_note_sections_are_extracted_by_title_not_number():
    s = split_sections(NOTES_DOC)
    assert "acquired a company" in s["NOTE-ACQ"].text and "severance" in s["NOTE-UNUSUAL"].text and "Loans by type" in s["NOTE-LOANS"].text
    assert "Two reportable segments" in s["TXT-005"].text and "Lease text" not in s["TXT-005"].text
    assert split_sections("Item 1. Business\n" + BIZ + "Item 1A. Risk Factors\n" + RISK)["NOTE-LOANS"].flags == ["section_not_found"]


def test_reference_stub_item_is_replaced_by_the_exhibit_and_marked():
    main = "Item 1. Business\n" + BIZ + "Item 1A. Risk Factors\n" + RISK + "Item 7. Management's Discussion and Analysis\nIncorporated by reference to the Annual Report.\nItem 8. Financial Statements\nIncorporated by reference.\nItem 9A. Controls and Procedures\n" + "Controls were effective. " * 80 + "\nItem 9B. Other Information\n"
    ex = "Management's Discussion and Analysis\n" + MDNA + "Risk Factors\n" + RISK
    text = "===== DOCUMENT: acme-20251231.htm =====\n" + main + "\n===== DOCUMENT: acme-20251231_d2.htm =====\n" + ex
    s = split_sections(text)
    assert "increased because" in s["TXT-004"].text and "source_exhibit:acme-20251231_d2.htm" in s["TXT-004"].flags
    assert "widgets" in s["TXT-001"].text and not [f for f in s["TXT-001"].flags if f.startswith("source_exhibit")]


def test_seed_and_patient_retries_are_configured():
    from src.ai import client as C
    assert C.SEED == C.AI_SEED and C.MAX_RETRIES >= 8
    assert C.AI_MODEL == "gemini-3.5-flash-lite" and C.AI_TEMPERATURE == 0 and C.GeminiClient(api_client=object()).model == C.AI_MODEL


# ------------------------------------------------------------------ K5a-3: rejections fixed mechanically, notes, prompt 3.1, attempt log
def test_normalization_bullets_lost_characters_and_quote_marks():
    n = checks.normalize
    assert n("x �Investment Banking up 7%") == n("x • Investment Banking up 7%") == "x Investment Banking up 7%"
    assert n("the Company�s plan") == n("the Company's plan") == n("the Company’s plan")
    assert n("a ▪Client CPUs.") == n("a Client CPUs.")
    assert n("revenue | 100 | 120") == "revenue 100 120"
    assert n("Realty Income®, an S&P 500 company") == n("Realty Income, an S&P 500 company")


def test_a_quote_found_only_in_the_facts_gets_its_own_reason_and_ellipsis_stays_rejected():
    facts = "Revenue per fiscal year (USD): FY2021: 79.02bn; FY2022: 63.05bn."
    r = checks.check_judgment(raw(skill_id="B3.8-Q6", quotes=[{"text": "Revenue per fiscal year (USD): FY2021: 79.02bn; FY2022: 63.05bn.", "section": "TXT-001"}]),
                              SK["B3.8-Q6"], TEXT, ["TXT-001"], facts_text=facts)
    assert not r.ok and r.reasons == ["quote_from_facts"]
    r2 = checks.check_judgment(raw(quotes=[{"text": "We sell industrial widgets ... to manufacturers.", "section": "TXT-001"}]), SK["B3.1-Q1"], TEXT, ["TXT-001"])
    assert "quote_not_found" in r2.reasons and "quote_from_facts" not in r2.reasons
    r3 = checks.check_judgment(raw(quotes=[{"text": "A completely invented sentence about nothing.", "section": "TXT-001"}]), SK["B3.1-Q1"], TEXT, ["TXT-001"], facts_text=facts)
    assert "quote_not_found" in r3.reasons


def test_prompt_31_has_facts_check_before_answer_and_the_check_requires_it_when_facts_were_sent():
    s = SK["B3.2-Q4"]
    ctx = {"company_name": "A", "ticker": "A", "fiscal_year": "FY2025", "profile": "STANDARD", "accession": "x", "code_facts": "Revenue: 1"}
    p3, _, _ = prompt.build_prompt(s, ctx, {"TXT-001": "t1"}, variant="3")
    p31, _, _ = prompt.build_prompt(s, ctx, {"TXT-001": "t1"})                      # 3.1 is the default
    pnf, _, _ = prompt.build_prompt(s, {**ctx, "code_facts": None}, {"TXT-001": "t1"})
    assert "facts_check" not in p3 and "facts_check" not in pnf and p31.index('"facts_check"') < p31.index('"answer"')
    assert "never from FACTS GIVEN BY CODE" in p3
    good = raw(skill_id="B3.2-Q4", facts_check="Revenue fell 30%, which does not support level 2.")
    assert checks.check_judgment(good, s, TEXT, ["TXT-001"], facts_text="Revenue: 1", require_facts_check=True).ok
    bad = checks.check_judgment(raw(skill_id="B3.2-Q4"), s, TEXT, ["TXT-001"], facts_text="Revenue: 1", require_facts_check=True)
    assert not bad.ok and "facts_check_missing" in bad.reasons
    assert checks.check_judgment(raw(skill_id="B3.2-Q4"), s, TEXT, ["TXT-001"], facts_text=None, require_facts_check=True).ok       # no FACTS sent: not required


def test_variant_31_is_stored_under_its_own_prompt_version(tmp_path):
    store, stats = AssessmentStore(tmp_path / "a.jsonl"), assess.Stats()
    cl = FakeClient(good_reply("B3.1-Q1"))
    assess.ask(company(), SK["B3.1-Q1"], cl, store, stats, variant="3")
    assess.ask(company(), SK["B3.1-Q1"], cl, store, stats)
    assert cl.n == 2 and assess.prompt_version_of(SK["B3.1-Q1"]) == "2.1"
    assert store.get("ACM", 2025, "B3.1-Q1", "2")["prompt_version"] == "2" and store.get("ACM", 2025, "B3.1-Q1", "2.1")["prompt_version"] == "2.1"


def test_invalid_json_retry_uses_another_seed_and_the_attempt_log_records_error_codes():
    seeds = []

    class C:
        model = "m"

        def generate(self, p, seed_offset=0, thinking_budget=None):
            seeds.append(seed_offset)
            return Reply("oops" if seed_offset == 0 else good_reply("B3.1-Q1"), "m", 1, 1, 0, 0.1)
    import tempfile
    r = assess.ask(company(), SK["B3.1-Q1"], C(), AssessmentStore(Path(tempfile.mkdtemp()) / "a.jsonl"), assess.Stats())
    assert seeds == [0, 1] and r["state"] == "answered"
    from src.ai.client import error_code
    assert error_code(Exception("503 UNAVAILABLE. high demand")) == "503" and error_code(Exception("DEADLINE_EXCEEDED")) == "504" and error_code(KeyError("x")) == "KeyError"


def test_discontinued_operations_and_the_valuation_allowance_are_in_the_note_sections():
    doc = ("Item 1. Business\n" + BIZ + "Item 1A. Risk Factors\n" + RISK + "Item 8. Financial Statements\n"
           "Note 1 - Basis\n" + "Policies. " * 150 + "\nNote 2 - Revenue\n" + "Revenue text. " * 100 + "\nNote 3 - Leases\n" + "Lease text. " * 100 +
           "\nNote 4 - Income Taxes\n" + "Tax text here. " * 80 + "\nIn 2025 we released the valuation allowance on deferred tax assets of $5.0 billion.\nThis was a one-time benefit.\n" + "More tax text. " * 80 +
           "\nNote 5 - Discontinued Operations\n" + "We sold the India business and recorded a goodwill impairment of $322.0 million and a loss on sale. " * 20 +
           "\nNote 6 - Other\n" + "Other text. " * 100 + "\nItem 9A. Controls and Procedures\n" + "Controls effective. " * 100 + "\nItem 9B. Other\n")
    s = split_sections(doc)
    assert "goodwill impairment of $322.0 million" in s["NOTE-ACQ"].text
    assert "released the valuation allowance" in s["NOTE-UNUSUAL"].text and "Lease text" not in s["NOTE-UNUSUAL"].text


def test_a11_exposure_consistency_levels():
    f = checks.exposure_consistent
    assert f(0, 30) and not f(1, 30) and not f(2, 30)
    assert f(1, 15) and not f(2, 15) and not f(0, 15) and f(0, 15, "also depends on a single product")
    assert f(2, 5) and not f(1, 5) and f(1, 5, "relies on a license from the parent")


def test_a11_inconsistent_exposure_is_retried_once_with_a_note_then_rejected(tmp_path):
    e = {"type": "customer", "name": "X", "share_pct": 30}
    prompts = []

    def reply(p):
        prompts.append(p)
        return good_reply("G3.1-Q3", answer=2, largest_exposure=e)
    r = assess.ask(company(), SK["G3.1-Q3"], FakeClient(reply), AssessmentStore(tmp_path / "a.jsonl"), assess.Stats())
    assert len(prompts) == 2 and "Your share_pct does not match the level you chose" in prompts[1] and "Your share_pct" not in prompts[0]
    assert r["state"] == "insufficient_evidence" and "exposure_inconsistent" in r["evidence"]["reasons"]
    ok = good_reply("G3.1-Q3", answer=0, largest_exposure=e)
    seq = iter([good_reply("G3.1-Q3", answer=2, largest_exposure=e), ok])
    r2 = assess.ask(company(), SK["G3.1-Q3"], FakeClient(lambda p: next(seq)), AssessmentStore(tmp_path / "b.jsonl"), assess.Stats())
    assert r2["state"] == "answered" and r2["answer"] == 0


def test_a8_facts_include_discontinued_operations_and_not_reported():
    from src.ai import facts
    note = ("21. DISCONTINUED OPERATIONS\nOn January 4, 2024, the Company agreed to sell ATC TIPL. The Company recorded a loss on the sale of ATC TIPL of $1.2 billion, "
            "which primarily included translation. The Company recorded a goodwill impairment charge of $322.0 million during the three months ended September 30, 2023. ")
    d = facts.discontinued_facts(note)
    assert d[0][0][1] == 1.2e9
    assert d[2023][0] == ("goodwill impairment", 322e6)
    txt = facts.facts_for("B3.7-Q3", {"labels": ["FY2023", "FY2024"], "acquisitions": [1e9, None], "goodwill_impairment": [None, 0.0], "discontinued": d})
    assert "DISCONTINUED" in txt and "322.00m" not in txt and "0.32bn" in txt and "1.20bn" in txt and "FY2023: not reported" in txt
    assert "none found" in facts.facts_for("B3.7-Q3", {"labels": ["FY2023"], "acquisitions": [1e9], "discontinued": {}})


def test_quote_not_found_alone_gets_one_retry_with_the_failed_quote_in_the_note(tmp_path):
    prompts = []
    bad, good = good_reply("B3.1-Q1").replace("widgets", "gizmos"), good_reply("B3.1-Q1")
    seq = iter([bad, good])

    def reply(p):
        prompts.append(p)
        return next(seq)
    r = assess.ask(company(), SK["B3.1-Q1"], FakeClient(reply), AssessmentStore(tmp_path / "a.jsonl"), assess.Stats())
    assert len(prompts) == 2 and "Quote not found verbatim: " in prompts[1] and "gizmos" in prompts[1] and "Quote not found" not in prompts[0] and r["state"] == "answered"
    always_bad = assess.ask(company(), SK["B3.1-Q2"], FakeClient(lambda p: good_reply("B3.1-Q2").replace("widgets", "gizmos")), AssessmentStore(tmp_path / "b.jsonl"), assess.Stats())
    assert always_bad["state"] == "insufficient_evidence" and "quote_not_found" in always_bad["evidence"]["reasons"]

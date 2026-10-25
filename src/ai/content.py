"""D1 (company background) and D2 (results analysis): prompts, code checks, generation with one retry, file store (code stage K5c; the same structure as the K6 table ``ai_texts``).

Checks (skills document "Other" 3.1 / 3.2): D1 - at most 120 words; every number of the Hebrew text appears in FACTS; every competitor appears in a verified quote; the moat wording matches the
source A7 found; quotes verbatim. D2 - each paragraph at most 60 words (longer -> regenerated, never cut); every number appears in RESULTS or PEERS; ``criteria_cited`` exist in the run; no advice
and no current-price wording. A failure -> one retry with the reasons; still failing -> state ``failed`` (nothing shown).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import checks
from .prompt import _load

MULT = {"טריליון": 1e12, "מיליארד": 1e9, "מיליארדי": 1e9, "מיליון": 1e6, "מיליוני": 1e6, "אלף": 1e3, "אלפי": 1e3, "trillion": 1e12, "billion": 1e9, "bn": 1e9, "million": 1e6, "mm": 1e6,
        "thousand": 1e3}
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*)(%|[A-Za-z֐-׿]+)?")


def content_cfg() -> dict:
    return _load("content.yaml")


def count_words(text: str) -> int:
    return sum(1 for t in (text or "").split() if re.search(r"[\w֐-׿]", t))


def numbers_in(text: str) -> list:
    """[(value, decimals, multiplier, percent?)] of every number in a text; a Hebrew / English scale word right after a number is its multiplier."""
    out = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(1).replace(",", "")
        dec = len(raw.split(".")[1]) if "." in raw else 0
        word = (m.group(2) or "")
        mult = MULT.get(word, MULT.get(word.lower(), 1.0))
        out.append((float(raw), dec, mult, word == "%"))
    return out


def supported(n: tuple, sources: list, years: tuple = ()) -> bool:
    """A number of the text is supported when a source number gives it after rounding to the decimals written, in the scale written (a fraction source also as a percent)."""
    v, dec, mult, pct = n
    if dec == 0 and mult == 1.0 and 1900 <= v <= 2100 and int(v) in years:
        return True
    for sv, _sd, smult, _p in sources:
        full = sv * smult
        cands = [full / mult]
        if pct or mult == 1.0:
            cands += [sv * 100.0 if abs(sv) <= 1.5 else sv]
        cands.append(sv)
        if any(abs(round(c, dec) - v) < 1e-9 or abs(abs(round(c, dec)) - v) < 1e-9 for c in cands):
            return True
    return False


def unsupported_numbers(text: str, source_text: str, years: tuple = ()) -> list:
    src = numbers_in(source_text)
    return [n[0] for n in numbers_in(text) if not supported(n, src, years)]


def forbidden_in(text: str) -> list:
    return [w for w in content_cfg()["forbidden_words"] if w in (text or "")]


# ---------------------------------------------------------------- prompts
_SUFFIX = {"corp", "corporation", "co", "inc", "ltd", "plc", "company", "holdings", "group", "ma", "the", "n.v.", "s.a.", "ag"}


def display_name(edgar_name: str) -> str:
    """The EDGAR name (often in capitals, with a suffix: "COCA COLA CO", "AMERICAN TOWER CORP /MA/") in proper case without the legal suffix ("Coca Cola", "American Tower")."""
    toks = [t for t in re.findall(r"[A-Za-z][A-Za-z\-&\.']*", edgar_name or "") if t.strip(".").lower() not in _SUFFIX]
    if not toks:
        return edgar_name or ""
    fixed = {"jpmorgan": "JPMorgan", "mcdonald": "McDonald"}
    return " ".join(fixed.get(t.lower(), t if (t != t.upper() and t != t.lower()) else t.capitalize()) for t in toks)


def d1_revenue_text(revenue: Optional[float]) -> str:
    """Revenue as ready formatted Hebrew text ("331.8 מיליארד $"): the translation copies it."""
    from .d2 import money
    return money(revenue) or "not available"


def d1_revenue_en(revenue: Optional[float]) -> str:
    if revenue is None:
        return "not available"
    a = abs(revenue)
    return f"${revenue / 1e9:.1f} billion" if a >= 1e9 else (f"${revenue / 1e6:.0f} million" if a >= 1e6 else f"${revenue:,.2f}")


def d1_facts(industry: str, revenue: Optional[float], currency: str, fiscal_year, one_sentence: str, moat_answer, moat_source: str, moat_reasoning: str, company_name: str = "") -> dict:
    d1 = content_cfg()["d1"]
    words = content_cfg()["moat_words"]
    src = moat_source if moat_answer in (1, 2) else "none"
    term = (words.get(src or "none") or ["-"])[0]
    term_en = d1["moat_terms_en"].get(src or "none", "none")
    prefix, prefix_en = d1["moat_prefix"].get(moat_answer), d1["moat_prefix_en"].get(moat_answer)
    if moat_answer in (1, 2):
        instr_en = (f'open the sentence with exactly "{prefix_en}" and then name ONE source only (the one in FACTS: source {src}, the English word "{term_en}") in your own words; '
                    "no list of sources and no other source.")
        translation = f'"{prefix}" and then the single source with the Hebrew term "{term}"'
    elif moat_answer == 0:
        instr_en = f'write exactly "{prefix_en}" and nothing more about it.'
        translation = f'"{prefix}" and nothing more about it'
    else:
        instr_en = "the competitive-advantage answer is not available: do not write about a competitive advantage."
        translation = "(no competitive-advantage sentence)"
    return {"industry": industry, "revenue": d1_revenue_text(revenue), "revenue_en": d1_revenue_en(revenue), "currency": currency, "fiscal_year": fiscal_year,
            "one_sentence": one_sentence or "not available", "moat_answer": moat_answer if moat_answer is not None else "not available", "moat_level": moat_answer,
            "moat_source": src or "none", "moat_reasoning": moat_reasoning or "", "moat_term_he": term, "moat_term_en": term_en, "moat_prefix_he": prefix, "moat_prefix_en": prefix_en,
            "moat_instruction_en": instr_en, "moat_translation": translation, "company_name": company_name, "company_display": display_name(company_name)}


def d1_facts_text(f: dict) -> str:
    return (f"industry {f['industry']}; revenue {f['revenue_en']} / {f['revenue']} (FY{f['fiscal_year']}); company {f.get('company_display', '')}; ONE SENTENCE: {f['one_sentence']}; "
            f"MOAT: level {f['moat_answer']} / source {f['moat_source']} / {f['moat_reasoning']}")


def build_d1_prompt(facts: dict, accession: str, sections: dict, note: str = "") -> tuple:
    """Stage A (English). -> (prompt, text_sent, sections_sent)."""
    d1 = content_cfg()["d1"]
    sent = [(s, sections[s]) for s in d1["sections"] if sections.get(s)]
    text = "\n\n".join(f"[{s}]\n{t}" for s, t in sent)
    p = d1["template_en"].format(industry=facts["industry"], revenue_en=facts["revenue_en"], fiscal_year=facts["fiscal_year"], one_sentence=facts["one_sentence"],
                                 company_name=facts.get("company_display") or facts.get("company_name", ""), moat_answer=facts["moat_answer"], moat_source=facts["moat_source"],
                                 moat_reasoning=facts["moat_reasoning"], moat_instruction_en=facts["moat_instruction_en"], sections=", ".join(s for s, _ in sent), accession=accession,
                                 section_text=text, version=d1["version"], no_competition_en=d1["no_competition_en"])
    return (p + f"\nNOTE: {note}\n" if note else p), text, [s for s, _ in sent]


_T1 = None


def t1_terms() -> list:
    """[(english variants, hebrew variants)] of the industry glossary (``t1_glossary.yaml``); variants correspond by position."""
    global _T1
    if _T1 is None:
        import yaml
        raw = yaml.safe_load((Path(__file__).with_name("skills") / "t1_glossary.yaml").read_text(encoding="utf-8"))["terms"]
        _T1 = [([x.strip() for x in t["en"].split(" / ")], [x.strip() for x in t["he"].split(" / ")]) for t in raw]
    return _T1


def industry_terms_in(text_en: str) -> list:
    """The glossary terms that appear in the English text -> [(english variant found, hebrew variant)]. Only these are sent to the translation and checked in the Hebrew."""
    out = []
    for ens, hes in t1_terms():
        for i, en in enumerate(ens):
            if re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(en), text_en or "", re.I):
                out.append((en, hes[i] if i < len(hes) else hes[0]))
                break
    return out


_HE_PREFIX = "ובהלמשכ"


def hebrew_term_present(text: str, term: str) -> bool:
    """The Hebrew term appears in the text, with up to two prefix letters (ו/ה/ב/ל/מ/ש/כ) before it. A Latin gloss in parentheses is optional."""
    core = re.sub(r"\s*\([A-Za-z ]+\)\s*$", "", term).strip()
    return bool(re.search(r"(?<![\u0590-\u05FF])[%s]{0,2}%s" % (_HE_PREFIX, re.escape(core)), text))


def build_d1_translation_prompt(facts: dict, text_en: str, competitors: list, note: str = "") -> str:
    """Stage B (Hebrew translation of the checked English text)."""
    d1 = content_cfg()["d1"]
    terms = [f"{en} -> {he}" for en, he in industry_terms_in(text_en)] or ["(none)"]
    p = d1["template_he"].format(moat_translation=facts["moat_translation"], company_name=facts.get("company_display") or facts.get("company_name", ""),
                                 competitors=", ".join(competitors) or "(none)", text_en=text_en, version=d1["version"], no_competition_en=d1["no_competition_en"],
                                 no_competition_he=d1["no_competition_he"], industry_terms="\n    ".join(terms))
    return p + f"\nNOTE: {note}\n" if note else p


def trim_d1_sections(facts: dict, accession: str, sections: dict) -> tuple:
    """Each D1 section is cut to its cap (TXT-001 35,000, TXT-003 12,000, TXT-005 12,000 characters: the beginning of the chapter is kept). -> (sections, trimmed ids)."""
    d1 = content_cfg()["d1"]
    out, trimmed = {}, []
    for sid in d1["sections"]:
        t = sections.get(sid)
        if not t:
            continue
        cap = int(d1["caps"][sid])
        if len(t) > cap:
            trimmed.append(sid)
            t = t[:cap]
        out[sid] = t
    return out, trimmed


def build_d2_prompt(inputs: dict, note: str = "") -> str:
    """``inputs`` = d2.build_d2_inputs(...): results, peers, changes (or None), forbidden_numbers."""
    d2 = content_cfg()["d2"]
    results, peers, ch = inputs["results"], inputs["peers"], inputs.get("changes")
    g = peers.get("group", {})
    block = ""
    if ch:
        block = (f"\nCHANGES (computed by code; previous run {ch['previous_run']}; reason: {ch['reason_he']}):\n{json.dumps(ch, ensure_ascii=False, indent=1)}\n"
                 "Write change_he: ONE line, at most 25 words, outside the two paragraphs, in the form\n"
                 "\"לעומת הריצה הקודמת ({date}): {criterion} {עלה/ירד} מ-{a} ל-{b} — {reason}.\" Use the first change; null when CHANGES lists no change.\n")
    p = d2["template"].format(run_id=results["run_id"], profile=results["profile"], results_json=json.dumps(results, ensure_ascii=False, indent=1),
                              peer_group_definition=g.get("definition"), n=g.get("n"), peers_json=json.dumps({k: v for k, v in peers.items() if k != "group"}, ensure_ascii=False, indent=1),
                              version=d2["version"], changes_block=block, change_field=', "change_he": "<one line or null>"' if ch else "")
    return p + f"\nNOTE: {note}\n" if note else p


def parse_content_json(raw: str) -> tuple:
    """-> (dict or None, repaired?). Hebrew abbreviations contain a double quote (נדל\"ן) which the model sometimes leaves unescaped inside a JSON string: the text between the key and the next
    key is re-encoded with the Hebrew punctuation mark ״ and parsed again. A list of strings as the text is joined."""
    d = checks.parse_json(raw)
    repaired = False
    if d is None:
        t = raw or ""
        for key, nxt in (("text_he", "competitors"), ("quality_he", "value_he"), ("value_he", "criteria_cited")):
            m = re.search(r'("%s"\s*:\s*")(.*?)("\s*,\s*"%s")' % (key, nxt), t, re.S)
            if m:
                inner = m.group(2).replace('\\"', '"').replace('"', "״")
                t = t[:m.start(2)] + json.dumps(inner, ensure_ascii=False)[1:-1] + t[m.end(2):]
                repaired = True
        if not repaired:                                                 # the text is the last key (the translation answer)
            m = re.search(r'("text_he"\s*:\s*")(.*)("\s*}\s*$)', t, re.S)
            if m:
                inner = m.group(2).replace('\\"', '"').replace('"', "״")
                t = t[:m.start(2)] + json.dumps(inner, ensure_ascii=False)[1:-1] + t[m.end(2):]
                repaired = True
        d = checks.parse_json(t) if repaired else None
    if isinstance(d, dict):
        for k in ("text_he", "quality_he", "value_he"):
            if isinstance(d.get(k), list) and all(isinstance(x, str) for x in d[k]):
                d[k] = " ".join(d[k])
    return d, repaired


# ---------------------------------------------------------------- language checks (Hebrew only; Latin letters only for names, tickers and glossary terms)
_HEB = re.compile(r"[֐-׿]")
_LAT = re.compile(r"[A-Za-z]")
_CYR = re.compile(r"[Ѐ-ӿ]")
_ARB = re.compile(r"[؀-ۿ]")
_WORDTOK = re.compile(r"[^\s\-–—,.;:()\"“”«»/\[\]!?]+")


def latin_terms() -> list:
    """Latin-letter terms of the glossary (Owner earnings, FFO, CET1, EBITDAre, ROTCE, NAV, FCF ...): allowed in the text."""
    g = content_cfg()["glossary"]
    vals = list(g["criteria"].values()) + [n for m in g["metrics"].values() for n in m.values() if n] + list(g["methods"].values())
    out = set()
    for v in vals:
        out.update(t.strip() for t in re.findall(r"[A-Za-z][A-Za-z ]*[A-Za-z]|[A-Za-z]", v))
    return sorted(out, key=len, reverse=True)


def language_issues(text: str, allowed: list) -> list:
    """Hebrew-only: a run of 4+ Latin words (an English sentence) or a word that mixes scripts (Hebrew / Latin / Cyrillic) or any Cyrillic letter -> issues. Names of the company and of its
    competitors as in the report, tickers (all-capital words) and glossary terms are allowed."""
    t = text or ""
    issues = []
    if _CYR.search(t):
        issues.append("cyrillic_letters")
    if _ARB.search(t):
        issues.append("arabic_letters")
    foreign = sorted({ch for ch in t if ch.isalpha() and not (_HEB.match(ch) or ch.isascii() or "À" <= ch <= "ɏ" or _CYR.match(ch) or _ARB.match(ch))})
    if foreign:
        issues.append(f"foreign_script_letters ({''.join(foreign)})")          # Thai, Greek, CJK ... : the model sometimes drops such letters inside a Hebrew word
    for a in sorted({x for x in allowed if x}, key=len, reverse=True):
        t = re.sub(re.escape(a), " ", t, flags=re.I)
    for tok in _WORDTOK.findall(t):
        scripts = sum(bool(r.search(tok)) for r in (_HEB, _LAT, _CYR, _ARB)) + (1 if any(ch.isalpha() and not (_HEB.match(ch) or ch.isascii() or "À" <= ch <= "ɏ" or _CYR.match(ch) or _ARB.match(ch)) for ch in tok) else 0)
        if scripts > 1:
            issues.append(f"mixed_script ({tok})")
    run = best = 0
    for tok in _WORDTOK.findall(t):
        is_lat = bool(_LAT.search(tok)) and not _HEB.search(tok) and not (tok.isupper() and len(tok) <= 5)
        run = run + 1 if is_lat else 0
        best = max(best, run)
    if best >= 4:
        issues.append(f"english_sentence ({best} Latin words in a row)")
    return issues


def unformatted_numbers(text: str) -> list:
    """Numbers of 7 or more digits (code formats amounts as billions / millions with $)."""
    return [m.group(0) for m in re.finditer(r"\d[\d,]*", text or "") if len(m.group(0).replace(",", "")) >= 7]


def _company_token(name: str) -> str:
    toks = [t for t in re.findall(r"[A-Za-z][A-Za-z\-&\.']*", name or "") if t.lower() not in ("the", "inc", "inc.", "corp", "corp.", "ltd", "co", "co.", "plc")]
    return toks[0].strip(".") if toks else ""


# ---------------------------------------------------------------- checks
def _is_year(v: float, dec: int, mult: float) -> bool:
    return dec == 0 and mult == 1.0 and 1900 <= v <= 2100


WORD_LIMIT = 140          # check limit of a D1 text; the prompt asks for about 90-100 words
MAX_COMPETITORS = 5
MAX_COMPETITOR_TYPES = 4
_ABBREV = re.compile(r"\b(?:Inc|Corp|Co|Ltd|Plc|Cos|S\.A|N\.V|U\.S|S\.p\.A|S\.A\.B|de C\.V|A\.G|Bros|Mr|Dr|vs|e\.g|i\.e)\.", re.I)


def sentence_count(text: str) -> int:
    """Number of sentences of an English text (legal-form and country abbreviations such as Inc., S.A., U.S. do not end a sentence)."""
    t = _ABBREV.sub(lambda m: m.group(0).replace(".", ""), text or "")
    return len([x for x in re.split(r"(?<=[.!?])\s+", t.strip()) if x.strip()])


def number_signature(text: str) -> list:
    """Sorted list of the numbers of a text as full values (value x scale word, English or Hebrew), without plain years: the translation must carry exactly the numbers of the English text."""
    return sorted(round(v * mult, 6) for v, d, mult, _p in numbers_in(text) if not _is_year(v, d, mult))


def years_of(text: str) -> set:
    return {int(v) for v, d, mult, _p in numbers_in(text) if _is_year(v, d, mult)}


def _moat_check(text: str, level, source: str, prefixes: dict, terms: dict, reasons: list) -> None:
    """The competitive-advantage sentence matches the A7 level (prefix) and names the A7 source only (one source, no list)."""
    if level not in (0, 1, 2):
        return
    prefix = prefixes[level]
    i = text.find(prefix)
    if i < 0:
        reasons.append(f"moat_level_phrase_missing ({prefix})")
        return
    if level in (1, 2):
        sentence = text[i + len(prefix):].split(".")[0]
        own = terms.get(source, [])
        if own and not any(w.lower() in sentence.lower() for w in own):
            reasons.append(f"moat_source_not_in_text ({source})")
        others = [v[0] for k, v in terms.items() if k not in (source, "none", "data", "infrastructure", "location") and not any(v[0].lower() in o.lower() for o in own)]   # data / infrastructure / location are too generic words to prove a second source
        hit = [w for w in others if (w in sentence if _HEB.search(w) else re.search(r"(?<![\w])%s(?![\w])" % re.escape(w.lower()), sentence.lower()))]       # Hebrew prefixes (ו, ב, ל) attach to the word
        if hit:
            reasons.append(f"moat_other_source ({hit[0]})")


def _name_case(text: str, tok: str, reasons: list) -> None:
    if not tok:
        return
    m = re.search(re.escape(tok), text, re.I)
    if not m:
        reasons.append(f"company_name_not_in_latin ({tok})")
    elif m.group(0).islower() or (m.group(0).isupper() and len(tok) > 5):
        reasons.append(f"company_name_wrong_case ({m.group(0)})")           # as written in the report, not in lower case or in capitals


def check_background_en(raw: str, facts: dict, text_sent: str, sent: list, fiscal_year: Optional[int] = None) -> checks.CheckResult:
    """D1 stage A: the English text against the report - <= 120 words, numbers from the report text or FACTS, quotes verbatim, competitors named and quoted, the company name, the competitive
    advantage matching the A7 level and its single source, no investment wording."""
    res = checks.CheckResult(False, "failed")
    d = checks.parse_json(raw)
    if d is None:
        res.reasons.append("invalid_json")
        return res
    res.parsed = d
    cfg = content_cfg()
    d1 = cfg["d1"]
    if d.get("skill_id") != d1["skill_id"]:
        res.reasons.append("skill_id_mismatch")
    text = d.get("text_en")
    if not isinstance(text, str) or not text.strip():
        res.reasons.append("text_missing")
        return res
    if _HEB.search(text):
        res.reasons.append("not_english")
    if count_words(text) > WORD_LIMIT:
        res.reasons.append(f"over_{WORD_LIMIT}_words ({count_words(text)})")
    bad = unsupported_numbers(text, text_sent + "\n" + d1_facts_text(facts), (fiscal_year,) if fiscal_year else ())
    if bad:
        res.reasons.append("number_not_in_report (" + ", ".join(str(int(b) if b == int(b) else b) for b in bad) + ")")
    res.quotes = checks._check_quotes(d.get("quotes"), checks.normalize(text_sent), sent, res.reasons, res.flags)
    comps, types = d.get("competitors") or [], d.get("competitor_types") or []
    if not (isinstance(comps, list) and all(isinstance(c, str) for c in comps) and isinstance(types, list) and all(isinstance(c, str) for c in types)):
        res.reasons.append("competitors_invalid")
        comps, types = [], []
    if comps and types:
        res.reasons.append("competitors_and_types_mixed")                  # names or types, never both
    if not res.quotes and (comps or types):
        res.reasons.append("no_quote")
    if len(comps) > MAX_COMPETITORS:
        res.reasons.append(f"too_many_competitors ({len(comps)})")
    if len(types) > MAX_COMPETITOR_TYPES:
        res.reasons.append(f"too_many_competitor_types ({len(types)})")
    qtext = " ".join(checks.normalize(q["text"]).casefold() for q in res.quotes if q["found"])
    res.reasons += [f"competitor_is_a_category ({c})" for c in comps if c[:1].islower()]
    res.reasons += [f"competitor_not_in_quote ({c})" for c in comps if checks.normalize(c).casefold() not in qtext]
    res.reasons += [f"competitor_type_not_in_quote ({c})" for c in types if checks.normalize(c).casefold() not in qtext]
    if not comps and not types and d1["no_competition_en"] not in text:
        res.reasons.append("competition_sentence_missing")                 # no name and no type: the fixed sentence
    if sentence_count(text) != 5:
        res.reasons.append(f"sentences_not_five ({sentence_count(text)})")
    _name_case(text, _company_token(facts.get("company_display") or facts.get("company_name", "")), res.reasons)
    _moat_check(text, facts.get("moat_level"), facts["moat_source"], d1["moat_prefix_en"], {k: [v] for k, v in d1["moat_terms_en"].items()}, res.reasons)
    res.reasons += [f"forbidden_word ({w})" for w in d1["forbidden_en"] if re.search(r"\b%s\b" % re.escape(w), text, re.I)]
    res.extra = {"competitors": comps, "competitor_types": types, "words": count_words(text)}
    res.ok = not res.reasons
    res.state = "stored" if res.ok else "failed"
    return res


def check_translation(raw: str, en_text: str, facts: dict, competitors: list) -> checks.CheckResult:
    """D1 stage B: the Hebrew translation against the checked English text - the same numbers, the same names, Hebrew only (Latin letters only for the names), no mixed scripts, the competitive
    advantage phrase of the A7 level and its single source in Hebrew, <= 120 words."""
    res = checks.CheckResult(False, "failed")
    d, repaired = parse_content_json(raw)
    if d is None:
        res.reasons.append("invalid_json")
        return res
    if repaired:
        res.flags.append("repaired_inner_quotes")
    res.parsed = d
    cfg = content_cfg()
    d1 = cfg["d1"]
    text = d.get("text_he")
    if not isinstance(text, str) or not text.strip():
        res.reasons.append("text_missing")
        return res
    if count_words(text) > WORD_LIMIT:
        res.reasons.append(f"over_{WORD_LIMIT}_words ({count_words(text)})")
    disp = facts.get("company_display") or facts.get("company_name", "")
    names = [disp] + list(competitors)
    res.reasons += language_issues(text, names + latin_terms())
    if unformatted_numbers(text):
        res.reasons.append("unformatted_number (" + ", ".join(unformatted_numbers(text)) + ")")
    en_words = count_words(en_text)
    if en_words and not (0.6 * en_words <= count_words(text) <= 1.4 * en_words):
        res.reasons.append(f"length_off_by_more_than_40_percent (english {en_words}, hebrew {count_words(text)})")
    res.reasons += [f"industry_term_missing ({en} -> {he})" for en, he in industry_terms_in(en_text) if not hebrew_term_present(text, he)]
    if d1["no_competition_en"] in en_text and d1["no_competition_he"] not in text:
        res.reasons.append("competition_sentence_not_translated")
    en_sig, he_sig = number_signature(en_text), number_signature(text)
    if en_sig != he_sig:
        res.reasons.append(f"numbers_differ (english {en_sig}, hebrew {he_sig})")
    extra_years = years_of(text) - years_of(en_text) - {facts.get("fiscal_year")}
    if extra_years:
        res.reasons.append(f"year_not_in_english ({sorted(extra_years)})")
    res.reasons += [f"name_missing ({n})" for n in names if n and n in en_text and n not in text]
    _name_case(text, _company_token(disp), res.reasons)
    _moat_check(text, facts.get("moat_level"), facts["moat_source"], d1["moat_prefix"], cfg["moat_words"], res.reasons)
    res.reasons += [f"forbidden_word ({w})" for w in forbidden_in(text)]
    res.extra = {"words": count_words(text)}
    res.ok = not res.reasons
    res.state = "stored" if res.ok else "failed"
    return res


def criteria_ids_of(results: dict) -> set:
    return {c["id"] for m in results["models"].values() for c in m["criteria"]}


def _ordered(text: str, words: list) -> bool:
    pos = -1
    for w in words:
        i = text.find(w, pos + 1)
        if i < 0:
            return False
        pos = i
    return True


def check_analysis(raw: str, inputs: dict) -> checks.CheckResult:
    """D2 checks (skills document 3.2 / 3.3 and the decisions of 2026-10-24): word limits (longer -> regenerated, never cut), every number in RESULTS / PEERS / CHANGES and formatted by code,
    no price-dependent number, criteria cited exist, glossary names only, Hebrew only, frames in order, the score text / lowest criterion / values / buy prices copied, peers only when
    ``compare``, no advice or current-price wording, the score-change line."""
    res = checks.CheckResult(False, "failed")
    d, repaired = parse_content_json(raw)
    if d is None:
        res.reasons.append("invalid_json")
        return res
    if repaired:
        res.flags.append("repaired_inner_quotes")
    res.parsed = d
    cfg = content_cfg()
    if d.get("skill_id") != cfg["d2"]["skill_id"]:
        res.reasons.append("skill_id_mismatch")
    results, ch, peers = inputs["results"], inputs.get("changes"), inputs["peers"]
    src = json.dumps(results, ensure_ascii=False) + "\n" + json.dumps(peers, ensure_ascii=False) + "\n" + (json.dumps(ch, ensure_ascii=False) if ch else "")
    bad_prices = {round(x, 2) for x in inputs.get("forbidden_numbers", [])}
    gl = cfg["glossary"]
    names = list(gl["criteria"].values()) + [n for m in gl["metrics"].values() for n in m.values() if n] + list(gl["models"].values()) + list(gl["methods"].values())
    words, texts = {}, {}
    for k in ("quality_he", "value_he"):
        t = d.get(k)
        if not isinstance(t, str) or not t.strip():
            res.reasons.append(f"{k}_missing")
            continue
        texts[k] = t
        words[k] = count_words(t)
        if words[k] > 60:
            res.reasons.append(f"{k}_over_60_words ({words[k]})")           # regenerated, not cut
        bad = unsupported_numbers(t, src)
        if bad:
            res.reasons.append(f"{k}_number_not_in_results (" + ", ".join(str(int(b) if b == int(b) else b) for b in bad) + ")")
            hit = [b for b in bad if round(b, 2) in bad_prices]
            if hit:
                res.reasons.append(f"{k}_price_dependent_number ({hit[0]})")
        if unformatted_numbers(t):
            res.reasons.append(f"{k}_unformatted_number ({unformatted_numbers(t)[0]})")
        res.reasons += [f"{k}_forbidden_word ({w})" for w in forbidden_in(t)]
        res.reasons += [f"{k}_{x}" for x in language_issues(t, latin_terms())]
        rest = t
        for n in sorted(names, key=len, reverse=True):
            rest = rest.replace(n, " ")
        res.reasons += [f"{k}_not_glossary_form ({w})" for w in cfg["forbidden_synonyms"] if w in rest]
    models = results["models"]
    if "quality_he" in texts:
        q = texts["quality_he"]
        if not _ordered(q, cfg["frames"]["quality"]):
            res.reasons.append("quality_he_frame_missing")
        for m, blk in models.items():
            if blk["score_display"] and blk["score_display"] not in q:
                res.reasons.append(f"quality_he_score_text_missing ({m})")
            lo = blk.get("lowest_he")
            if lo and f"{lo['name_he']} ({lo['strength_he']})" not in q:
                res.reasons.append(f"quality_he_lowest_criterion_missing ({m})")
        if peers["group"]["compare"]:
            if "ביחס ל" not in q or not all(v["position_he"] in q for v in peers["quality"].values() if v["position_he"]):
                res.reasons.append("quality_he_peer_comparison_missing")
        elif "עמיתים" in q or "ביחס ל" in q:
            res.reasons.append("quality_he_peer_comparison_not_allowed")        # fewer than 5 peers with a final score, or this company's score is a range
    if "value_he" in texts:
        v = texts["value_he"]
        if not _ordered(v, cfg["frames"]["value"]):
            res.reasons.append("value_he_frame_missing")
        for m, blk in models.items():
            if blk["value_text"] and blk["value_text"] not in v:
                res.reasons.append(f"value_he_value_text_missing ({m})")
            if blk["method_he"] not in v and blk["value_text"]:
                res.reasons.append(f"value_he_method_missing ({m})")
            if blk["buy_price_text"] is not None:
                if "מחיר הקנייה" not in v or blk["buy_price_text"] not in v:
                    res.reasons.append(f"value_he_buy_price_missing ({m})")
                if m == gl["models"]["buffett"] and blk["required_mos_text"] and blk["required_mos_text"] not in v:
                    res.reasons.append(f"value_he_required_margin_missing ({m})")
            elif blk["state_he"] and blk["state_he"] not in v:
                res.reasons.append(f"value_he_state_missing ({m})")
    cited = d.get("criteria_cited")
    ids = criteria_ids_of(results)
    if not isinstance(cited, list) or not all(isinstance(c, str) for c in cited):
        res.reasons.append("criteria_cited_invalid")
        cited = []
    else:
        res.reasons += [f"criterion_not_in_run ({c})" for c in cited if c not in ids]
    chg = d.get("change_he")
    if ch is None:
        if chg not in (None, ""):
            res.reasons.append("change_he_without_previous_run")
    elif chg not in (None, ""):
        if not isinstance(chg, str):
            res.reasons.append("change_he_invalid")
        else:
            words["change_he"] = count_words(chg)
            if words["change_he"] > 25:
                res.reasons.append(f"change_he_over_25_words ({words['change_he']})")
            bad = unsupported_numbers(chg, src)
            if bad:
                res.reasons.append("change_he_number_not_in_results (" + ", ".join(str(b) for b in bad) + ")")
            if ch["previous_run"] and ch["previous_run"] not in chg:
                res.reasons.append("change_he_previous_run_date_missing")
            res.reasons += [f"change_he_forbidden_word ({w})" for w in forbidden_in(chg)]
    elif ch["changes"]:
        res.reasons.append("change_he_missing")
    res.extra = {"words": words, "criteria_cited": cited}
    res.ok = not res.reasons
    res.state = "stored" if res.ok else "failed"
    return res


# ---------------------------------------------------------------- store
class TextStore:
    """texts.jsonl in the structure of ``ai_texts``: one row per (company, fiscal year, kind, language, prompt version, run_id). Generated once and shown as is."""

    def __init__(self, path: Path):
        self.path, self._rows = Path(path), {}
        if self.path.exists():
            for ln in self.path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    r = json.loads(ln)
                    self._rows[self.key(r)] = r

    @staticmethod
    def key(r: dict) -> tuple:
        return (r["ticker"], int(r["fiscal_year"]), r["kind"], r["language"], str(r["prompt_version"]), r.get("run_id") or "")

    def get(self, ticker, fiscal_year, kind, prompt_version, run_id="", language="he"):
        return self._rows.get((ticker, int(fiscal_year), kind, language, str(prompt_version), run_id or ""))

    def put(self, row: dict) -> dict:
        row = {**row, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self._rows[self.key(row)] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lead = "\n" if (self.path.exists() and self.path.stat().st_size and not self.path.read_bytes().endswith(b"\n")) else ""
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(lead + json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row

    def rows(self) -> list:
        return list(self._rows.values())

    def migrate_review_status(self) -> int:
        """Adds ``approval_status`` / ``edited_by`` / ``human_reviewed`` to rows written before the review rule; a row that passed is ``approved`` (a Hebrew background that an earlier version
        stored as ``pending_review`` becomes ``approved``, ``human_reviewed`` False). -> rows changed."""
        n = 0
        for k, r in list(self._rows.items()):
            if "approval_status" in r and r["approval_status"] != "pending_review" and "human_reviewed" in r:
                continue
            st = "approved" if r.get("state") == "stored" else "failed"
            self.put({**r, "approval_status": st, "edited_by": r.get("edited_by", "ai"), "human_reviewed": bool(r.get("human_reviewed", False))})
            n += 1
        return n


# ---------------------------------------------------------------- generation
SEED_SHIFT = 0          # a later run of a failed text uses other seeds (the model is deterministic per seed)


def _call(client, prompt: str, seed_offset: int):
    return client.generate(prompt, seed_offset=seed_offset + SEED_SHIFT)


def retry_note(reasons: list, facts: dict, text_words: Optional[int] = None) -> str:
    """The note of the single retry of a stage: the generic list of failed checks, plus (decision 2026-10-24) the actual word count with a request to shorten to about 100 words, and the
    competitive-advantage source / phrase that must appear."""
    d1 = content_cfg()["d1"]
    note = "Your previous answer failed these checks: " + "; ".join(reasons) + ". Fix them and answer again."
    m = next((re.search(r"over_\d+_words \((\d+)\)", r) for r in reasons if r.startswith("over_")), None)
    if m:
        note += f" Your text has {m.group(1)} words: shorten it to about 100 words, one sentence per part."
    if any(r.startswith(("moat_source_not_in_text", "moat_level_phrase_missing")) for r in reasons) and facts.get("moat_level") in (1, 2):
        note += (f' The competitive-advantage sentence must begin with "{d1["moat_prefix_en"][facts["moat_level"]]}" (in Hebrew "{d1["moat_prefix"][facts["moat_level"]]}") and name this source: '
                 f'{facts["moat_term_en"]} (in Hebrew "{facts["moat_term_he"]}").')
    if any(r.startswith("too_many_competitors") for r in reasons):
        note += " Name at most 5 main competitors."
    return note


class BudgetExceeded(RuntimeError):
    pass


class BudgetClient:
    """A hard cap on the number of model calls, enforced here (the shared daily counter still applies on top): the call that would exceed the cap is not sent."""

    def __init__(self, client, cap: int):
        self._client, self.cap, self.calls = client, cap, 0
        self.model = getattr(client, "model", "")

    def generate(self, *a, **kw):
        if self.calls >= self.cap:
            raise BudgetExceeded(f"call cap of {self.cap} reached")
        self.calls += 1
        return self._client.generate(*a, **kw)


def review_status(language: str, state: str, first_load: bool = True) -> str:
    """ai_texts.approval_status (decision 2026-10-25 12:00): a text that passed all checks is ``approved`` at once - the Hebrew background with ``human_reviewed = False`` (the screen adds the
    marker "תרגום אוטומטי" until a person confirms or edits it); anything that failed is ``failed``. ``pending_review`` is only set by a person who sends a text back."""
    return "approved" if state == "stored" else "failed"


def _row(co, language: str, text, state: str, pv: str, rep, res, attempts: list, extra: Optional[dict] = None) -> dict:
    return {"ticker": co.ticker, "fiscal_year": co.fiscal_year, "kind": "background", "language": language, "text": text, "model": getattr(rep, "model", ""), "prompt_version": pv, "run_id": "",
            "state": state, "accession": co.filing.accession, "quotes": res.quotes if res else [], "competitors": (res.extra.get("competitors", []) if res else []),
            "checks": {"ok": bool(res and res.ok), "reasons": res.reasons if res else [], "flags": res.flags if res else [], "attempts": attempts}, "raw_answer": getattr(rep, "text", None),
            "competitor_types": (res.extra.get("competitor_types", []) if res else []), "edited_by": "ai", "approval_status": review_status(language, state), "human_reviewed": False, **(extra or {})}


def generate_background(co, facts: dict, sections: dict, client, store: TextStore, force: bool = False) -> dict:
    """D1 in two stages (decision 2026-10-24). A: the model writes the background in English and every check runs on it against the report; B: a second call translates the checked text into
    Hebrew with the glossary and the translation is checked against the English (same numbers, same names, Hebrew only). Both versions are stored (language en / he). -> the Hebrew row (or the
    last failed / skipped row). A failed stage is asked again in a later run; a stored English text is not written again."""
    pv = str(content_cfg()["d1"]["version"])
    he = store.get(co.ticker, co.fiscal_year, "background", pv, "", "he")
    if he is not None and he.get("state") == "stored" and not force:
        return he
    sections, trimmed = trim_d1_sections(facts, co.filing.accession, sections)
    en = store.get(co.ticker, co.fiscal_year, "background", pv, "", "en")
    try:
        if en is None or en.get("state") != "stored" or force:
            note, attempts = "", []
            for attempt in (1, 2):
                prompt, text_sent, sent = build_d1_prompt(facts, co.filing.accession, sections, note)
                rep = _call(client, prompt, attempt - 1)
                res = check_background_en(rep.text, facts, text_sent, sent, co.fiscal_year)
                attempts.append({"attempt": attempt, "ok": res.ok, "reasons": list(res.reasons), "prompt_chars": len(prompt)})
                if res.ok:
                    break
                note = retry_note(res.reasons, facts)
            en = store.put(_row(co, "en", res.parsed.get("text_en") if res.ok else None, res.state, pv, rep, res, attempts, {"trimmed": trimmed, "stage": "A"}))
            if not res.ok:
                return {**en, "stage_failed": "A"}
        note, attempts, comps = "", [], en.get("competitors", [])
        for attempt in (1, 2):
            prompt = build_d1_translation_prompt(facts, en["text"], comps, note)
            rep = _call(client, prompt, attempt - 1)
            res = check_translation(rep.text, en["text"], facts, comps)
            attempts.append({"attempt": attempt, "ok": res.ok, "reasons": list(res.reasons), "prompt_chars": len(prompt)})
            if res.ok:
                break
            note = retry_note(res.reasons, facts)
        row = _row(co, "he", res.parsed.get("text_he") if res.ok else None, res.state, pv, rep, res, attempts, {"stage": "B", "competitors": comps, "quotes": en.get("quotes", [])})
        if not res.ok and he is not None and he.get("state") == "stored":
            return {**he, "regeneration_failed": [a["reasons"] for a in attempts]}
        return store.put(row)
    except BudgetExceeded as e:
        return {"ticker": co.ticker, "fiscal_year": co.fiscal_year, "kind": "background", "language": "he", "state": "skipped_budget", "text": None,
                "checks": {"ok": False, "reasons": [str(e)], "attempts": []}}


def recheck_background(co, facts: dict, sections: dict, store: TextStore) -> dict:
    """Re-run the CURRENT checks on the stored raw answers of both stages (no model call). A failed stage that now passes is stored; a stored stage that fails the current checks is marked failed.
    -> {"en": row, "he": row}."""
    pv = str(content_cfg()["d1"]["version"])
    sections, _ = trim_d1_sections(facts, co.filing.accession, sections)
    _, text_sent, sent = build_d1_prompt(facts, co.filing.accession, sections)
    en = store.get(co.ticker, co.fiscal_year, "background", pv, "", "en")
    he = store.get(co.ticker, co.fiscal_year, "background", pv, "", "he")
    if en and en.get("raw_answer"):
        res = check_background_en(en["raw_answer"], facts, text_sent, sent, co.fiscal_year)
        if res.ok != (en.get("state") == "stored"):
            en = store.put({**en, "text": res.parsed.get("text_en") if res.ok else None, "state": res.state, "quotes": res.quotes, "competitors": res.extra.get("competitors", []), "rechecked": True,
                            "checks": {"ok": res.ok, "reasons": res.reasons, "flags": res.flags, "attempts": en["checks"]["attempts"] + [{"attempt": "recheck", "ok": res.ok, "reasons": list(res.reasons)}]}})
    if he and he.get("raw_answer") and en and en.get("state") == "stored":
        res = check_translation(he["raw_answer"], en["text"], facts, en.get("competitors", []))
        if res.ok != (he.get("state") == "stored"):
            he = store.put({**he, "text": res.parsed.get("text_he") if res.ok else None, "state": res.state, "rechecked": True,
                            "checks": {"ok": res.ok, "reasons": res.reasons, "flags": res.flags, "attempts": he["checks"]["attempts"] + [{"attempt": "recheck", "ok": res.ok, "reasons": list(res.reasons)}]}})
    elif he and en and en.get("state") != "stored" and he.get("state") == "stored":
        he = store.put({**he, "text": None, "state": "failed", "rechecked": True})
    return {"en": en, "he": he}


def generate_analysis(ticker: str, fiscal_year: int, inputs: dict, client, store: TextStore, force: bool = False) -> dict:
    """D2 once per scoring run (keyed by run_id); never regenerated when a page is opened. ``inputs`` = d2.build_d2_inputs(...)."""
    d2 = content_cfg()["d2"]
    pv = str(d2["version"])
    run_id = inputs["results"]["run_id"]
    if inputs.get("ai_pending"):                                    # D2 only after every AI question of the company was handled
        return {"ticker": ticker, "fiscal_year": fiscal_year, "kind": "analysis", "state": "skipped_ai_pending", "run_id": run_id, "text": None,
                "checks": {"ok": False, "reasons": [f"{inputs['ai_pending']} AI questions are still pending"], "attempts": []}}
    ex = None if force else store.get(ticker, fiscal_year, "analysis", pv, run_id)
    if ex is not None and ex.get("state") == "stored":
        return ex
    note, attempts = "", []
    for attempt in (1, 2):
        prompt = build_d2_prompt(inputs, note)
        rep = _call(client, prompt, attempt - 1)
        res = check_analysis(rep.text, inputs)
        attempts.append({"attempt": attempt, "ok": res.ok, "reasons": list(res.reasons), "prompt_chars": len(prompt)})
        if res.ok:
            break
        note = "Your previous answer failed these checks: " + "; ".join(res.reasons) + ". Rewrite (shorter where a paragraph was too long; do not cut) and answer again."
    p = res.parsed or {}
    text = (p.get("quality_he", "") + "\n\n" + p.get("value_he", "")) if res.ok else None
    return store.put({"ticker": ticker, "fiscal_year": fiscal_year, "kind": "analysis", "language": "he", "text": text, "quality_he": p.get("quality_he") if res.ok else None,
                      "value_he": p.get("value_he") if res.ok else None, "change_he": p.get("change_he") if res.ok else None, "criteria_cited": res.extra.get("criteria_cited", []),
                      "model": rep.model, "prompt_version": pv, "run_id": run_id, "state": res.state, "quotes": [],
                      "checks": {"ok": res.ok, "reasons": res.reasons, "flags": res.flags, "attempts": attempts}, "raw_answer": rep.text})

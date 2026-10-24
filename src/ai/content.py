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
def d1_revenue_text(revenue: Optional[float]) -> str:
    """Revenue as ready formatted text ("331.8 מיליארד $"): the model copies it."""
    from .d2 import money
    return money(revenue) or "not available"


_SUFFIX = {"corp", "corporation", "co", "inc", "ltd", "plc", "company", "holdings", "group", "ma", "the", "n.v.", "s.a.", "ag"}


def display_name(edgar_name: str) -> str:
    """The EDGAR name (often in capitals, with a suffix: "COCA COLA CO", "AMERICAN TOWER CORP /MA/") in proper case without the legal suffix ("Coca Cola", "American Tower")."""
    toks = [t for t in re.findall(r"[A-Za-z][A-Za-z\-&\.']*", edgar_name or "") if t.strip(".").lower() not in _SUFFIX]
    if not toks:
        return edgar_name or ""
    fixed = {"jpmorgan": "JPMorgan", "mcdonald": "McDonald"}
    return " ".join(fixed.get(t.lower(), t if (t != t.upper() and t != t.lower()) else t.capitalize()) for t in toks)


def d1_facts(industry: str, revenue: Optional[float], currency: str, fiscal_year, one_sentence: str, moat_answer, moat_source: str, moat_reasoning: str, company_name: str = "") -> dict:
    d1 = content_cfg()["d1"]
    words = content_cfg()["moat_words"]
    src = moat_source if moat_answer in (1, 2) else "none"
    term = (words.get(src or "none") or ["-"])[0]
    prefix = d1["moat_prefix"].get(moat_answer)
    if moat_answer in (1, 2):
        instr = (f'open the sentence with exactly "{prefix}" and then name ONE source only (the one in FACTS: source {src}, Hebrew term "{term}") in your own words; '
                 "no list of sources and no other source.")
    elif moat_answer == 0:
        instr = f'write exactly "{prefix}" and nothing more about it.'
    else:
        instr = "the competitive-advantage answer is not available: do not write about a competitive advantage."
    return {"industry": industry, "revenue": d1_revenue_text(revenue), "currency": currency, "fiscal_year": fiscal_year, "one_sentence": one_sentence or "not available",
            "moat_answer": moat_answer if moat_answer is not None else "not available", "moat_level": moat_answer, "moat_source": src or "none", "moat_reasoning": moat_reasoning or "",
            "moat_term_he": term, "moat_prefix_he": prefix, "moat_instruction": instr, "company_name": company_name, "company_display": display_name(company_name)}


def d1_facts_text(f: dict) -> str:
    return (f"industry {f['industry']}; revenue {f['revenue']} (FY{f['fiscal_year']}); company {f.get('company_name', '')}; ONE SENTENCE: {f['one_sentence']}; "
            f"MOAT: level {f['moat_answer']} / source {f['moat_source']} / {f['moat_reasoning']}")


def build_d1_prompt(facts: dict, accession: str, sections: dict, note: str = "") -> tuple:
    d1 = content_cfg()["d1"]
    sent = [(s, sections[s]) for s in d1["sections"] if sections.get(s)]
    text = "\n\n".join(f"[{s}]\n{t}" for s, t in sent)
    p = d1["template"].format(industry=facts["industry"], revenue=facts["revenue"], fiscal_year=facts["fiscal_year"], one_sentence=facts["one_sentence"], company_name=facts.get("company_display") or facts.get("company_name", ""),
                              moat_answer=facts["moat_answer"], moat_source=facts["moat_source"], moat_reasoning=facts["moat_reasoning"], moat_instruction=facts["moat_instruction"],
                              sections=", ".join(s for s, _ in sent), accession=accession, section_text=text, version=d1["version"])
    return (p + f"\nNOTE: {note}\n" if note else p), text, [s for s, _ in sent]


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
    for a in sorted({x for x in allowed if x}, key=len, reverse=True):
        t = re.sub(re.escape(a), " ", t, flags=re.I)
    for tok in _WORDTOK.findall(t):
        scripts = sum(bool(r.search(tok)) for r in (_HEB, _LAT, _CYR, _ARB))
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
def check_background(raw: str, facts: dict, text_sent: str, sent: list, fiscal_year: Optional[int] = None) -> checks.CheckResult:
    """D1: <= 120 words, numbers from FACTS only (formatted by code), quotes verbatim, competitors in quotes, Hebrew only, the company name in Latin letters, the competitive advantage
    matches the A7 level (prefix) and names the A7 source only (one source, no list)."""
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
    facts_text = d1_facts_text(facts)
    if d.get("skill_id") != d1["skill_id"]:
        res.reasons.append("skill_id_mismatch")
    text = d.get("text_he")
    if not isinstance(text, str) or not text.strip():
        res.reasons.append("text_missing")
        return res
    if count_words(text) > 120:
        res.reasons.append(f"over_120_words ({count_words(text)})")
    bad = unsupported_numbers(text, facts_text, (fiscal_year,) if fiscal_year else ())
    if bad:
        res.reasons.append("number_not_in_facts (" + ", ".join(str(int(b) if b == int(b) else b) for b in bad) + ")")
    if unformatted_numbers(text):
        res.reasons.append("unformatted_number (" + ", ".join(unformatted_numbers(text)) + ")")
    res.quotes = checks._check_quotes(d.get("quotes"), checks.normalize(text_sent), sent, res.reasons, res.flags)
    comps = d.get("competitors")
    if not isinstance(comps, list) or not all(isinstance(c, str) for c in comps):
        res.reasons.append("competitors_invalid")
        comps = []
    if not res.quotes and comps:                       # the quotes support the named competitors; a text that names none needs no quote
        res.reasons.append("no_quote")
    qtext = " ".join(checks.normalize(q["text"]).casefold() for q in res.quotes if q["found"])
    res.reasons += [f"competitor_is_a_category ({c})" for c in comps if c[:1].islower()]          # "other banks", "large carriers": not a company named in the report
    for c in comps:
        if checks.normalize(c).casefold() not in qtext:
            res.reasons.append(f"competitor_not_in_quote ({c})")
    res.reasons += language_issues(text, [facts.get("company_name", "")] + comps + latin_terms())
    tok = _company_token(facts.get("company_display") or facts.get("company_name", ""))
    if tok:
        m = re.search(re.escape(tok), text, re.I)
        if not m:
            res.reasons.append(f"company_name_not_in_latin ({tok})")
        elif m.group(0).islower() or (m.group(0).isupper() and len(tok) > 5):
            res.reasons.append(f"company_name_wrong_case ({m.group(0)})")           # as written in the report, not in lower case or in capitals ("coca cola", "MICROSOFT")
    level = facts.get("moat_level")
    words = cfg["moat_words"]
    if level in (0, 1, 2):
        prefix = d1["moat_prefix"][level]
        i = text.find(prefix)
        if i < 0:
            res.reasons.append(f"moat_level_phrase_missing ({prefix})")
        elif level in (1, 2):
            sentence = text[i + len(prefix):].split(".")[0]
            own = words.get(facts["moat_source"], [])
            if own and not any(w in sentence for w in own):
                res.reasons.append(f"moat_source_not_in_text ({facts['moat_source']})")
            others = [v[0] for k, v in words.items() if k not in (facts["moat_source"], "none") and not any(v[0] in o for o in own)]
            hit = [w for w in others if w in sentence]
            if hit:
                res.reasons.append(f"moat_other_source ({hit[0]})")
    res.reasons += [f"forbidden_word ({w})" for w in forbidden_in(text)]
    res.extra = {"competitors": comps, "words": count_words(text)}
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
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row

    def rows(self) -> list:
        return list(self._rows.values())


# ---------------------------------------------------------------- generation
SEED_SHIFT = 0          # a later run of a failed text uses other seeds (the model is deterministic per seed)


def _call(client, prompt: str, seed_offset: int):
    return client.generate(prompt, seed_offset=seed_offset + SEED_SHIFT)


def generate_background(co, facts: dict, sections: dict, client, store: TextStore, force: bool = False) -> dict:
    """D1 once per annual report. ``co`` needs ticker, fiscal_year, filing.accession."""
    d1 = content_cfg()["d1"]
    pv = str(d1["version"])
    prev = store.get(co.ticker, co.fiscal_year, "background", pv)
    ex = None if force else prev
    if ex is not None and ex.get("state") == "stored":                # a failed text is asked again in a later run
        return ex
    sections, trimmed = trim_d1_sections(facts, co.filing.accession, sections)
    note, attempts = "", []
    for attempt in (1, 2):
        prompt, text_sent, sent = build_d1_prompt(facts, co.filing.accession, sections, note)
        rep = _call(client, prompt, attempt - 1)
        res = check_background(rep.text, facts, text_sent, sent, co.fiscal_year)
        attempts.append({"attempt": attempt, "ok": res.ok, "reasons": list(res.reasons)})
        if res.ok:
            break
        note = "Your previous answer failed these checks: " + "; ".join(res.reasons) + ". Fix them and answer again."
    p = res.parsed or {}
    if not res.ok and prev is not None and prev.get("state") == "stored":                 # a forced regeneration that fails keeps the text that passed before
        return {**prev, "regeneration_failed": [a["reasons"] for a in attempts]}
    return store.put({"ticker": co.ticker, "fiscal_year": co.fiscal_year, "kind": "background", "language": "he", "text": p.get("text_he") if res.ok else None, "model": rep.model,
                      "prompt_version": pv, "run_id": "", "state": res.state, "accession": co.filing.accession, "quotes": res.quotes, "competitors": res.extra.get("competitors", []),
                      "trimmed": trimmed, "prompt_chars": len(prompt), "checks": {"ok": res.ok, "reasons": res.reasons, "flags": res.flags, "attempts": attempts}, "raw_answer": rep.text})


def recheck_background(co, facts: dict, sections: dict, store: TextStore) -> Optional[dict]:
    """Re-run the CURRENT checks on the stored raw answer of a D1 (no model call): a failed text that now passes becomes ``stored``; a stored text that fails the current checks becomes ``failed``
    (nothing is shown) with the reasons."""
    pv = str(content_cfg()["d1"]["version"])
    ex = store.get(co.ticker, co.fiscal_year, "background", pv)
    if not ex or not ex.get("raw_answer"):
        return ex
    sections, _ = trim_d1_sections(facts, co.filing.accession, sections)
    _, text_sent, sent = build_d1_prompt(facts, co.filing.accession, sections)
    res = check_background(ex["raw_answer"], facts, text_sent, sent, co.fiscal_year)
    if res.ok and ex.get("state") != "stored":
        p = res.parsed
        return store.put({**ex, "text": p.get("text_he"), "state": "stored", "quotes": res.quotes, "competitors": res.extra.get("competitors", []), "rechecked": True,
                          "checks": {"ok": True, "reasons": [], "flags": res.flags, "attempts": ex["checks"]["attempts"] + [{"attempt": "recheck", "ok": True, "reasons": []}]}})
    if not res.ok and ex.get("state") == "stored":
        return store.put({**ex, "text": None, "state": "failed", "rechecked": True,
                          "checks": {"ok": False, "reasons": res.reasons, "flags": res.flags, "attempts": ex["checks"]["attempts"] + [{"attempt": "recheck", "ok": False, "reasons": list(res.reasons)}]}})
    return ex


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

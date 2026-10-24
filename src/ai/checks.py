"""Code checks on every AI answer (AI spec section 4.4). Pure. A rejected answer becomes ``insufficient_evidence`` with the reasons recorded (R16)."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

MOAT_SOURCES = ("brand", "switching_costs", "scale", "network_effect", "regulation", "data", "infrastructure", "location", "none")
EXPOSURE_TYPES = ("customer", "product", "license", "market", "none")
MAX_ONE_SENTENCE_WORDS = 25
MIN_QUOTE_CHARS = 12

# Normalization applied to the quote and to the text sent (check 3). Quote marks of every kind are dropped (a lost apostrophe in a cached filing is U+FFFD, "Company�s");
# a U+FFFD between two word characters is such a lost apostrophe (dropped), anywhere else it is a lost bullet / quote (a space); bullet glyphs are spaces; dashes are one hyphen.
_QUOTE_CHARS = "'‘’‚′ʼ“”„″«»\"`"
_MARKS = "®™©℠"                           # registered / trademark / copyright signs: dropped on both sides
_BULLETS = "•▪◦●‣⁃■□·∙"
_DASHES = {"–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-", "‒": "-", "­": ""}


def normalize(s: str) -> str:
    """Whitespace, quote-mark, bullet and lost-character normalization applied to both the quote and the text sent (check 3)."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"(?<=\w)�(?=\w)", "", s)
    s = s.replace("�", " ")
    s = s.translate({**{ord(c): None for c in _QUOTE_CHARS + _MARKS}, **{ord(c): " " for c in _BULLETS}})
    s = s.replace("|", " ")                      # table-cell separator inserted by the html -> text conversion
    for k, v in _DASHES.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", " ", s).strip()



@dataclass
class CheckResult:
    ok: bool
    state: str                                   # answered | insufficient_evidence
    answer: Optional[int] = None
    reasons: list = field(default_factory=list)  # why rejected / flags
    flags: list = field(default_factory=list)
    quotes: list = field(default_factory=list)   # [{text, section, found}]
    reasoning: str = ""
    extra: dict = field(default_factory=dict)
    parsed: Optional[dict] = None


def parse_json(raw: str) -> Optional[dict]:
    t = (raw or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    try:
        v = json.loads(t)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", t, flags=re.S)
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return None
    return v if isinstance(v, dict) else None


def _section_of(qn: str, text_norm: str) -> Optional[str]:
    """The sent section that contains the (normalized) quote; sections are marked '[TXT-00x]' in the text sent."""
    parts = re.split(r"\[((?:TXT|NOTE)-[A-Z0-9]+)\]", text_norm)
    for sid, body in zip(parts[1::2], parts[2::2]):
        if qn in body:
            return sid
    return None


def _check_quotes(quotes, text_norm: str, sections_sent: list, reasons: list, reasons_flag: Optional[list] = None, facts_norm: str = "") -> list:
    out = []
    reasons_flag = reasons_flag if reasons_flag is not None else []
    if not isinstance(quotes, list):
        reasons.append("quotes_not_a_list")
        return out
    for q in quotes:
        if isinstance(q, str):                      # a bare string is accepted as a quote (still verified word for word), flagged
            q = {"text": q, "section": None}
            reasons_flag.append("quote_as_string")
        if not isinstance(q, dict) or not isinstance(q.get("text"), str):
            reasons.append("quote_malformed")
            continue
        qn = normalize(q["text"])
        found = len(qn) >= MIN_QUOTE_CHARS and qn in text_norm and "..." not in qn and "…" not in qn
        if not found:
            # a quote taken from FACTS GIVEN BY CODE is not a quote from the report (K5a-3): its own reason, so the prompt can be fixed
            reasons.append("quote_from_facts" if (facts_norm and len(qn) >= MIN_QUOTE_CHARS and qn in facts_norm) else "quote_not_found")
        actual = _section_of(qn, text_norm) if found else None
        if found and q.get("section") and actual and q["section"] != actual:
            reasons_flag.append("quote_section_label_corrected")      # the label is the model's; the section that contains the text is what we store
        out.append({"text": q["text"], "section": actual or q.get("section"), "found": found})
    return out


_OTHER_DEPENDENCE = re.compile(r"single product|one product|product dependence|licen[cs]e|one market|single market|sole source|depends? (?:heavily )?on (?:a )?single", re.I)


_DELIBERATION = re.compile(r"\b(?:Wait|Hmm)\b|\bActually,|\bLet(?:'s| me) (?:re)?check|\bLet(?:'s| me) re(?:read|think|consider)", re.I)
_SCALE_QUOTE = re.compile(r"\b(?:level\s*[012]|scale|includes?|above 25%|the card)\b", re.I)


def has_deliberation(reasoning: str) -> bool:
    """Thinking aloud inside the reasoning field ("Wait, ...") - the reasoning must be the final explanation."""
    return bool(_DELIBERATION.search(reasoning or ""))


def exposure_consistent(answer: int, share_pct: float, reasoning: str = "") -> bool:
    """A11 code_check: a customer's share of revenue vs the level. > 25 allows 0; 10-25 allows 1 (or 0 only with another stated dependence: product, license, market);
    < 10 allows 2 (or 0 / 1 only with such another dependence)."""
    # sentences that merely quote the scale ("Level 0 includes ... a single product ...") are not a stated dependence of the company
    own = " ".join(x for x in re.split(r"(?<=[.;?!])\s+", reasoning or "") if not _SCALE_QUOTE.search(x))
    other = bool(_OTHER_DEPENDENCE.search(own))
    if share_pct > 25:
        return answer == 0
    if share_pct >= 10:
        return answer == 1 or (answer == 0 and other)
    return answer == 2 or other


def check_judgment(raw: str, skill: dict, text_sent: str, sections_sent: list, facts_text: Optional[str] = None, require_facts_check: bool = False) -> CheckResult:
    """Type A (quality judgment). Checks 1, 2, 3, 6 and the extra-output checks of the skill. ``facts_text`` = the FACTS sent (a quote found only there is `quote_from_facts`);
    ``require_facts_check`` = prompt version x.1: when FACTS were sent, `facts_check` must be a non-empty sentence."""
    res = CheckResult(False, "insufficient_evidence")
    d = parse_json(raw)
    if d is None:
        res.reasons.append("invalid_json")
        return res
    res.parsed = d
    if d.get("skill_id") != skill["skill_id"]:
        res.reasons.append("skill_id_mismatch")
    if d.get("version") != skill["version"]:
        res.flags.append("version_mismatch_in_answer")
    ans, insuff = d.get("answer"), d.get("insufficient_evidence")
    res.reasoning = str(d.get("reasoning", ""))[:1500]
    if insuff is True or ans is None:
        if not (insuff is True and ans is None):
            res.reasons.append("inconsistent_insufficient_evidence")
            return res
        res.ok, res.state = True, "insufficient_evidence"          # the model itself found no evidence: valid, counted as missing
        res.flags.append("model_insufficient_evidence")
        return res
    if isinstance(ans, bool) or ans not in (0, 1, 2):
        res.reasons.append("answer_not_allowed")
        return res
    res.quotes = _check_quotes(d.get("quotes"), normalize(text_sent), sections_sent, res.reasons, res.flags, normalize(facts_text) if facts_text else "")
    if not res.quotes:
        res.reasons.append("no_quote")                               # check 6
    if has_deliberation(res.reasoning):
        res.reasons.append("reasoning_deliberation")
    sid = skill["skill_id"]
    extra: dict = {}
    if require_facts_check and facts_text:
        fc = d.get("facts_check")
        if not (isinstance(fc, str) and fc.strip()):
            res.reasons.append("facts_check_missing")
        else:
            extra["facts_check"] = fc.strip()
    if sid == "B3.1-Q4" and ans == 2:
        r = d.get("main_risks")
        if not (isinstance(r, list) and 2 <= len(r) <= 4 and all(isinstance(x, str) and x.strip() for x in r)):
            res.reasons.append("main_risks_invalid")
        extra["main_risks"] = r
    if sid == "B3.1-Q5":
        s = d.get("one_sentence")
        if not isinstance(s, str) or not s.strip():
            res.reasons.append("one_sentence_missing")
        else:
            words = len(s.split())
            extra["one_sentence"], extra["one_sentence_words"] = s, words
            if ans == 2 and words > MAX_ONE_SENTENCE_WORDS:
                res.reasons.append("one_sentence_over_25_words")
    if sid == "B3.2-Q5":
        m = d.get("moat_source")
        if m not in MOAT_SOURCES:
            res.reasons.append("moat_source_not_allowed")
        extra["moat_source"] = m
    if sid == "G3.1-Q3":
        e = d.get("largest_exposure")
        if not (isinstance(e, dict) and e.get("type") in EXPOSURE_TYPES):
            res.reasons.append("largest_exposure_invalid")
        else:
            sp = e.get("share_pct")
            if sp is not None and (isinstance(sp, bool) or not isinstance(sp, (int, float))):
                res.reasons.append("largest_exposure_share_invalid")
            elif e.get("type") == "customer" and sp is not None and not exposure_consistent(ans, float(sp), res.reasoning):
                res.reasons.append("exposure_inconsistent")      # the caller retries once with a note; a second inconsistency is a rejection (code_check of A11)
        extra["largest_exposure"] = e
    if sid == "G3.8-Q3":
        it = d.get("items")
        if not isinstance(it, list):
            res.reasons.append("items_missing")
        extra["items"] = it
    res.extra = extra
    res.ok = not res.reasons
    res.state = "answered" if res.ok else "insufficient_evidence"
    res.answer = int(ans) if res.ok else None
    if not res.ok:
        res.flags.append("rejected")
    return res


def check_classification(raw: str, industries: list, text_sent: str) -> CheckResult:
    res = CheckResult(False, "insufficient_evidence")
    d = parse_json(raw)
    if d is None:
        res.reasons.append("invalid_json")
        return res
    res.parsed = d
    res.reasoning = str(d.get("reasoning", ""))[:1500]
    ind, insuff = d.get("industry"), d.get("insufficient_evidence")
    if ind is None or insuff is True:
        res.ok = insuff is True and ind is None
        if not res.ok:
            res.reasons.append("inconsistent_insufficient_evidence")
        res.flags.append("model_insufficient_evidence")
        return res
    if ind not in industries:
        res.reasons.append("industry_not_in_list")
    res.quotes = _check_quotes(d.get("quotes"), normalize(text_sent), ["TXT-001"], res.reasons, res.flags)
    if not res.quotes:
        res.reasons.append("no_quote")
    res.ok = not res.reasons
    res.state = "answered" if res.ok else "insufficient_evidence"
    res.extra = {"industry": ind if res.ok else None}
    return res

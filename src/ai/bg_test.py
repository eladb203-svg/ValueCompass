"""Background (D1) writing test 1 - the English text only (five ways to write it, compared blind).

Fixes that apply to versions 2-5 (and are applied to version 1 only as a measurement):
  * money amounts exactly as FACTS formats them ("$331.8 billion"); a raw figure ("$331,839 million", "$5,749,377 thousand") is rejected;
  * no "meta" sentences ("in the report", "report text", "named by name", "the filing", "we have");
  * the Competition chapter of Item 1 is always sent (heading search; else the paragraphs that talk about competition);
  * a competitor is defined in the prompt (similar products or services to the same customers - not suppliers, customers, distributors or brokers);
  * the industry label of FACTS is context only: it is not copied into a sentence.
Versions: V1 the stored text; V2 today's input + the competition chapter; V3 only the opening of Item 1 + the chapter; V4 the Yahoo description + the chapter; V5 the opening of the English Wikipedia article +
the chapter. In V4 and V5 the outside text is context only: a number that is only there is rejected, and competitors come from the chapter of the report only.
"""
from __future__ import annotations

import re
from typing import Optional

from src.ai import checks, content as C

VERSIONS = ("V1", "V2", "V3", "V4", "V5")
OVERVIEW_CHARS = 6000
CHAPTER_CAP = 6000
COMPETITION_HEADING = re.compile(r"^\s*(?:Item\s+1[A-Z]?\.?\s*)?(Competition|Competitors|Competitive\s+(?:Conditions|Environment|Landscape|Position)|Competition\s+and\s+[A-Za-z ]{0,30})\s*[.:]?\s*$", re.I)
META = (r"\bin the report\b", r"\breport text\b", r"\bnamed by name\b", r"\bthe filing\b", r"\bwe have\b")
_SCALE = r"(?:thousand|million|billion|trillion)"
_RAW_MONEY = re.compile(r"(?:\$\s?)?(\d{1,3}(?:,\d{3})+(?:\.\d+)?)\s*(" + _SCALE + r")?", re.I)

TEMPLATE = """SYSTEM
You assist ValueCompass. Write a short background of the company for investors, using ONLY the sources provided below and the facts. Do not use outside knowledge. Do not give opinions on the
stock, its price or its score. Write in English, plain and neutral, as a statement about the company: never refer to the source ("the report", "the filing", "report text", "named by name") and never
write in the first person ("we have", "our").
Numbers: use only numbers that appear in FACTS or word for word in the TEXT blocks. Write every money amount exactly as FACTS writes it (for example "$331.8 billion"); never copy a raw figure such
as "$331,839 million" or "$5,749,377 thousand".
Competitors are companies offering similar products or services to the same customers - not suppliers, customers, distributors or brokers. "competitors" lists only such companies named BY NAME in
the COMPETITION text (at most 5 main ones, as written); "competitor_types" is used ONLY when that text names no competitor but describes the competition (at most 4 TYPES of competitors, in its own
words); never fill both. Every name or type you use must appear in one of your quotes (several quotes are allowed). Copy each quote as one continuous passage, exactly as it appears in a TEXT
block, without shortening or joining passages; quotes must come from the TEXT blocks, never from FACTS or from the DESCRIPTION.
Write the company name exactly as given in FACTS and begin the first sentence with it. The industry label in FACTS is context only: do not copy it into a sentence. Never use the ASCII
double-quote character inside the text. Write your final text, not your thinking process.

STRUCTURE (exactly these five parts, one sentence each; about 90-100 words in total)
1. What the company does and its main products or services.
2. Main segments.
3. Where it operates (main markets / geographies).
4. Business environment and main competitors:
   a. If the COMPETITION text NAMES competitors: at most 5 main ones, by name as written.
   b. If it names none but describes the competition: at most 4 TYPES of competitors, in its own words.
   c. If it does not describe the competition: write exactly "{no_competition_en}"
   Never mix names and types.
5. Competitive advantage. Level {moat_answer}: {moat_instruction_en}

FACTS (from ValueCompass): industry label (context only) {industry}; revenue {revenue_en} (FY{fiscal_year}); company name: {company_name};
ONE SENTENCE: {one_sentence}; MOAT: level {moat_answer} / source {moat_source} / {moat_reasoning}
{description_block}
TEXT ({sections}, filing {accession}):
<<<
{section_text}
>>>

OUTPUT
{{"skill_id": "BG-1", "version": {version}, "text_en": "<background>",
 "competitors": ["<as named>"], "competitor_types": ["<as written>"], "quotes": [{{"text": "<exact quote>", "section": "..."}}]}}
"""


# ---------------------------------------------------------------- the competition chapter
def competition_chapter(item1_text: str) -> dict:
    """The Competition chapter of Item 1 -> {"text", "method": heading | paragraphs | none, "length"}. By heading: from the heading line to the next short heading line (at most 6,000 characters).
    Without a heading: the paragraphs that mention "compet" (at most 6,000 characters in all)."""
    lines = (item1_text or "").split("\n")
    for i, ln in enumerate(lines):
        if len(ln) <= 70 and COMPETITION_HEADING.match(ln):
            body, total = [], 0
            for nxt in lines[i + 1:]:
                short_heading = len(nxt.strip()) <= 60 and nxt.strip() and not nxt.strip().endswith((".", ",", ";", ":")) and not nxt.strip().startswith(("|", "•", "-", "(")) and total > 300
                if short_heading:
                    break
                if nxt.strip():
                    body.append(nxt)
                    total += len(nxt)
                if total >= CHAPTER_CAP:
                    break
            text = "\n".join(body)[:CHAPTER_CAP]
            if len(text) > 100:
                return {"text": text, "method": "heading", "length": len(text), "heading": ln.strip()}
    paras = [p for p in lines if re.search(r"compet", p, re.I) and len(p.strip()) > 60]
    text = "\n".join(paras)[:CHAPTER_CAP]
    if text:
        return {"text": text, "method": "paragraphs", "length": len(text), "heading": None}
    return {"text": "", "method": "none", "length": 0, "heading": None}


def item1_overview(item1_text: str, n: int = OVERVIEW_CHARS) -> str:
    """The opening of Item 1 (the Overview)."""
    return (item1_text or "")[:n]


# ---------------------------------------------------------------- the added checks
def raw_money_numbers(text: str) -> list:
    """Raw money figures: a number with thousands separators and a scale word ("331,839 million"), or 1,000,000 and more written out ("$5,749,377,000")."""
    out = []
    for m in _RAW_MONEY.finditer(text or ""):
        value = float(m.group(1).replace(",", ""))
        scale = (m.group(2) or "").lower()
        if scale and value >= 1000:
            out.append(m.group(0).strip())
        elif not scale and value >= 1_000_000 and m.group(0).strip().startswith("$"):
            out.append(m.group(0).strip())
    return out


def meta_phrases(text: str) -> list:
    return [p.replace("\\b", "") for p in META if re.search(p, text or "", re.I)]


def industry_copied(text: str, industry: str) -> bool:
    """The industry label of FACTS (e.g. "Insurance Carriers") written into the text."""
    label = re.sub(r"\s+", " ", (industry or "").strip()).lower()
    return bool(label) and len(label) > 3 and label in re.sub(r"\s+", " ", (text or "")).lower()


def extra_reasons(text: str, facts: dict) -> list:
    out = []
    raw = raw_money_numbers(text)
    if raw:
        out.append("raw_money_number (" + ", ".join(raw) + ")")
    out += [f"meta_phrase ({p})" for p in meta_phrases(text)]
    if industry_copied(text, facts.get("industry", "")):
        out.append(f"industry_label_copied ({facts.get('industry')})")
    return out


def check_version(raw: str, facts: dict, text_sent: str, sent: list, fiscal_year: Optional[int]) -> checks.CheckResult:
    """The usual D1 stage-A checks plus the three added ones."""
    res = C.check_background_en(raw, facts, text_sent, sent, fiscal_year)
    text = (res.parsed or {}).get("text_en") if isinstance(res.parsed, dict) else None
    if isinstance(text, str):
        extra = extra_reasons(text, facts)
        res.reasons += extra
        if extra:
            res.ok, res.state = False, "failed"
    return res


# ---------------------------------------------------------------- inputs and prompts
def blocks_for(version: str, sections: dict, chapter: dict, outside: Optional[str]) -> dict:
    """-> {"blocks": [(label, text)], "description": text or None, "input_chars": n} for V2-V5. V4 / V5 need ``outside`` (None -> no source)."""
    d1 = C.content_cfg()["d1"]
    comp = [("COMPETITION", chapter["text"])] if chapter["text"] else []
    if version == "V2":
        trimmed, _ = C.trim_d1_sections({}, "", sections)
        blocks = [(s, trimmed[s]) for s in d1["sections"] if trimmed.get(s)] + comp
        desc = None
    elif version == "V3":
        blocks = ([("OVERVIEW", item1_overview(sections.get("TXT-001", "")))] if sections.get("TXT-001") else []) + comp
        desc = None
    elif version in ("V4", "V5"):
        if not outside:
            return {"blocks": [], "description": None, "input_chars": 0, "no_source": True}
        blocks, desc = comp, outside
    else:
        raise ValueError(version)
    return {"blocks": blocks, "description": desc, "input_chars": sum(len(t) for _, t in blocks) + len(desc or ""), "no_source": False}


def build_prompt(version: str, facts: dict, accession: str, blocks: list, description: Optional[str], note: str = "") -> tuple:
    """-> (prompt, text_sent, sections_sent). ``text_sent`` is what the numbers and quotes are checked against: the TEXT blocks only (never the outside description)."""
    d1 = C.content_cfg()["d1"]
    text = "\n\n".join(f"[{s}]\n{t}" for s, t in blocks)
    desc_block = ("\nDESCRIPTION (context only, from "
                  + ("Yahoo Finance" if version == "V4" else "Wikipedia")
                  + "; not verified: take no number and no competitor from it, quote nothing from it):\n<<<\n" + (description or "") + "\n>>>\n") if description else ""
    p = TEMPLATE.format(industry=facts["industry"], revenue_en=facts["revenue_en"], fiscal_year=facts["fiscal_year"], one_sentence=facts["one_sentence"],
                        company_name=facts.get("company_display") or facts.get("company_name", ""), moat_answer=facts["moat_answer"], moat_source=facts["moat_source"],
                        moat_reasoning=facts["moat_reasoning"], moat_instruction_en=facts["moat_instruction_en"], sections=", ".join(s for s, _ in blocks), accession=accession,
                        section_text=text, version=d1["version"], no_competition_en=d1["no_competition_en"], description_block=desc_block)
    return (p + f"\nNOTE: {note}\n" if note else p), text, [s for s, _ in blocks]


def retry_note(reasons: list, facts: dict) -> str:
    note = C.retry_note([r for r in reasons if not r.startswith(("raw_money_number", "meta_phrase", "industry_label_copied"))] or ["see below"], facts)
    if any(r.startswith("raw_money_number") for r in reasons):
        note += f" Write money amounts exactly as FACTS writes them (revenue {facts['revenue_en']}); no raw figures."
    if any(r.startswith("meta_phrase") for r in reasons):
        note += " Do not refer to the source or write in the first person (no 'in the report', 'the filing', 'named by name', 'we have')."
    if any(r.startswith("industry_label_copied") for r in reasons):
        note += " Do not copy the industry label from FACTS into the text."
    return note

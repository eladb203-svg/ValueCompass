"""BP-1 - the business-profile extraction (AI skills 2026-10-26_10-30, 3.1.4): one model call per company per annual report, the model answers with codes and quotes, code checks everything.

``select_text`` picks what is sent, ``build_prompt`` fills the skill, ``validate`` checks every field on its own (a failed field is ``failed``, the others are kept), ``run`` makes the call and the one
retry (with the exact reasons of the failed fields). Pure apart from the model call, which goes through ``client.generate`` (a capped client).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from src.ai import checks
from src.ai.checks import normalize
from src.ai.sections import split_sections

from .vocab import Vocab, region_of

SKILL_ID, SKILL_VERSION = "BP-1", "3"
OPENING_CHARS = 8000
COMPETITION_CAP = 12000
PRODUCTS_CAP = 4000
MAX_CORE_WORDS = 12
CONTENT_WORD_SHARE = 0.70
MAX_COMPETITORS, MAX_TYPES = 5, 4
FIELDS = ("display_name", "core_activity", "customer_types", "revenue_models", "competitors", "competitor_types", "segments", "products_services", "regions")
ALWAYS = ("display_name", "core_activity", "customer_types", "revenue_models", "competitors", "competitor_types")
PRAISE = ("leading", "largest", "world-class", "world class", "premier", "best-in-class", "foremost", "renowned", "number one", "world's", "greatest", "unrivaled", "unparalleled")
_STOP = {"and", "the", "for", "its", "with", "that", "from", "into", "other", "such", "various", "related", "their", "which", "also", "has", "have", "are", "services", "service", "products", "product"}

HEAD = """SYSTEM
You assist ValueCompass. From the annual-report TEXT below, fill the JSON under OUTPUT.
Use ONLY the TEXT. For every item give an exact, contiguous quote from the TEXT that supports it.
Use ONLY the codes listed for closed fields. If nothing fits, use "other" with the original words.
If the TEXT does not say, return null or []. Do not guess. Return ONLY the JSON object.

FIELDS
"""
TAIL = """
TEXT (filing {accession}, sections: {section_list}):
<<<
{text}
>>>

OUTPUT
{output}
"""
# the text of each field of the skill (v2 of 2026-10-26: display_name added; revenue_models only from a description of the revenue; customer_types include business and institutional customers)
FIELD_TEXT = {
    "display_name": """display_name: the short name the company uses for itself in the report (for example "Coca-Cola", "Intel", "Chubb"), without a legal suffix such as Inc., Corp., Co., Ltd. or plc. The quote must show the
  company using that name.""",
    "core_activity": """core_activity: what the company does — a verb phrase of at most 12 words, third person,
  built from the words of your quote (e.g., "manufactures and sells beverage concentrates and
  finished beverages"). No praise words (leading, largest, world-class, premier), no numbers.""",
    "customer_types": """customer_types: 1–3 codes from {customer_types}. Include business, institutional and government customers when the TEXT mentions them.""",
    "revenue_models": """revenue_models: 1–3 codes from {revenue_models}, the main one first, from what the TEXT says the company sells or charges for (a bank earns interest, fees and trading; a manufacturer sells products ...). Quote the text that shows it. Return [] only if the TEXT says nothing about it.""",
    "competitors": """competitors: up to 5 companies the report names as competitors (read every competition paragraph, including those of each segment). A competitor offers similar
  products or services to the same customers — not a supplier, customer, distributor or broker.""",
    "competitor_types": """competitor_types: ONLY if the report names no competitor — up to 4 items, each
  {{"industry": code from {industries} or a generic code from {generic_types}, "scope": one of
   {scopes} or null}}.""",
    "segments": """segments: the reportable segments exactly as the report names them — {{"name": "<as reported>", "share_pct": <percent of total revenue if the TEXT states it, else null>, "quote": "..."}}.""",
    "products_services": """products_services: up to 5 main product lines, services or brands — {{"name": "<as reported>", "kind": "product_line" | "service" | "brand", "share_pct": <percent if stated, else null>, "quote": "..."}}.""",
    "regions": """regions: revenue by geographic area as the report names it — {{"name": "<as reported>", "share_pct": <percent of total revenue if the TEXT states it, else null>, "quote": "..."}}.""",
}
SHAPES = {
    "display_name": {"value": "...", "quote": "..."},
    "core_activity": {"value": "...", "quote": "..."},
    "customer_types": [{"code": "...", "other_text": None, "quote": "..."}],
    "revenue_models": [{"code": "...", "other_text": None, "quote": "..."}],
    "competitors": [{"name": "...", "quote": "..."}],
    "competitor_types": [{"industry": "...", "scope": None, "quote": "..."}],
    "segments": [{"name": "...", "share_pct": None, "quote": "..."}],
    "products_services": [{"name": "...", "kind": "product_line", "share_pct": None, "quote": "..."}],
    "regions": [{"name": "...", "share_pct": None, "quote": "..."}],
}
ORDER = ("display_name", "core_activity", "customer_types", "revenue_models", "competitors", "competitor_types", "segments", "products_services", "regions")


# ---------------------------------------------------------------- the text sent
def _paragraphs(t: str) -> list:
    return [p.strip() for p in re.split(r"\n\s*\n|\n", t) if len(p.strip()) > 40]


def select_text(filing_text: str, need_products: bool) -> tuple:
    """-> ([(section id, text)], error or None). Item 1 opening (8,000 characters); ALL the competition paragraphs of Item 1 (the Competition sub-section and every other paragraph that contains
    "compet", e.g. one per segment), always; the paragraphs about products and brands only when XBRL has no product axis."""
    secs = split_sections(filing_text)
    item1 = secs["TXT-001"].text
    if not item1:
        return [], "business_section_not_found"
    out = [("TXT-001", item1[:OPENING_CHARS])]
    opening = normalize(item1[:OPENING_CHARS])
    parts, seen = [], set()
    for chunk in ([secs["TXT-003"].text] if secs["TXT-003"].text else []) + [p for p in _paragraphs(item1) if re.search(r"compet", p, re.I)]:
        for p in _paragraphs(chunk):
            k = normalize(p)
            if k not in seen and k not in opening:
                seen.add(k)
                parts.append(p)
    comp = "\n".join(parts)
    if comp:
        out.append(("TXT-003", comp[:COMPETITION_CAP]))
    if need_products:
        prod = [p for p in _paragraphs(item1[OPENING_CHARS:]) if re.search(r"\b(brands?|product lines?|products? (?:include|are)|offerings?)\b", p, re.I)]
        if prod:
            out.append(("TXT-PRD", "\n".join(prod)[:PRODUCTS_CAP]))
    return out, None


def sent_text(sections: list) -> str:
    return "\n\n".join(f"[{s}]\n{t}" for s, t in sections)


# ---------------------------------------------------------------- prompt
def fields_wanted(have_segments: bool, have_products: bool, have_regions: bool) -> list:
    return list(ALWAYS) + [f for f, have in (("segments", have_segments), ("products_services", have_products), ("regions", have_regions)) if not have]


def output_shape(fields: list) -> str:
    shape = {"skill_id": SKILL_ID, "version": int(SKILL_VERSION)}
    shape.update({f: SHAPES[f] for f in ORDER if f in fields})
    return json.dumps(shape, ensure_ascii=False)


def build_prompt(vocab: Vocab, accession: str, sections: list, fields: list, note: str = "") -> str:
    cc = vocab.competitor_codes()
    body = "\n".join(FIELD_TEXT[f] for f in ORDER if f in fields)
    body = body.format(customer_types=", ".join(vocab.codes("customer_types")), revenue_models=", ".join(vocab.codes("revenue_models")), industries=", ".join(cc["industry"]),
                       generic_types=", ".join(cc["generic"]), scopes="/".join(cc["scope"]))
    p = HEAD + body + "\n" + TAIL.format(accession=accession, section_list=", ".join(s for s, _ in sections), text=sent_text(sections), output=output_shape(fields))
    return p + (f"\nNOTE: {note}\n" if note else "")


# ---------------------------------------------------------------- checks
def third_person_verb(word: str) -> bool:
    """A third-person singular verb as the first word of core_activity ("provides", "operates", "is", "has"): ends with a single s."""
    w = word.lower().strip(",.;:")
    return w.isalpha() and w.endswith("s") and not w.endswith("ss")


def stem(w: str) -> str:
    w = w.lower()
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    return w[:-1] if w.endswith("e") and len(w) > 3 else w


def same_word(a: str, b: str) -> bool:
    """Two stems are the same word family: equal, or one is the other with a derivational ending ("design" / "designer", "manufactur" / "manufacturer", "manag" / "management"): a common prefix of
    at least 4 letters that covers all of the shorter stem but at most one letter."""
    if a == b:
        return True
    m = 0
    for x, y in zip(a, b):
        if x != y:
            break
        m += 1
    return m >= 4 and m >= min(len(a), len(b)) - 1


def content_words(t: str) -> list:
    return [w for w in re.findall(r"[A-Za-z][A-Za-z\-']+", t or "") if len(w) >= 3 and w.lower() not in _STOP]


def _quote(q, text_norm: str, sections: list, reasons: list, label: str) -> Optional[dict]:
    if not isinstance(q, str) or not q.strip():
        reasons.append(f"{label}: quote_missing")
        return None
    sub: list = []
    res = checks._check_quotes([{"text": q, "section": None}], text_norm, [s for s, _ in sections], sub)
    if sub or not res or not res[0]["found"]:
        reasons.append(f"{label}: quote_not_found")
        return None
    return {"text": q, "section": res[0]["section"]}


def _num(x) -> Optional[float]:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _share(item: dict, quote: dict) -> Optional[float]:
    """share_pct as a fraction when the number appears in the quote; otherwise None (a share the quote does not show is not kept)."""
    s = _num(item.get("share_pct"))
    if s is None or not (0 < s <= 100):
        return None
    shown = {m.replace(",", "") for m in re.findall(r"\d[\d,]*\.?\d*", quote["text"])}
    cands = {f"{s:g}", f"{s:.1f}", f"{s:.0f}"}
    return s / 100.0 if cands & shown else None


def check_core(v, text_norm, sections) -> dict:
    reasons: list = []
    if v in (None, "", {}) or (isinstance(v, dict) and not v.get("value")):
        return {"status": "not_found", "source": "ai", "items": [], "reasons": []}
    if not isinstance(v, dict):
        return {"status": "failed", "source": "ai", "items": [], "reasons": ["core_activity: not_an_object"]}
    value = str(v.get("value") or "").strip()
    q = _quote(v.get("quote"), text_norm, sections, reasons, "core_activity")
    words = value.split()
    if len(words) > MAX_CORE_WORDS:
        reasons.append(f"core_activity: over_{MAX_CORE_WORDS}_words ({len(words)}): shorten it to at most {MAX_CORE_WORDS} words")
    if words and not third_person_verb(words[0]):
        reasons.append(f"core_activity: must be a verb phrase that starts with a third-person singular verb such as 'manufactures' or 'provides' (it starts with '{words[0]}')")
    if re.search(r"\d", value):
        reasons.append("core_activity: contains_digits")
    praise = [w for w in PRAISE if w in value.lower()]
    if praise:
        reasons.append(f"core_activity: praise_words ({', '.join(praise)})")
    if checks.has_deliberation(value):
        reasons.append("core_activity: deliberation_words")
    if q:
        cw = content_words(value)
        qs = {stem(w) for w in content_words(q["text"])} | {stem(w) for w in re.findall(r"[A-Za-z]+", q["text"])}
        if cw:
            share = sum(1 for w in cw if any(same_word(stem(w), x) for x in qs)) / len(cw)
            if share < CONTENT_WORD_SHARE:
                reasons.append(f"core_activity: only {share:.0%} of the content words are in the quote (need {CONTENT_WORD_SHARE:.0%})")
    if reasons:
        return {"status": "failed", "source": "ai", "items": [], "reasons": reasons}
    return {"status": "ok", "source": "ai", "reasons": [], "items": [{"value": value, "quote": q["text"], "section": q["section"], "source": "ai", "status": "ok"}]}


_LEGAL_SUFFIX = re.compile(r"[\s,]+(?:inc|corp|corporation|co|company|ltd|limited|plc|llc|lp|n\.?v|s\.?a|ag|se|incorporated)\.?$", re.I)


def check_display(v, text_norm, sections) -> dict:
    """display_name: the short name the report itself uses; no legal suffix; it must be in its quote."""
    if v in (None, "", {}) or (isinstance(v, dict) and not v.get("value")):
        return {"status": "not_found", "source": "ai", "items": [], "reasons": []}
    if not isinstance(v, dict):
        return {"status": "failed", "source": "ai", "items": [], "reasons": ["display_name: not_an_object"]}
    value, reasons = str(v.get("value") or "").strip(), []
    q = _quote(v.get("quote"), text_norm, sections, reasons, "display_name")
    if len(value.split()) > 5:
        reasons.append("display_name: more_than_5_words")
    if q:                                                    # a legal suffix or a leading "The" is removed by code when the shorter name is still in the quote
        short = re.sub(r"^the\s+", "", _LEGAL_SUFFIX.sub("", value).strip(" ,"), flags=re.I).strip()
        if short and short != value and normalize(short).lower() in normalize(q["text"]).lower():
            value = short
    if _LEGAL_SUFFIX.search(value):
        reasons.append("display_name: ends_with_a_legal_suffix (Inc., Corp., Co., Ltd. ...)")
    if q and normalize(value).lower() not in normalize(q["text"]).lower():
        reasons.append("display_name: name_not_in_quote")
    if reasons:
        return {"status": "failed", "source": "ai", "items": [], "reasons": reasons}
    return {"status": "ok", "source": "ai", "reasons": [], "items": [{"value": value, "quote": q["text"], "section": q["section"], "source": "ai", "status": "ok"}]}


_LICENSING_QUOTE = re.compile(r"licens|royalt|franchis", re.I)
_REVENUE_WORDS = re.compile(r"revenue|fee|income|royalt|earn|generat|receiv|paid|payment", re.I)


def licensing_described(quote: str) -> bool:
    """`licensing` is a revenue model only when the quote itself talks about licensing / royalties as income ("we own or license brands" is not that)."""
    return bool(_LICENSING_QUOTE.search(quote or "") and _REVENUE_WORDS.search(quote or ""))


def check_coded(items, field: str, vocab: Vocab, text_norm, sections, limit: int = 3) -> dict:
    """customer_types / revenue_models: codes in the list; `other` keeps the original text and is flagged."""
    if not items:
        return {"status": "not_found", "source": "ai", "items": [], "reasons": []}
    if not isinstance(items, list):
        return {"status": "failed", "source": "ai", "items": [], "reasons": [f"{field}: not_a_list"]}
    reasons, out, seen = [], [], set()
    for it in items[:limit + 3]:
        if not isinstance(it, dict):
            reasons.append(f"{field}: item_not_an_object")
            continue
        code = str(it.get("code") or "").strip()
        if code not in vocab.labels[field]:
            m = vocab.match_label(field, code)
            if m:
                code = m
            else:
                reasons.append(f"{field}: code_not_in_list ({code})")
                continue
        other_text = (it.get("other_text") or None) if code == "other" else None
        if code == "other" and not other_text:
            reasons.append(f"{field}: other_without_text")
            continue
        q = _quote(it.get("quote"), text_norm, sections, reasons, f"{field}/{code}")
        if q is None or code in seen:
            continue
        if field == "revenue_models" and code == "licensing" and not licensing_described(q["text"]):
            continue                                        # no quote that describes licensing income: the item is dropped
        seen.add(code)
        out.append({"code": code, "other_text": other_text, "quote": q["text"], "section": q["section"], "source": "ai", "status": "other" if code == "other" else "ok"})
    if len(items) > limit:
        reasons.append(f"{field}: more_than_{limit}_items")
    out = out[:limit]
    if reasons:
        return {"status": "failed", "source": "ai", "items": out, "reasons": reasons}
    return {"status": "other" if any(i["status"] == "other" for i in out) else "ok", "source": "ai", "reasons": [], "items": out}


def check_competitors(items, text_norm, sections, company_name: str = "") -> dict:
    if not items:
        return {"status": "not_found", "source": "ai", "items": [], "reasons": []}
    if not isinstance(items, list):
        return {"status": "failed", "source": "ai", "items": [], "reasons": ["competitors: not_a_list"]}
    reasons, out, seen = [], [], set()
    own = re.sub(r"[^a-z0-9]", "", company_name.lower())
    for it in items:
        name = str((it or {}).get("name") or "").strip() if isinstance(it, dict) else ""
        if not name:
            reasons.append("competitors: name_missing")
            continue
        q = _quote(it.get("quote"), text_norm, sections, reasons, f"competitors/{name}")
        if q is None:
            continue
        if normalize(name).lower() not in normalize(q["text"]).lower():
            reasons.append(f"competitors/{name}: name_not_in_quote")
            continue
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in seen or (own and key and (key in own or own in key)):
            continue
        seen.add(key)
        out.append({"name": name, "quote": q["text"], "section": q["section"], "source": "ai", "status": "ok"})
    if len(out) > MAX_COMPETITORS:
        reasons.append(f"competitors: more_than_{MAX_COMPETITORS} ({len(out)})")
    if reasons:
        return {"status": "failed", "source": "ai", "items": out[:MAX_COMPETITORS], "reasons": reasons}
    return {"status": "ok" if out else "not_found", "source": "ai", "reasons": [], "items": out}


def check_types(items, vocab: Vocab, text_norm, sections) -> dict:
    if not items:
        return {"status": "not_found", "source": "ai", "items": [], "reasons": []}
    if not isinstance(items, list):
        return {"status": "failed", "source": "ai", "items": [], "reasons": ["competitor_types: not_a_list"]}
    cc = vocab.competitor_codes()
    allowed = set(cc["industry"]) | set(cc["generic"])
    reasons, out, seen = [], [], set()
    for it in items:
        if not isinstance(it, dict):
            reasons.append("competitor_types: item_not_an_object")
            continue
        ind = str(it.get("industry") or "").strip()
        if ind not in allowed:
            m = vocab.match_label("competitor_types", ind) or next((c for n, c in vocab.industry_codes.items() if n.lower() == ind.lower()), None)
            if m in allowed:
                ind = m
            else:
                reasons.append(f"competitor_types: industry_not_in_list ({ind})")
                continue
        scope = it.get("scope")
        if scope not in (None, "") and scope not in cc["scope"]:
            reasons.append(f"competitor_types/{ind}: scope_not_in_list ({scope})")
            continue
        q = _quote(it.get("quote"), text_norm, sections, reasons, f"competitor_types/{ind}")
        if q is None or (ind, scope) in seen:
            continue
        seen.add((ind, scope))
        out.append({"industry": ind, "scope": scope or None, "quote": q["text"], "section": q["section"], "source": "ai", "status": "other" if ind == "other" else "ok"})
    if len(out) > MAX_TYPES:
        reasons.append(f"competitor_types: more_than_{MAX_TYPES} ({len(out)})")
    out = out[:MAX_TYPES]
    if reasons:
        return {"status": "failed", "source": "ai", "items": out, "reasons": reasons}
    return {"status": "other" if any(i["status"] == "other" for i in out) else ("ok" if out else "not_found"), "source": "ai", "reasons": [], "items": out}


def check_named_list(items, field: str, text_norm, sections, limit: int = 5, kinds: bool = False, region: bool = False) -> dict:
    """segments / products_services / regions from the text (the fallback of a missing XBRL axis): the name must appear in its quote."""
    if not items:
        return {"status": "not_found", "source": "ai", "items": [], "reasons": []}
    if not isinstance(items, list):
        return {"status": "failed", "source": "ai", "items": [], "reasons": [f"{field}: not_a_list"]}
    reasons, out = [], []
    for it in items:
        name = str((it or {}).get("name") or "").strip() if isinstance(it, dict) else ""
        if not name:
            reasons.append(f"{field}: name_missing")
            continue
        q = _quote(it.get("quote"), text_norm, sections, reasons, f"{field}/{name}")
        if q is None:
            continue
        if normalize(name).lower() not in normalize(q["text"]).lower():
            reasons.append(f"{field}/{name}: name_not_in_quote")
            continue
        row = {"name": name, "share": _share(it, q), "quote": q["text"], "section": q["section"], "source": "ai", "status": "ok"}
        if kinds:
            k = it.get("kind")
            row["kind"] = k if k in ("product_line", "service", "brand") else "product_line"
        if region:
            code = region_of(name)
            row = {**row, "code": code, "status": "ok" if code != "other" else "other"}
            if code == "other":
                row["other_text"] = name
        out.append(row)
    if reasons:
        return {"status": "failed", "source": "ai", "items": out[:limit], "reasons": reasons}
    out = out[:limit]
    return {"status": "other" if any(i["status"] == "other" for i in out) else ("ok" if out else "not_found"), "source": "ai", "reasons": [], "items": out}


def validate(answer: Optional[dict], vocab: Vocab, sections: list, fields: list, company_name: str = "") -> dict:
    """-> {field: field result} for the requested fields. A field with a problem is `failed` with its reasons; the others are unaffected. Competitors and competitor types are never both kept."""
    if not isinstance(answer, dict):
        return {f: {"status": "failed", "source": "ai", "items": [], "reasons": ["invalid_json"]} for f in fields}
    text_norm = normalize(sent_text(sections))
    res = {}
    for f in fields:
        v = answer.get(f)
        if f == "display_name":
            res[f] = check_display(v, text_norm, sections)
        elif f == "core_activity":
            res[f] = check_core(v, text_norm, sections)
        elif f in ("customer_types", "revenue_models"):
            res[f] = check_coded(v, f, vocab, text_norm, sections)
        elif f == "competitors":
            res[f] = check_competitors(v, text_norm, sections, company_name)
        elif f == "competitor_types":
            res[f] = check_types(v, vocab, text_norm, sections)
        elif f == "segments":
            res[f] = check_named_list(v, f, text_norm, sections, limit=10)
        elif f == "products_services":
            res[f] = check_named_list(v, f, text_norm, sections, limit=5, kinds=True)
        elif f == "regions":
            res[f] = check_named_list(v, f, text_norm, sections, limit=10, region=True)
    if res.get("competitors", {}).get("items") and res.get("competitor_types", {}).get("items"):
        res["competitor_types"] = {"status": "not_found", "source": "ai", "items": [], "reasons": [], "note": "dropped: the report names competitors"}
    for f, r in res.items():
        for it in r["items"]:
            for key in ("value", "other_text"):
                if key in it and it[key] and checks.has_deliberation(str(it[key])):
                    r["status"] = "failed"
                    r["reasons"].append(f"{f}: deliberation_words")
    return res


# ---------------------------------------------------------------- the call
def retry_note(failed: dict) -> str:
    return ("Your previous answer failed these checks: " + " | ".join(f"{f}: {'; '.join(r['reasons'])}" for f, r in failed.items())
            + ". Fix ONLY these fields (keep the others as they were) and answer again with the whole JSON object.")


def run(client, vocab: Vocab, accession: str, sections: list, fields: list, company_name: str = "", seed_base: int = 0, note0: str = "") -> dict:
    """-> {"fields": {field: result}, "attempts": [...], "model": str}. One call; one retry when a field failed (or the JSON is invalid) with the exact reasons. A field that still fails is `failed`."""
    note, attempts, result = note0, [], {}
    model = getattr(client, "model", "")
    for attempt in (1, 2):
        prompt = build_prompt(vocab, accession, sections, fields, note)
        rep = client.generate(prompt, seed_offset=seed_base + attempt - 1)
        model = getattr(rep, "model", model) or model
        answer = checks.parse_json(rep.text)
        res = validate(answer, vocab, sections, fields, company_name)
        for f in fields:                       # a field that passed in an earlier attempt is kept
            if f not in result or result[f]["status"] == "failed":
                result[f] = res[f]
        failed = {f: r for f, r in result.items() if r["status"] == "failed"}
        attempts.append({"attempt": attempt, "seed_offset": seed_base + attempt - 1, "prompt_chars": len(prompt), "raw": rep.text, "failed": {f: r["reasons"] for f, r in res.items() if r["status"] == "failed"}})
        if not failed:
            break
        note = retry_note(failed)
    return {"fields": result, "attempts": attempts, "model": model}

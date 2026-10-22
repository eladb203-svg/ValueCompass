"""Run the AI skills for one company-year: build prompts, call the model, check, store (AI spec sections 4, 5, 8).

Nothing here computes a score: it returns/stores answers; the engines turn them into points (src/scoring/ai_items.py).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from . import checks
from .prompt import build_classification_prompt, build_prompt, prompt_version, scoring_skills, txt_sections
from .sections import Filing, split_sections
from .store import AssessmentStore


@dataclass
class Company:
    ticker: str
    name: str
    profile: str
    fiscal_year: int                  # fiscal year of the annual report assessed (the engines' latest fiscal year)
    filing: Filing
    code_facts: dict = field(default_factory=dict)   # skill id -> text given to the AI (A8, A13)
    _sections: Optional[dict] = None

    def sections(self) -> dict:
        if self._sections is None:
            self._sections = split_sections(self.filing.text)
        return self._sections


@dataclass
class Stats:
    calls: int = 0
    cached: int = 0
    rejected: int = 0
    seconds: float = 0.0
    prompt_tokens: int = 0
    output_tokens: int = 0


def _row(co: Company, skill: dict, model: str) -> dict:
    return {"ticker": co.ticker, "fiscal_year": co.fiscal_year, "question_id": skill["skill_id"], "prompt_version": str(skill["version"]),
            "accession": co.filing.accession, "model": model, "approval_status": "approved"}


def prompt_version_of(skill: dict, variant: str = "3.1") -> str:
    """The stored prompt version: the skill version, plus `.1` for the candidate template with `facts_check` (K5a-3)."""
    return str(skill["version"]) + (".1" if variant == "3.1" else "")


def ask(co: Company, skill: dict, client, store: AssessmentStore, stats: Stats, force: bool = False, variant: str = "3.1", thinking_budget=None) -> dict:
    """One skill for one company-year. Returns the stored row. An existing row (same company, year, question, prompt version) is returned without a call unless ``force``."""
    model = client.model if client is not None else ""
    pv = prompt_version_of(skill, variant)
    ex = None if force else store.get(co.ticker, co.fiscal_year, skill["skill_id"], pv)
    if ex is not None:
        stats.cached += 1
        return ex
    secs = co.sections()
    need = txt_sections(skill)
    base = {**_row(co, skill, model), "prompt_version": pv}
    sections = {sid: secs[sid].text for sid in need if sid in secs and secs[sid].found}
    flags = [f"section_not_found:{sid}" for sid in need if sid not in sections]
    flags += [f"{sid}:{f}" for sid in need if sid in secs for f in secs[sid].flags if f != "section_not_found"]
    if need[0] not in sections:        # the primary section is missing: no call, insufficient evidence
        row = {**base, "answer": None, "state": "insufficient_evidence", "model": "",
               "evidence": {"quotes": [], "reasoning": "", "extra": {}, "flags": flags + ["section_not_found"], "reasons": ["primary_section_missing"], "check_ok": True,
                            "sections_sent": []}, "raw_answer": None, "usage": {}}
        return store.put(row)
    ctx = {"company_name": co.name, "ticker": co.ticker, "fiscal_year": f"FY{co.fiscal_year}", "profile": co.profile, "accession": co.filing.accession,
           "code_facts": co.code_facts.get(skill["skill_id"])}
    prompt, text_sent, sent = build_prompt(skill, ctx, sections, variant)
    facts_text = ctx.get("code_facts")
    last = None
    finishes = []
    retry_note = ""
    used = set()                       # each retry kind at most once: invalid JSON (another seed), A11 inconsistency, a quote not found (AI skills document 14-49)
    attempt = 0
    while True:
        attempt += 1
        if retry_note:
            prompt, text_sent, sent = build_prompt(skill, ctx, sections, variant, note=retry_note)
        t0 = time.monotonic()
        rep = client.generate(prompt, seed_offset=attempt - 1, thinking_budget=thinking_budget) if thinking_budget is not None else client.generate(prompt, seed_offset=attempt - 1)
        stats.calls += 1
        stats.seconds += time.monotonic() - t0
        stats.prompt_tokens += rep.prompt_tokens
        stats.output_tokens += rep.output_tokens
        finishes.append(rep.finish_reason)
        res = checks.check_judgment(rep.text, skill, text_sent, sent, facts_text, require_facts_check=(variant == "3.1"))
        last = (rep, res)
        if "exposure_inconsistent" in res.reasons and "exposure" not in used:
            used.add("exposure")
            retry_note = "Your share_pct does not match the level you chose"
            continue
        if res.reasons and set(res.reasons) == {"quote_not_found"} and "quote" not in used:
            used.add("quote")
            bad = next((q["text"] for q in res.quotes if not q["found"]), "")
            retry_note = f"Quote not found verbatim: {bad[:120]}. Copy one continuous passage exactly as it appears in the TEXT."
            continue
        if "invalid_json" in res.reasons and "json" not in used:
            used.add("json")
            continue
        break
    rep, res = last
    if not res.ok:
        stats.rejected += 1
    row = {**base, "model": rep.model, "answer": res.answer, "state": res.state,
           "evidence": {"quotes": res.quotes, "reasoning": res.reasoning, "extra": res.extra, "flags": flags + res.flags, "reasons": res.reasons, "check_ok": res.ok,
                        "sections_sent": sent, "text_chars_sent": len(text_sent)},
           "raw_answer": rep.text, "usage": {"prompt_tokens": rep.prompt_tokens, "output_tokens": rep.output_tokens, "thought_tokens": rep.thought_tokens,
                                            "latency_s": round(rep.latency, 2), "attempts": rep.attempts, "finish_reasons": finishes, "attempt_log": rep.attempt_log}}
    return store.put(row)


def classify_industry(co: Company, sic, sic_description, provider_industry, client, store: AssessmentStore, stats: Stats, industries: list, force: bool = False) -> dict:
    """C1 / CLS-1 (tier 3 of Part B.1): returns the stored row; ``evidence.extra.industry`` is the chosen industry (None when rejected / insufficient)."""
    from .prompt import classification_skill
    skill = classification_skill()
    ex = None if force else store.get(co.ticker, co.fiscal_year, "CLS-1", skill["version"])
    if ex is not None:
        stats.cached += 1
        return ex
    base = _row(co, skill, client.model)
    sec = co.sections()["TXT-001"]
    if not sec.found:
        row = {**base, "model": "", "answer": None, "state": "insufficient_evidence", "evidence": {"flags": ["section_not_found:TXT-001"], "quotes": [], "extra": {}, "reasons": [], "check_ok": True},
               "raw_answer": None, "usage": {}}
        return store.put(row)
    ctx = {"company_name": co.name, "ticker": co.ticker, "fiscal_year": f"FY{co.fiscal_year}", "sic": sic, "sic_description": sic_description,
           "provider_industry": provider_industry, "accession": co.filing.accession}
    prompt = build_classification_prompt(ctx, sec.text, industries)
    text_sent = f"[TXT-001]\n{sec.text}"
    for attempt in (1, 2):
        t0 = time.monotonic()
        rep = client.generate(prompt)
        stats.calls += 1
        stats.seconds += time.monotonic() - t0
        stats.prompt_tokens += rep.prompt_tokens
        stats.output_tokens += rep.output_tokens
        res = checks.check_classification(rep.text, industries, text_sent)
        if "invalid_json" not in res.reasons:
            break
    if not res.ok:
        stats.rejected += 1
    row = {**base, "model": rep.model, "answer": None, "state": res.state,
           "evidence": {"quotes": res.quotes, "reasoning": res.reasoning, "extra": res.extra, "flags": res.flags + sec.flags, "reasons": res.reasons, "check_ok": res.ok},
           "raw_answer": rep.text, "usage": {"prompt_tokens": rep.prompt_tokens, "output_tokens": rep.output_tokens, "latency_s": round(rep.latency, 2)}}
    return store.put(row)

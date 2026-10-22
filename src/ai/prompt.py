"""Skill files (data) and the single prompt template (AI skills document, section 1). Pure; the only I/O is reading the YAML files."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

SKILLS_DIR = Path(__file__).with_name("skills")


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    return yaml.safe_load((SKILLS_DIR / name).read_text(encoding="utf-8"))


def scoring_skills() -> dict:
    d = _load("scoring.yaml")
    return {s["skill_id"]: s for s in d["skills"]}


def scoring_template(variant: str = "3") -> str:
    """variant "3" = the standard template; "3.1" = the candidate with a mandatory `facts_check` field before `answer` (K5a-3)."""
    return _load("scoring.yaml")["template_31" if variant == "3.1" else "template"]


def classification_skill() -> dict:
    return _load("classification.yaml")["skills"][0]


def classification_template() -> str:
    return _load("classification.yaml")["template"]


def prompt_version(skill: dict) -> str:
    return str(skill["version"])


def txt_sections(skill: dict) -> list:
    """The sections of a skill: TXT-00x text sections and NOTE-xxx note sections (the first one listed is the primary section)."""
    return [s for s in skill["sections"] if s.startswith(("TXT-", "NOTE-"))]


def build_prompt(skill: dict, ctx: dict, sections: dict, variant: str = "3") -> tuple:
    """-> (prompt, text_sent, sections_sent). ``sections`` = {TXT-00x: text}; ``ctx`` = company_name, ticker, fiscal_year, profile, accession, code_facts (optional)."""
    sent = [(sid, sections[sid]) for sid in txt_sections(skill) if sections.get(sid)]
    text = "\n\n".join(f"[{sid}]\n{t}" for sid, t in sent)
    pn = (skill.get("profile_notes") or {}).get(ctx.get("profile"))
    extra = skill.get("extra_output")
    prompt = scoring_template(variant).format(
        skill_id=skill["skill_id"], version=skill["version"], question=skill["question"], card=skill["card"], scale_2=skill["scale_2"], scale_1=skill["scale_1"],
        scale_0=skill["scale_0"], evidence_focus=skill["evidence_focus"], profile_note=(f"Profile note ({ctx.get('profile')}): {pn}" if pn else ""),
        code_facts=ctx.get("code_facts") or "(none provided for this question)",
        company_name=ctx["company_name"], ticker=ctx["ticker"], fiscal_year=ctx["fiscal_year"], profile=ctx.get("profile", ""),
        sections=", ".join(s for s, _ in sent), accession=ctx.get("accession", ""), section_text=text,
        extra_output=(", " + extra) if extra else "")
    return prompt, text, [s for s, _ in sent]


def build_classification_prompt(ctx: dict, text: str, industries: list) -> str:
    skill = classification_skill()
    defs = skill.get("industry_definitions") or {}
    lst = "\n".join(f"- {i}" for i in industries)
    if defs:   # boundaries in a separate block, so the model answers with the bare name from the list
        lst += "\nBoundaries (the answer is still only the name):\n" + "\n".join(f"* {k} = {v}" for k, v in defs.items())
    return classification_template().format(
        industry_list_with_definitions=lst, company_name=ctx["company_name"], ticker=ctx["ticker"], fiscal_year=ctx["fiscal_year"], sic=ctx.get("sic") or "",
        sic_description=ctx.get("sic_description") or "", provider_industry=ctx.get("provider_industry") or "", accession=ctx.get("accession", ""),
        section_text=f"[TXT-001]\n{text}", version=skill["version"])

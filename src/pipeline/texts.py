"""Review of the Hebrew backgrounds (K6c section 5; AI skills document 2026-10-25_12-00, 3.2). A Hebrew background that passed every check is shown at once with the marker
"תרגום אוטומטי" (``human_reviewed = false``). A person can:

  confirm    as is                       -> human_reviewed = true, the marker goes away
  edit       a corrected text            -> the code runs the Hebrew checks again (numbers, names, script, length, glossary terms, moat phrase); stored with edited_by = human and
                                            human_reviewed = true; a corrected word is proposed for the T1 glossary
  sendback   pull the text               -> approval_status = pending_review: not shown until it is fixed
  glossary approve   add a proposed term (with its English term) to ``t1_glossary.yaml`` - only a person adds to the glossary.
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
PROPOSALS = ROOT / "scripts" / "ai_store" / "glossary_proposals.jsonl"
GLOSSARY = ROOT / "src" / "ai" / "skills" / "t1_glossary.yaml"


class EditRejected(Exception):
    def __init__(self, reasons: list):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def pending_review(store) -> list:
    """Approved Hebrew backgrounds nobody has looked at yet, with the English text next to each: [{id, ticker, fiscal_year, he, en, ...}]."""
    out = []
    for r in store.rows():
        if r["kind"] == "background" and r["language"] == "he" and r["approval_status"] == "approved" and not r["human_reviewed"]:
            en = store.get(r["ticker"], r["fiscal_year"], "background", r["prompt_version"], r.get("run_id") or "", "en")
            out.append({"id": r["id"], "ticker": r["ticker"], "fiscal_year": r["fiscal_year"], "prompt_version": r["prompt_version"], "he": r["text"], "en": (en or {}).get("text")})
    return sorted(out, key=lambda x: (x["ticker"], x["fiscal_year"]))


def confirm(store, text_id: int) -> dict:
    return store.update(text_id, human_reviewed=True)


def sendback(store, text_id: int) -> dict:
    return store.update(text_id, approval_status="pending_review")


def check_edit(he_text: str, en_text: str, facts: dict, competitors: list) -> list:
    """The Hebrew checks of stage B on a corrected text. -> the reasons it is rejected for (empty = accepted)."""
    from src.ai import content as C
    raw = json.dumps({"skill_id": "TR-1", "version": 1, "text_he": he_text}, ensure_ascii=False)
    return list(C.check_translation(raw, en_text, facts, competitors).reasons)


def propose_glossary(old: str, new: str, ticker: str, text_id: int, path: Path = PROPOSALS) -> list:
    """Word replacements between the old and the corrected Hebrew text (up to 3 words each side) -> proposals in the file (one per replacement, once)."""
    a, b = re.findall(r"[֐-׿\"'-]+", old or ""), re.findall(r"[֐-׿\"'-]+", new or "")
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b).get_opcodes():
        if tag == "replace" and 0 < i2 - i1 <= 3 and 0 < j2 - j1 <= 3:
            out.append({"old_he": " ".join(a[i1:i2]), "new_he": " ".join(b[j1:j2]), "ticker": ticker, "text_id": text_id})
    existing = read_proposals(path)
    keys = {(p["old_he"], p["new_he"]) for p in existing}
    fresh = [{"n": len(existing) + k + 1, **p, "status": "proposed"} for k, p in enumerate(x for x in out if (x["old_he"], x["new_he"]) not in keys)]
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            for p in fresh:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    return fresh


def read_proposals(path: Path = PROPOSALS) -> list:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()] if path.exists() else []


def edit(store, text_id: int, new_he: str, facts: dict, competitors: list, proposals_path: Path = PROPOSALS) -> dict:
    """Store a person's correction. Raises EditRejected (nothing is stored) when the checks fail."""
    row = store.get_by_id(text_id)
    if row is None or row["kind"] != "background" or row["language"] != "he":
        raise ValueError(f"text {text_id} is not a Hebrew background")
    en = store.get(row["ticker"], row["fiscal_year"], "background", row["prompt_version"], row.get("run_id") or "", "en")
    reasons = check_edit(new_he, (en or {}).get("text") or "", facts, competitors)
    if reasons:
        raise EditRejected(reasons)
    out = store.update(text_id, text=new_he, edited_by="human", human_reviewed=True, approval_status="approved", state="stored",
                       checks={**(row.get("checks") or {}), "edit_checks": {"ok": True, "reasons": []}})
    out["glossary_proposals"] = propose_glossary(row["text"], new_he, row["ticker"], text_id, proposals_path)
    return out


def glossary_approve(n: int, english: str, proposals_path: Path = PROPOSALS, glossary_path: Path = GLOSSARY) -> dict:
    """Add proposal ``n`` to the T1 glossary under the given English term. The glossary is only extended here, by a person's command."""
    props = read_proposals(proposals_path)
    p = next((x for x in props if x["n"] == n), None)
    if p is None or p["status"] != "proposed":
        raise ValueError(f"no open proposal {n}")
    if not english.strip():
        raise ValueError("the English term is required")
    line = '  - {en: "%s", he: "%s"}\n' % (english.strip().replace('"', "'"), p["new_he"].replace('"', "'"))
    text = glossary_path.read_text(encoding="utf-8")
    glossary_path.write_text(text + ("" if text.endswith("\n") else "\n") + line, encoding="utf-8")
    proposals_path.write_text("\n".join(json.dumps({**x, "status": "approved" if x["n"] == n else x["status"]}, ensure_ascii=False) for x in props) + "\n", encoding="utf-8")
    from src.ai import content as C
    C._T1 = None                                   # the glossary is read again
    return {**p, "status": "approved", "en": english.strip()}

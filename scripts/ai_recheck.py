"""Code stage K5a: re-apply the CURRENT code checks (src/ai/checks.py) to the raw answers already stored - no model call.

Used after a change of the checker (e.g. quote normalization): the stored raw answer and the text sent are unchanged, only the check result and the derived state / answer / evidence
are recomputed. Rewrites assessments.jsonl and assessments_repeat.jsonl in place and prints how many rows changed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.ai import checks  # noqa: E402
from src.ai.prompt import build_prompt, scoring_skills  # noqa: E402
from src.ai.sections import find_filing, split_sections  # noqa: E402
from run_ai_k5a import ENGINE_OF, meta  # noqa: E402

STORE = ROOT / "scripts" / "ai_store"


def recheck(path: Path):
    sk = scoring_skills()
    cache = {}
    out, changed = [], 0
    for ln in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)
        if r["question_id"] not in sk or not r.get("raw_answer"):
            out.append(r)
            continue
        t = r["ticker"]
        if t not in cache:
            m = meta(t)
            f = find_filing(t, str(m["end"][-1])[:10])
            cache[t] = (m, f, split_sections(f.text))
        m, f, secs = cache[t]
        skill = sk[r["question_id"]]
        sections = {sid: secs[sid].text for sid in skill["sections"] if sid in secs and secs[sid].found}
        ctx = {"company_name": m["name"], "ticker": t, "fiscal_year": f"FY{r['fiscal_year']}", "profile": m["profile"], "accession": f.accession, "code_facts": None}
        _, text_sent, sent = build_prompt(skill, ctx, sections)
        res = checks.check_judgment(r["raw_answer"], skill, text_sent, sent)
        old = (r["state"], r["answer"])
        ev = r["evidence"]
        keep = [x for x in ev.get("flags", []) if x.startswith(("section_not_found", "note_not_included")) or ":" in x]
        r["state"], r["answer"] = res.state, res.answer
        r["evidence"] = {**ev, "quotes": res.quotes, "reasoning": res.reasoning, "extra": res.extra, "flags": keep + res.flags, "reasons": res.reasons, "check_ok": res.ok, "sections_sent": sent}
        if (r["state"], r["answer"]) != old:
            changed += 1
        out.append(r)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in out) + "\n", encoding="utf-8", newline="\n")
    return len(out), changed


if __name__ == "__main__":
    for name in ("assessments.jsonl", "assessments_repeat.jsonl"):
        p = STORE / name
        if p.exists():
            print(name, "rows / state changed:", recheck(p))

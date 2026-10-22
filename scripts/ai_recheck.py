"""Code stage K5a / K5a-3: re-apply the CURRENT code checks (src/ai/checks.py) and the CURRENT sections to the raw answers already stored - no model call.

Usage: python scripts/ai_recheck.py <store dir> [--write]
Without --write the stored files are untouched and the script only prints how many rows would change. With --write the check result and the derived state / answer / evidence
are rewritten in place (the raw answer and the model are never changed). The text sent is rebuilt from the current sections, so use it after a checker change, not after a change
of the sections (those need new answers).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.ai import checks  # noqa: E402
from src.ai.facts import facts_for  # noqa: E402
from src.ai.prompt import build_prompt, scoring_skills  # noqa: E402
from src.ai.sections import find_filing, split_sections  # noqa: E402
from run_ai_k5a import meta  # noqa: E402
from run_ai_k5a2 import facts_data  # noqa: E402


def recheck(path: Path, write: bool):
    sk = scoring_skills()
    cache = {}
    out, changed, still_rejected = [], [], 0
    for ln in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)
        if r["question_id"] not in sk or not r.get("raw_answer"):
            out.append(r)
            continue
        t = r["ticker"]
        if t not in cache:
            m = meta(t)
            f = find_filing(t, str(m["end"][-1])[:10])
            cache[t] = (m, f, split_sections(f.text), facts_data(t, m))
        m, f, secs, fd = cache[t]
        skill = sk[r["question_id"]]
        variant = "3.1" if str(r["prompt_version"]).endswith(".1") else "3"
        sections = {sid: secs[sid].text for sid in skill["sections"] if sid in secs and secs[sid].found}
        facts = facts_for(r["question_id"], fd)
        ctx = {"company_name": m["name"], "ticker": t, "fiscal_year": f"FY{r['fiscal_year']}", "profile": m["profile"], "accession": f.accession, "code_facts": facts}
        _, text_sent, sent = build_prompt(skill, ctx, sections, variant)
        res = checks.check_judgment(r["raw_answer"], skill, text_sent, sent, facts, require_facts_check=(variant == "3.1"))
        old = (r["state"], r["answer"], tuple(r["evidence"].get("reasons", [])))
        ev = r["evidence"]
        keep = [x for x in ev.get("flags", []) if x.startswith("section_not_found") or ":" in x]
        new = {**r, "state": res.state, "answer": res.answer,
               "evidence": {**ev, "quotes": res.quotes, "reasoning": res.reasoning, "extra": res.extra, "flags": keep + res.flags, "reasons": res.reasons, "check_ok": res.ok, "sections_sent": sent}}
        if (new["state"], new["answer"], tuple(new["evidence"]["reasons"])) != old:
            changed.append((t, r["question_id"], old[0], old[1], old[2], new["state"], new["answer"], tuple(res.reasons)))
        still_rejected += not res.ok
        out.append(new)
    if write:
        path.write_text("\n".join(json.dumps(x, ensure_ascii=False, sort_keys=True) for x in out) + "\n", encoding="utf-8", newline="\n")
    return len(out), changed, still_rejected


if __name__ == "__main__":
    d = Path(sys.argv[1])
    for name in ("assessments.jsonl", "assessments_repeat.jsonl"):
        p = d / name
        if p.exists():
            n, ch, rej = recheck(p, "--write" in sys.argv)
            print(name, "rows", n, "| changed", len(ch), "| rejected after:", rej)
            for c in ch:
                print("   ", c)

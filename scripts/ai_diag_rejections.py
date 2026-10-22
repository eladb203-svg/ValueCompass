"""Code stage K5a-3: why were answers rejected? For every stored row that failed the quote check, show each missing quote against the text that was sent
(longest matching prefix / where it diverges). Usage: python scripts/ai_diag_rejections.py <dir with assessments.jsonl>"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from src.ai import checks
from src.ai.prompt import build_prompt, scoring_skills
from src.ai.sections import find_filing, split_sections
from run_ai_k5a import meta
from run_ai_k5a2 import facts_data
from src.ai.facts import facts_for

sk = scoring_skills()
d = Path(sys.argv[1])
cache = {}
for ln in (d / "assessments.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(ln)
    if r["question_id"] not in sk or r["state"] == "answered" or not r.get("raw_answer"):
        continue
    t = r["ticker"]
    if t not in cache:
        m = meta(t); f = find_filing(t, str(m["end"][-1])[:10]); cache[t] = (m, split_sections(f.text), f)
    m, secs, f = cache[t]
    skill = sk[r["question_id"]]
    sections = {s: secs[s].text for s in skill["sections"] if s in secs and secs[s].found}
    fd = facts_data(t, m)
    ctx = {"company_name": m["name"], "ticker": t, "fiscal_year": f"FY{r['fiscal_year']}", "profile": m["profile"], "accession": f.accession, "code_facts": facts_for(r["question_id"], fd)}
    _, text_sent, sent = build_prompt(skill, ctx, sections)
    tn = checks.normalize(text_sent)
    print(f"=== {t} {r['question_id']} reasons={r['evidence'].get('reasons')}")
    try:
        parsed = checks.parse_json(r["raw_answer"])
    except Exception as e:
        parsed = None
    if parsed is None:
        print("   RAW (first 300):", repr(r["raw_answer"][:300]), "... tail:", repr(r["raw_answer"][-120:]), "len", len(r["raw_answer"]))
        continue
    for q in parsed.get("quotes") or []:
        qt = q["text"] if isinstance(q, dict) else q
        qn = checks.normalize(qt)
        if qn in tn:
            continue
        lo, hi = 0, len(qn)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if qn[:mid] in tn: lo = mid
            else: hi = mid - 1
        i = tn.find(qn[:lo]) if lo else -1
        print("   QUOTE:", repr(qt[:160]))
        print(f"   matches the text for {lo}/{len(qn)} chars; diverges at: {qn[lo:lo+40]!r} vs text: {tn[i+lo:i+lo+40]!r}" if lo else "   no prefix match")
        print("   in FACTS?", (ctx['code_facts'] and qn[:40] in checks.normalize(ctx['code_facts'])))

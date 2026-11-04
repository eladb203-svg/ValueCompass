"""Calibration item 6: for every answer of the re-ask experiment (scripts/state/cal_ai_experiment.jsonl) check - without any model call - that EACH quote is found word for word in the annual report
(same normalisation as the production check), in which section, and print the full quote, the whole reasoning and the scale of the question, so a person can judge whether the quote supports the level.
Usage: python scripts/cal_verify_quotes.py"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

import vc  # noqa: E402
from src.ai import assess  # noqa: E402
from src.ai.checks import normalize  # noqa: E402
from src.ai.prompt import scoring_skills  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.pipeline import scoring as S  # noqa: E402

runner = vc.make_runner(0)
S._paths()
sk = scoring_skills()
rows = {}
for line in open(ROOT / "scripts" / "state" / "cal_ai_experiment.jsonl", encoding="utf-8"):
    r = json.loads(line)
    rows[(r["ticker"], r["question_id"])] = r
meta_cache = {}
for (t, q), r in rows.items():
    ev = r.get("evidence") or {}
    if r.get("state") != "answered":
        continue
    if t not in meta_cache:
        co = dict(runner.companies.get_by_symbol(t, "US"))
        if not co.get("profile"):
            co["profile"] = runner.client.table("company_score_summary").select("profile").eq("company_id", co["id"]).execute().data[0]["profile"]
        res = runner.load_result(t)
        K5 = runner._meta_context(co, res)
        m = K5.meta(t)
        filing = find_filing(t, str(m["end"][-1])[:10])
        a = assess.Company(t, m["name"], m["profile"], int(m["fy"][-1][2:]), filing)
        meta_cache[t] = normalize(" ".join((getattr(s, "text", s) or "") for s in a.sections().values()))
    full = meta_cache[t]
    print("=" * 110, f"\n{t} {q}  answer={r['answer']}  (question: {str(sk[q].get('title') or sk[q].get('question') or '')[:150]})")
    print("REASONING:", ev.get("reasoning"))
    for i, qu in enumerate(ev.get("quotes") or []):
        txt = qu.get("text") or ""
        qn = normalize(txt)
        print(f"QUOTE {i + 1} (section {qu.get('section')}) found word for word in the report: {qn in full}  [{len(qn)} chars]\n   {txt}")

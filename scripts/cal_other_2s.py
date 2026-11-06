"""Owner decision 2026-11-05 (item 3): the stored answers of 2 to the AI questions B3.2-Q4, B3.2-Q5, B3.7-Q5, B3.8-Q6 for a sample of 15 non-REIT companies (3 STANDARD + 2 TECH_ASSET_LIGHT, 5 BANK, 5 INSURANCE), with reasoning
and quotes and the verbatim check, for grading. No model calls. Sample: companies with all four answers, every k-th in alphabetical order (no cherry-picking)."""
import collections, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
import vc
from src.ai import assess
from src.ai.checks import normalize
from src.ai.db_stores import select_all
from src.ai.sections import find_filing
runner = vc.make_runner(0); c = runner.client
QS = ["B3.2-Q4", "B3.2-Q5", "B3.7-Q5", "B3.8-Q6"]
summ = {x["company_id"]: x["profile"] for x in select_all(c, "company_score_summary", order="company_id")}
sym = {x["id"]: x["symbol"] for x in select_all(c, "companies", order="id")}
ans = collections.defaultdict(dict)
for a in select_all(c, "ai_assessments", order="company_id"):
    if a["question_id"] in QS and a.get("approval_status") == "approved" and a.get("answer") is not None:
        ans[a["company_id"]].setdefault(a["question_id"], a)
by = collections.defaultdict(list)
for cid, d in ans.items():
    if len(d) == 4 and cid in summ: by[summ[cid]].append(sym[cid])
def pick(profiles, n):
    pool = sorted(t for p in profiles for t in by[p]); k = max(1, len(pool) // n)
    return pool[::k][:n]
sample = pick(["STANDARD"], 3) + pick(["TECH_ASSET_LIGHT"], 2) + pick(["BANK"], 5) + pick(["INSURANCE"], 5)
print("pools:", {p: len(v) for p, v in by.items()}); print("sample:", sample)
prof = {sym[cid]: p for cid, p in summ.items()}
for t in sample:
    co = dict(runner.companies.get_by_symbol(t, "US")); res = runner.load_result(t); m = runner._meta_context(co, res).meta(t)
    a = assess.Company(t, m["name"], prof[t], int(m["fy"][-1][2:]), find_filing(t, str(m["end"][-1])[:10]))
    text = normalize(" ".join((getattr(s, "text", s) or "") for s in a.sections().values()))
    for q in QS:
        row = ans[co["id"]][q]; ev = row.get("evidence") or {}
        print(f"== {t} [{prof[t]}] {q} v{row.get('prompt_version')} answer={row.get('answer')}")
        if row.get("answer") == 2:
            print("   reasoning:", str(ev.get("reasoning"))[:300])
            for qu in ev.get("quotes") or []:
                print(f"   quote [{'FOUND' if normalize(qu.get('text') or '') in text else 'NOT FOUND'}]: {str(qu.get('text'))[:330]}")

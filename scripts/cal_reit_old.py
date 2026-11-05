"""Owner decision 2026-11-05 (item 2): dump the answers of 2 of the OLD wording (stored production answers) for the 15 REITs of the before/after comparison, with reasoning and quotes, verbatim check. No model calls."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
import vc
from src.ai import assess
from src.ai.checks import normalize
from src.ai.sections import find_filing
runner = vc.make_runner(0)
sc = json.loads((ROOT / "scripts/state/cal_reit_score.json").read_text(encoding="utf-8"))
ok = [t for t, r in sc.items() if r.get("before") and r.get("after") and not r["before"]["ai_pending"] and r["before"]["score"] is not None and r["after"]["score"] is not None]
print("15?", len(ok), ok)
QS = ["B3.2-Q4", "B3.2-Q5", "B3.7-Q5", "B3.8-Q6"]
for t in ok:
    co = dict(runner.companies.get_by_symbol(t, "US")); co["profile"] = "INCOME_REAL_ESTATE"
    res = runner.load_result(t); m = runner._meta_context(co, res).meta(t)
    a = assess.Company(t, m["name"], "INCOME_REAL_ESTATE", int(m["fy"][-1][2:]), find_filing(t, str(m["end"][-1])[:10]))
    text = normalize(" ".join((getattr(s, "text", s) or "") for s in a.sections().values()))
    fy = a.fiscal_year if a.fiscal_year > 2000 else 2000 + a.fiscal_year
    for q in QS:
        row = None
        for v in ("3.1", "2.1", "3", "2", "1", "1.1"):
            row = runner.ai_store.get(t, fy, q, v)
            if row: break
        if not row: print(f"== {t} {q} OLD none"); continue
        ev = row.get("evidence") or {}
        print(f"== {t} {q} OLD v{row.get('prompt_version')} answer={row.get('answer')} ({row.get('state')})")
        if row.get("answer") == 2:
            print("   reasoning:", str(ev.get("reasoning"))[:400])
            for qu in ev.get("quotes") or []:
                print(f"   quote [{'FOUND' if normalize(qu.get('text') or '') in text else 'NOT FOUND'}]: {str(qu.get('text'))[:380]}")

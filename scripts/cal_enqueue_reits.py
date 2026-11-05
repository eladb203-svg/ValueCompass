"""Owner decision 2026-11-05 (item 4): queue ai_assess (priority bulk = 4) for the 8 REITs among the 44 K5 companies without any AI answer. Nothing else is queued; no model call here."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
import vc
from src.repositories.work_queue_repository import PRIORITY
REITS = ["SPG", "FRT", "ARE", "PLD", "BXP", "EQR", "PSA", "EQIX"]
runner = vc.make_runner(0)
for t in REITS:
    co = dict(runner.companies.get_by_symbol(t, "US"))
    res = runner.load_result(t)
    fy = int(sorted(res.get("fiscal_years") or {k: 0 for k in (res.get("inputs") or {}).get("fy", [])})[-1][2:])
    skills = runner.missing_assessments(t, res, fy)
    if not skills:
        print(t, "nothing missing"); continue
    task, state = runner.enqueue(co["id"], "ai_assess", fy, None, PRIORITY["bulk"], {"skills": skills})
    print(t, "FY", fy, "skills", len(skills), "task", task["id"], state, "priority", task["priority"])

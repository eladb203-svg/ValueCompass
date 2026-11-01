"""K6d-2 fixes 2026-11-01: ask again the assessments stored as 'insufficient evidence' while sections were missing (stale_insufficient), then re-score. Usage: python scripts/k14_reask.py TICKER Q1 Q2 ..."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import vc  # noqa: E402

runner = vc.make_runner(30)
t, qs = sys.argv[1].upper(), sys.argv[2:]
co = runner.companies.get_by_symbol(t, "US")
out = runner.exec_assess({"company_id": co["id"], "priority": 2, "payload": {"skills": qs}})
print(t, out)
runner.enqueue(co["id"], "score", None, "first", 1)
vc.print_report(runner.run(20, only={t}))

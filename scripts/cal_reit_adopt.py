"""Owner decision 2026-11-05 (item 2): store the collected answers of the reworded REIT questions (scripts/state/cal_reit_reask.jsonl, versions "<v>-reit.1") in the test database (ai_assessments), approval status as the
row was checked (answered + check_ok -> approved; the rest as given), then rescore the REITs that have answers, with no model call. Prints before/after of the Buffett quality score per REIT."""
import json, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
import vc
from src.ai.store import AssessmentStore
from src.etl.db_io import FactSetDb
from src.pipeline import scoring as S
runner = vc.make_runner(0); c = runner.client
src = AssessmentStore(ROOT / "scripts" / "state" / "cal_reit_reask.jsonl").rows()
def score(t):
    o = S.score_company(t, "INCOME_REAL_ESTATE", FactSetDb(c), runner.ai_store, runner.item_store, Path(tempfile.mkdtemp()))
    if o.status != "scored": return None
    q = o.result["buffett_quality"]; return (round(q["score"], 1) if q.get("score") is not None else None, q.get("coverage"))
tick = sorted({r["ticker"] for r in src})
before = {t: score(t) for t in tick}
n = 0
for r in src:
    ev = r.get("evidence") or {}
    row = dict(r); row["approval_status"] = "approved" if (r.get("state") == "answered" and ev.get("check_ok") is not False) else (r.get("approval_status") or "approved")
    runner.ai_store.put(row); n += 1
print("stored", n, "rows for", len(tick), "REITs")
for t in tick:
    print(t, "before", before[t], "after", score(t), flush=True)

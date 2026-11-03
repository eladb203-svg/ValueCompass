"""K6d-2 fixes 2026-11-03: the companies of the first stages (K5) have a score and an empty processing_state. Give each the state that fits its data - `complete` when its latest score run has no sub-item that waits
for the AI, `scored_partial` otherwise - without any AI call. TEST database only (the script refuses another target). Usage: python scripts/k18_set_states.py [--apply]"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai.db_stores import select_all  # noqa: E402
from src.db import db_target, get_supabase_client  # noqa: E402
from src.repositories.company_repository import CompanyRepository  # noqa: E402

if db_target() != "test":
    sys.exit(f"refused: the database target is {db_target()!r}, this script changes only the test database")
c = get_supabase_client()
repo = CompanyRepository(c)
summ = {r["company_id"]: r for r in select_all(c, "company_score_summary", order="company_id")}
todo = []
for co in select_all(c, "companies", order="id"):
    if co["exchange"] != "US" or co.get("processing_state") or co["id"] not in summ or not summ[co["id"]].get("latest_run_id"):
        continue
    run = summ[co["id"]]["latest_run_id"]
    pending = sum(1 for d in select_all(c, "score_details", {"run_id": run}) if (d.get("evidence") or {}).get("state") == "ai_pending")
    todo.append((co["id"], co["symbol"], "scored_partial" if pending else "complete", pending))
print(f"{len(todo)} companies without a processing state and with a score")
for _cid, sym, state, pend in sorted(todo, key=lambda x: x[1]):
    print(f"  {sym:6}{state:15}ai-pending sub-items: {pend}")
if "--apply" in sys.argv:
    for cid, _sym, state, _p in todo:
        repo.set_processing_state(cid, state)
    print("applied:", len(todo))
else:
    print("(dry run: --apply writes)")

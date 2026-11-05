"""Owner decision 2026-11-05 (item 4): the companies with AI items pending, grouped by cause. Read only."""
import sys, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
import vc
from src.ai.db_stores import select_all
r = vc.make_runner(0); c = r.client
cos = {x["id"]: x for x in select_all(c, "companies", order="id")}
summ = select_all(c, "company_score_summary", order="company_id")
asm = collections.Counter(x["company_id"] for x in select_all(c, "ai_assessments", order="company_id"))
ext = collections.defaultdict(collections.Counter)
for x in select_all(c, "extraction_items", order="id"): ext[x["company_id"]][x["approval_status"]] += 1
q = collections.defaultdict(collections.Counter)
for x in select_all(c, "work_queue", order="id"): q[x["company_id"]][(x["job_type"], x["state"])] += 1
none = [s for s in summ if asm[s["company_id"]] == 0]
print("companies scored:", len(summ), "| without any AI assessment:", len(none))
g = collections.defaultdict(list)
for s in none:
    co = cos[s["company_id"]]
    ai_q = sum(v for (tt, st), v in q[s["company_id"]].items() if tt == "ai_assess")
    key = (s["profile"], str(co.get("created_at"))[:10], "has_ai_task" if ai_q else "no_ai_task", "pending_extraction" if ext[s["company_id"]]["pending"] else "no_pending_extraction")
    g[key].append(co["symbol"])
for k, v in sorted(g.items()): print(k, len(v), v)
print("distinct task types in queue:", sorted({tt for cq in q.values() for (tt, st) in cq}))

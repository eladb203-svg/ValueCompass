"""Owner decision 2026-11-05 (items 1-2): rescore every profiled company in the test database with the flag on; no model calls (budget 0). Writes scripts/state/cal5_rescore.json (before/after of the summary)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
import vc
from src.ai.db_stores import select_all
r = vc.make_runner(0)
c = r.client
before = {x["company_id"]: x for x in select_all(c, "company_score_summary", order="company_id")}
off = json.load(open(ROOT / "scripts/state/cal5_off.json", encoding="utf-8")); on = json.load(open(ROOT / "scripts/state/cal5_on.json", encoding="utf-8"))
movers = {t for t in off if t in on and "buffett_quality" in off[t] and "buffett_quality" in on[t] and (off[t]["buffett_quality"]["score"] or 0) != (on[t]["buffett_quality"]["score"] or 0)}   # only companies the break rule moves
cos = [x for x in select_all(c, "companies", order="id") if x.get("profile") and x["id"] in before and x["symbol"] in movers]
print("movers", len(movers), "to rescore", len(cos), flush=True)
out = {}
for co in cos:
    try:
        r.exec_score({"company_id": co["id"], "skill": "final", "priority": 4})
    except Exception as e:  # noqa: BLE001
        out[co["symbol"]] = {"error": str(e)[:200]}; print(co["symbol"], "ERR", str(e)[:120], flush=True); continue
    a = select_all(c, "company_score_summary", order="company_id")
    after = next(x for x in a if x["company_id"] == co["id"])
    out[co["symbol"]] = {"profile": co["profile"], "before": {k: v for k, v in before[co["id"]].items() if "score" in k or "cover" in k}, "after": {k: v for k, v in after.items() if "score" in k or "cover" in k}}
    print(co["symbol"], flush=True)
    Path(ROOT / "scripts/state/cal5_rescore.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
Path(ROOT / "scripts/state/cal5_rescore.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print("model attempts", r.gemini.attempts)

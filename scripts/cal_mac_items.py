"""Owner decision 2026-11-05 (item 3): why does MAC score ~76-78 (coverage 71%)? Item-by-item Buffett quality of MAC against the mean of the strong REITs. Scoring only, no writes."""
import json, sys, tempfile, statistics as st
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import vc
from src.etl.db_io import FactSetDb
from src.pipeline import scoring as S
runner = vc.make_runner(0); c = runner.client
tmp = Path(tempfile.mkdtemp(prefix="cal_mac_"))
WEAK = {"PK", "BDN", "DHC", "HPP", "MAC"}
from src.ai.db_stores import select_all
reits = sorted({x["symbol"] for x in select_all(c, "companies", order="id") if x["exchange"] == "US"} & {s["symbol"] for s in []} ) 
rows = select_all(c, "company_score_summary", order="company_id"); cos = {x["id"]: x["symbol"] for x in select_all(c, "companies", order="id")}
reits = sorted(cos[r["company_id"]] for r in rows if r["profile"] == "INCOME_REAL_ESTATE")
res = {}
for t in reits:
    o = S.score_company(t, "INCOME_REAL_ESTATE", FactSetDb(c), runner.ai_store, runner.item_store, tmp)
    if o.status != "scored": continue
    q = o.result["buffett_quality"]
    res[t] = {"score": q.get("score"), "coverage": q.get("coverage"), "items": {f"{cr['id']}.{it['id']}": (it.get("name") or it.get("title"), it.get("state"), it.get("points"), it.get("max") or it.get("max_points"), it.get("flags")) for cr in q.get("criteria", []) for it in cr.get("items", [])}}
Path(ROOT / "scripts/state/cal_mac_items.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
strong = [t for t in res if t not in WEAK]
print("REITs scored:", len(res), "strong:", len(strong))
print("MAC score", res["MAC"]["score"], "coverage", res["MAC"]["coverage"], "| strong mean score", round(st.mean(res[t]["score"] for t in strong), 1), "coverage", round(st.mean(res[t]["coverage"] for t in strong), 2))
print(f"{'item':7} {'name':42} {'max':>4} {'MAC':>12} {'strong mean pts (n scored)':>26}")
for k, (nm, state, pts, mx, fl) in res["MAC"]["items"].items():
    sp = [res[t]["items"][k][2] for t in strong if k in res[t]["items"] and res[t]["items"][k][1] in ("score", "scored", "answered")]
    allp = [res[t]["items"][k][2] for t in strong if k in res[t]["items"] and res[t]["items"][k][2] is not None]
    print(f"{k:7} {str(nm)[:42]:42} {mx!s:>4} {str(state)[:8]:>8} {pts if pts is None else round(pts,2)!s:>5} {round(st.mean(allp),2) if allp else None!s:>12} ({len(allp)})")

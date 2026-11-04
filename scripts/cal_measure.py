"""Calibration measurement: calculate the quality scores of every company of the test database WITHOUT writing anything to the database (the engines run on the stored facts and answers; the result files go
to a temporary folder), with the calibration parameters given in the environment (VC_CAL_<NAME>=1), and write them to a json file. Run twice (parameter off / on) and compare with cal_compare.py.
Usage: VC_CAL_GROWTH_WINDOW_10Y=1 python scripts/cal_measure.py OUT.json [TICKER ...]"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import vc  # noqa: E402
from src.ai.db_stores import select_all  # noqa: E402
from src.etl.db_io import FactSetDb  # noqa: E402
from src.pipeline import scoring as S  # noqa: E402

runner = vc.make_runner(0)
c = runner.client
summ = {x["company_id"]: x for x in select_all(c, "company_score_summary", order="company_id")}
cos = [x for x in select_all(c, "companies", order="id") if x["exchange"] == "US" and x["id"] in summ and summ[x["id"]].get("profile") not in (None, "UNSUPPORTED")]
tmp = Path(tempfile.mkdtemp(prefix="cal_results_"))
out = {}
only = set(sys.argv[2:])                         # optional: re-measure only these tickers and merge them into an existing OUT.json
if only and Path(sys.argv[1]).exists():
    out = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for co in sorted(cos, key=lambda x: x["symbol"]):
    if only and co["symbol"] not in only:
        continue
    t = co["symbol"]
    try:
        o = S.score_company(t, summ[co["id"]]["profile"], FactSetDb(c), runner.ai_store, runner.item_store, tmp)
    except Exception as e:   # noqa: BLE001
        out[t] = {"error": f"{type(e).__name__}: {e}"[:200]}
        continue
    if o.status != "scored":
        out[t] = {"status": o.status}
        continue
    r = o.result
    row = {"profile": summ[co["id"]]["profile"]}
    for k in ("buffett_quality", "graham_quality"):
        q = r.get(k) or {}
        row[k] = {"score": q.get("score"), "coverage": q.get("coverage")}
        row[k + "_items"] = {f"{cr['id']}.{it['id']}": [it.get("state"), it.get("points")] for cr in q.get("criteria", []) for it in cr.get("items", [])}
    out[t] = row
    print(t, row["buffett_quality"], row["graham_quality"], flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print("written", sys.argv[1], len(out))

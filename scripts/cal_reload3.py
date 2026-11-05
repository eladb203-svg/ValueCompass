"""Owner decision 2026-11-05 (item 3): reload MAC, BDN, HPP (stage companies, test database) with the widened interest search and report Buffett before/after. No model calls."""
import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
import vc
from src.etl.db_io import FactSetDb
from src.pipeline import scoring as S
runner = vc.make_runner(0); c = runner.client
PIPE = vc.make_pipeline()
def snap(t):
    o = S.score_company(t, "INCOME_REAL_ESTATE", FactSetDb(c), runner.ai_store, runner.item_store, Path(tempfile.mkdtemp()))
    if o.status != "scored": return (o.status, None, {})
    q = o.result["buffett_quality"]
    items = {f"{cr['id']}.{it['id']}": (it.get("state"), None if it.get("points") is None else round(it["points"], 2)) for cr in q["criteria"] for it in cr["items"]}
    return (round(q["score"], 1) if q.get("score") is not None else None, q.get("coverage"), {k: items[k] for k in ("3.6.1", "3.6.2", "3.8.4", "3.6.3") if k in items})
for t in sys.argv[1:] or ["MAC", "BDN", "HPP"]:
    b = snap(t); r = PIPE.load(t, "repair"); a = snap(t)
    print(t, "before", b, "\n    after ", a, "\n    job:", getattr(r, "status", r), flush=True)

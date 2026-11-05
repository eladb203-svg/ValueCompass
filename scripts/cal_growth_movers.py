"""Calibration analysis (owner request 2026-11-04, item 6): for each company that moves by more than 2 points under `growth_window_10y`, record the series behind every growth sub-item and both results
(5-year window of R14 / revenue endpoints, and 10-year first-3 against last-3), so the years that cause the change can be seen. Scoring only - nothing is written to the database.
Usage: python scripts/cal_growth_movers.py OUT.json TICKER [TICKER ...]"""
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
from src.scoring import bank, buffett, calibration, insurance, metrics  # noqa: E402

CALLS: list = []
_orig_w = metrics.smoothed_growth_w
_orig_g10 = metrics.growth10


def w_rec(window5, full):
    r = _orig_w(window5, full)
    CALLS.append({"kind": "smoothed", "window5": list(window5), "full": list(full), "r5": metrics.smoothed_growth(window5), "r10": metrics.growth10(full)})
    return r


def g10_rec(full, *a, **k):
    r = _orig_g10(full, *a, **k)
    v5 = list(full)[-5:]
    r5 = None
    if len(v5) == 5 and v5[0] and v5[-1] and v5[0] > 0 and v5[-1] > 0:
        r5 = (v5[-1] / v5[0]) ** (1 / 4) - 1
    CALLS.append({"kind": "revenue", "window5": v5, "full": list(full), "r5": {"kind": "growth" if r5 is not None else "nonpositive", "value": r5, "start_avg": v5[0] if v5 else None, "end_avg": v5[-1] if v5 else None}, "r10": r})
    return r


for mod in (buffett, bank, insurance):
    if hasattr(mod, "smoothed_growth_w"):
        mod.smoothed_growth_w = w_rec
buffett.growth10 = g10_rec

runner = vc.make_runner(0)
c = runner.client
summ = {x["company_id"]: x for x in select_all(c, "company_score_summary", order="company_id")}
cos = {x["symbol"]: x for x in select_all(c, "companies", order="id") if x["exchange"] == "US"}
tmp = Path(tempfile.mkdtemp(prefix="cal_movers_"))
out = {}
for t in sys.argv[2:]:
    co = cos[t]
    CALLS.clear()
    with calibration.override(growth_window_10y=True):
        o = S.score_company(t, summ[co["id"]]["profile"], FactSetDb(c), runner.ai_store, runner.item_store, tmp)
    out[t] = {"profile": summ[co["id"]]["profile"], "calls": [dict(x) for x in CALLS], "status": o.status}
    print(t, o.status, len(CALLS), flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
print("written", sys.argv[1])

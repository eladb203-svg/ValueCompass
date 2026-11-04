"""Calibration (REIT, a): Buffett 3.4.1 - incremental return over WACC. For every REIT of the test database: the basis of the incremental return (direct yield or NOI_PROXY), the yield, +2.5%, the WACC proxy with its
components (debt weight, cost of debt, 10% cost of equity) and the spread and points; the classification of a zero (data or anchors) and the sensitivity to the cost of equity (8 / 9 / 10%) and to the anchors.
No change in any score. Usage: python scripts/cal_reit_341.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai.db_stores import select_all  # noqa: E402
from src.db import get_supabase_client  # noqa: E402
from src.scoring.interpolate import interpolate  # noqa: E402

ANCHORS = {"now 0..4pp": [(0.0, 0), (0.01, 1), (0.02, 2), (0.03, 3), (0.04, 4)],
           "zero at -2pp": [(-0.02, 0), (-0.01, 1), (0.0, 2), (0.01, 3), (0.02, 4)],
           "zero at -2pp, 4 at +4pp": [(-0.02, 0), (0.04, 4)]}
KD_TAX = 0.0
c = get_supabase_client()
cos = {x["id"]: x["symbol"] for x in select_all(c, "companies", order="id")}
run = {}
for r in select_all(c, "score_runs", order="id"):
    run[r["company_id"]] = r["id"]
reits = [x["company_id"] for x in select_all(c, "company_score_summary", order="company_id") if x["profile"] == "INCOME_REAL_ESTATE"]
print(f"{'REIT':6}{'basis':10}{'yield':>7}{'+2.5%':>7}{'incr':>7}{'D/(D+E)':>9}{'kd':>7}{'WACC':>7}{'spread':>8}{'pts':>6}  zero is due to")
rows = []
for cid in sorted(reits, key=lambda i: cos[i]):
    d = c.table("score_details").select("inputs,criterion_score,evidence").eq("run_id", run[cid]).eq("model", "buffett").eq("criterion_key", "3.4").eq("sub_criterion_key", "1").execute().data[0]
    inp = d["inputs"] or {}
    ev = d["evidence"] or {}
    w, inc, basis = inp.get("wacc") or {}, inp.get("incremental_return"), inp.get("metric_basis")
    if inc is None or not w.get("value"):
        print(f"{cos[cid]:6}{str(basis):10} missing: {str(ev.get('note'))[:110]}")
        continue
    spread, pts = inc - w["value"], d["criterion_score"]
    wd, kd = w["weight_debt"], w["kd"]
    sens = {}
    for re_ in (0.08, 0.09, 0.10):
        wacc = wd * kd * (1 - KD_TAX) + (1 - wd) * re_
        for name, an in ANCHORS.items():
            sens[(re_, name)] = round(interpolate(inc - wacc, an), 2)
    cause = "-"
    if pts == 0:
        cause = "anchors / cost of equity (positive at 9% or with zero at -2pp)" if (sens[(0.09, "now 0..4pp")] > 0 or sens[(0.10, "zero at -2pp")] > 0) else "data is not the cause: the spread is negative by more than 2pp"
        if basis != "direct":
            cause += "; basis is a PROXY"
    rows.append((cos[cid], basis, inc, w, spread, pts, sens, cause))
    y = (inc - 0.025) if basis == "direct" else None
    print(f"{cos[cid]:6}{str(basis):10}{'' if y is None else format(y, '.1%'):>7}{'2.5%':>7}{inc:>7.1%}{wd:>9.1%}{kd:>7.1%}{w['value']:>7.1%}{spread:>8.1%}{pts:>6.2f}  {cause}")
print("\nSENSITIVITY - points of 4 under (cost of equity, anchors):")
cols = [(r, n) for r in (0.08, 0.09, 0.10) for n in ANCHORS]
print("REIT   " + " ".join(f"{int(r * 100)}%/{n[:9]:9}" for r, n in cols))
for t, basis, inc, w, spread, pts, sens, cause in rows:
    print(f"{t:6} " + " ".join(f"{sens[k]:>13.2f}" for k in cols))
import statistics as st
print("\naverage points:", {f"{int(r * 100)}% {n}": round(st.mean(x[6][(r, n)] for x in rows), 2) for r, n in cols})
print("REITs with a positive score:", {f"{int(r * 100)}% {n}": sum(1 for x in rows if x[6][(r, n)] > 0) for r, n in cols}, "of", len(rows))

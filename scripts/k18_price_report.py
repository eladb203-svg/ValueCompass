"""K6d-2 fixes 2026-11-03 - input for the calibration: (1) one Yahoo request for the last price of EVERY company of the database that has a score run (the daily job skips the companies whose processing_state is empty,
the K5-era companies), written to market_snapshot and to the price part of the latest run in place (no new run, no AI); (2) the distribution of the price score and of price / fair value per profile and model.
Usage: python scripts/k18_price_report.py [--no-refresh]"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai.db_stores import select_all  # noqa: E402
from src.db import get_supabase_client  # noqa: E402

c = get_supabase_client()
cos = {x["id"]: x for x in select_all(c, "companies", order="id") if x["exchange"] == "US"}
runs = {}
for r in select_all(c, "score_runs", order="id"):
    runs[r["company_id"]] = r
targets = [cos[i] for i in runs if i in cos]
print(f"companies with a score run: {len(targets)}")
if "--no-refresh" not in sys.argv:
    from src.sched.jobs import JobRunner
    from src.sched.schedule import Config
    jr = JobRunner(c, Config.load(None))
    prices = jr.fetch_batch([t["symbol"] for t in targets], intraday=True)
    out = jr.apply_prices(targets, prices)
    print("refresh:", out.status, out.detail, "warnings:", out.warnings[:8])

summ = {x["company_id"]: x for x in select_all(c, "company_score_summary", order="company_id")}
snap = {x["company_id"]: x for x in select_all(c, "market_snapshot", order="company_id")}
vals = defaultdict(dict)
for v in select_all(c, "valuations", order="id"):
    vals[v["run_id"]][v["model"]] = v
BINS = ((0, "0"), (5, "0-5"), (10.0001, "5-10"))


def sbin(x):
    if x is None:
        return "no score"
    if x == 0:
        return "0"
    return "0-5" if x <= 5 else "5-10"


def rbin(r):
    if r is None:
        return "n/a"
    for hi, lab in ((0.5, "<0.5"), (0.8, "0.5-0.8"), (1.0, "0.8-1.0"), (1.2, "1.0-1.2"), (1e9, ">1.2")):
        if r < hi:
            return lab
    return ">1.2"


rows, tab, ratio = [], defaultdict(Counter), defaultdict(Counter)
for t in targets:
    run = runs[t["id"]]
    profile = (summ.get(t["id"]) or {}).get("profile") or run.get("profile") or t.get("profile") or "?"
    price = (snap.get(t["id"]) or {}).get("current_price")
    for model in ("buffett", "graham"):
        v = vals[run["id"]].get(model) or {}
        fv, ps, state = v.get("fair_value"), v.get("price_score"), v.get("price_state")
        r = (price / fv) if (price and fv and fv > 0) else None
        tab[(profile, model)][sbin(ps) if state == "scored" or ps is not None else (state or "no valuation")] += 1
        ratio[(profile, model)][rbin(r)] += 1
        rows.append([t["symbol"], profile, model, price, (snap.get(t["id"]) or {}).get("market_date"), fv, None if r is None else round(r, 3), ps, state, v.get("buy_price_state")])
out = ROOT / "scripts" / "state" / "price_report_2026-11-03.csv"
with out.open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["ticker", "profile", "model", "price", "price_date", "fair_value", "price_over_fair_value", "price_score", "price_state", "buy_price_state"])
    w.writerows(rows)
print("\nPRICE SCORE (0-10) by profile and model: how many get 0 / (0,5] / (5,10] / no score or the reason")
for k in sorted(tab):
    print(f"  {k[0]:20}{k[1]:8}{dict(tab[k])}")
print("\nPRICE / FAIR VALUE by profile and model")
for k in sorted(ratio):
    print(f"  {k[0]:20}{k[1]:8}{dict(ratio[k])}")
tot = Counter()
for k in tab:
    for lab, n in tab[k].items():
        tot[(k[1], lab)] += n
print("\nTOTAL by model:", {f"{m}:{l}": n for (m, l), n in sorted(tot.items())})
print("csv:", out)

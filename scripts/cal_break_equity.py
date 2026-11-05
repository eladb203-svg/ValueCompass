"""Owner decision 2026-11-05 (item 1b): acquisitions (cash for businesses + shares issued for acquisitions) over OPENING equity (StockholdersEquity at the previous fiscal year end). Measure only."""
import json, sys, re
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
import cal_growth_table as G
CACHE = ROOT / "scripts" / "cache" / "sec"
ACQ = ["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross", "PaymentsToAcquireBusinessesAndInterestInAffiliates", "PaymentsToAcquireBusinessesNetOfCashAcquiredIncludingInterestInAffiliates"]
STK = ["StockIssuedDuringPeriodValueAcquisitions", "StockIssuedDuringPeriodValueBusinessAcquisitionNet"]
EQ = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
def series(facts, tags, instant):
    out = {}
    for tag in tags:
        node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
        if not node: continue
        for unit, rows in node["units"].items():
            if unit != "USD": continue
            best = {}
            for r in rows:
                if not str(r.get("form", "")).startswith("10-K"): continue
                if not instant:
                    if not r.get("start"): continue
                    if not 340 <= (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days <= 380: continue
                if r["end"] not in best or r["filed"] >= best[r["end"]]["filed"]: best[r["end"]] = r
            for e, r in best.items(): out.setdefault(e, r["val"])
        if out: break
    return out
tick = json.loads((CACHE / "company_tickers.json").read_text(encoding="utf-8"))
cik = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in tick.values()}
break_rule = json.loads((ROOT / "scripts/state/cal_break_rule.json").read_text(encoding="utf-8"))
res = {}
for t in break_rule:
    p = CACHE / f"facts_{cik.get(t, '')}.json"
    if not p.exists(): continue
    f = json.loads(p.read_text(encoding="utf-8"))
    acq, stk, eq = series(f, ACQ, False), series(f, STK, False), series(f, EQ, True)
    ends = sorted(eq)
    best = None
    for e in sorted(set(acq) | set(stk)):
        if int(e[:4]) < 2016: continue
        prev = [x for x in ends if x < e and (date.fromisoformat(e) - date.fromisoformat(x)).days < 400]
        if not prev: continue
        o = eq[prev[-1]]
        if not o or o <= 0: continue
        v = ((acq.get(e) or 0) + (stk.get(e) or 0)) / o
        if best is None or v > best[0]: best = (v, e[:4])
    res[t] = best
rows = [(G.C[t][0] if t in G.C else "-", t, res.get(t)) for t in res]
for cls in ("b", "a"):
    print(f"-- class ({cls}) sorted by max acquisitions / opening equity")
    for k, t, b in sorted([r for r in rows if r[0] == cls], key=lambda r: -(r[2][0] if r[2] else -1)):
        print(f"  {t:5} {'n/a' if b is None else f'{b[0]*100:6.1f}% ({b[1]})'}")
json.dump({t: v for t, v in res.items()}, open(ROOT / "scripts/state/cal_break_equity.json", "w"), indent=1)
others = sorted([(v[0], t, v[1]) for t, v in res.items() if v and t not in G.C], reverse=True)[:12]
print("-- others (not in the 44), top:", [(t, round(v * 100, 1), y) for v, t, y in others])
b_vals = sorted([r[2][0] for r in rows if r[0] == "b" and r[2]]); a_vals = sorted([r[2][0] for r in rows if r[0] == "a" and r[2]], reverse=True)
print("min b:", [round(x * 100, 1) for x in b_vals][:4], " max a:", [round(x * 100, 1) for x in a_vals][:6])
for th in (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5):
    cb = sum(1 for r in rows if r[0] == "b" and r[2] and r[2][0] > th); ca = sum(1 for r in rows if r[0] == "a" and r[2] and r[2][0] > th)
    print(f"  threshold {th*100:.0f}%: b caught {cb}/10, a caught {ca}/34")

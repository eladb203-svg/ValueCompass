"""Item 6: per mover, per growth call: 5y vs 10y growth, the start/end averages, and the largest year-on-year jump (candidate cause)."""
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
d = json.load(open("scripts/state/cal_growth_movers.json", encoding="utf-8"))
def avg(x): x=[v for v in x if v is not None]; return sum(x)/len(x) if x else None
for t, o in d.items():
    print("==", t, o["profile"], o["status"])
    for i, c in enumerate(o["calls"]):
        f = [v for v in c["full"]]
        r5 = c["r5"].get("value") if isinstance(c["r5"], dict) else c["r5"]
        r10 = c["r10"].get("value") if isinstance(c["r10"], dict) else c["r10"]
        jumps = [(round(f[k]/f[k-1],2) if f[k-1] not in (None,0) and f[k] is not None else None) for k in range(1,len(f))]
        print(f"  {c['kind']:8} n={len(f)} r5={r5 if r5 is None else round(r5,3)} r10={r10 if r10 is None else round(r10,3)} series={[None if v is None else round(v/1e6,1) if abs(v)>1e5 else round(v,2) for v in f]}")

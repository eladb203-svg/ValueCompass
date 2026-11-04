"""Calibration: compare two cal_measure.py outputs (parameter off / on). Per profile: companies, mean score before/after, count moving more than 2 points, the REIT-versus-others gap; list of movers.
Usage: python scripts/cal_compare.py OFF.json ON.json [--items 3.1,3.2.4]"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
off = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
on = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
common = sorted(t for t in off if t in on and "profile" in off[t] and "profile" in on[t])
print(f"companies compared: {len(common)} (off {len(off)}, on {len(on)})")
for k in ("buffett_quality", "graham_quality"):
    print("=" * 90, "\n", k)
    by = defaultdict(list)
    for t in common:
        a, b = off[t][k]["score"], on[t][k]["score"]
        if a is None or b is None:
            continue
        by[off[t]["profile"]].append((t, a, b))
    print(f"{'profile':22}{'n':>4}{'mean off':>10}{'mean on':>10}{'moved>2':>9}{'up':>4}{'down':>6}")
    for p, L in sorted(by.items()):
        mv = [x for x in L if abs(x[2] - x[1]) > 2]
        print(f"{p:22}{len(L):>4}{st.mean(x[1] for x in L):>10.1f}{st.mean(x[2] for x in L):>10.1f}{len(mv):>9}{sum(1 for x in mv if x[2] > x[1]):>4}{sum(1 for x in mv if x[2] < x[1]):>6}")
    others = [x for p, L in by.items() if p != "INCOME_REAL_ESTATE" for x in L]
    if "INCOME_REAL_ESTATE" in by and others:
        g0 = st.mean(x[1] for x in others) - st.mean(x[1] for x in by["INCOME_REAL_ESTATE"])
        g1 = st.mean(x[2] for x in others) - st.mean(x[2] for x in by["INCOME_REAL_ESTATE"])
        print(f"gap (others - REIT) mean: {g0:.1f} -> {g1:.1f};  median: {st.median(x[1] for x in others) - st.median(x[1] for x in by['INCOME_REAL_ESTATE']):.1f} -> {st.median(x[2] for x in others) - st.median(x[2] for x in by['INCOME_REAL_ESTATE']):.1f}")
    movers = sorted((x for L in by.values() for x in L if abs(x[2] - x[1]) > 2), key=lambda x: -abs(x[2] - x[1]))
    print("movers >2:", [(t, off[t]["profile"], round(a, 1), round(b, 1)) for t, a, b in movers])
    cov = [(t, off[t][k]["coverage"], on[t][k]["coverage"]) for t in common if off[t][k]["coverage"] != on[t][k]["coverage"]]
    print("coverage changed:", cov[:30])
    ch = defaultdict(int)
    for t in common:
        for i, v in off[t][k + "_items"].items():
            if on[t][k + "_items"].get(i) != v:
                ch[i] += 1
    print("items changed (item -> companies):", dict(sorted(ch.items())))

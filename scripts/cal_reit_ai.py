"""Calibration 1(c): the AI-answered items of the Buffett quality score (3.1, 3.2 #4-#5, 3.7 #5, 3.8 #6) - distribution of their points per profile, from a cal_measure.py output.
Usage: python scripts/cal_reit_ai.py OFF.json"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
sel = lambda k: k.startswith("3.1.") or k in ("3.2.4", "3.2.5", "3.7.5", "3.8.6")  # noqa: E731
by = defaultdict(list)
per_item = defaultdict(lambda: defaultdict(list))
for t, r in d.items():
    if "profile" not in r:
        continue
    it = {k: v for k, v in r["buffett_quality_items"].items() if sel(k)}
    pts = [v[1] for v in it.values() if v[1] is not None]
    by[r["profile"]].append((t, sum(pts), len(pts)))
    for k, v in it.items():
        per_item[r["profile"]][k].append(v[1])
print("items taken:", sorted({k for r in d.values() if "buffett_quality_items" in r for k in r["buffett_quality_items"] if sel(k)}))
print(f"{'profile':22}{'n':>4}{'mean pts':>10}{'median':>8}{'full':>6}{'items':>7}")
for p, L in sorted(by.items()):
    mx = max(x[2] for x in L)
    print(f"{p:22}{len(L):>4}{st.mean(x[1] for x in L):>10.1f}{st.median(x[1] for x in L):>8.1f}{sum(1 for x in L if x[1] >= 17):>6}{mx:>7}")
print("\nREITs:", sorted(by.get("INCOME_REAL_ESTATE", []), key=lambda x: -x[1]))
print("\nper item mean points, REIT vs all other profiles:")
for k in sorted({k for p in per_item for k in per_item[p]}):
    rv = [x for x in per_item["INCOME_REAL_ESTATE"][k] if x is not None]
    ov = [x for p in per_item if p != "INCOME_REAL_ESTATE" for x in per_item[p][k] if x is not None]
    if rv and ov:
        print(f"  {k:8} REIT {st.mean(rv):.2f} (n={len(rv)})   others {st.mean(ov):.2f} (n={len(ov)})")

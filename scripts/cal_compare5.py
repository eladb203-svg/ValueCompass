"""Item 1 (2026-11-05): growth_window_10y with the acquisition break, before (off) / after (on) for every company that moved. Buffett quality and Graham quality."""
import json, sys, statistics as st, collections
sys.stdout.reconfigure(encoding="utf-8")
off = json.load(open("scripts/state/cal5_off.json", encoding="utf-8")); on = json.load(open("scripts/state/cal5_on.json", encoding="utf-8"))
old = json.load(open("scripts/state/cal_growth10.json", encoding="utf-8"))          # the first (no exception) measurement, for the comparison
rows = []
for t in sorted(off):
    a, b = off[t], on.get(t)
    if "buffett_quality" not in a or not b or "buffett_quality" not in b: continue
    sa, sb = a["buffett_quality"]["score"], b["buffett_quality"]["score"]
    ga, gb = a["graham_quality"]["score"], b["graham_quality"]["score"]
    if sa is None or sb is None: continue
    moved = {k: (round(a["buffett_quality_items"][k][1] or 0, 2), round(b["buffett_quality_items"][k][1] or 0, 2)) for k in a["buffett_quality_items"] if (a["buffett_quality_items"][k][1] or 0) != (b["buffett_quality_items"].get(k, [0, 0])[1] or 0)}
    o = old.get(t, {}).get("buffett_quality", {}).get("score")
    rows.append((t, a["profile"], sa, sb, a["buffett_quality"]["coverage"], b["buffett_quality"]["coverage"], ga, gb, moved, o))
mv = [r for r in rows if abs(r[3] - r[2]) > 0.05]
print("companies compared", len(rows), "| moved (any):", len(mv), "| moved > 2:", sum(1 for r in mv if abs(r[3]-r[2]) > 2))
print("ticker profile buffett off->on (delta) cov off->on | graham off->on | items | first run without exception")
for r in sorted(mv, key=lambda r: -abs(r[3]-r[2])):
    print(f"{r[0]:5} {r[1][:8]:8} {r[2]:6.1f}->{r[3]:6.1f} ({r[3]-r[2]:+.1f}) cov {r[4]:.2f}->{r[5]:.2f} | graham {r[6] if r[6] is None else round(r[6],1)}->{r[7] if r[7] is None else round(r[7],1)} | {r[8]} | {None if r[9] is None else round(r[9],1)}")
g = collections.defaultdict(list)
for r in rows: g[r[1]].append(r[3]-r[2])
print({p: (len(v), round(st.mean(v), 2)) for p, v in g.items()})
rei = [r for r in rows if r[1] == "INCOME_REAL_ESTATE"]; oth = [r for r in rows if r[1] != "INCOME_REAL_ESTATE"]
print("REIT mean off/on", round(st.mean(r[2] for r in rei),1), round(st.mean(r[3] for r in rei),1), "others", round(st.mean(r[2] for r in oth),1), round(st.mean(r[3] for r in oth),1))

"""Calibration 1(d): the weak REIT reference set. (1) external evidence from the stored facts (dividend per share, diluted EPS by year) for the weak and for some strong REITs;
(2) quality score and item points of the weak REITs against the mean of the strong REITs of the baseline measurement, item by item.
Usage: python scripts/cal_weak_reit.py scripts/state/cal_off.json scripts/state/cal_weak.json"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.db import get_supabase_client  # noqa: E402
from src.repositories.financial_repository import FinancialRepository  # noqa: E402

off = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
weak = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
WEAK = ["MAC", "BDN", "PK", "DHC", "HPP"]
c = get_supabase_client()
fin = FinancialRepository(c)
cid = {r["symbol"]: r["id"] for r in c.table("companies").select("id,symbol").eq("exchange", "US").in_("symbol", WEAK + ["PLD", "O", "AVB"]).execute().data}
print("(1) EXTERNAL EVIDENCE from the stored facts (per year)")
for t in WEAK + ["O", "PLD", "AVB"]:
    h = fin.get_history(cid[t])
    by = defaultdict(dict)
    for f in h:
        by[f["fiscal_year"]][f.get("item_key") or fin.item_key(f["item_id"])] = f["value"]
    for key in ("dps", "eps_diluted", "ffo", "ffo_per_share"):
        row = [(y, round(by[y][key], 2)) for y in sorted(by) if by[y].get(key) is not None]
        if row:
            print(f"  {t:5} {key:13} {row}")

print("\n(2) SCORES: weak REITs against the strong REITs of the baseline (Buffett quality)")
strong = {t: v for t, v in off.items() if v.get("profile") == "INCOME_REAL_ESTATE" and t not in WEAK and (v.get("buffett_quality") or {}).get("score") is not None}
print(f"strong REITs: {len(strong)}, mean score {st.mean(v['buffett_quality']['score'] for v in strong.values()):.1f}, median {st.median(v['buffett_quality']['score'] for v in strong.values()):.1f}")
for t in WEAK:
    q, g = weak[t]["buffett_quality"], weak[t]["graham_quality"]
    print(f"  {t:5} Buffett {q['score']} (coverage {q['coverage']})   Graham {g['score']} (coverage {g['coverage']})")
rows = []
for i in sorted({i for v in strong.values() for i in v["buffett_quality_items"]}):
    sv = [v["buffett_quality_items"][i][1] for v in strong.values() if i in v["buffett_quality_items"] and v["buffett_quality_items"][i][1] is not None]
    wv = [weak[t]["buffett_quality_items"].get(i, [None, None]) for t in WEAK]
    wp = [x[1] for x in wv if x[1] is not None]
    if sv and wp:
        rows.append((i, st.mean(sv), st.mean(wp), len(wp), [f"{str(x[0])[:4]}:{x[1]}" for x in wv]))
print("\nitems where the weak mean is at least 0.5 point below the strong mean (the method discriminates):")
for i, s, w, n, det in sorted(rows, key=lambda r: r[2] - r[1]):
    if w - s <= -0.5:
        print(f"  {i:7} strong {s:.2f}  weak {w:.2f} (n={n})  gap {w - s:+.2f}   {det}")
print("\nitems where the weak REITs are NOT lower (>= strong - 0.5):", [r[0] for r in rows if r[2] - r[1] > -0.5])
miss = defaultdict(list)
for t in WEAK:
    for i, (state, pts) in weak[t]["buffett_quality_items"].items():
        if pts is None:
            miss[i].append(f"{t}:{state}")
print("items without points in the weak REITs:", dict(sorted(miss.items())))

"""Calibration (price scale), analysis only - no change in any score: (1) the sensitivity of the Buffett DCF fair value to the discount rate 9 / 10 / 11% (recomputed from the stored DCF inputs of the latest run);
(2) an alternative price scale; (3) the correlation of the price score with the quality score. Prices: the refreshed market_snapshot. Usage: python scripts/cal_price_scale.py"""
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.ai.db_stores import select_all  # noqa: E402
from src.db import get_supabase_client  # noqa: E402
from src.scoring import buffett as B  # noqa: E402
from src.scoring import graham as G  # noqa: E402
from src.scoring.interpolate import interpolate  # noqa: E402

c = get_supabase_client()
cos = {x["id"]: x["symbol"] for x in select_all(c, "companies", order="id") if x["exchange"] == "US"}
run = {}
for r in select_all(c, "score_runs", order="id"):
    run[r["company_id"]] = r["id"]
summ = {x["company_id"]: x for x in select_all(c, "company_score_summary", order="company_id")}
snap = {x["company_id"]: x for x in select_all(c, "market_snapshot", order="company_id")}
vals = defaultdict(dict)
for v in select_all(c, "valuations", order="id"):
    vals[v["run_id"]][v["model"]] = v

ALT = [(-0.20, 0.0), (0.0, 2.0), (0.40, 10.0)]          # the alternative: 0 at a 20% premium, 2 at par, 10 at a 40% discount
CUR_B, CUR_G = B.PRICE_ANCHORS, G.CLASSIC_PRICE


def median(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 3) if xs else None


def spearman(a, b):
    def rk(x):
        o = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        i = 0
        while i < len(o):
            j = i
            while j + 1 < len(o) and x[o[j + 1]] == x[o[i]]:
                j += 1
            for k in range(i, j + 1):
                r[o[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    ra, rb = rk(a), rk(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return None if den == 0 else round(num / den, 3)


rows = []
for cid, sym in sorted(cos.items(), key=lambda kv: kv[1]):
    if cid not in run or cid not in snap or cid not in summ:
        continue
    s, price = summ[cid], snap[cid]["current_price"]
    prof = s.get("profile") or "?"
    for model in ("buffett", "graham"):
        v = vals[run[cid]].get(model) or {}
        fv, state = v.get("fair_value"), v.get("price_state")
        q = s.get(f"{model}_quality_score")
        rec = {"sym": sym, "profile": prof, "model": model, "price": price, "fv": fv, "state": state, "q": q, "details": v.get("details") or {}}
        if fv and fv > 0 and price:
            disc = (fv - price) / fv
            an = CUR_B if model == "buffett" else CUR_G
            rec.update({"disc": disc, "cur": interpolate(disc, an), "alt": interpolate(disc, ALT), "ratio": price / fv})
        rows.append(rec)

print("=" * 100, "\n(1) BUFFETT DCF: discount rate 9% / 10% (today) / 11% - companies whose fair value is a DCF with stored inputs")
by = defaultdict(lambda: defaultdict(list))
n_dcf = Counter()
for r in rows:
    if r["model"] != "buffett" or "disc" not in r:
        continue
    d = r["details"].get("dcf") or {}
    ys = d.get("years")
    if not ys or r["details"].get("base") is None:
        continue
    g1, base = ys[0]["growth"], r["details"]["base"]
    excess = d["equity_value"] - d["pv_cash_flows"] - d["pv_terminal_value"]
    shares = d["equity_value"] / d["fair_value_per_share"]
    n_dcf[r["profile"]] += 1
    for rate in (0.09, 0.10, 0.11):
        fv = B.dcf_fair_value(base, g1, excess, shares, r=rate)["fair_value_per_share"]
        disc = (fv - r["price"]) / fv if fv > 0 else None
        by[r["profile"]][rate].append((fv, r["price"], None if disc is None else interpolate(disc, CUR_B)))
print(f"{'profile':20}{'n':>4}   " + "   ".join(f"{int(rt * 100)}%: >0 / median price/FV" for rt in (0.09, 0.10, 0.11)))
for prof in sorted(by):
    cells = []
    for rate in (0.09, 0.10, 0.11):
        L = by[prof][rate]
        cells.append(f"{sum(1 for _f, _p, sc in L if sc and sc > 0):>3}/{len(L):<3}  {median([p / f for f, p, _ in L if f > 0])!s:>6}")
    print(f"{prof:20}{n_dcf[prof]:>4}   " + "   ".join(cells))
allr = {rate: [x for p in by for x in by[p][rate]] for rate in (0.09, 0.10, 0.11)}
print("all DCF companies: " + "; ".join(f"{int(rt * 100)}%: {sum(1 for _f, _p, sc in L if sc and sc > 0)} of {len(L)} above 0, median price/FV {median([p / f for f, p, _ in L if f > 0])}" for rt, L in allr.items()))

print("\n" + "=" * 100, "\n(2) THE SCALE: today (Buffett -25%->0, -20%->0.5, 0->2.5, +10%->4.5, +40%->10; Graham: CLASSIC_PRICE) against the alternative (0 at a 20% premium, 2 at par, 10 at a 40% discount)")
for model in ("buffett", "graham"):
    L = [r for r in rows if r["model"] == model and "disc" in r]
    moved = [r for r in L if abs(r["alt"] - r["cur"]) > 0.5]
    print(f"{model}: valued {len(L)}; moved by more than 0.5 point {len(moved)}; up {sum(1 for r in moved if r['alt'] > r['cur'])}, down {sum(1 for r in moved if r['alt'] < r['cur'])}; "
          f"zero today {sum(1 for r in L if r['cur'] == 0)} -> zero in the alternative {sum(1 for r in L if r['alt'] == 0)}; mean {st.mean(r['cur'] for r in L):.2f} -> {st.mean(r['alt'] for r in L):.2f}")
print("anchors today for Buffett:", B.describe(CUR_B) if hasattr(B, "describe") else CUR_B, "| Graham:", G.CLASSIC_PRICE)
print("The buy price does not change: it is fixed by the margin of safety of the quality score (M7), not by the scale.")

print("\n" + "=" * 100, "\n(3) PRICE SCORE AGAINST QUALITY SCORE (Spearman) - does the scale prefer weak companies that are cheap?")
for model in ("buffett", "graham"):
    L = [r for r in rows if r["model"] == model and "disc" in r and r["q"] is not None]
    rho = spearman([r["q"] for r in L], [r["cur"] for r in L])
    low = [r for r in L if r["q"] < 55]
    hi = [r for r in L if r["q"] >= 85]
    mid = [r for r in L if 55 <= r["q"] < 85]
    print(f"{model}: n={len(L)}  Spearman(quality, price score) = {rho}   mean price score: quality<55 ({len(low)}): {median([r['cur'] for r in low])} median; 55-85 ({len(mid)}): {median([r['cur'] for r in mid])}; >=85 ({len(hi)}): {median([r['cur'] for r in hi])}")
    cheap_weak = [r for r in L if r["q"] < 55 and r["cur"] >= 5]
    print(f"   weak (quality<55) and cheap (price score>=5): {len(cheap_weak)} {[(r['sym'], round(r['q']), round(r['cur'], 1)) for r in cheap_weak]}")
    for prof in sorted({r['profile'] for r in L}):
        P = [r for r in L if r["profile"] == prof]
        if len(P) >= 6:
            print(f"   {prof:20} n={len(P):<3} Spearman = {spearman([r['q'] for r in P], [r['cur'] for r in P])}")

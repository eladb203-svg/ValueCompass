"""Owner decision 2026-11-05 (item 1): measure the material-change exception of growth_window_10y from XBRL evidence (cached SEC companyfacts, no network, no model):
a year is a BREAK when (business-acquisition payments + shares issued for acquisitions) > 25% of total assets, or discontinued-operations revenue > 25% of revenue.
Usage: python scripts/cal_break_rule.py  ->  scripts/state/cal_break_rule.json"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
CACHE = ROOT / "scripts" / "cache" / "sec"
ACQ = ["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross", "PaymentsToAcquireBusinessesAndInterestInAffiliates", "PaymentsToAcquireBusinessesNetOfCashAcquiredIncludingInterestInAffiliates"]
STK = ["StockIssuedDuringPeriodValueAcquisitions", "StockIssuedDuringPeriodValueBusinessAcquisitionNet"]
CONS = ["BusinessCombinationConsiderationTransferred1"]
DISC = ["DisposalGroupIncludingDiscontinuedOperationRevenue", "DiscontinuedOperationRevenue"]
REV = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "RevenuesNetOfInterestExpense", "RealEstateRevenueNet", "SalesRevenueGoodsNet"]
def annual(facts, tags, instant=False):
    """-> {fiscal year(end year): value} from 10-K facts; the last filed value per end date wins."""
    out = {}
    for ns in ("us-gaap",):
        for tag in tags:
            node = facts.get("facts", {}).get(ns, {}).get(tag)
            if not node: continue
            for unit, rows in node["units"].items():
                if unit != "USD": continue
                best = {}
                for r in rows:
                    if not str(r.get("form", "")).startswith("10-K"): continue
                    if not instant:
                        from datetime import date
                        s, e = r.get("start"), r["end"]
                        if not s: continue
                        d = (date.fromisoformat(e) - date.fromisoformat(s)).days
                        if not 340 <= d <= 380: continue
                    if r["end"] not in best or r["filed"] >= best[r["end"]]["filed"]: best[r["end"]] = r
                for e, r in best.items():
                    out.setdefault(e, r["val"])
            if out: break                        # first tag with data wins
    return out
def fy_of(end):                                   # fiscal year label by end date (Jan/Feb year-ends belong to the previous year)
    y, m = int(end[:4]), int(end[5:7])
    return y - 1 if m <= 2 else y
tick = json.loads((CACHE / "company_tickers.json").read_text(encoding="utf-8"))
cik = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in tick.values()}
from src.ai.db_stores import select_all
import vc
runner = vc.make_runner(0); c = runner.client
syms = sorted({x["symbol"] for x in select_all(c, "companies", order="id") if x["exchange"] == "US"})
out = {}
for t in syms:
    p = CACHE / f"facts_{cik.get(t, '')}.json"
    if not p.exists(): out[t] = {"error": "no cache"}; continue
    f = json.loads(p.read_text(encoding="utf-8"))
    acq, stk, disc, rev, ast = annual(f, ACQ), annual(f, STK), annual(f, DISC), annual(f, REV), annual(f, ["Assets"], instant=True)
    cons = annual(f, CONS)
    years = {}
    for e in sorted(set(acq) | set(stk) | set(disc) | set(cons)):
        fy = fy_of(e)
        if fy < 2016: continue
        a = ast.get(e); r = rev.get(e)
        deal = (acq.get(e) or 0) + (stk.get(e) or 0)
        wide = max(deal, cons.get(e) or 0)
        years[fy] = {"deal": deal, "assets": a, "deal_pct": (deal / a if a else None), "consideration_pct": (wide / a if a else None), "disc_rev": disc.get(e), "revenue": r, "disc_pct": (disc[e] / r if e in disc and r else None)}
    brk = [y for y, v in years.items() if (v["deal_pct"] or 0) > 0.25 or (v["disc_pct"] or 0) > 0.25]
    out[t] = {"years": years, "breaks": sorted(brk)}
Path(ROOT / "scripts/state/cal_break_rule.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
hit = {t: v["breaks"] for t, v in out.items() if v.get("breaks")}
print("companies:", len(out), "with a break:", len(hit)); print(hit)

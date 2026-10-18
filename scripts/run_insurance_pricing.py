"""INSURANCE pricing round (spec 2026-10-13_12-40: Q7, P1-P4). Writes scripts/output_insurance_pricing/; earlier outputs are kept.

Usage:  .venv/Scripts/python -X utf8 scripts/run_insurance_pricing.py   (needs the ASCII CA bundle env vars for yfinance on this machine)
"""
from __future__ import annotations

import json
import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_insurance_test as r1  # noqa: E402
import run_insurance_test_v3 as r3  # noqa: E402
from run_insurance_test import COMPANIES, jsonable  # noqa: E402
from run_insurance_test_v2 import _ranks  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.insurance_facts import load_insurance_regulatory  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring import insurance as INS  # noqa: E402
from src.scoring.insurance import LINE_OF_BUSINESS  # noqa: E402

OUT = ROOT / "scripts" / "output_insurance_pricing"
R3 = ROOT / "scripts" / "output_insurance_v3"
SPEC = "docs/scoring/ValueCompass_Insurance_Rules_2026-10-13_12-40_EN.md"
_PRICE_DATE = {}
_PRICED = {}


def _lp(t, ends, labels):
    pr = _orig_lp(t, ends, labels)
    _PRICE_DATE[t] = pr.get("current_date")
    return pr


def _sip(ii):
    res = INS.score_insurance_priced(ii)
    _PRICED[ii.ticker] = res
    return res


_orig_lp = price_provider.load_prices
price_provider.load_prices = _lp
r1.price_provider.load_prices = _lp
r1.score_insurance = _sip


def f(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def p(x, nd=1):
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def rng(r):
    return "n/a" if not r else f"{r[0]:,.0f}-{r[1]:,.0f}"


def buy(b):
    if not isinstance(b, dict):
        return "n/a"
    if b.get("state") == "computed":
        return f(b["buy_price"])
    inf = b.get("informational_buy_price_ignoring_coverage")
    return b.get("state", "n/a") + (f" (info {f(inf)})" if inf else "")


def ret(x):
    return x if isinstance(x, str) else p(x)


def build(runs, failures):
    T = list(runs)
    old = {t: json.loads((R3 / f"{t}.json").read_text(encoding="utf-8")) for t in T}
    dates = sorted({str(v) for v in _PRICE_DATE.values()})
    L = [f"# ValueCompass INSURANCE pricing round - {date.today().isoformat()}\n",
         f"Spec: `{SPEC}` (supersedes 12-05). Quality rules closed except **Q7**. Prices: latest close from the existing price provider, date(s): {', '.join(dates)}. "
         "No DB writes, no AI calls (AI items stay `ai_pending`), nothing committed. Earlier outputs are kept.\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    # ---- Q7
    L.append("## 1. Q7 - years flagged under Q4 leave the cost-of-float series\n")
    L.append("| Company | Excluded cost-of-float years (Q4 flag) | Buffett R3 -> now | Graham R3 -> now | 3.5.1 | 3.5.2 | 3.5.4 | Coverage B |")
    L.append("|---|---|---|---|---|---|---|---|")
    chg = []
    for t in T:
        d, bq, gq = runs[t]["d"], runs[t]["bq"], runs[t]["gq"]
        ex = [f"{runs[t]['ii'].fy[i]}" for i, fl in enumerate(d["cost_flags"]) if fl and fl.startswith("structural_change_Q4")]
        o = old[t]
        cells = []
        for iid in ("1", "2", "4"):
            oi = next(i for c in o["buffett_quality"]["criteria"] if c["id"] == "3.5" for i in c["items"] if i["id"] == iid)
            ni = r1._item(bq, "3.5", iid)
            a = oi["state"] if oi["points"] is None else f"{oi['points']:.2f}"
            b = ni.state if ni.points is None else f"{ni.points:.2f}"
            cells.append(a if a == b else f"{a} -> **{b}**")
        db, dg = bq.score - o["buffett_quality"]["score"], gq.score - o["graham_quality"]["score"]
        if abs(db) > 0.005 or abs(dg) > 0.005:
            chg.append(t)
        L.append(f"| {t} | {', '.join(ex) or '-'} | {o['buffett_quality']['score']:.1f} -> {bq.score:.1f} ({db:+.1f}) | {o['graham_quality']['score']:.1f} -> {gq.score:.1f} ({dg:+.1f}) | "
                 f"{cells[0]} | {cells[1]} | {cells[2]} | {o['buffett_quality']['coverage']:.0%} -> {bq.coverage:.0%} |")
    L.append("\nCompanies whose quality score changed because of Q7: " + (", ".join(chg) or "none") + ".\n")
    rb3 = _ranks({t: old[t]["buffett_quality"]["score"] for t in T})
    rb4 = _ranks({t: runs[t]["bq"].score for t in T})
    L.append("Buffett rank changes: " + (", ".join(f"{t} {rb3[t]}->{rb4[t]}" for t in T if rb3[t] != rb4[t]) or "none") + ".\n")
    # ---- main table
    L.append("## 2. Full table (price in USD per share)\n")
    L.append("| Company | Line | Price | Q Buffett | Q Graham | Buffett value | Range (erosion / +-1pp) | Graham value (operating) | Graham value (reported EPS, display) | Buffett price score | Graham price score | Buffett buy price | Graham buy price | Implied return | Implied ROE |")
    L.append("|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|---:|---:|---:|---:|")
    for t in T:
        r, bp, gp = runs[t], _PRICED[t]["buffett_price"], _PRICED[t]["graham_price"]
        gps = gp["price_score"]
        rep = gp.get("reported_eps_comparison")
        bb, gb = bp.get("buy_price"), gp.get("buy_price")
        L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {f(r['ii'].price_current)} | {r['bq'].score:.1f} | {r['gq'].score:.1f} | "
                 f"{f(bp.get('fair_value')) if bp['state'] == 'valued' else 'cannot be valued'} | {rng(bp.get('sensitivity_range')) if bp['state'] == 'valued' else 'n/a'} | "
                 f"{f(gp.get('value')) if gp['state'] == 'valued' else 'cannot be valued'} | {f(rep['graham_number']) if rep else 'n/a'} | "
                 f"{f(bp['price_score'].get('points'))} | {f(gps.get('points')) if gps.get('points') is not None else gps.get('state')} | "
                 f"{buy(bb)} | {buy(gb)} | "
                 f"{ret(bp.get('implied_return')) if 'implied_return' in bp else 'n/a'} | "
                 f"{ret(bp.get('implied_roe')) if 'implied_roe' in bp else 'n/a'} |")
    # ---- inputs
    L.append("\n## 3. Pricing inputs per company\n")
    L.append("| Company | E0 adjusted equity (USD bn) | Shares (m) | Adjusted BVPS | ROE median | ROE_norm | Payout | Growth gate | g1 | Value / adj. book | Price / adj. book | Justified P/B (single stage) | Operating EPS 10y avg | Years | Adj. TBVPS | Loss years |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for t in T:
        bp, gp = _PRICED[t]["buffett_price"], _PRICED[t]["graham_price"]
        gate = bp.get("growth_gate")
        L.append(f"| {t} | {f((bp.get('e0') or 0) / 1e9, 1) if bp.get('e0') is not None else 'n/a'} | {f((bp.get('shares') or 0) / 1e6, 0) if bp.get('shares') else 'n/a'} | "
                 f"{f(bp.get('adjusted_bvps'))} | {p(bp.get('roe_median'))} | {p(bp.get('roe_norm'))} | {p(bp.get('payout'))} | "
                 f"{('pass' if gate['passed'] else 'FAIL') if gate else 'n/a'} | {p(bp.get('g1'))} | {f(bp.get('value_to_adjusted_book'))}x | {f(bp.get('price_to_adjusted_book'))}x | "
                 f"{f(bp.get('justified_pb_single_stage'))}x | {f(gp.get('normalized_eps'))} | {gp.get('years_available')} | {f(gp.get('tbvps_adj'))} | {', '.join(gp.get('loss_years') or []) or '-'} |")
    L.append("\n### Buffett value detail (sensitivity, per share)\n")
    L.append("| Company | State | Base | Erosion (ROE_norm > 10% only) | ROE +1pp | ROE -1pp | Reason if not valued |")
    L.append("|---|---|---:|---:|---:|---:|---|")
    for t in T:
        bp = _PRICED[t]["buffett_price"]
        s = bp.get("sensitivity") or {}
        L.append(f"| {t} | {bp['state']} | {f(s.get('base'))} | {f(s.get('erosion'))} | {f(s.get('roe_plus_1pp'))} | {f(s.get('roe_minus_1pp'))} | {bp.get('reason', '')} |")
    L.append("\n### Graham operating EPS series (USD per diluted share)\n")
    for t in T:
        gp = _PRICED[t]["graham_price"]
        L.append(f"- **{t}** ({gp['state']}): " + ", ".join(f"{k[2:]}: {v:.2f}" if v is not None else f"{k[2:]}: n/a" for k, v in gp["operating_eps_series"].items())
                 + (f" - {gp['reason']}" if gp.get("reason") else ""))
    # ---- flags & sanity
    L.append("\n## 4. Flags and sanity checks\n")
    for t in T:
        bp, gp = _PRICED[t]["buffett_price"], _PRICED[t]["graham_price"]
        fl = [f"B: {x}" for x in bp.get("flags", [])] + [f"G: {x}" for x in gp.get("flags", [])]
        L.append(f"- **{t}**: " + ("; ".join(fl) if fl else "no flags"))
    hi = [t for t in T if _PRICED[t]["buffett_price"].get("value_to_adjusted_book", 0) > 3]
    lo = [t for t in T if _PRICED[t]["buffett_price"]["state"] == "valued" and _PRICED[t]["buffett_price"]["value_to_adjusted_book"] < 0.5]
    L.append(f"\nValue above 3x adjusted book: {', '.join(hi) or 'none'}. Value below 0.5x adjusted book: {', '.join(lo) or 'none'}.")
    L.append("\n## 5. Open issues\n")
    ip = ROOT / "scripts" / "insurance_rule_issues_pricing.md"
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(not written yet)")
    (OUT / "summary_insurance_pricing.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    r1.OUT = OUT
    r1.InsuranceInputs = r3._make_inputs
    sec = SecClient()
    reg_all = load_insurance_regulatory()
    runs, failures = {}, []
    for t in COMPANIES:
        try:
            runs[t] = r1.run_company(sec, reg_all, t)
            pr = {"price_date": _PRICE_DATE.get(t), "buffett_price": _PRICED[t]["buffett_price"], "graham_price": _PRICED[t]["graham_price"]}
            (OUT / f"{t}_pricing.json").write_text(json.dumps(jsonable(pr), indent=1, ensure_ascii=False, default=str), encoding="utf-8")
            print(f"{t}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    if runs:
        build(runs, failures)


if __name__ == "__main__":
    main()

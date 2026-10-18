"""INSURANCE confirmation run (spec 2026-10-13_13-00: ETL share-scale guard, Q8 a-e, Q9, P5). Writes scripts/output_insurance_final/.

Usage:  .venv/Scripts/python -X utf8 scripts/run_insurance_final.py     (run scripts/audit_share_guard.py first for the 44-company guard audit)
Earlier outputs are kept; the comparison base is the pricing round (scripts/output_insurance_pricing).
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

import run_insurance_pricing as rp  # noqa: E402  (patches the price loader and score function; provides _PRICED / _PRICE_DATE)
import run_insurance_test as r1  # noqa: E402
import run_insurance_test_v3 as r3  # noqa: E402
from run_insurance_pricing import _PRICE_DATE, _PRICED, buy, f, p, rng, ret  # noqa: E402
from run_insurance_test import COMPANIES, jsonable  # noqa: E402
from run_insurance_test_v2 import _crit_pts, _ranks  # noqa: E402
from src.providers.insurance_facts import load_insurance_regulatory  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring.insurance import LINE_OF_BUSINESS  # noqa: E402

OUT = ROOT / "scripts" / "output_insurance_final"
PREV = ROOT / "scripts" / "output_insurance_pricing"
SPEC = "docs/scoring/ValueCompass_Insurance_Rules_2026-10-13_17-15_EN.md (Q8-Q10; supersedes 13-00) + the ETL-guard and P5 definitions in the request"


def _prev(t):
    return (json.loads((PREV / f"{t}.json").read_text(encoding="utf-8")), json.loads((PREV / f"{t}_pricing.json").read_text(encoding="utf-8")))


def _g(x):
    return "n/a" if x is None else ("pass" if x["passed"] else "FAIL")


def build(runs, failures):
    T = list(runs)
    old = {t: _prev(t) for t in T}
    audit = json.loads((OUT / "share_guard_audit.json").read_text(encoding="utf-8")) if (OUT / "share_guard_audit.json").exists() else {}
    dates = sorted({str(v) for v in _PRICE_DATE.values()})
    L = [f"# ValueCompass INSURANCE confirmation run - {date.today().isoformat()}\n",
         f"Spec: {SPEC}. Prices: latest close from the existing price provider ({', '.join(dates)}). No DB writes, no AI calls (AI items stay `ai_pending`), nothing committed. "
         "Earlier outputs are kept; the comparison base is the pricing round.\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    # ------------------------------------------------------------ 1 guard
    L.append("## 1. ETL share-scale guard (all profiles)\n")
    L.append("Rule (in `guard_share_scale`, `src/providers/sec_companyfacts.py`, called by the general, bank and insurance ETLs): a share count about 1,000x smaller or larger than its reference "
             "(period-end count: its own neighbours; weighted-average counts: the period-end count of the same year) is rescaled and the year flagged in the tag log and the data "
             "problems; any other mismatch (outside 0.2x-5x of every reference) becomes missing. The earlier scale rule for values below 100,000 (reported in millions) is unchanged. "
             "The guard that lived in `operating_eps_series` was removed.\n")
    if audit:
        fired = [v for v in audit.values() if v.get("fired")]
        errs = [v for v in audit.values() if v.get("error")]
        counts = {}
        for v in audit.values():
            counts[v["group"]] = counts.get(v["group"], 0) + 1
        L.append("Audit of every company's ETL series (" + ", ".join(f"{n} {g}" for g, n in counts.items()) + f" = {len(audit)} companies): "
                 f"the guard fired for **{len(fired)}** - " + (", ".join(f"{v['group']}:{v['ticker']}" for v in fired) or "none") + ". "
                 + (f"Errors: {', '.join(v['ticker'] for v in errs)}." if errs else "No company failed to build."))
        for v in fired:
            L.append(f"\n- {v['group']}:{v['ticker']}: {v['events'][0]}")
    else:
        L.append("(run scripts/audit_share_guard.py to produce the 44-company audit)")
    wrb = runs.get("WRB")
    if wrb:
        o_b, o_g = old["WRB"][0]["buffett_quality"], old["WRB"][0]["graham_quality"]
        L.append(f"\nQuality effect of the guard (WRB): Buffett {o_b['score']:.1f} -> {wrb['bq'].score:.1f}, Graham {o_g['score']:.1f} -> {wrb['gq'].score:.1f} (shares_dil FY2017-FY2022 now correct; "
                 "see the per-criterion table in section 4 for the exact items). Every other company's ETL series is unchanged by the guard.\n")
    # ------------------------------------------------------------ 2 Q8 / Q9
    L.append("## 2. Q8a / Q9 / Q10 / Q7 - flagged years and reasons\n")
    L.append("| Company | Q8a/Q10: year missing | Q8a/Q10: counted as 0 (flag) | Q9 basis-mismatch | Q4/Q7 structural | Q8e undefined-ROE | Graham 3.7.3 | Cost-of-float years valid (last 5) |")
    L.append("|---|---|---|---|---|---|---|---|")
    for t in T:
        d, ii = runs[t]["d"], runs[t]["ii"]
        miss_ = [f"{ii.fy[i]} ({x.split(': ', 1)[-1]})" for i, x in enumerate(d["cost_flags"]) if x and ("_Q10" in x)]
        zero_ = [f"{ii.fy[i]} ({x})" for i, x in enumerate(d["uw_flags"]) if x]
        q9 = [f"{k} ({v})" for k, v in d["basis_mismatch"].items()]
        q4 = [f"{ii.fy[i]}" for i, x in enumerate(d["cost_flags"]) if x and x.startswith("structural_change_Q4")]
        q8e = [ii.fy[i] for i, x in enumerate(d["roe_flags"]) if x]
        it = r1._item(runs[t]["gq"], "3.7", "3")
        nvalid = sum(1 for x in d["cost_of_float"][-5:] if x is not None)
        L.append(f"| {t} | {'; '.join(miss_) or '-'} | {'; '.join(zero_) or '-'} | {'; '.join(q9) or '-'} | {', '.join(q4) or '-'} | {', '.join(q8e) or '-'} | "
                 f"{it.state}{'' if it.points is None else f' ({it.points:.2f})'} | {nvalid} of 5 |")
    L.append("\nQ8d (3.5.4 condition) and Q8c (Graham 3.8.1) were already implemented as specified (cumulative gap < 0 and >= 3 valid years below the yield; sum of net income <= 0 gives 0 points); "
             "tests added.\n")
    # ------------------------------------------------------------ 3 gate
    L.append("## 3. Growth gate before and after P5\n")
    L.append("Pricing round = total operating revenue and reported EPS (earlier run); 'same data, old basis' isolates the data changes; P5 = insurance revenue (premiums earned + policy fees) and operating EPS, thresholds unchanged.\n")
    L.append("| Company | Pricing round | Same data, old basis | P5 gate | Failing conditions under P5 | g1 before -> after | Revenue rises (4) | EPS falls >10% | EPS positive (5) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for t in T:
        bp, ob = _PRICED[t]["buffett_price"], old[t][1]["buffett_price"]
        gt, gb = bp.get("growth_gate"), bp.get("growth_gate_before_P5")
        og = ob.get("growth_gate")
        L.append(f"| {t} | {_g(og)} | {_g(gb)} | **{_g(gt)}** | {'; '.join(gt['failing']) if gt and gt['failing'] else '-'} | {p(ob.get('g1'))} -> {p(bp.get('g1'))} | "
                 f"{gt['revenue_rises'] if gt else 'n/a'} | {gt['eps_falls_gt10'] if gt else 'n/a'} | {gt['eps_positive_years'] if gt else 'n/a'} |")
    # ------------------------------------------------------------ 4 quality
    L.append("\n## 4. Quality: pricing round -> confirmation run\n")
    rb2 = _ranks({t: old[t][0]["buffett_quality"]["score"] for t in T})
    rb3 = _ranks({t: runs[t]["bq"].score for t in T})
    rg2 = _ranks({t: old[t][0]["graham_quality"]["score"] for t in T})
    rg3 = _ranks({t: runs[t]["gq"].score for t in T})
    L.append("| Company | Line | Buffett | Rank | Graham | Rank | Coverage B | Coverage G | Status B / G | Range B | Range G |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for t in T:
        bq, gq, ob, og = runs[t]["bq"], runs[t]["gq"], old[t][0]["buffett_quality"], old[t][0]["graham_quality"]
        rg_ = lambda m: "withheld" if m.min_score is None else f"{m.min_score:.1f}-{m.max_score:.1f}"  # noqa: E731
        L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {ob['score']:.1f} -> {bq.score:.1f} ({bq.score - ob['score']:+.1f}) | {rb2[t]} -> {rb3[t]}{' *' if rb2[t] != rb3[t] else ''} | "
                 f"{og['score']:.1f} -> {gq.score:.1f} ({gq.score - og['score']:+.1f}) | {rg2[t]} -> {rg3[t]}{' *' if rg2[t] != rg3[t] else ''} | "
                 f"{ob['coverage']:.0%} -> {bq.coverage:.0%} | {og['coverage']:.0%} -> {gq.coverage:.0%} | {bq.status} / {gq.status} | {rg_(bq)} | {rg_(gq)} |")
    errs = [(t, k) for t in T for k, m in (("Buffett", runs[t]["bq"]), ("Graham", runs[t]["gq"])) if m.range_error]
    L.append("\n`*` = rank changed. Rank changes - Buffett: " + (", ".join(f"{t} {rb2[t]}->{rb3[t]}" for t in T if rb2[t] != rb3[t]) or "none") + "; Graham: "
             + (", ".join(f"{t} {rg2[t]}->{rg3[t]}" for t in T if rg2[t] != rg3[t]) or "none") + ".")
    L.append("\n**D14 range checks (min <= score <= max):** " + ("all 24 model ranges are consistent." if not errs else "FAILED: " + ", ".join(f"{t} {k}" for t, k in errs)))
    L.append("\n### Criteria that changed (points / applicable maximum; `!` = invalid under M2)\n")
    for t in T:
        ch = []
        for model, key, tag in (("buffett_quality", "buffett_quality", "B"), ("graham_quality", "graham_quality", "G")):
            for c in runs[t]["res"][key]["criteria"]:
                oo, om, ov = _crit_pts(old[t][0][model], c["id"])
                no, nm, nv = _crit_pts(runs[t]["res"][key], c["id"])
                a, b = f"{oo:.1f}/{om:g}" + ("" if ov else "!"), f"{no:.1f}/{nm:g}" + ("" if nv else "!")
                if a != b:
                    ch.append(f"{tag}{c['id']} {a} -> {b}")
        L.append(f"- **{t}**: " + ("; ".join(ch) if ch else "no criterion changed"))
    L.append("\n### Items that changed state or points\n")
    for t in T:
        ch = []
        for model, tag in (("buffett_quality", "B"), ("graham_quality", "G")):
            oi = {(c["id"], i["id"]): i for c in old[t][0][model]["criteria"] for i in c["items"]}
            for c in runs[t]["res"][model]["criteria"]:
                for i in c["items"]:
                    o = oi.get((c["id"], i["id"]))
                    if o is None:
                        continue
                    pa = o["state"] if o["points"] is None else f"{o['points']:.2f}"
                    pb = i["state"] if i["points"] is None else f"{i['points']:.2f}"
                    if pa != pb:
                        ch.append(f"{tag}{c['id']}.{i['id']} {pa} -> {pb}")
        if ch:
            L.append(f"- **{t}**: " + "; ".join(ch))
    # ------------------------------------------------------------ 5 pricing changes
    L.append("\n## 5. Pricing: pricing round -> confirmation run (per share, USD)\n")
    L.append("| Company | Buffett value | Range | Graham value | Buffett price score | Graham price score | Buffett buy price | Graham buy price | Implied return |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for t in T:
        bp, gp = _PRICED[t]["buffett_price"], _PRICED[t]["graham_price"]
        ob, og = old[t][1]["buffett_price"], old[t][1]["graham_price"]
        L.append(f"| {t} | {f(ob.get('fair_value'))} -> **{f(bp.get('fair_value'))}** | {rng(ob.get('sensitivity_range'))} -> {rng(bp.get('sensitivity_range'))} | "
                 f"{f(og.get('value'))} -> **{f(gp.get('value'))}** | {f(ob['price_score'].get('points'))} -> {f(bp['price_score'].get('points'))} | "
                 f"{f(og['price_score'].get('points'))} -> {f(gp['price_score'].get('points'))} | {buy(ob.get('buy_price'))} -> {buy(bp.get('buy_price'))} | "
                 f"{buy(og.get('buy_price'))} -> {buy(gp.get('buy_price'))} | {ret(ob.get('implied_return')) if 'implied_return' in ob else 'n/a'} -> "
                 f"{ret(bp.get('implied_return')) if 'implied_return' in bp else 'n/a'} |")
    # ------------------------------------------------------------ 6 final table
    L.append("\n## 6. Final table (price in USD per share)\n")
    L.append("| Company | Line | Price | Q Buffett | Q Graham | Buffett value | Range (erosion / +-1pp) | Graham value (operating) | Graham (reported EPS, display) | Buffett price score | Graham price score | Buffett buy price | Graham buy price | Implied return | Implied ROE |")
    L.append("|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for t in T:
        r, bp, gp = runs[t], _PRICED[t]["buffett_price"], _PRICED[t]["graham_price"]
        rep = gp.get("reported_eps_comparison")
        gps = gp["price_score"]
        L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {f(r['ii'].price_current)} | {r['bq'].score:.1f} | {r['gq'].score:.1f} | "
                 f"{f(bp.get('fair_value')) if bp['state'] == 'valued' else 'cannot be valued'} | {rng(bp.get('sensitivity_range')) if bp['state'] == 'valued' else 'n/a'} | "
                 f"{f(gp.get('value')) if gp['state'] == 'valued' else 'cannot be valued'} | {f(rep['graham_number']) if rep else 'n/a'} | "
                 f"{f(bp['price_score'].get('points'))} | {f(gps.get('points')) if gps.get('points') is not None else gps.get('state')} | "
                 f"{buy(bp.get('buy_price'))} | {buy(gp.get('buy_price'))} | {ret(bp.get('implied_return')) if 'implied_return' in bp else 'n/a'} | "
                 f"{ret(bp.get('implied_roe')) if 'implied_roe' in bp else 'n/a'} |")
    L.append("\n### Pricing inputs per company\n")
    L.append("| Company | E0 adjusted equity (USD bn) | Adjusted BVPS | ROE median | ROE_norm | Payout | Growth gate (P5) | g1 | Value / adj. book | Price / adj. book | Justified P/B | Operating EPS 10y avg | Years | Adj. TBVPS | Loss years |")
    L.append("|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for t in T:
        bp, gp = _PRICED[t]["buffett_price"], _PRICED[t]["graham_price"]
        L.append(f"| {t} | {f((bp['e0'] / 1e9) if bp.get('e0') is not None else None, 1)} | {f(bp.get('adjusted_bvps'))} | {p(bp.get('roe_median'))} | {p(bp.get('roe_norm'))} | {p(bp.get('payout'))} | "
                 f"{_g(bp.get('growth_gate'))} | {p(bp.get('g1'))} | {f(bp.get('value_to_adjusted_book'))}x | {f(bp.get('price_to_adjusted_book'))}x | "
                 f"{f(bp.get('justified_pb_single_stage'))}x | {f(gp.get('normalized_eps'))} | {gp.get('years_available')} | {f(gp.get('tbvps_adj'))} | {', '.join(gp.get('loss_years') or []) or '-'} |")
    L.append("\n### Flags and sanity checks\n")
    for t in T:
        bp, gp = _PRICED[t]["buffett_price"], _PRICED[t]["graham_price"]
        fl = [f"B: {x}" for x in bp.get("flags", [])] + [f"G: {x}" for x in gp.get("flags", [])]
        L.append(f"- **{t}**: " + ("; ".join(fl) if fl else "no flags"))
    hi = [t for t in T if _PRICED[t]["buffett_price"].get("value_to_adjusted_book", 0) > 3]
    lo = [t for t in T if _PRICED[t]["buffett_price"]["state"] == "valued" and _PRICED[t]["buffett_price"]["value_to_adjusted_book"] < 0.5]
    L.append(f"\nValue above 3x adjusted book: {', '.join(hi) or 'none'}. Value below 0.5x adjusted book: {', '.join(lo) or 'none'}.")
    L.append("\n## 7. Open issues\n")
    ip = ROOT / "scripts" / "insurance_rule_issues_final.md"
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(not written yet)")
    L.append("\n## Data problems by company\n")
    for t in T:
        L.append(f"- **{t}**: " + ("; ".join(runs[t]["res"]["data_problems"]) if runs[t]["res"]["data_problems"] else "none detected"))
    (OUT / "summary_insurance_final.md").write_text("\n".join(L) + "\n", encoding="utf-8")


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

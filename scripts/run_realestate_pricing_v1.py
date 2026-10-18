"""INCOME_REAL_ESTATE pricing round 1 (RP1-RP3 + QA Q1-Q5; spec docs/scoring/ValueCompass_RealEstate_Rules_2026-10-14_22-30_EN.md, section 6).
Cached data only (SEC companyfacts and price cache; EQR price from the VMRK successor as in round 3). No DB, no AI calls, no extraction.
Writes scripts/output_realestate_pricing_v1/ (summary_pricing_v1.md + one JSON per company).

Usage:  .venv/Scripts/python -X utf8 scripts/run_realestate_pricing_v1.py   (CA bundle env vars for yfinance as in the earlier rounds)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_realestate_v5 import build_ri  # noqa: E402
from run_scoring_test import jsonable, model_json  # noqa: E402
from src.providers.realestate_facts import load_realestate_extracted  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring.realestate import conservative_cap_rate, score_realestate, score_realestate_pricing  # noqa: E402

T = ["O", "PLD", "SPG", "FRT", "BXP", "ARE", "EQR", "PSA", "EQIX", "AMT"]
OUT = ROOT / "scripts" / "output_realestate_pricing_v1"
V5 = ROOT / "scripts" / "output_realestate_v5"
SPEC = "docs/scoring/ValueCompass_RealEstate_Rules_2026-10-14_22-30_EN.md"
CSV = ROOT / "scripts" / "realestate_extracted.csv"
NL = "\n"


def f(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def pc(x, nd=1):
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def bn(x, nd=2):
    return "n/a" if x is None else f"{x / 1e9:,.{nd}f}"


def ps_txt(p):
    if p is None:
        return "n/a"
    if p.get("state") == "score":
        return f(p["points"])
    return {"blocked": "blocked", "not_applicable": "n/a", "missing": "missing"}.get(p.get("state"), str(p.get("state")))


def buy_txt(b):
    if not b:
        return "n/a"
    return f(b["buy_price"]) if b.get("state") == "computed" else b.get("state", "n/a") + ("" if not b.get("reason") else "")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sec = SecClient()
    reg_all = load_realestate_extracted()
    R, fails = {}, []
    for t in T:
        try:
            ri, raw = build_ri(sec, reg_all, t)
            sc = score_realestate(ri)
            pr = score_realestate_pricing(ri, sc)
            R[t] = {"ri": ri, "raw": raw, "sc": sc, "pr": pr}
            res = {"ticker": t, "name": ri.name, "asset_type": ri.asset_type, "spec": SPEC, "as_of": date.today(), "price": {"current": ri.price_current, "date": ri.price_date},
                   "buffett_quality": model_json(sc["buffett_quality"]), "graham_quality": model_json(sc["graham_quality"]),
                   "buffett_price": pr["buffett_price"], "graham_price": pr["graham_price"], "display": pr["display"], "data_problems": list(dict.fromkeys(ri.data_problems))}
            (OUT / f"{t}.json").write_text(json.dumps(jsonable(res), indent=1, ensure_ascii=False, default=str), encoding="utf-8")
            print(t, "ok")
        except Exception as e:  # noqa: BLE001
            fails.append((t, f"{type(e).__name__}: {e}"))
            traceback.print_exc()
    csv_rows = [r for r in csv.DictReader(CSV.open(encoding="utf-8")) if r["ticker"] and not r["ticker"].startswith("#")]
    v5 = {t: json.loads((V5 / f"{t}.json").read_text(encoding="utf-8")) for t in T if (V5 / f"{t}.json").exists()}
    cr = conservative_cap_rate()
    L = [f"# ValueCompass INCOME_REAL_ESTATE pricing round 1 (RP1-RP3) - {date.today().isoformat()}" + NL,
         f"Spec: `{SPEC}` (section 6, RE24-RE27). Cached data only; no DB, no AI, no extraction. SEC requests this run: {sec.requests_made}. "
         f"Parameters: Buffett discount rate {pc(0.10, 0)} (RP1, parameter), RP1a block above 8x net debt / EBITDAre; conservative cap rate = max(10-year US government yield + 3 pp, 6%) = "
         f"**{pc(cr['value'], 2)}** (US 10-year, {cr['gov_year']} annual average {pc(cr['gov_yield'], 2)} from `scripts/gov_yields.csv`; the file has annual averages only, no spot yield). "
         "Prices: latest close (EQR: VMRK successor close). Per-share values in USD." + NL]
    if fails:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in fails) + NL)

    # ------------------------------------------------------------------ 1 table per company
    L.append("## 1. Price, values, scores and buy prices (RP1-RP3)" + NL)
    L.append("Buffett value = DCF of OE per share (10%, two-stage, G1, no debt subtraction); Graham value = conservative NAV per share. Discount = (value - price) / value. "
             "A value shown for a blocked company is **not a buy price** (RP1a) or an indicative NAV (RP2 non-NOI assets incomplete)." + NL)
    L.append("| Company | Price | Buffett value | Discount | Price score | Buy price | RP1a block | Graham NAV | Discount | Price score | Buy price | RP2 block |")
    L.append("|---|---:|---:|---:|---:|---|---|---:|---:|---:|---|---|")
    for t in R:
        b, g, ri = R[t]["pr"]["buffett_price"], R[t]["pr"]["graham_price"], R[t]["ri"]
        pr_ = ri.price_current
        bv, gv = b.get("fair_value"), g.get("value")
        bd = None if bv is None or not pr_ else (bv - pr_) / bv
        gd = None if gv is None or not pr_ else (gv - pr_) / gv
        guard = b["guard"]
        blk = ("yes: " + "; ".join(guard["reasons"])) if guard["blocked"] else "no"
        bv_txt = f(bv) if bv is not None else b["state"] + (f" ({b['reason'][:70]}...)" if b.get("reason") else "")
        gblk = "yes: " + g["price_score"]["reason"][5:] if g.get("price_score", {}).get("state") == "blocked" else "no"
        gv_txt = f(gv) if gv is not None else g["state"] + (f" ({g['reason']})" if g.get("reason") else "")
        L.append(f"| {t} | {f(pr_)} | {bv_txt}{' (not a buy price)' if b.get('label') else ''} | {pc(bd)} | {ps_txt(b['price_score'])} | {buy_txt(b['buy_price'])} | {blk} | "
                 f"{gv_txt}{' (indicative)' if g.get('label') else ''} | {pc(gd)} | {ps_txt(g['price_score'])} | {buy_txt(g['buy_price'])} | {gblk} |")
    L.append(NL + "### Sensitivities (display only)" + NL)
    L.append("Graham: cap rate +/-1 pp. Buffett: discount rate +/-1 pp and stage-1 growth +/-1 pp (growth shock applies to the DCF stages, the base is held). Price / average normalized FFO is indicative only (FFO is before recurring capex).")
    L.append("| Company | NAV cap -1pp | NAV base | NAV cap +1pp | DCF r -1pp | DCF base | DCF r +1pp | DCF g -1pp | DCF g +1pp | Stage-1 g | Price / avg FFO (5y) | <= 15x | Indicative DCF on normalized FFO (not a value) |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|")
    for t in R:
        b, g, dsp = R[t]["pr"]["buffett_price"], R[t]["pr"]["graham_price"], R[t]["pr"]["display"]
        gs, bs = g.get("sensitivities") or {}, b.get("sensitivities") or {}
        L.append(f"| {t} | {f(gs.get('cap-1pp'))} | {f(g.get('value'))} | {f(gs.get('cap+1pp'))} | {f(bs.get('r-1pp'))} | {f(b.get('fair_value'))} | {f(bs.get('r+1pp'))} | "
                 f"{f(bs.get('g-1pp'))} | {f(bs.get('g+1pp'))} | {pc(b.get('stage1_growth'))} | {f(dsp['price_to_avg_ffo'], 1)} | {dsp['within_15x'] if dsp['within_15x'] is not None else 'n/a'} | {f(b.get('indicative_ffo_dcf_per_share'))} |")
    L.append(NL + "### Why a Buffett value is missing or blocked, and NAV components" + NL)
    L.append("| Company | Buffett state | Reason / flags | Base OE per share (median, bn-free) | NOI (bn) | Op. value at cap (bn) | Non-NOI counted (bn) | Net debt (bn) | Other claims (bn) | NAV (bn) | Unidentified assets / total assets |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for t in R:
        b, g = R[t]["pr"]["buffett_price"], R[t]["pr"]["graham_price"]
        c = g["components"]
        why = b.get("reason") or ("valued; " + "; ".join(b.get("flags", [])[:3]))
        L.append(f"| {t} | {b['state']} | {why[:230]} | {f((b.get('base_growth') or {}).get('median'))} | {bn(c.get('noi'))} | {bn(c.get('op_value'))} | {bn(c.get('non_noi_counted'))} | {bn(c.get('net_debt'))} | "
                 f"{bn(sum((c.get('other_claims') or {}).values()) if c.get('other_claims') else None)} | {bn(c.get('nav'))} | {pc(c.get('unidentified_share_of_assets'), 0)} |")

    # ------------------------------------------------------------------ 2 QA
    L.append(NL + "## 2. QA report (Q1-Q5)" + NL)
    # Q1
    L.append("### Q1. FFO definition (NAREIT vs company-adjusted) and reconciliation to the report" + NL)
    L.append("Our FFO follows the NAREIT form (RE17); the reported measure is the company's headline NAREIT FFO as extracted (not Core / Adjusted FFO; the CSV note of each reported_ffo row names the measure). "
             "Gap = ours vs reported; up to 3% = close, 3-10% = explained difference, above 10% = flagged." + NL)
    L.append("| Company | Reported measure (CSV note) | Our D&A source (latest year) | Gap FY2021-FY2025 | Years within 3% | Years 3-10% | Years above 10% | Match to the report |")
    L.append("|---|---|---|---|---:|---:|---:|---|")
    for t in R:
        d, ri = R[t]["sc"]["derived"], R[t]["ri"]
        notes = sorted({r["note"][:80] for r in csv_rows if r["ticker"] == t and r["item"] == "reported_ffo" and r["note"]})
        gaps = d["ffo_reconciliation_pct"][-5:]
        cells = ", ".join("n/a" if x is None else f"{x * 100:+.1f}%" for x in gaps)
        v = [abs(x) for x in gaps if x is not None]
        a, b_, c_ = sum(1 for x in v if x <= 0.03), sum(1 for x in v if 0.03 < x <= 0.10), sum(1 for x in v if x > 0.10)
        src = next((x for x in d["ffo_flags"][-1] if "D&A" in x or "total_DA" in x or "real_estate_depreciation" in x), "n/a")
        verdict = "close" if v and c_ == 0 and b_ == 0 else ("explained differences" if c_ == 0 else "FLAGGED (>10% in " + str(c_) + " year(s))")
        L.append(f"| {t} | {'; '.join(notes)[:150] or 'n/a'} | {src[:80]} | {cells} | {a} | {b_} | {c_} | {verdict} |")
    # Q2
    L.append(NL + "### Q2. EBITDAre computed vs reported" + NL)
    L.append("**Reported EBITDAre is not in the extraction CSV (no row) and no extraction was allowed this round, so the comparison to the reported figure was not performed** (open issue). "
             "Internal checks instead: EBITDAre / NOI (EBITDAre = NOI - G&A + JV income and other, so it should sit below NOI for a pure owner; outside 0.5-1.15 is flagged), "
             "and the identity gap EBITDAre - (our FFO + interest + income tax) as a share of EBITDAre (should equal the non-real-estate D&A, preferred / NCI items and the JV share)." + NL)
    L.append("| Company | EBITDAre (bn) FY2025 | NOI (bn) | EBITDAre / NOI | Identity gap (share of EBITDAre) | Net debt / EBITDAre | Flag |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    for t in R:
        d, ri = R[t]["sc"]["derived"], R[t]["ri"]
        e, n_, ffo = d["ebitdare"][-1], d["noi"][-1], d["ffo"][-1]
        it = ri.series("interest_expense")[-1]
        tx = ri.series("income_tax")[-1] or 0.0
        ratio = None if (e is None or not n_) else e / n_
        gap = None if (e is None or ffo is None or it is None) else (e - (ffo + it + tx)) / e
        flag = "" if ratio is None else ("EBITDAre/NOI outside 0.5-1.15" if not 0.5 <= ratio <= 1.15 else "")
        st = d["nd_ebitdare_state"][-1]
        L.append(f"| {t} | {bn(e)} | {bn(n_)} | {f(ratio)} | {pc(gap)} | {f(st[1]) if st[1] is not None else st[0]} | {flag or '-'} |")
    # Q3
    L.append(NL + "### Q3. Fixed-charge coverage consistency across years" + NL)
    L.append("Coverage = EBITDAre / (interest expense incl. capitalized interest + preferred dividends). Checks: the interest tag used in each year (a change of tag changes the definition), capitalized interest present, "
             "year-to-year move above 35% (flag)." + NL)
    L.append("| Company | FCC FY2021 ... FY2025 | Interest tags used (FY2021-FY2025) | Capitalized interest years | Max YoY move | Flag |")
    L.append("|---|---|---|---:|---:|---|")
    for t in R:
        d, ri = R[t]["sc"]["derived"], R[t]["ri"]
        fcc = d["fcc"][-5:]
        tags = [((ri.tag_log.get("interest_expense", {}) or {}).get(lab) or {}).get("tag") for lab in ri.fy[-5:]]
        tagset = sorted({x for x in tags if x})
        cap = sum(1 for x in ri.series("interest_capitalized")[-5:] if x)
        moves = [abs(b / a - 1) for a, b in zip(fcc[:-1], fcc[1:]) if a and b]
        fl = []
        if len(tagset) > 1:
            fl.append("interest tag changes across years")
        if any(x is None for x in tags):
            fl.append("interest tag missing in a year")
        if moves and max(moves) > 0.35:
            fl.append("YoY move > 35%")
        L.append(f"| {t} | {', '.join('n/a' if x is None else f'{x:.2f}x' for x in fcc)} | {', '.join(x.replace('ixbrl:', '') for x in tagset) or 'n/a'} | {cap} of 5 | {pc(max(moves)) if moves else 'n/a'} | {'; '.join(fl) or '-'} |")
    # Q4
    L.append(NL + "### Q4. Missing years and FFO_PROXY (last 5 fiscal years)" + NL)
    L.append("| Company | Net income | FFO | OE basis (OE / FFO_PROXY / missing years) | NOI | EBITDAre | Debt | Diluted shares | Same-property growth | Occupancy | Maintenance capex | TI/LC |")
    L.append("|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for t in R:
        d, ri = R[t]["sc"]["derived"], R[t]["ri"]
        miss5 = lambda xs: sum(1 for x in xs[-5:] if x is None)  # noqa: E731
        ob = d["oe_basis"][-5:]
        L.append(f"| {t} | {miss5(ri.series('net_income'))} | {miss5(d['ffo'])} | {ob.count('OE')} / {ob.count('FFO_PROXY')} / {ob.count(None)} | {miss5(d['noi'])} | {miss5(d['ebitdare'])} | {miss5(d['net_debt'])} | "
                 f"{miss5(ri.series('shares_dil'))} | {miss5(d['same_property_noi_growth'])} | {miss5(d['occupancy'])} | {miss5(d['maint_capex'])} | {miss5(d['tilc_pres'])} |")
    L.append("\n(cells = number of missing years out of 5, except the OE basis column = years on OE / years on FFO_PROXY / years missing)")
    # Q5
    L.append(NL + "### Q5. Source of every extracted field, and company-share vs group basis" + NL)
    L.append("XBRL fields are listed by the tag used in the latest year (`ixbrl:` = company extension element from the inline XBRL). Text-extracted fields come from the CSV (10-K or 8-K supplemental, with the exact quote and the basis in the note). "
             "Basis flags are taken from the note text: **share** = company / Operating Partnership share, **proportionate** = includes the share of unconsolidated ventures, **consolidated** = consolidated total (group)." + NL)
    for t in R:
        ri = R[t]["ri"]
        L.append(f"#### {t}" + NL)
        L.append("| Field | Source | Detail | Basis |")
        L.append("|---|---|---|---|")
        notag = []
        for fld, years in sorted(ri.tag_log.items()):
            last = [(lab, v) for lab, v in years.items() if v]
            if not last:
                continue
            tg = {v.get("tag") for _, v in last}
            if not any(tg):
                notag.append(fld)
                continue
            L.append(f"| {fld} | XBRL | {', '.join(sorted(x.replace('ixbrl:', 'ext:') for x in tg if x))[:110]} ({len(last)} years) | group (consolidated filing) |")
        if notag:
            L.append(f"| (no XBRL tag found in any year: missing unless extracted below) | - | {', '.join(notag)} | - |")
        byitem = {}
        for r in csv_rows:
            if r["ticker"] != t or r["value"] in ("not disclosed", "not extracted"):
                continue
            byitem.setdefault(r["item"], []).append(r)
        for item, rows in sorted(byitem.items()):
            src = sorted({("8-K supplemental" if "8-K" in r["source"] else "10-K text") for r in rows})
            notes = " | ".join(sorted({r["note"] for r in rows if r["note"]}))[:200]
            low = notes.lower()
            basis = [k for k, pat in (("share", r"\bshare\b|attributable|operating partnership|op unit"), ("proportionate", r"proportionate|pro rata|unconsolidated|joint venture|co-investment"),
                                      ("consolidated", r"consolidated|same-store|same property|domestic")) if re.search(pat, low)]
            L.append(f"| {item} | {'/'.join(src)} | {len(rows)} rows; {'verified' if all(r['verified'] == 'true' for r in rows) else 'UNVERIFIED'}; {notes or 'no note'} | {', '.join(basis) or 'not stated'} |")
        L.append("")

    # ------------------------------------------------------------------ 3 bias and double conservatism
    L.append("## 3. Bias by asset type and the double-conservatism check" + NL)
    L.append("One conservative cap rate for all asset types (round 1). Market-implied cap rate = NOI / (market capitalization + net debt + other claims - non-NOI assets). "
             f"When the market-implied rate is below the conservative {pc(cr['value'], 2)}, the conservative NAV is below the price before any margin of safety; the 50% Graham discount (score 10) is then unreachable, "
             "which is the stacking of the conservative cap rate and the margin the spec asks to check." + NL)
    L.append("| Company | Asset type | NOI basis | Market-implied cap | Conservative cap | Gap (pp) | NAV / price | Graham price score | Buffett value / price |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    zero_g = []
    for t in R:
        g, b, ri = R[t]["pr"]["graham_price"], R[t]["pr"]["buffett_price"], R[t]["ri"]
        mic = g.get("market_implied_cap_rate")
        capc = g["components"]["cap_rate"]
        navp = None if g.get("value") is None or not ri.price_current else g["value"] / ri.price_current
        bvp = None if b.get("fair_value") is None or not ri.price_current else b["fair_value"] / ri.price_current
        sc_ = g["price_score"]
        if sc_.get("state") == "score" and sc_["points"] == 0:
            zero_g.append(t)
        L.append(f"| {t} | {ri.asset_type} | {str(g['components'].get('noi_basis') or 'n/a')[:48]} | {pc(mic, 2)} | {pc(capc, 2)} | {'n/a' if mic is None else f'{(mic - capc) * 100:+.2f}'} | {f(navp)} | {ps_txt(sc_)} | {f(bvp)} |")
    n_blocked = [t for t in R if R[t]["pr"]["graham_price"].get("price_score", {}).get("state") == "blocked"]
    n_zero_ind = [t for t in n_blocked if R[t]["pr"]["graham_price"].get("value") is not None and R[t]["ri"].price_current and (R[t]["pr"]["graham_price"]["value"] - R[t]["ri"].price_current) / R[t]["pr"]["graham_price"]["value"] <= -0.25]
    L.append(NL + f"**Graham price score 0:** {len(zero_g)} of {len(R)} companies score 0" + (f" ({', '.join(zero_g)})" if zero_g else "") + f"; {len(n_blocked)} are blocked by RP2 (non-NOI assets missing and material: {', '.join(n_blocked) or 'none'}), "
             f"of which {len(n_zero_ind)} would have an indicative score 0 on the incomplete NAV ({', '.join(n_zero_ind) or 'none'}). Reasons per company are in the table (NAV / price below 0.75 = discount at or below -25% = score 0).")
    L.append("**Direction of the bias:** a single cap rate above the market's cap rate penalizes the asset types that trade at the lowest yields (residential, industrial, data centers, towers, self-storage) and spares high-yield office and retail; "
             "compare the 'Gap (pp)' column by asset type.")

    # ------------------------------------------------------------------ 4 comparison with v5
    L.append(NL + "## 4. Quality scores vs RE v5 after RE24 / RE26 / RE27" + NL)
    L.append("RE24 (straight-line sign: GAAP rent - cash rent, deducted; negative adjustment increases OE) is the convention the engine already applied (`OE = normalized FFO - straight-line - maintenance capex - TI/LC`); it is now documented, exposed per year "
             "(`straight_line_increases_oe`) and tested. RE26 (stress test) now returns missing when the carrying value of the other property is missing (it is missing for every company anyway: no fair value of real estate). "
             "RE27 (Graham 3.8.2) now requires positive OE in all five years and shows OE / FFO as a diagnostic." + NL)
    L.append("| Company | Buffett v5 | Buffett now | Coverage v5 -> now | Graham v5 | Graham now | Coverage v5 -> now | Changed items |")
    L.append("|---|---:|---:|---|---:|---:|---|---|")

    def items(j):
        return {(c["id"], i["id"]): (i.get("points"), i.get("state")) for m in ("buffett_quality", "graham_quality") for c in j[m]["criteria"] for i in c["items"]}
    for t in R:
        old = v5.get(t)
        sc = R[t]["sc"]
        nb, ng = sc["buffett_quality"], sc["graham_quality"]
        if not old:
            L.append(f"| {t} | n/a | {f(nb.score, 1)} | | n/a | {f(ng.score, 1)} | | no v5 json |")
            continue
        ob, og = old["buffett_quality"], old["graham_quality"]
        new_items = items({"buffett_quality": model_json(nb), "graham_quality": model_json(ng)})
        diff = [f"{k[0]}.{k[1]}" for k, v in items(old).items() if k in new_items and (round(v[0] or -1, 4), v[1]) != (round(new_items[k][0] or -1, 4), new_items[k][1])]
        L.append(f"| {t} | {f(ob['score'], 1)} | {f(nb.score, 1)} | {pc(ob['coverage'], 0)} -> {pc(nb.coverage, 0)} | {f(og['score'], 1)} | {f(ng.score, 1)} | {pc(og['coverage'], 0)} -> {pc(ng.coverage, 0)} | {', '.join(diff) or 'none'} |")
    d14 = all(not (R[t]["sc"][m].range_error) for t in R for m in ("buffett_quality", "graham_quality"))
    L.append(NL + f"**D14 range check:** {'all model ranges consistent' if d14 else 'RANGE ERRORS'} ({len(R) * 2} models).")
    ip = ROOT / "scripts" / "realestate_rule_issues_pricing_v1.md"
    L.append(NL + "## 5. Open issues and rule questions" + NL)
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(scripts/realestate_rule_issues_pricing_v1.md not written yet)")
    (OUT / "summary_pricing_v1.md").write_text(NL.join(L) + NL, encoding="utf-8")
    print("SEC requests:", sec.requests_made)


if __name__ == "__main__":
    main()

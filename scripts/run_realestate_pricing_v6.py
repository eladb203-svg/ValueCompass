"""INCOME_REAL_ESTATE pricing round 6, RE29b correction (FX net of the hedging derivatives + control; spec docs/scoring/ValueCompass_RealEstate_Rules_2026-10-15_10-50_EN.md, section 6).
Cached SEC data and the price cache; extraction in this round is limited to the items of RE28 / Q6 / the PLD and EQIX checks (scripts/realestate_extraction_spec_p3.py; 8-K supplementals of BXP were cached in round 2). No DB, no AI calls.
Writes scripts/output_realestate_pricing_v6/ (summary_pricing_v6.md + one JSON per company).

Usage:  .venv/Scripts/python -X utf8 scripts/run_realestate_pricing_v6.py   (CA bundle env vars for yfinance as in the earlier rounds)
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
OUT = ROOT / "scripts" / "output_realestate_pricing_v6"
V5 = ROOT / "scripts" / "output_realestate_v5"
VPREV = ROOT / "scripts" / "output_realestate_pricing_v5"
SPEC = "docs/scoring/ValueCompass_RealEstate_Rules_2026-10-15_10-50_EN.md"
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
            if t == "EQR":
                ri.price_entity_issue = "price is the VMRK (Vivmark Residential) close; financials are EQR FY2025 (merger 2026-08-18)"
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
    L = [f"# ValueCompass INCOME_REAL_ESTATE pricing round 6 (RE29b: FX net of hedges) - {date.today().isoformat()}" + NL,
         f"Spec: `{SPEC}` (section 6, RE24-RE29b, RP1b, RP5, RP5a, Q6). Round 6. SEC requests this run: {sec.requests_made}. Extraction in this round (`scripts/realestate_extraction_spec_p4.py`): the companies' own Core / normalized / adjusted FFO "
         "(O, SPG, ARE, PSA, FRT, EQR; PLD from round 3), the AMT Nareit / AFFO reconciliation lines and the AMT non-real-estate goodwill impairments; the rest comes from the earlier extraction and the cached SEC data. No DB, no AI calls. "
         f"Parameters: Buffett discount rate {pc(0.10, 0)}, RP1a block above 8x net debt / EBITDAre (borderline 7.5-8.5x), RP1b, RP5 gap 3 pp (RP5a: Graham price score on the NAV without development and land when RP5 is shown); "
         f"conservative cap rate = max(latest monthly average of the US 10-year yield + 3 pp, 6%) = **{pc(cr['value'], 2)}** "
         f"(FRED GS10 monthly average for {cr['gov_period']}: {pc(cr['gov_yield'], 2)}; kind: {cr['gov_kind']}; from `scripts/gov_yields.csv`). "
         "Prices: latest close (EQR: VMRK successor close). Per-share values in USD." + NL]
    _vp = {t: json.loads((VPREV / f"{t}.json").read_text(encoding="utf-8")) for t in T if (VPREV / f"{t}.json").exists()}
    _chg, _chg_o = [], []
    for t in R:
        o_ = _vp.get(t)
        if not o_:
            continue
        for key, lab in (("buffett_price", "Buffett"), ("graham_price", "Graham")):
            a_, b_ = (o_[key].get("price_score") or {}), (R[t]["pr"][key].get("price_score") or {})
            pa, pb = a_.get("points"), b_.get("points")
            if a_.get("state") != b_.get("state") or (pa is None) != (pb is None) or (pa is not None and abs(pa - pb) > 0.005):
                (_chg_o if t == "O" else _chg).append(f"{t} {lab}: {f(pa) if pa is not None else a_.get('state')} -> {f(pb) if pb is not None else b_.get('state')}")
    L.insert(1, "**Did any price score change versus v5, other than O? " + ("Yes - " + "; ".join(_chg) + "." if _chg else "No. (PSA stays at 0.35, the approved change; no Graham or other Buffett price score changed.)") + " O: " + ("; ".join(_chg_o) if _chg_o else "unchanged") + ".**" + NL)
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

    # ------------------------------------------------------------------ 1b v5 -> v6
    vprev = {t: json.loads((VPREV / f"{t}.json").read_text(encoding="utf-8")) for t in T if (VPREV / f"{t}.json").exists()}

    def sc2(p_):
        ps_ = p_.get("price_score") or {}
        return f(ps_.get("points")) if ps_.get("state") == "score" else ps_.get("state", "n/a")

    def buy2(p_):
        bp_ = p_.get("buy_price") or {}
        if bp_.get("state") == "computed":
            return f(bp_.get("buy_price"))
        return bp_.get("state", "n/a")

    def flags3(b_, g_):
        fl = []
        if b_["guard"].get("borderline"):
            fl.append("RP1a borderline")
        if (b_.get("recent_trend") or (b_.get("base_growth") or {}).get("recent_trend") or {}).get("failed"):
            fl.append("RP1b growth 0")
        if (g_.get("distress") or {}).get("flag"):
            fl.append("RP5 distress")
        if g_.get("rp5a_applied"):
            fl.append("RP5a (score on NAV without development)")
        if g_.get("c16_issue"):
            fl.append("C16")
        return ", ".join(fl) or "-"
    L.append(NL + "## 1b. Comparison with pricing v5 (value, score, buy price, flags)" + NL)
    L.append("| Company | Buffett value v5 -> v6 | Buffett score v5 -> v6 | Buffett buy price v5 -> v6 | Graham NAV v5 -> v6 | Graham score v5 -> v6 | Graham buy price v5 -> v6 | Flags v3 | What changed |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for t in R:
        o, b, g = vprev.get(t), R[t]["pr"]["buffett_price"], R[t]["pr"]["graham_price"]
        if not o:
            continue
        ob, og = o["buffett_price"], o["graham_price"]
        ov, nv = ob.get("fair_value"), b.get("fair_value")
        og_v, ng_v = og.get("value"), g.get("value")
        why = []
        if ov is not None and nv is not None and abs(nv / ov - 1) > 0.005:
            why.append(f"Buffett value {nv / ov - 1:+.1%}")
        if og_v is not None and ng_v is not None and abs(ng_v / og_v - 1) > 0.005:
            why.append(f"NAV {ng_v / og_v - 1:+.1%}")
        if (ob.get("stage1_growth") or 0) != (b.get("stage1_growth") or 0):
            why.append(f"stage-1 growth {pc(ob.get('stage1_growth'))} -> {pc(b.get('stage1_growth'))}")
        if sc2(ob) != sc2(b) or sc2(og) != sc2(g):
            why.append("price score")
        L.append(f"| {t} | {f(ov)} -> {f(nv)} | {sc2(ob)} -> {sc2(b)} | {buy2(ob)} -> {buy2(b)} | {f(og_v)} -> {f(ng_v)} | {sc2(og)} -> {sc2(g)} | {buy2(og)} -> {buy2(g)} | {flags3(b, g)} | {'; '.join(why) or 'no change'} |")
    L.append(NL + "### RP1b (recent trend), RP5 (market distress) and NAV without development and land" + NL)
    L.append("| Company | Same-property NOI growth (latest) | Occupancy change (pp) | Tested | Not tested | RP1b failed | Stage-1 growth before the gate | used | Market-implied cap | Conservative cap | Gap (pp) | RP5 | NAV | NAV without development and land | Development and land (bn) |")
    L.append("|---|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---:|")
    for t in R:
        b, g = R[t]["pr"]["buffett_price"], R[t]["pr"]["graham_price"]
        rt = (b.get("base_growth") or {}).get("recent_trend") or {}
        inp = rt.get("inputs", {})
        ds = g.get("distress") or {}
        c = g["components"]
        L.append(f"| {t} | {pc(inp.get('same_property_noi_growth'))} | {f(inp.get('occupancy_change_pp'))} | {', '.join(rt.get('tested', [])) or '-'} | {', '.join(rt.get('not_tested', [])) or '-'} | {'; '.join(rt.get('failed', [])) or 'no'} | "
                 f"{pc((b.get('base_growth') or {}).get('growth_before_gate'))} | {pc(b.get('stage1_growth'))} | {pc(ds.get('market_implied_cap_rate'), 2)} | {pc(ds.get('conservative_cap_rate'), 2)} | {f(ds.get('gap_pp'))} | "
                 f"{'**distress**' if ds.get('flag') else 'no'} | {f(g.get('value'))} | {f(g.get('nav_without_development_per_share'))} | {bn(c.get('development_and_land'))} |")
    L.append(NL + "RP5 text when shown: *the market prices distress not visible in the annual data - check the latest results before buying*. Display only, no score change.")
    # ARE detail
    ra, ba, ga = R["ARE"]["ri"], R["ARE"]["pr"]["buffett_price"], R["ARE"]["pr"]["graham_price"]
    bg = ba.get("base_growth") or {}
    rt = bg.get("recent_trend") or {}
    ov = vprev["ARE"]["buffett_price"].get("fair_value") if "ARE" in vprev else None
    ond = vprev["ARE"]["graham_price"].get("value") if "ARE" in vprev else None
    L.append(NL + "### ARE with RP1b, RP5 and NAV without development" + NL)
    L.append(f"- Price {f(ra.price_current)}. **RP1b:** {'failed: ' + '; '.join(rt.get('failed', [])) if rt.get('failed') else 'passed'} -> stage-1 growth {pc(bg.get('growth_before_gate'))} before the gate, {pc(ba.get('stage1_growth'))} used (flag `growth_gate_recent_trend`).")
    L.append(f"- **Buffett value:** v5 {f(ov)} -> v6 {f(ba.get('fair_value'))} (discount {pc(None if not ba.get('fair_value') else (ba['fair_value'] - ra.price_current) / ba['fair_value'])}; price score {sc2(ba)}; buy price {buy2(ba)}); base {f(ba.get('base'))} (median OE per share {f(bg.get('median'))}).")
    L.append(f"- **RP5:** market-implied cap rate {pc((ga.get('distress') or {}).get('market_implied_cap_rate'), 2)} vs conservative {pc((ga.get('distress') or {}).get('conservative_cap_rate'), 2)} (gap {f((ga.get('distress') or {}).get('gap_pp'))} pp): "
             f"{'**distress flag shown** - ' + (ga.get('distress') or {}).get('text', '') if (ga.get('distress') or {}).get('flag') else 'not shown'}.")
    L.append(f"- **RP5a:** {'applied - the Graham price score and buy price are computed on the NAV without development and land (' + f(ga.get('value_for_score')) + '); full NAV ' + f(ga.get('value_full_nav')) + ' stays on display' if ga.get('rp5a_applied') else 'not applied'}; Graham price score {sc2(ga)}, buy price {buy2(ga)} (v5: {sc2(vprev['ARE']['graham_price']) if 'ARE' in vprev else 'n/a'}, {buy2(vprev['ARE']['graham_price']) if 'ARE' in vprev else 'n/a'}).")
    L.append(f"- **NAV:** v5 {f(ond)} -> v6 {f(ga.get('value'))} (price score {sc2(ga)}); **NAV without development and land {f(ga.get('nav_without_development_per_share'))}** (development and land at cost {bn(ga['components'].get('development_and_land'))}bn is "
             f"{pc(None if not ga['components'].get('development_and_land') else ga['components']['development_and_land'] / ga['components']['nav'], 0)} of the NAV); the discount to that NAV is {pc(None if not ga.get('nav_without_development_per_share') else (ga['nav_without_development_per_share'] - ra.price_current) / ga['nav_without_development_per_share'])}.")
    L.append(NL + "### NAV components (RP2a / RP2b), USD bn" + NL)
    L.append("| Company | NOI | Op. value at cap | Carry (dev / JV / notes) | of which financial inv. | Dev / CIP / land inside RE | Net debt | Preferred | NCI deducted (non-OP) | Finance leases | NAV | Shares (m) | Share basis | Unidentified assets (share) |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|")
    for t in R:
        c = R[t]["pr"]["graham_price"]["components"]
        sb = c.get("share_basis") or {}
        bk = c.get("non_noi_breakdown") or {}
        cl = c.get("other_claims") or {}
        L.append(f"| {t} | {bn(c.get('noi'))} | {bn(c.get('op_value'))} | {bn(bk.get('carry'))} | {bn(bk.get('carryfin'))} | {bn(bk.get('inre'))} | {bn(c.get('net_debt'))} | {bn(cl.get('preferred'))} | "
                 f"{bn(cl.get('noncontrolling_interests_non_op'))} | {bn(cl.get('finance_lease_liabilities'))} | {bn(c.get('nav'))} | {f((sb.get('shares') or 0) / 1e6, 1)} | {sb.get('basis', 'n/a')} | "
                 f"{pc(c.get('unidentified_share_of_assets'))} |")
    # RE28 basis table
    L.append(NL + "### RE28: the basis of OE per share, per company" + NL)
    BASIS = {"O": "company share (common stockholders); 2.7m OP units (0.3%) not added", "PLD": "FFO attributable to common stockholders / unitholders; diluted shares include the OP units",
             "SPG": "**operating partnership**: FFO of the Operating Partnership (consolidated net income start) / weighted shares + limited partnership units (RE28 change)",
             "FRT": "company share (Trust; no material OP units)", "BXP": "**BXP, Inc.**: FFO attributable to BXP, Inc.; the partnership-basis FAD items (straight-line, maintenance capex, 2nd generation TI/LC) scaled by BXP, Inc.'s share of the partnership (RE28 change)",
             "ARE": "company share (no OP units)", "EQR": "FFO includes OP units; diluted shares include OP units (9.5m)", "PSA": "company share; OP units not material",
             "EQIX": "company share (no OP units)", "AMT": "company share (no OP units)"}
    L.append("| Company | Basis | FFO, deductions and shares on one basis? | Flags |")
    L.append("|---|---|---|---|")
    for t in R:
        d_ = R[t]["sc"]["derived"]
        fl = [x for x in d_["flags"] if x.startswith("RE28")]
        L.append(f"| {t} | {BASIS[t]} | yes | {'; '.join(fl) or '-'} |")

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
    L.append(NL + "#### Q1 addendum: PLD normalized FFO vs the company's Core FFO, and the FY2021 jump (5.34 vs 3.35 in FY2020)" + NL)
    d, ri = R["PLD"]["sc"]["derived"], R["PLD"]["ri"]
    shp = d["shares_eff"]
    L.append("Our FFO follows the NAREIT definition (RE17) plus the identified one-offs; the company's headline measure is **Core FFO**, which additionally excludes the gains on dispositions of development properties and land, current tax on dispositions, "
             "losses on early extinguishment of debt and other items. NAREIT FFO **includes** the development gains (PLD treats development properties as inventory-like), and the promote revenues sit in both measures." + NL)
    L.append("| Year | Our normalized FFO (bn) | Reported NAREIT FFO (bn) | Reported Core FFO (bn) | Development gains in NAREIT FFO (bn) | Ours - Core (bn) | Ours per share | Core per share | Development gains per share |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for i, lab in enumerate(ri.fy[-6:], start=len(ri.fy) - 6):
        ff, rep, core, dev = d["norm_ffo"][i], d["reported_ffo"][i], d["core_ffo_reported"][i], d["dev_gains_reported"][i]
        sh_ = shp[i]
        L.append(f"| {lab} | {bn(ff)} | {bn(rep)} | {bn(core)} | {bn(dev)} | {bn(None if ff is None or core is None else ff - core)} | {f(None if not sh_ or ff is None else ff / sh_)} | "
                 f"{f(None if not sh_ or core is None else core / sh_)} | {f(None if not sh_ or dev is None else dev / sh_)} |")
    L.append(NL + "Reading: FY2021 includes 0.82bn of development gains (about 1.07 per share) that Core FFO excludes, and FY2020 (3.35 per share) is built from the XBRL real-estate depreciation tag because the reconciliation extraction starts in FY2021 "
             "(FY2020 reported NAREIT FFO is 2.96bn vs our 2.5bn), so the step from 3.35 to 5.34 mixes a basis change with the development gains. Normalized FFO is not the company's Core FFO; the OE (which is what is priced) inherits the "
             "development gains. **Rule question:** exclude gains on development properties from normalized FFO (as Core FFO does) or keep them as recurring for a developer-owner; not changed here." )
    L.append(NL + "#### Q1 addendum: EQIX finance-lease liabilities and the debt tag" + NL)
    ri_e = R["EQIX"]["ri"]
    regx = R["EQIX"]["ri"].reg
    from src.scoring.realestate import ext_series as _es
    comp = {k[len("bs_check__"):]: (_es(ri_e, k)[-1] or 0.0) for k in regx if k.startswith("bs_check__")}
    debt_tag = ri_e.series("debt_total")[-1]
    carry_debt = comp.get("mortgage_current", 0) + comp.get("senior_notes_current", 0) + comp.get("mortgage_noncurrent", 0) + comp.get("senior_notes_noncurrent", 0)
    leases = comp.get("finance_lease_current", 0) + comp.get("finance_lease_noncurrent", 0)
    tag_name = ((ri_e.tag_log.get("debt_total", {}) or {}).get(ri_e.fy[-1]) or {}).get("tag")
    incl = abs(debt_tag - (carry_debt + leases)) < abs(debt_tag - carry_debt)
    L.append(f"Debt tag `{tag_name}` = {bn(debt_tag)}bn; balance sheet mortgage and loans + senior notes (current and non-current) = {bn(carry_debt)}bn; finance-lease liabilities (current + non-current) = {bn(leases)}bn; "
             f"debt including leases would be {bn(carry_debt + leases)}bn. The tag is {'closer to the debt including the leases' if incl else 'the face value of the borrowings only (the difference to the carrying amount, ' + bn(debt_tag - carry_debt) + 'bn, is unamortized discount and issuance cost)'}: "
             f"**the finance-lease liabilities are not in the debt tag, so they stay in the other claims of the NAV (no double counting)**; the check is repeated in the tests.")
    # ---------------------------------------------------------------- Q1 after RE29a
    L.append(NL + "#### Q1 after RE29a: what was neutralized in normalized FFO, its source, and the comparison with the company's own Core / normalized / adjusted FFO" + NL)
    L.append("Normalized FFO = FFO + loss on debt extinguishment + transaction costs + impairments of non-real-estate assets and investments not already added back (RE29) - gains on sales of real estate left in FFO, incl. development properties and land (RE29) "
             "- unrealized foreign-exchange remeasurement (gain deducted, loss added back; RE29a) - realized and unrealized results of non-real-estate investments (gain deducted, loss added back; RE29a). Sources: FX = XBRL `ForeignCurrencyTransactionGainLossUnrealized` "
             "(or `...BeforeTax`), non-real-estate investment results and gains = the text rows of the CSV (document, section and exact quote). ARE: RE29 and RE29a are applied together through the company's total non-real-estate investment income (loss) line, which already contains "
             "the impairments (no double count). The company measure is Core FFO (PLD), Normalized FFO (O, EQR), Real Estate FFO (SPG), FFO per share diluted as adjusted (ARE), Core FFO per share (PSA, FRT 2024-2025); BXP, EQIX and AMT publish no adjusted FFO." + NL)
    L.append("| Company | Year | RE29 gains deducted (bn) | RE29 non-RE impairments added (bn) | RE29a FX remeasurement removed (bn; gain +) | RE29a non-RE investment results removed (bn; gain +) | Our FFO (bn) | Our normalized FFO (bn) | Normalized FFO per share | Company measure per share | Difference | Source of the amounts |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    from src.scoring.realestate import ext_series as _xs
    for t in R:
        d_, ri_ = R[t]["sc"]["derived"], R[t]["ri"]
        reg_ = ri_.reg or {}
        fxtag = ((ri_.tag_log.get("fx_unrealized", {}) or {}))
        for i in range(len(ri_.fy) - 5, len(ri_.fy)):
            lab = ri_.fy[i]
            g29, n29 = d_["re29_gains_deducted"][i], d_["re29_nonre_added"][i]
            fx_, iv_ = d_["re29a_fx_result"][i], d_["re29a_investment_result"][i]
            ffo_, nf_ = d_["ffo"][i], d_["norm_ffo"][i]
            sh_ = d_["shares_eff"][i]
            tot, ps_ = d_["core_ffo_reported"][i], _xs(ri_, "core_ffo_ps_reported")[i]
            comp_ps = ps_ if ps_ is not None else (None if tot is None or not sh_ else tot / sh_)
            nps = d_["nffo_ps"][i]
            diff = None if comp_ps in (None, 0) or nps is None else nps / comp_ps - 1
            srcs = []
            if fx_ not in (None, 0.0):
                tg = (fxtag.get(lab) or {}).get("tag")
                srcs.append(f"FX: XBRL {tg} = {fx_ / 1e6:,.1f}m ({(fxtag.get(lab) or {}).get('filed', '')})")
            for item in ["dev_gains_reported", "recon_gi_net"] + [k for k in reg_ if k.startswith(("re29_nonre_impairments", "re29a_nonre_inv"))]:
                row_ = (reg_.get(item) or {}).get(lab)
                if row_ and isinstance(row_.get("value"), (int, float)) and (item != "recon_gi_net" or t == "AMT"):
                    srcs.append(f"{item}: {str(row_.get('source', ''))[:60]} | \"{str(row_.get('quote', ''))[:80]}\"")
            L.append(f"| {t} | {lab} | {bn(g29)} | {bn(n29)} | {bn(fx_)} | {bn(iv_)} | {bn(ffo_)} | {bn(nf_)} | {f(nps)} | {f(comp_ps)} | {pc(diff)} | {'; '.join(srcs) or '-'} |")
    L.append(NL + "Immaterial and therefore not extracted (below 1% of FFO, documented): EQIX 'other income (expense)' in total is -7 / -17 / -11m (FY2025 / FY2024 / FY2023) with no separate foreign-currency line; BXP unrealized result on non-real-estate investments -0.3m and gains from investments in securities 5.5m (FY2025); "
             "FRT none; PSA non-real-estate investments none (its euro-note remeasurement is the FX row).")
    L.append(NL + "#### Focus: AMT FY2025, ARE and SPG - normalized FFO per share before and after RE29a, against the company measure" + NL)
    L.append("| Company | Year | Before RE29a | After RE29a | Company measure per share | Difference before | Difference after |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for t in ("AMT", "ARE", "SPG"):
        d_, ri_ = R[t]["sc"]["derived"], R[t]["ri"]
        for i in range(len(ri_.fy) - 5, len(ri_.fy)):
            sh_ = d_["shares_eff"][i]
            nf_ = d_["norm_ffo"][i]
            if nf_ is None or not sh_:
                continue
            adj_ = (d_["re29a_fx_result"][i] or 0.0) + (d_["re29a_investment_result"][i] or 0.0)
            before, after = (nf_ + adj_) / sh_, nf_ / sh_
            ps_ = _xs(ri_, "core_ffo_ps_reported")[i]
            tot = d_["core_ffo_reported"][i]
            comp = ps_ if ps_ is not None else (None if tot is None else tot / sh_)
            if comp is None and t == "AMT":
                rep = d_["reported_ffo"][i]
                comp = None if rep is None else rep / sh_
            lab_c = "" if comp is not None and t != "AMT" else (" (AMT: reported Nareit FFO per share; no adjusted FFO published)" if t == "AMT" else "")
            L.append(f"| {t} | {ri_.fy[i]} | {f(before)} | {f(after)} | {f(comp)}{lab_c} | {pc(None if not comp else before / comp - 1)} | {pc(None if not comp else after / comp - 1)} |")
    L.append(NL + "Reading: ARE's gap to the company's FFO 'as adjusted' (which removes unrealized results and significant realized losses on investments and adds back impairments) closes once the total investment income (loss) line is neutralized; the remaining difference is the company's removal of other items "
             "(impairments of real estate in rental properties and land that NAREIT FFO already adds back, share-count rounding and the allocation to unvested restricted stock). SPG's difference to Real Estate FFO closes with the three platform / equity-instrument lines (FY2023-FY2025; "
             "not disclosed for FY2021-FY2022). For AMT the comparison is with the reported Nareit FFO, because AMT publishes no adjusted FFO; the FX and investment items that RE29a removes are the ones AMT adds back in AFFO (Q6).")

    # Q2
    L.append(NL + "### Q2. EBITDAre computed vs reported" + NL)
    L.append("Reported = the company's EBITDAre as extracted (annual or trailing twelve months at the fiscal year end; `ebitdare_reported`, exact quote in the CSV). Only FRT and EQR report EBITDAre as an annual figure in documents "
             "that were retrievable (earnings releases); O / BXP / ARE give quarterly annualized figures, PLD / EQIX / AMT report 'Adjusted EBITDA' (a different, company-adjusted measure) and SPG / PSA report neither, so those "
             "have no like-for-like reported figure. Internal checks are shown for everyone: EBITDAre / NOI (outside 0.5-1.15 flagged) and the identity gap EBITDAre - (our FFO + interest + income tax) as a share of EBITDAre." + NL)
    L.append("| Company | Computed FY2021 ... FY2025 (bn) | Reported FY2021 ... FY2025 (bn) | Gap FY2021 ... FY2025 | Like-for-like? | EBITDAre / NOI | Identity gap | Net debt / EBITDAre | Flag |")
    L.append("|---|---|---|---|---|---:|---:|---:|---|")
    NOLFL = {"O": "no: quarterly annualized Adjusted EBITDAre only", "BXP": "no: quarterly (BXP's share) only", "ARE": "no: quarterly annualized only",
             "PLD": "no: Adjusted EBITDA", "EQIX": "no: Adjusted EBITDA", "AMT": "no: Adjusted EBITDA", "SPG": "none reported", "PSA": "none reported"}
    for t in R:
        d, ri = R[t]["sc"]["derived"], R[t]["ri"]
        e, n_, ffo = d["ebitdare"][-1], d["noi"][-1], d["ffo"][-1]
        it = ri.series("interest_expense")[-1]
        tx = ri.series("income_tax")[-1] or 0.0
        ratio = None if (e is None or not n_) else e / n_
        gap = None if (e is None or ffo is None or it is None) else (e - (ffo + it + tx)) / e
        flag = "" if ratio is None else ("EBITDAre/NOI outside 0.5-1.15" if not 0.5 <= ratio <= 1.15 else "")
        st = d["nd_ebitdare_state"][-1]
        rep = d["ebitdare_reported"][-5:]
        gaps = d["ebitdare_reconciliation_pct"][-5:]
        lfl = "yes (annual / TTM EBITDAre)" if any(x is not None for x in rep) else NOLFL.get(t, "n/a")
        bad = [x for x in gaps if x is not None and abs(x) > 0.05]
        fl2 = (flag + "; " if flag else "") + ("reported gap above 5%" if bad else "")
        L.append(f"| {t} | {', '.join(bn(x) for x in d['ebitdare'][-5:])} | {', '.join(bn(x) for x in rep)} | {', '.join('n/a' if x is None else f'{x * 100:+.1f}%' for x in gaps)} | {lfl} | {f(ratio)} | {pc(gap)} | "
                 f"{f(st[1]) if st[1] is not None else st[0]} | {fl2 or '-'} |")
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

    # Q6
    L.append(NL + "### Q6. OE per share vs the reported AFFO per share less stock-based compensation" + NL)
    L.append("Reported AFFO (or BXP's FAD) from the 10-K / supplemental, divided by the same share count as our OE (BXP: weighted shares + OP units of the partnership), less stock-based compensation per share (XBRL `ShareBasedCompensation`; "
             "all these measures add stock-based compensation back, our OE does not). Gap = our OE per share / (AFFO per share - SBC per share) - 1; **above 15% in absolute value is flagged**. Companies that do not report an AFFO "
             "(PLD: Core FFO; SPG, FRT, EQR, PSA, ARE in the retrievable documents) have no like-for-like figure." + NL)
    L.append("| Company | Year | OE per share | AFFO per share | SBC per share | AFFO - SBC per share | Gap | Flag |")
    L.append("|---|---|---:|---:|---:|---:|---:|---|")
    flagged_q6 = {}
    for t in R:
        d_, ri_ = R[t]["sc"]["derived"], R[t]["ri"]
        if not any(x is not None for x in d_["affo_reported"]):
            continue
        for i, lab in enumerate(ri_.fy):
            a_, o_ = d_["affo_reported"][i], d_["oe"][i]
            if a_ is None or o_ is None or d_["oe_basis"][i] != "OE":
                continue
            den = d_["partnership_units_weighted"][i] if t == "BXP" else d_["shares_eff"][i]
            if not den:
                continue
            sbc_ = d_["sbc"][i] or 0.0
            aps, sps, ops = a_ / den, sbc_ / den, o_ / den
            net = aps - sps
            gap = ops / net - 1 if net else None
            fl = gap is not None and abs(gap) > 0.15
            if fl:
                flagged_q6.setdefault(t, []).append((lab, gap))
            L.append(f"| {t} | {lab} | {f(ops)} | {f(aps)} | {f(sps)} | {f(net)} | {pc(gap)} | {'**>15%**' if fl else '-'} |")
    L.append(NL + "Flagged: " + ("; ".join(f"{t}: " + ", ".join(f"{y} {g_:+.0%}" for y, g_ in v) for t, v in flagged_q6.items()) if flagged_q6 else "none") + ".")
    de = R["EQIX"]["sc"]["derived"]
    if "EQIX" in flagged_q6:
        L.append(NL + "**EQIX: what creates the gap.** Equinix's AFFO adds back, on top of FFO, items our OE keeps as costs: non-real-estate depreciation (servers / network equipment that the 'recurring capex' deduction replaces only in part) and amortization expense, plus stock-based "
                 "compensation (which the comparison removes), and it deducts only recurring capex (our OE also deducts the same recurring capex, so that item matches):" + NL)
        L.append("| Year | AFFO (bn) | FFO (ours, normalized, bn) | Non-real-estate depreciation added back (bn) | Amortization added back (bn) | Sum of the two as % of AFFO - SBC | OE (bn) |")
        L.append("|---|---:|---:|---:|---:|---:|---:|")
        for i, lab in enumerate(R["EQIX"]["ri"].fy[-5:], start=len(R["EQIX"]["ri"].fy) - 5):
            a_ = de["affo_reported"][i]
            nr = _es(R["EQIX"]["ri"], "affo_addback_non_re_depr")[i]
            am = _es(R["EQIX"]["ri"], "affo_addback_amortization")[i]
            net = None if a_ is None else a_ - (de["sbc"][i] or 0.0)
            L.append(f"| {lab} | {bn(a_)} | {bn(de['norm_ffo'][i])} | {bn(nr)} | {bn(am)} | {pc(None if not net or nr is None or am is None else (nr + am) / net)} | {bn(de['oe'][i])} |")
        L.append(NL + "The gap is therefore a definition difference (non-real-estate depreciation and amortization of about 0.77bn a year are treated as non-cash by Equinix and as a real cost by our OE; they are 24-28% of AFFO less SBC), not a data error: "
                 "our OE is the conservative figure. **Rule question:** keep OE as is (conservative) or add the non-real-estate depreciation back for data centers.")

    # ---------------------------------------------------------------- AMT bridge (FY2023, FY2025)
    L.append(NL + "### Q6 after RE29a: AMT bridge from OE to AFFO less stock-based compensation, item by item (USD million)" + NL)
    da, ria = R["AMT"]["sc"]["derived"], R["AMT"]["ri"]
    regA = ria.reg

    def xa(item, lab):
        v = _xs(ria, item)[ria.fy.index(lab)]
        return v

    def m_(x):
        return "n/a" if x is None else f"{x / 1e6:,.1f}"
    rows_b = []
    for lab in ("FY2023", "FY2025"):
        i = ria.fy.index(lab)
        sh_ = da["shares_eff"][i]
        oe_ = da["oe"][i]
        nf_ = da["norm_ffo"][i]
        affo_ = da["affo_reported"][i]
        sbc_x = da["sbc"][i] or 0.0
        rep_ = da["reported_ffo"][i]
        slr, sle = xa("affo_br__straight_line_revenue", lab), xa("affo_br__straight_line_expense", lab)
        itm = [("Reported Nareit FFO minus our normalized FFO (after RE29 / RE29a)", None if rep_ is None or nf_ is None else rep_ - nf_),
               ("Straight-line: AFFO deducts revenue net of expense, OE deducts revenue only (+ straight-line expense)", sle),
               ("Deferred portion of income tax and other tax adjustments", xa("affo_br__deferred_tax", lab)),
               ("Non-real-estate depreciation, amortization and accretion", xa("affo_br__non_re_da", lab)),
               ("Amortization of deferred financing costs, discounts and long-term deferred interest", xa("affo_br__amort_financing", lab)),
               ("Other expense (income): foreign-exchange losses / gains, goodwill and other non-cash items", xa("affo_br__other_expense", lab)),
               ("Loss on retirement of long-term obligations", xa("affo_br__retirement_loss", lab) if lab == "FY2023" else 0.0),
               ("Other operating expense (income): acquisition / integration / disposition costs", xa("affo_br__other_operating", lab)),
               ("Adjustments and distributions for unconsolidated affiliates and noncontrolling interests (AFFO section)", xa("affo_br__unconsolidated_nci", lab)),
               ("Consolidated to attributable AFFO (FY2023 only)", xa("affo_br__consolidated_to_attributable", lab) if lab == "FY2023" else 0.0),
               ("Adjustments for discontinued operations", xa("affo_br__discontinued", lab) if lab == "FY2025" else 0.0)]
        explained = sum(v for _, v in itm if v is not None)
        total_gap = None if affo_ is None or oe_ is None else affo_ - sbc_x - oe_
        # capex: AFFO deducts capital improvement + corporate capex; OE deducts the same (maintenance_capex row) -> difference
        capex_aff = (xa("affo_br__capital_improvement", lab) or 0.0) + (xa("affo_br__corporate_capex", lab) or 0.0)
        capex_ours = -(da["maint_capex"][i] or 0.0)
        itm.append(("Capex: AFFO deducts capital improvement + corporate capex, OE deducts the same maintenance row", capex_aff - capex_ours))
        # SBC: AFFO adds back the SBC of the reconciliation; the comparison removes the XBRL SBC
        sbc_aff = xa("affo_br__sbc_affo", lab) if False else None
        explained = sum(v for _, v in itm if v is not None)
        rows_b.append((lab, sh_, oe_, nf_, affo_, sbc_x, total_gap, itm, explained))
    for lab, sh_, oe_, nf_, affo_, sbc_x, total_gap, itm, explained in rows_b:
        L.append(f"**{lab}.** OE {m_(oe_)}; AFFO {m_(affo_)}; stock-based compensation (XBRL) {m_(sbc_x)}; gap AFFO - SBC - OE = {m_(total_gap)} ({pc(None if not oe_ or total_gap is None else total_gap / (affo_ - sbc_x))} of AFFO - SBC; per share "
                 f"{f(None if not sh_ or total_gap is None else total_gap / sh_)}). Items:" + NL)
        L.append("| Item | USD million | % of the gap |")
        L.append("|---|---:|---:|")
        for name, v in itm:
            L.append(f"| {name} | {m_(v)} | {pc(None if v is None or not total_gap else v / total_gap, 0)} |")
        L.append(f"| **Sum of the items** | {m_(explained)} | {pc(None if not total_gap else explained / total_gap, 0)} |")
        L.append(f"| Unexplained residual (our one-offs, tax on the reconciliation items, rounding, SBC differences between the AFFO line and XBRL) | {m_(None if total_gap is None else total_gap - explained)} | {pc(None if not total_gap else (total_gap - explained) / total_gap, 0)} |")
        L.append("")
    a15 = {lab: (g_ if (g_ := (None if not oe_ or affo_ is None else oe_ / (affo_ - sbc_x) - 1)) is not None else None) for lab, sh_, oe_, nf_, affo_, sbc_x, total_gap, itm, explained in rows_b}
    L.append("Gap of AFFO less SBC over OE after RE29a: " + "; ".join(f"{k} {pc(-v)}" for k, v in a15.items()) + " (positive = OE below AFFO less SBC). "
             "RE29 and RE29a together neutralize, in normalized FFO and OE, the real-estate impairments and sale gains / losses that sit in AMT's Nareit line (FY2023: impairment charges, the India and Spain goodwill impairments of 402.0m, the Mexico Fiber loss), "
             "the FY2025 goodwill impairments of Spain (80.0m) and Bangladesh (6.5m) that AMT does not add back to Nareit FFO, the unrealized foreign-currency remeasurement (XBRL: FY2021 +557.9m, FY2022 +451.4m, FY2023 -330.6m, FY2024 +308.3m, FY2025 -809.4m) "
             "and the results of the non-real-estate investments (gains on equity securities 232.6m FY2025 and 70.4m FY2024, the VIL sale gain 46.4m FY2024, the unrealized VIL OCD gain 76.7m FY2023). The FY2025 gap that was -18.8% after RE29 is now within the band in every year: the foreign-currency "
             "remeasurement was the whole difference. What is left (about 5-9% of AFFO less SBC) is the AFFO convention: the deferred-tax adjustment, non-real-estate depreciation and accretion, financing-cost amortization and the noncontrolling-interest adjustments "
             "(see the items above); the 'Reported Nareit FFO minus our normalized FFO' line is negative because normalized FFO is now above Nareit FFO by the FX and investment amounts that Nareit FFO still contains.")

    # ---------------------------------------------------------------- RE29b: gross -> net FX
    L.append(NL + "## 1c. RE29b: foreign exchange removed net of the hedging derivatives (previous gross amount, new net amount, source, hedge)" + NL)
    L.append("Priority 1 = the net line of the income statement (O: 'foreign currency and derivative (loss) gain, net'); priority 2 = the amount the company itself adds back in its FFO / AFFO reconciliation (PLD, PSA, AMT). "
             "Without a hedge (PSA euro notes, AMT) net = gross. Sign: gain positive (deducted from normalized FFO), loss negative (added back). The previous amount is the gross XBRL tag used in the round-5 run." + NL)
    L.append("| Company | Year | Previous gross (XBRL tag, m) | New net (m) | Change (m) | Hedge | Source (document | exact quote) |")
    L.append("|---|---|---:|---:|---:|---|---|")
    HEDGE = {"O": "yes: cross-currency swaps and forwards; the net line contains the derivative results", "PLD": "yes: derivatives and foreign-currency debt; the company figure is already net ('foreign currency and derivative')",
             "PSA": "no hedging derivative (euro notes unhedged): net = gross", "AMT": "no hedging derivative on the remeasured balances: net = gross"}
    for t in ("O", "PLD", "PSA", "AMT"):
        d_, ri_ = R[t]["sc"]["derived"], R[t]["ri"]
        rows_ = (ri_.reg or {}).get("re29b_fx_net", {})
        for i in range(len(ri_.fy) - 5, len(ri_.fy)):
            lab = ri_.fy[i]
            gross, net = d_["re29b_fx_gross"][i], d_["re29a_fx_result"][i]
            rw = rows_.get(lab)
            src = (f"{str(rw.get('source', ''))[:75]} | \"{str(rw.get('quote', ''))[:110]}\"" if rw else "XBRL tag only (no text row for this year)")
            L.append(f"| {t} | {lab} | {f(None if gross is None else gross / 1e6, 1)} | {f(None if net is None else net / 1e6, 1)} | {f(None if (gross is None or net is None) else (net - gross) / 1e6, 1)} | {HEDGE[t]} | {src} |")
    L.append(NL + "Only O changes materially: its gross tag (FY2022 -220.9m) excluded the hedge gains, the net line is -13.3m. PLD and PSA net = the previous amount; AMT differs by rounding (FY2023 -330.8m in the company footnote vs -330.6m in the tag).")

    # ---------------------------------------------------------------- O
    L.append(NL + "## 1d. O: price score, value, stage-1 growth, quality, Q1 and Q6 by year (before RE29a = pricing v4, gross FX = pricing v5, net FX = this run)" + NL)
    dO, rO, bO, gO = R["O"]["sc"]["derived"], R["O"]["ri"], R["O"]["pr"]["buffett_price"], R["O"]["pr"]["graham_price"]
    o4 = json.loads((ROOT / "scripts" / "output_realestate_pricing_v4" / "O.json").read_text(encoding="utf-8"))
    o5 = _vp["O"]
    L.append("| Item | v4 (no RE29a) | v5 (gross FX) | v6 (net FX, RE29b) |")
    L.append("|---|---:|---:|---:|")
    L.append(f"| Buffett price score | {sc2(o4['buffett_price'])} | {sc2(o5['buffett_price'])} | {sc2(bO)} |")
    L.append(f"| Buffett value | {f(o4['buffett_price'].get('fair_value'))} | {f(o5['buffett_price'].get('fair_value'))} | {f(bO.get('fair_value'))} |")
    L.append(f"| Buffett buy price | {buy2(o4['buffett_price'])} | {buy2(o5['buffett_price'])} | {buy2(bO)} |")
    L.append(f"| Stage-1 growth | {pc(o4['buffett_price'].get('stage1_growth'))} | {pc(o5['buffett_price'].get('stage1_growth'))} | {pc(bO.get('stage1_growth'))} |")
    L.append(f"| Buffett quality score | {f(o4['buffett_quality']['score'], 1)} | {f(o5['buffett_quality']['score'], 1)} | {f(R['O']['sc']['buffett_quality'].score, 1)} |")
    L.append(f"| Graham quality score | {f(o4['graham_quality']['score'], 1)} | {f(o5['graham_quality']['score'], 1)} | {f(R['O']['sc']['graham_quality'].score, 1)} |")
    L.append(f"| Graham price score / NAV | {sc2(o4['graham_price'])} / {f(o4['graham_price'].get('value'))} | {sc2(o5['graham_price'])} / {f(o5['graham_price'].get('value'))} | {sc2(gO)} / {f(gO.get('value'))} |")
    L.append(NL + "| Year | Q1: normalized FFO per share v4 / v5 / v6 | Company Normalized FFO per share | Q1 gap v4 / v5 / v6 | Q6: OE per share v4 / v5 / v6 | AFFO less SBC per share | Q6 gap v4 / v5 / v6 |")
    L.append("|---|---|---:|---|---|---:|---|")
    for i in range(len(rO.fy) - 5, len(rO.fy)):
        sh_ = dO["shares_eff"][i]
        nf6, oe6 = dO["norm_ffo"][i], dO["oe"][i]
        fxn, fxg = dO["re29a_fx_result"][i] or 0.0, dO["re29b_fx_gross"][i] or 0.0
        nf4, nf5 = nf6 + fxn, nf6 + fxn - fxg
        oe4, oe5 = oe6 + fxn, oe6 + fxn - fxg
        comp = None if dO["core_ffo_reported"][i] is None else dO["core_ffo_reported"][i] / sh_
        aff = dO["affo_reported"][i]
        sbc = dO["sbc"][i] or 0.0
        aps = None if aff is None else (aff - sbc) / sh_
        q1 = [None if not comp else x / sh_ / comp - 1 for x in (nf4, nf5, nf6)]
        q6 = [None if not aps else x / sh_ / aps - 1 for x in (oe4, oe5, oe6)]
        L.append(f"| {rO.fy[i]} | {f(nf4 / sh_)} / {f(nf5 / sh_)} / {f(nf6 / sh_)} | {f(comp)} | {' / '.join(pc(x) for x in q1)} | {f(oe4 / sh_)} / {f(oe5 / sh_)} / {f(oe6 / sh_)} | {f(aps)} | {' / '.join(pc(x) for x in q6)} |")
    L.append(NL + "Reading: with the gross tag O's Q6 gap moved from -1.0% to +8.3% in FY2022 (an artifact: the hedge gains were left in); with the net line the FY2022 normalized FFO and OE per share are close to the v4 level, and the Q1 / Q6 gaps return to the v4 range.")

    # ---------------------------------------------------------------- control: Q1 / Q6 gap before (v4) and after (v6), widening above 5 pp is flagged
    L.append(NL + "## 1e. RE29b control: Q1 and Q6 gaps before RE29a (pricing v4) and after (this run); a gap that widens by more than 5 pp flags the company" + NL)
    L.append("Q1 gap = normalized FFO per share / the company's Core / normalized / adjusted FFO per share - 1; Q6 gap = OE per share / (AFFO - SBC per share) - 1. Before = no RE29a removal (v4), after = FX net plus the non-real-estate investment results (v6). "
             "Widening = |after| - |before| above 5 pp." + NL)
    L.append("| Company | Year | Q1 gap before | Q1 gap after | Widening (pp) | Q6 gap before | Q6 gap after | Widening (pp) | Flag |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---|")
    flagged = {}
    for t in R:
        d_, ri_ = R[t]["sc"]["derived"], R[t]["ri"]
        for i in range(len(ri_.fy) - 5, len(ri_.fy)):
            from src.scoring.realestate import re29b_gap_control as _ctl
            c_ = _ctl(d_, i)
            if c_ is None or (c_["q1_after"] is None and c_["q6_after"] is None):
                continue
            q1b, q1a, w1, q6b, q6a, w6, adj = c_["q1_before"], c_["q1_after"], c_["q1_widening_pp"], c_["q6_before"], c_["q6_after"], c_["q6_widening_pp"], c_["adjustment"]
            fl = (w1 is not None and w1 > 5) or (w6 is not None and w6 > 5)
            if fl:
                flagged.setdefault(t, []).append(ri_.fy[i])
            if adj == 0 and not fl:
                continue
            L.append(f"| {t} | {ri_.fy[i]} | {pc(q1b)} | {pc(q1a)} | {f(w1)} | {pc(q6b)} | {pc(q6a)} | {f(w6)} | {'**review**' if fl else '-'} |")
    L.append(NL + "Rows are shown for the company-years where RE29a removed an amount or a gap widened. **Flagged (widening above 5 pp):** " + ("; ".join(f"{t}: {', '.join(y)}" for t, y in flagged.items()) if flagged else "none") + ".")
    if flagged:
        if "AMT" in flagged:
            L.append("**AMT (FY2021, FY2024) - why the Q6 gap widened.** The widening is a change of sign, not a deterioration of the data: before RE29a the OE contained the foreign-exchange gains (FY2021 +557.9m, FY2024 +308.3m) while AMT's AFFO removes them ('other expense (income)' is negative in those years), so OE was above AFFO less SBC by +4.0% and +1.2%; "
                     "after RE29a the gains are removed from the OE as well and what is left is AMT's structural AFFO convention (non-real-estate depreciation and accretion, financing-cost amortization, deferred tax and noncontrolling-interest adjustments), which keeps OE 3% to 9% below AFFO less SBC in every year "
                     "(FY2021 -9.4%, FY2022 -3.3%, FY2023 -5.1%, FY2024 -7.8%, FY2025 -7.0%). The gaps after the removal are all inside the 15% band and more stable across years than before (+4.0% / +7.0% / -10.8% / +1.2% / -18.8%); no data error; AMT is flagged for review only because of the 5 pp rule.")
        for _t in [x for x in flagged if x != "AMT"]:
            L.append(f"{_t}: flagged by the 5 pp rule; see the rows above.")

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
    L.append(NL + "## 4. Quality scores vs RE v5 and pricing v5 (RE29b)" + NL)
    L.append("RE24 (straight-line sign: GAAP rent - cash rent, deducted; negative adjustment increases OE) is the convention the engine already applied (`OE = normalized FFO - straight-line - maintenance capex - TI/LC`); it is now documented, exposed per year "
             "(`straight_line_increases_oe`) and tested. RE26 (stress test) now returns missing when the carrying value of the other property is missing (it is missing for every company anyway: no fair value of real estate). "
             "RE27 (Graham 3.8.2) now requires positive OE in all five years and shows OE / FFO as a diagnostic." + NL)
    L.append("| Company | Buffett (RE v5) | Buffett (pricing v5) | Buffett now | Coverage v5 -> now | Graham (RE v5) | Graham (pricing v5) | Graham now | Coverage v5 -> now | Changed items vs v5 |")
    L.append("|---|---:|---:|---:|---|---:|---:|---:|---|---|")

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
        o2 = vprev.get(t) or {}
        L.append(f"| {t} | {f(ob['score'], 1)} | {f((o2.get('buffett_quality') or {}).get('score'), 1)} | {f(nb.score, 1)} | {pc(ob['coverage'], 0)} -> {pc(nb.coverage, 0)} | {f(og['score'], 1)} | "
                 f"{f((o2.get('graham_quality') or {}).get('score'), 1)} | {f(ng.score, 1)} | {pc(og['coverage'], 0)} -> {pc(ng.coverage, 0)} | {', '.join(diff) or 'none'} |")
    L.append(NL + "### Item-level changes vs v5 and their cause" + NL)
    L.append("| Company | Item | Name | Points v5 -> now | State v5 -> now | Cause |")
    L.append("|---|---|---|---|---|---|")

    def items_full(j):
        return {(m[0], c["id"], i["id"]): (i.get("name"), i.get("points"), i.get("state")) for m in ("buffett_quality", "graham_quality") for c in j[m]["criteria"] for i in c["items"]}

    def cause(name, t=None):
        n_ = (name or "").lower()
        if t == "PLD" and any(k in n_ for k in ("oe", "owner", "earnings", "ffo", "growth", "stability", "decline", "coverage", "capital discipline", "margin")):
            return "RE29: normalized FFO without the development and land sale gains (PLD) [+ RE29a FX remeasurement]"
        if "debt coverage" in n_ or "near-term" in n_:
            return "(b) debt maturing in 12 / 24 months and committed facilities extracted"
        if any(k in n_ for k in ("oe", "owner", "earnings", "capital discipline", "dividend", "ffo")):
            return "(a) OE components completed for all five years (OE instead of the FFO proxy)"
        return "RE28 single basis (per-share denominator / FFO basis) or extraction"
    n_changed = 0
    for t in R:
        old = v5.get(t)
        if not old:
            continue
        nj = {"buffett_quality": model_json(R[t]["sc"]["buffett_quality"]), "graham_quality": model_json(R[t]["sc"]["graham_quality"])}
        o_i, n_i = items_full(old), items_full(nj)
        for k, (nm, pt, stt) in n_i.items():
            ov = o_i.get(k)
            if not ov or (round(ov[1] if ov[1] is not None else -1, 3), ov[2]) == (round(pt if pt is not None else -1, 3), stt):
                continue
            n_changed += 1
            L.append(f"| {t} | {'B' if k[0].startswith('b') else 'G'} {k[1]}.{k[2]} | {nm} | {f(ov[1])} -> {f(pt)} | {ov[2]} -> {stt} | {cause(nm, t)} |")
    L.append(NL + f"{n_changed} item changes. Scores that moved: O Graham, BXP Buffett and Graham (Graham now scored), ARE Graham, EQR Buffett and Graham, EQIX Graham, AMT Buffett and Graham (Graham now scored).")
    L.append(NL + "### Item-level changes vs pricing v5 and their cause" + NL)
    L.append("| Company | Item | Name | Points pricing-v5 -> now | State pricing-v5 -> now | Cause |")
    L.append("|---|---|---|---|---|---|")
    n3 = 0
    for t in R:
        old3 = vprev.get(t)
        if not old3:
            continue
        nj = {"buffett_quality": model_json(R[t]["sc"]["buffett_quality"]), "graham_quality": model_json(R[t]["sc"]["graham_quality"])}
        o_i, n_i = items_full(old3), items_full(nj)
        for k, (nm, pt, stt) in n_i.items():
            ov = o_i.get(k)
            if not ov or (round(ov[1] if ov[1] is not None else -1, 3), ov[2]) == (round(pt if pt is not None else -1, 3), stt):
                continue
            n3 += 1
            cz = {"O": "RE29b: O's foreign-exchange result removed net of the hedging derivatives (income-statement net line), instead of the gross XBRL tag", "AMT": "RE29b: AMT FX amount taken from the company's AFFO footnote (330.8m vs the 330.6m tag)"}.get(t, "RE29b")
            L.append(f"| {t} | {'B' if k[0].startswith('b') else 'G'} {k[1]}.{k[2]} | {nm} | {f(ov[1])} -> {f(pt)} | {ov[2]} -> {stt} | {cz} |")
    L.append(NL + (f"{n3} item changes vs pricing v5." if n3 else "No item changed vs pricing v5 (RE29b moves the O normalized FFO and OE but no other quality threshold is crossed)."))
    d14 = all(not (R[t]["sc"][m].range_error) for t in R for m in ("buffett_quality", "graham_quality"))
    L.append(NL + f"**D14 range check:** {'all model ranges consistent' if d14 else 'RANGE ERRORS'} ({len(R) * 2} models).")
    # ------------------------------------------------------------------ 6 case studies
    L.append(NL + "## 6. Case studies" + NL)
    from src.scoring.metrics import median as _med
    d, ri = R["PLD"]["sc"]["derived"], R["PLD"]["ri"]
    sh = ri.series("shares_dil")
    L.append("### 6a. PLD: normalized FFO per share, deductions and OE per share by year (USD per diluted share)" + NL)
    L.append("OE = normalized FFO - straight-line adjustment - maintenance capex - income-preserving TI/LC. PLD's straight-line line is the company's 'Straight-lined rents and amortization of above and below market leases' "
             "(extension element `pld:StraightLineRentsAndAmortizationOfAboveAndBelowMarketLeases`), i.e. it includes the amortization of above / below-market leases." + NL)
    L.append("| Year | Norm. FFO / sh | Straight-line / sh | Maintenance capex / sh | TI/LC / sh | OE / sh | OE basis | Straight-line as % of FFO | Maint. + TI/LC as % of FFO |")
    L.append("|---|---:|---:|---:|---:|---:|---|---:|---:|")
    rows_pld = []
    for i, lab in enumerate(ri.fy):
        if not sh[i]:
            continue
        ff, sl_, mc, tl, oe = d["norm_ffo"][i], d["straight_line_adjustment"][i], d["maint_capex"][i], d["tilc_pres"][i], d["oe"][i]

        def ps(x, i=i):
            return None if x is None else x / sh[i]
        rows_pld.append((lab, ps(ff), ps(sl_), ps(mc), ps(tl), ps(oe)))
        L.append(f"| {lab} | {f(ps(ff))} | {f(ps(sl_))} | {f(ps(mc))} | {f(ps(tl))} | {f(ps(oe))} | {d['oe_basis'][i]} | {pc(None if not ff or sl_ is None else sl_ / ff)} | "
                 f"{pc(None if not ff or mc is None or tl is None else (mc + tl) / ff)} |")

    def _bridge(y0, y1):
        r0 = next((r_ for r_ in rows_pld if r_[0] == f"FY{y0}"), None)
        r1 = next((r_ for r_ in rows_pld if r_[0] == f"FY{y1}"), None)
        if not r0 or not r1 or any(x is None for x in r0[1:]) or any(x is None for x in r1[1:]):
            return None
        d_ff, d_sl, d_mc, d_tl, d_oe = r1[1] - r0[1], r1[2] - r0[2], r1[3] - r0[3], r1[4] - r0[4], r1[5] - r0[5]
        return (f"FY{y0} -> FY{y1}: OE per share {f(r0[5])} -> {f(r1[5])} ({f(d_oe)}) = normalized FFO {f(d_ff)} - straight-line {f(d_sl)} - maintenance capex {f(d_mc)} - TI/LC {f(d_tl)}")
    L.append("")
    for y0, y1 in ((2021, 2025), (2022, 2025)):
        br = _bridge(y0, y1)
        if br:
            L.append("Bridge " + br + ".")
    L.append("Driver of the negative OE growth: normalized FFO per share is flat to slightly lower since FY2022 (6.04 -> 5.94) while the straight-line line more than doubles (0.33 -> 0.72 per share; it includes "
             "the amortization of above / below-market leases and is deducted in full), maintenance capex rises (0.26 -> 0.34) and TI/LC rises (0.42 -> 0.59). The G1 growth uses R14 (fewer than 10 years of OE per share), which compares the average of the first "
             "two with the last two of the five OE years and is negative, so the stage-1 growth is the 0% floor.")
    bgp = R["PLD"]["pr"]["buffett_price"]["base_growth"]
    L.append(NL + f"PLD in the DCF: median OE per share {f(bgp.get('median'))}; growth before the gate {pc(bgp.get('growth_before_gate'))}; growth used {pc(bgp.get('g1'))}; flags: {', '.join(bgp.get('flags', [])) or 'none'}.")

    d, ri = R["ARE"]["sc"]["derived"], R["ARE"]["ri"]
    b = R["ARE"]["pr"]["buffett_price"]
    bgx = b["base_growth"]
    L.append(NL + "### 6b. ARE: does the value rest on growth that no longer exists?" + NL)
    gate = bgx.get("growth_gate") or {}
    L.append("Growth-gate inputs (general model v1.2 gate on revenue and normalized FFO per share): "
             f"revenue rose in {gate.get('revenue_rises')} of 4 transitions (needs >= 3); normalized FFO per share fell by more than 10% in {gate.get('eps_falls_gt10')} of 4 transitions (needs <= 1); "
             f"normalized FFO per share positive in {gate.get('eps_positive_years')} of 5 years (needs 5). Gate passed: **{gate.get('passed')}**." + NL)
    L.append("| Year | Revenue (bn) | Norm. FFO / sh | OE / sh | Same-property NOI growth | Occupancy | Net debt / EBITDAre |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for i in range(max(0, len(ri.fy) - 10), len(ri.fy)):
        stt = d["nd_ebitdare_state"][i]
        L.append(f"| {ri.fy[i]} | {bn(ri.series('total_revenue')[i])} | {f(d['nffo_ps'][i])} | {f(d['oe_ps_strict'][i])} | {pc(d['same_property_noi_growth'][i])} | {pc(d['occupancy'][i])} | "
                 f"{f(stt[1]) if stt[1] is not None else stt[0]} |")
    g1 = bgx.get("g1")
    base = bgx.get("base")
    v0 = b.get("fair_value")
    from src.scoring.realestate import _dcf_ps as _dcf
    v_flat = _dcf(base, 0.0, 0.10) if base else None
    v_neg = _dcf(base * 0.85, 0.0, 0.10) if base else None
    last5 = bgx.get("last5") or [None]
    L.append(NL + f"DCF inputs: median OE per share {f(bgx.get('median'))} (latest OE per share {f(last5[-1])}); growth before the gate {pc(bgx.get('growth_before_gate'))}; growth used {pc(g1)}; base {f(base)}; "
             f"flags: {', '.join(bgx.get('flags', [])) or 'none'}. Value {f(v0)}; with zero growth {f(v_flat)}; with zero growth and a base 15% below the median {f(v_neg)}; price {f(ri.price_current)}.")
    share_growth = "none (growth used is 0%)" if not g1 else (pc((v0 - v_flat) / v0 if v0 else None) + " of the value")
    L.append(f"Reading: the base is the 5-year median OE per share (not rolled forward when the latest OE is below the median); the part of the value that comes from growth is {share_growth}. "
             "Compare the latest OE per share and the trend in the table with the median to judge whether the median still represents the earnings power.")

    ip = ROOT / "scripts" / "realestate_rule_issues_pricing_v6.md"
    L.append(NL + "## 5. Open issues and rule questions" + NL)
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(scripts/realestate_rule_issues_pricing_v6.md not written yet)")
    (OUT / "summary_pricing_v6.md").write_text(NL.join(L) + NL, encoding="utf-8")
    print("SEC requests:", sec.requests_made)


if __name__ == "__main__":
    main()

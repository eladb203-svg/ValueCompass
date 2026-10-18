"""INCOME_REAL_ESTATE pricing round 2 (RP1-RP3, RP2a / RP2b, C16 + QA Q1-Q5; spec docs/scoring/ValueCompass_RealEstate_Rules_2026-10-14_22-35_EN.md, section 6).
Cached data only (SEC companyfacts and price cache; EQR price from the VMRK successor as in round 3). No DB, no AI calls, no extraction.
Writes scripts/output_realestate_pricing_v2/ (summary_pricing_v2.md + one JSON per company).

Usage:  .venv/Scripts/python -X utf8 scripts/run_realestate_pricing_v2.py   (CA bundle env vars for yfinance as in the earlier rounds)
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
OUT = ROOT / "scripts" / "output_realestate_pricing_v2"
V5 = ROOT / "scripts" / "output_realestate_v5"
V1 = ROOT / "scripts" / "output_realestate_pricing_v1"
SPEC = "docs/scoring/ValueCompass_RealEstate_Rules_2026-10-14_22-35_EN.md"
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

    # ------------------------------------------------------------------ 1b v1 -> v2
    v1 = {t: json.loads((V1 / f"{t}.json").read_text(encoding="utf-8")) for t in T if (V1 / f"{t}.json").exists()}
    L.append(NL + "## 1b. Comparison with pricing v1 (value, score, block, reason)" + NL)
    L.append("| Company | Buffett value v1 -> v2 | Buffett score v1 -> v2 | RP1a v1 | RP1a v2 | Graham NAV v1 -> v2 | Graham score v1 -> v2 | RP2 block v1 -> v2 | What changed |")
    L.append("|---|---|---|---|---|---|---|---|---|")

    def sc2(p_):
        ps_ = p_.get("price_score") or {}
        return f(ps_.get("points")) if ps_.get("state") == "score" else ps_.get("state", "n/a")
    for t in R:
        o, b, g = v1.get(t), R[t]["pr"]["buffett_price"], R[t]["pr"]["graham_price"]
        if not o:
            continue
        ob, og = o["buffett_price"], o["graham_price"]
        ov, nv = ob.get("fair_value"), b.get("fair_value")
        og_v, ng_v = og.get("value"), g.get("value")
        oblk = "; ".join((ob.get("guard") or {}).get("reasons", [])) or "no"
        nblk = "; ".join(b["guard"]["reasons"]) or "no"
        gb_o = (og.get("price_score") or {}).get("state") == "blocked"
        gb_n = (g.get("price_score") or {}).get("state") == "blocked"
        why = []
        if (ov is None) != (nv is None):
            why.append("Buffett value " + ("now exists (OE completed)" if nv is not None else "lost"))
        elif ov is not None and nv is not None and abs(nv / ov - 1) > 0.005:
            why.append(f"Buffett value {nv / ov - 1:+.1%} (OE components / unlevered growth inputs)")
        if oblk != nblk:
            why.append("RP1a: 12-month near-term debt coverage with extracted maturities / facilities")
        if og_v is not None and ng_v is not None and abs(ng_v / og_v - 1) > 0.005:
            why.append(f"NAV {ng_v / og_v - 1:+.1%} (RP2a assets at carrying value, RP2b share basis)")
        if gb_o != gb_n:
            why.append("RP2 block " + ("lifted (unidentified assets now below 10%)" if gb_o and not gb_n else "applied"))
        if g.get("c16_issue"):
            why.append("C16: cannot be priced")
        bl = " (borderline 7.5-8.5x)" if b["guard"].get("borderline") else ""
        L.append(f"| {t} | {f(ov)} -> {f(nv)} | {sc2(ob)} -> {sc2(b)} | {oblk[:60]} | {nblk[:60]}{bl} | {f(og_v)} -> {f(ng_v)} | {sc2(og)} -> {sc2(g)} | "
                 f"{'yes' if gb_o else 'no'} -> {'yes' if gb_n else 'no'} | {'; '.join(why) or 'no change'} |")
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
    L.append(NL + "RP2a classes (USD bn, FY2025): " + "; ".join(f"{t}: " + ", ".join(f"{k} {v / 1e9:,.1f}" for k, v in sorted((R[t]['pr']['graham_price']['components'].get('bsa_classes') or {}).items())) for t in R) + ".")

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
    L.append(NL + "### Item-level changes vs v5 and their cause" + NL)
    L.append("| Company | Item | Name | Points v5 -> now | State v5 -> now | Cause |")
    L.append("|---|---|---|---|---|---|")

    def items_full(j):
        return {(m[0], c["id"], i["id"]): (i.get("name"), i.get("points"), i.get("state")) for m in ("buffett_quality", "graham_quality") for c in j[m]["criteria"] for i in c["items"]}

    def cause(name):
        n_ = (name or "").lower()
        if "debt coverage" in n_ or "near-term" in n_:
            return "(b) debt maturing in 12 / 24 months and committed facilities extracted"
        if any(k in n_ for k in ("oe", "owner", "earnings", "capital discipline", "dividend", "ffo")):
            return "(a) OE components completed for all five years (OE instead of the FFO proxy)"
        return "extraction round 2"
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
            L.append(f"| {t} | {'B' if k[0].startswith('b') else 'G'} {k[1]}.{k[2]} | {nm} | {f(ov[1])} -> {f(pt)} | {ov[2]} -> {stt} | {cause(nm)} |")
    L.append(NL + f"{n_changed} item changes. Scores that moved: O Graham, BXP Buffett and Graham (Graham now scored), ARE Graham, EQR Buffett and Graham, EQIX Graham, AMT Buffett and Graham (Graham now scored).")
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

    ip = ROOT / "scripts" / "realestate_rule_issues_pricing_v2.md"
    L.append(NL + "## 5. Open issues and rule questions" + NL)
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(scripts/realestate_rule_issues_pricing_v2.md not written yet)")
    (OUT / "summary_pricing_v2.md").write_text(NL.join(L) + NL, encoding="utf-8")
    print("SEC requests:", sec.requests_made)


if __name__ == "__main__":
    main()

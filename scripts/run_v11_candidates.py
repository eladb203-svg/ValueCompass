"""HISTORICAL (2026-10-13): regression test for the v1.1 candidate clarifications C12 / C13 (at that time flags default OFF; since then C13 is ON and C12 is display-only).

Runs the 14 companies of the v1.0 rounds and the 6 managed-care companies with the flags OFF and ON, using the production ETL
(including the new ETL tag fixes). Output: scripts/output_v11_candidates/summary_v11.md (+ json). No DB, no AI calls.
"""
from __future__ import annotations

raise SystemExit("HISTORICAL: C12 was rejected and removed from scoring on 2026-10-13 (C13 is ON by default); outputs of the 2026-10-13 regression are kept in scripts/output_v11_candidates/.")

import json
import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_scoring_test import COMPANIES, jsonable  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.sec_companyfacts import SecClient, build_inputs  # noqa: E402
from src.scoring.candidates import candidates  # noqa: E402
from src.scoring.inputs import CompanyInputs  # noqa: E402
from src.scoring.profiles import score_company  # noqa: E402

OUT = ROOT / "scripts" / "output_v11_candidates"
OLD14 = ROOT / "scripts" / "output"
OLD_MC = ROOT / "scripts" / "output_managed_care"
MC = ["UNH", "ELV", "CI", "HUM", "CNC", "MOH"]
SCENARIOS = {
    "OFF": dict(c12=None, c13=False),
    "C12 explicit": dict(c12="explicit", c13=False),
    "C12 derived": dict(c12="derived", c13=False),
    "C13": dict(c12=None, c13=True),
    "C12 explicit + C13": dict(c12="explicit", c13=True),
}
ON_MAIN = "C12 explicit + C13"


def build(sec, ticker, profile):
    splits = price_provider.get_splits(ticker)
    raw = build_inputs(sec, ticker, profile, splits)
    pr = price_provider.load_prices(ticker, raw["ends"], raw["labels"])
    inp = CompanyInputs(ticker=ticker, name=raw["name"], profile=profile, fy=raw["labels"], end=raw["ends"], f=raw["f"],
                        sbc_state=raw["sbc_state"], price_current=pr["current"], price_avg=pr["avg"],
                        first_annual_report=raw["first_annual_report"], as_of=date.today(), flags=list(raw["flags"]),
                        data_problems=list(raw["problems"]) + list(pr["notes"]), tag_log=raw["tag_log"], assumed_zero=raw["assumed_zero"])
    return inp, raw


def items_of(model):
    return {(c.id, i.id): (i.state, None if i.points is None else round(i.points, 4), i.name, i.max_pts) for c in model.criteria for i in c.items}


def snapshot(sc):
    bq, gq, bp, gp = sc["buffett_quality"], sc["graham_quality"], sc["buffett_price"], sc["graham_price"]
    gn = gp.get("graham_number") or {}
    return {"b": bq.score, "g": gq.score, "b_cov": bq.coverage, "g_cov": gq.coverage, "b_items": items_of(bq), "g_items": items_of(gq),
            "b_val": bp.get("fair_value"), "g_val": gn.get("value") if gn.get("state") == "valued" else None,
            "b_ps": (bp.get("price_score") or {}).get("points"), "g_ps": ((gp.get("price_score") or {}).get("points")),
            "b_inv": [c["id"] for c in []], "b_invalid": [c.id for c in bq.criteria if not c.valid], "g_invalid": [c.id for c in gq.criteria if not c.valid],
            "gm": sc["derived"]["gross_margin"][-1], "cr": sc["derived"]["current_ratio"][-1], "wc": sc["derived"]["working_capital"][-1],
            "qr": sc["derived"]["quick_ratio"][-1], "lt_md": sc["derived"]["lt_mdebt_used"][-1]}


def fx(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def bn(x):
    return "n/a" if x is None else f"{x / 1e9:,.2f}"


def ranks(scores: dict):
    order = sorted(scores, key=lambda t: -(scores[t] if scores[t] is not None else -1))
    return {t: i + 1 for i, t in enumerate(order)}


def load_old(group, t):
    base = OLD14 if group == "14" else OLD_MC
    f = base / f"{t}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sec = SecClient()
    universe = [(t, p, "14") for t, p, _ in COMPANIES] + [(t, "STANDARD", "MC") for t in MC]
    data, failures = {}, []
    for t, prof, grp in universe:
        try:
            inp, raw = build(sec, t, prof)
            res = {}
            for name, kw in SCENARIOS.items():
                with candidates(**kw):
                    sc = score_company(inp)
                res[name] = snapshot(sc)
            data[t] = {"group": grp, "inp": inp, "res": res, "raw": raw}
            print(f"{t}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    write_report(data, failures)
    (OUT / "results.json").write_text(json.dumps(jsonable({t: {"group": v["group"], "res": {k: {kk: vv for kk, vv in r.items() if kk not in ("b_items", "g_items")} for k, r in v["res"].items()}}
                                                             for t, v in data.items()}), indent=1), encoding="utf-8")
    print("SEC requests this run:", sec.requests_made)


def write_report(data, failures):
    L = [f"# v1.1 candidates C12 / C13 - regression test ({date.today().isoformat()})\n",
         "Flags are implemented in `src/scoring/candidates.py`, (at that time) **default OFF**; production rules are unchanged. Scenarios: OFF; C12 explicit "
         "(only a non-current marketable-debt tag); C12 derived (explicit, else AFS debt total less current investments - an estimate); C13; "
         "C12 explicit + C13 (= \"ON\"). The ETL tag fixes (Cigna capex and claims liability from the 10-K inline XBRL, premium receivables) are "
         "production in all scenarios. Cached filings and prices; new SEC requests only for what is new. No DB; no AI (AI items stay `ai_pending`).\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    T14 = [t for t, v in data.items() if v["group"] == "14"]
    TMC = [t for t, v in data.items() if v["group"] == "MC"]
    # ------------------------------------------------------------ ETL fixes
    L.append("## 1. ETL tag fixes (production)\n")
    L.append("| Fix | Company | Result | Tag found |")
    L.append("|---|---|---|---|")
    ci = data.get("CI")
    if ci:
        lg = ci["raw"]["tag_log"]
        capex = {l: v for l, v in lg["capex"].items() if v.get("tag")}
        by_tag = {}
        for l, v in capex.items():
            by_tag.setdefault(v["tag"], []).append(l[2:])
        L.append("| Capex | CI | " + ", ".join(f"{l[2:]}: {bn(ci['inp'].f['capex'][ci['inp'].fy.index(l)])}bn" for l in ci["inp"].fy[-6:]) + " | " +
                 "; ".join(f"`{k}` ({','.join(v)})" for k, v in by_tag.items()) + " |")
        cl = {l: v for l, v in lg["claims_liability"].items() if v.get("tag")}
        by_tag = {}
        for l, v in cl.items():
            by_tag.setdefault(v["tag"], []).append(l[2:])
        L.append("| Claims liability | CI | " + (", ".join(f"{l[2:]}: {bn(ci['inp'].f['claims_liability'][ci['inp'].fy.index(l)])}bn" for l in ci["inp"].fy[-6:]
                                                         if ci["inp"].f["claims_liability"][ci["inp"].fy.index(l)] is not None) or "none found") + " | " +
                 ("; ".join(f"`{k}` ({','.join(v)})" for k, v in by_tag.items()) or "none") + " |")
    for t in ("ELV", "CNC"):
        if t in data:
            lg = data[t]["raw"]["tag_log"]["receivables"]
            by_tag = {}
            for l, v in lg.items():
                by_tag.setdefault(v.get("tag") or "-", []).append(l[2:])
            L.append(f"| Premium receivables | {t} | FY{data[t]['inp'].fy[-1][2:]}: {bn(data[t]['inp'].f['receivables'][-1])}bn | " +
                     "; ".join(f"`{k}` ({','.join(v)})" for k, v in by_tag.items()) + " |")
    L.append("\nNote: Cigna reports capex and the claims liability under its own namespace (`ci:`), which `companyfacts` does not carry. "
             "They are read from the 10-K inline XBRL (new module `src/providers/sec_ixbrl.py`), only for fiscal years the standard chain leaves "
             "empty (capex: all companies; claims liability: only companies that report earned premiums / policyholder benefits). "
             "Cigna reports `ci:LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent` (unpaid claims and claim expenses) only per business segment "
             "(Cigna Healthcare + all other segments); there is no undimensioned value, so the exhaustive segment members are summed. Only FY2025 "
             "resolves this way (prior-year values in the same filing use disposal-group variants of the element). The undimensioned balance-sheet line "
             "`ci:InsuranceAndContractholderLiabilitiesCurrent` (claims plus other insurance liabilities) is not used, and \"Pharmacy and service costs "
             "payable\" (`ci:PharmacyAndServiceCostsPayable`, 30.3bn) is not a claims liability and is not included.\n")
    fetched = [t for t, v in data.items() if any("extension element read" in p for p in v["inp"].data_problems)]
    L.append("Companies where the extension fallback filled values: " + (", ".join(fetched) or "none") + ".\n")
    # ETL regression vs earlier stored outputs
    L.append("### ETL fixes: change vs the stored earlier outputs (flags OFF)\n")
    L.append("| Company | Buffett quality before -> after | Graham quality before -> after | Changed sub-items |")
    L.append("|---|---|---|---|")
    for t in T14 + TMC:
        old = load_old(data[t]["group"], t)
        new = data[t]["res"]["OFF"]
        if not old or "buffett_quality" not in old:
            L.append(f"| {t} | (no stored output) | | |")
            continue
        ob, og = old["buffett_quality"]["score"], old["graham_quality"]["score"]
        ch = []
        for key, mk, mdl in (("b_items", "buffett_quality", "B"), ("g_items", "graham_quality", "G")):
            oi = {(c["id"], i["id"]): i for c in old[mk]["criteria"] for i in c["items"]}
            for k, v in new[key].items():
                o = oi.get(k)
                if o is None:
                    continue
                op = o.get("points")
                if (o["state"] != v[0]) or (op is not None and v[1] is not None and abs(op - v[1]) > 0.005):
                    ch.append(f"{mdl}{k[0]}.{k[1]} {o['state'] if op is None else round(op, 2)}->{v[0] if v[1] is None else v[1]}")
        L.append(f"| {t} | {fx(ob, 1)} -> {fx(new['b'], 1)} | {fx(og, 1)} -> {fx(new['g'], 1)} | {', '.join(ch) or 'none'} |")
    L.append("")
    # ------------------------------------------------------------ tags used for C12 / C13
    L.append("## 2. Tags used by the candidates (latest fiscal year)\n")
    L.append("| Company | C12 explicit non-current tag | value (bn) | C12 derived estimate (AFS debt total - ST investments, bn) | C13 claims expense tag | value (bn) | Reported GrossProfit |")
    L.append("|---|---|---:|---:|---|---:|---|")
    for t, v in data.items():
        lg = v["raw"]["tag_log"]
        inp = v["inp"]
        lab = inp.fy[-1]
        e = lg["lt_mdebt_explicit"].get(lab, {})
        c = lg["claims_expense"].get(lab, {})
        g = lg["gross_profit"].get(lab, {}).get("tag") or "-"
        L.append(f"| {t} | {('`' + e['tag'] + '`') if e.get('tag') else '-'} | {bn(inp.f['lt_mdebt_explicit'][-1])} | {bn(inp.f['lt_mdebt_derived'][-1])} | "
                 f"{('`' + c['tag'] + '`') if c.get('tag') else '-'} | {bn(inp.f['claims_expense'][-1])} | {'reported' if not g.startswith('DERIVED') and g != '-' else g[:40]} |")
    L.append("\nThe derived tier is an estimate: the AFS debt total can include securities classified as cash equivalents, so it may overstate the non-current portfolio. "
             "`BenefitsLossesAndExpenses` is **not** used for C13: it is total benefits, losses and expenses (ELV 192.4bn, CI 265.7bn incl. 215.0bn cost of goods), "
             "so adding it to cost of revenue would double count; the narrower `PolicyholderBenefitsAndClaimsIncurredNet` is used. MOH reports its medical costs "
             "as `CostOfGoodsAndServicesSold` (already cost of revenue) and has no claims tag, so C13 does not apply.\n")
    # ------------------------------------------------------------ summary tables
    def group_tables(title, tickers):
        L.append(f"## {title}\n")
        L.append("Quality scores: OFF vs each scenario (change in points); rank within the group in brackets (OFF -> ON). Flag = change > 3 points.\n")
        sc_names = list(SCENARIOS)
        for mkey, mlabel in (("b", "Buffett quality"), ("g", "Graham quality")):
            L.append(f"**{mlabel}**\n")
            L.append("| Company | OFF | " + " | ".join(n for n in sc_names[1:]) + " | Rank OFF -> ON | Flag |")
            L.append("|---|---:|" + "---:|" * (len(sc_names) - 1) + "---|---|")
            roff = ranks({t: data[t]["res"]["OFF"][mkey] for t in tickers})
            ron = ranks({t: data[t]["res"][ON_MAIN][mkey] for t in tickers})
            for t in tickers:
                off = data[t]["res"]["OFF"][mkey]
                cells = []
                for n in sc_names[1:]:
                    x = data[t]["res"][n][mkey]
                    cells.append("-" if abs(x - off) < 0.005 else f"{x:.1f} ({x - off:+.1f})")
                big = [n for n in sc_names[1:] if abs(data[t]["res"][n][mkey] - off) > 3]
                L.append(f"| {t} | {off:.1f} | " + " | ".join(cells) + f" | {roff[t]} -> {ron[t]}{' *' if roff[t] != ron[t] else ''} | "
                         f"{('**>3: ' + ', '.join(big) + '**') if big else ''} |")
            chg = [t for t in tickers if roff[t] != ron[t]]
            L.append(f"\nRank changes (OFF -> ON): {', '.join(f'{t} {roff[t]}->{ron[t]}' for t in chg) or 'none'}.\n")
        # price side
        L.append("**Values and price scores (OFF -> ON)**\n")
        L.append("| Company | Buffett value | Buffett price score | Graham value | Graham price score | Coverage Buffett | Coverage Graham | Invalid criteria OFF -> ON |")
        L.append("|---|---|---|---|---|---|---|---|")
        for t in tickers:
            a, b = data[t]["res"]["OFF"], data[t]["res"][ON_MAIN]
            L.append(f"| {t} | {fx(a['b_val'])} -> {fx(b['b_val'])} | {fx(a['b_ps'], 1)} -> {fx(b['b_ps'], 1)} | {fx(a['g_val'])} -> {fx(b['g_val'])} | "
                     f"{fx(a['g_ps'], 1)} -> {fx(b['g_ps'], 1)} | {a['b_cov']:.0%} -> {b['b_cov']:.0%} | {a['g_cov']:.0%} -> {b['g_cov']:.0%} | "
                     f"B{','.join(a['b_invalid']) or '-'} G{','.join(a['g_invalid']) or '-'} -> B{','.join(b['b_invalid']) or '-'} G{','.join(b['g_invalid']) or '-'} |")
        L.append("")
        L.append("**Liquidity and margin inputs (latest fiscal year)**\n")
        L.append("| Company | Current ratio OFF -> C12 | Working capital OFF -> C12 (bn) | Quick ratio OFF -> C12 | LT marketable debt added (bn) | Gross margin OFF -> C13 |")
        L.append("|---|---|---|---|---|---|")
        for t in tickers:
            a, c12, c13 = data[t]["res"]["OFF"], data[t]["res"]["C12 explicit"], data[t]["res"]["C13"]
            L.append(f"| {t} | {fx(a['cr'])} -> {fx(c12['cr'])} | {bn(a['wc'])} -> {bn(c12['wc'])} | {fx(a['qr'])} -> {fx(c12['qr'])} | {bn(c12['lt_md'])} | "
                     f"{('n/a' if a['gm'] is None else f'{a['gm']:.1%}')} -> {('n/a' if c13['gm'] is None else f'{c13['gm']:.1%}')} |")
        L.append("")
        L.append("**Per-sub-item changes (OFF -> ON; only items whose points or state changed)**\n")
        L.append("| Company | Changes |")
        L.append("|---|---|")
        for t in tickers:
            a, b = data[t]["res"]["OFF"], data[t]["res"][ON_MAIN]
            ch = []
            for key, mdl in (("b_items", "B"), ("g_items", "G")):
                for k, v in b[key].items():
                    o = a[key][k]
                    if o[0] != v[0] or (o[1] is not None and v[1] is not None and abs(o[1] - v[1]) > 0.005):
                        ch.append(f"{mdl}{k[0]}.{k[1]} {o[2][:24]} ({v[3]:g}): {'n/a' if o[1] is None else o[1]}{'' if o[1] is not None else '[' + o[0] + ']'} -> "
                                  f"{'n/a' if v[1] is None else v[1]}{'' if v[1] is not None else '[' + v[0] + ']'}")
            L.append(f"| {t} | {'; '.join(ch) or 'no change'} |")
        L.append("")
        L.append("**Which flag causes which change** (sub-item changes by scenario)\n")
        L.append("| Company | C12 explicit | C12 derived | C13 |")
        L.append("|---|---|---|---|")
        for t in tickers:
            cells = []
            for n in ("C12 explicit", "C12 derived", "C13"):
                a, b = data[t]["res"]["OFF"], data[t]["res"][n]
                ch = []
                for key, mdl in (("b_items", "B"), ("g_items", "G")):
                    for k, v in b[key].items():
                        o = a[key][k]
                        if o[0] != v[0] or (o[1] is not None and v[1] is not None and abs(o[1] - v[1]) > 0.005):
                            ch.append(f"{mdl}{k[0]}.{k[1]} {'n/a' if o[1] is None else o[1]}->{'n/a' if v[1] is None else v[1]}")
                cells.append(", ".join(ch) or "-")
            L.append(f"| {t} | " + " | ".join(cells) + " |")
        L.append("")

    group_tables("3. The 14 companies of the v1.0 test rounds", T14)
    group_tables("4. The 6 managed-care companies", TMC)
    flagged = []
    for t, v in data.items():
        for n in list(SCENARIOS)[1:]:
            for mkey, ml in (("b", "Buffett"), ("g", "Graham")):
                d_ = v["res"][n][mkey] - v["res"]["OFF"][mkey]
                if abs(d_) > 3:
                    flagged.append(f"{t} {ml} {n} {d_:+.1f}")
    L.append("## 5. Companies whose quality score moves by more than 3 points\n")
    L.append("\n".join(f"- {x}" for x in flagged) if flagged else "None.")
    ip = ROOT / "scripts" / "v11_candidates_findings.md"
    L.append("\n## 6. Findings and open issues\n")
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(findings not written yet)")
    L.append("\n## Data problems (new extension-element notes)\n")
    for t, v in data.items():
        probs = [p for p in v["inp"].data_problems if "extension" in p]
        if probs:
            L.append(f"- **{t}**: " + "; ".join(probs))
    (OUT / "summary_v11.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

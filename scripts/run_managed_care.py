"""Diagnostic run: US managed-care companies under the STANDARD profile, v1.0 general rules. No rule changes.

Usage: .venv/Scripts/python scripts/run_managed_care.py
Output: scripts/output_managed_care/<TICKER>.json and summary_managed_care.md (untracked). No DB, no AI calls.
"""
from __future__ import annotations

import dataclasses
import json
import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_scoring_test as rst  # noqa: E402
from run_scoring_test import jsonable, model_json  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.sec_companyfacts import SecClient, annual_series, build_inputs  # noqa: E402
from src.scoring.inputs import CompanyInputs  # noqa: E402
from src.scoring.profiles import score_company  # noqa: E402

OUT = ROOT / "scripts" / "output_managed_care"
COMPANIES = ["UNH", "ELV", "CI", "HUM", "CNC", "MOH"]

# ---- insurance-liability components for the profile test (latest year-end)
INS_COMPONENTS = {
    "claims / medical costs payable": ["LiabilityForClaimsAndClaimsAdjustmentExpense", "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseNet",
                                       "ShortdurationInsuranceContractsLiabilityForUnpaidClaimsAndAllocatedClaimAdjustmentExpenseNet"],
    "unearned premiums": ["UnearnedPremiums"],
    "future policy benefits": ["LiabilityForFuturePolicyBenefits", "LiabilityForFuturePolicyBenefitAfterReinsurance"],
    "policyholder contract deposits": ["PolicyholderContractDeposits"],
    "separate accounts liability": ["SeparateAccountsLiability"],
    "market risk benefit liability": ["MarketRiskBenefitLiabilityAmount"],
}
# ---- liquidity diagnostics tags
CLAIMS_TAGS = INS_COMPONENTS["claims / medical costs payable"]
UNEARNED_TAGS = ["UnearnedPremiums", "DeferredRevenueCurrent", "ContractWithCustomerLiabilityCurrent"]
LT_DEBT_NC_TAGS = ["AvailableForSaleSecuritiesDebtSecuritiesNoncurrent", "DebtSecuritiesAvailableForSaleNoncurrent"]
AFS_TOTAL_TAGS = ["AvailableForSaleSecuritiesDebtSecurities", "DebtSecuritiesAvailableForSaleExcludingAccruedInterest"]
AFS_CURRENT_TAGS = ["AvailableForSaleSecuritiesDebtSecuritiesCurrent", "MarketableSecuritiesCurrent", "ShortTermInvestments"]


def _val(facts, tags, end, unit="USD", kind="instant"):
    """First tag of the chain with a value at (or within 10 days of) the fiscal-year end -> (value, tag)."""
    for tag in tags:
        s = annual_series(facts, tag, unit, kind)
        for e, fct in s.items():
            if abs((e - end).days) <= 10:
                return fct.val, tag
    return None, None


def lt_marketable_debt(facts, end):
    v, tag = _val(facts, LT_DEBT_NC_TAGS, end)
    if v is not None:
        return v, tag, "tagged non-current"
    tot, ttag = _val(facts, AFS_TOTAL_TAGS, end)
    cur, ctag = _val(facts, AFS_CURRENT_TAGS, end)
    if tot is not None and cur is not None:
        return max(0.0, tot - cur), f"DERIVED: {ttag} - {ctag}", "derived estimate (no non-current tag)"
    li, ltag = _val(facts, ["LongTermInvestments"], end)
    if li is not None:
        return li, ltag, "PROXY: balance-sheet long-term investments (may include non-debt investments; upper bound)"
    return None, None, "not available"


def liquidity_rows(facts, inp, d):
    rows = []
    for i in range(inp.n - 5, inp.n):
        end, lab = inp.end[i], inp.fy[i]
        ca, cl = inp.series("cur_assets")[i], inp.series("cur_liab")[i]
        cash, sti = inp.series("cash")[i], inp.series("sti")[i]
        claims, ctag = _val(facts, CLAIMS_TAGS, end)
        unearned, utag = _val(facts, UNEARNED_TAGS, end)
        lt, lttag, ltnote = lt_marketable_debt(facts, end)
        alt_ca = None if ca is None else ca + (lt or 0.0)
        rows.append({
            "fy": lab, "cur_assets": ca, "cur_liab": cl, "current_ratio": None if not cl or ca is None else ca / cl,
            "working_capital": None if ca is None or cl is None else ca - cl,
            "claims": claims, "claims_tag": ctag, "claims_pct_cl": None if claims is None or not cl else claims / cl,
            "unearned": unearned, "unearned_tag": utag, "unearned_pct_cl": None if unearned is None or not cl else unearned / cl,
            "cash_sti": None if cash is None else cash + (sti or 0.0), "cash": cash, "sti": sti,
            "lt_debt_sec": lt, "lt_debt_tag": lttag, "lt_debt_note": ltnote,
            "alt_current_ratio": None if alt_ca is None or not cl else alt_ca / cl,
            "alt_working_capital": None if alt_ca is None or cl is None else alt_ca - cl,
        })
    return rows


def profile_check(facts, inp):
    end = inp.end[-1]
    liab, _ = _val(facts, ["Liabilities"], end)
    comps, tot = {}, 0.0
    for name, tags in INS_COMPONENTS.items():
        v, tag = _val(facts, tags, end)
        comps[name] = {"value": v, "tag": tag}
        tot += v or 0.0
    ratio = None if not liab else tot / liab
    missing = [n for n, c in comps.items() if c["value"] is None]
    return {"total_liabilities": liab, "components": comps, "insurance_liabilities": tot, "ratio": ratio, "missing_components": missing,
            "passes_insurance_test": None if ratio is None else ratio >= 0.5}


def alt_inputs(inp, liq):
    """Copy of the inputs with long-term marketable debt securities added to current assets (diagnostic only)."""
    f = {k: list(v) for k, v in inp.f.items()}
    ca = list(f["cur_assets"])
    # liq covers the last 5 years; earlier years use the same chain
    for r in liq:
        i = inp.fy.index(r["fy"])
        if ca[i] is not None:
            ca[i] = ca[i] + (r["lt_debt_sec"] or 0.0)
    f["cur_assets"] = ca
    return dataclasses.replace(inp, f=f)


def run_one(sec, ticker):
    splits = price_provider.get_splits(ticker)
    raw = build_inputs(sec, ticker, "STANDARD", splits)
    pr = price_provider.load_prices(ticker, raw["ends"], raw["labels"])
    inp = CompanyInputs(ticker=ticker, name=raw["name"], profile="STANDARD", fy=raw["labels"], end=raw["ends"], f=raw["f"],
                        sbc_state=raw["sbc_state"], price_current=pr["current"], price_avg=pr["avg"],
                        first_annual_report=raw["first_annual_report"], as_of=date.today(), flags=list(raw["flags"]),
                        data_problems=list(raw["problems"]) + list(pr["notes"]), tag_log=raw["tag_log"], assumed_zero=raw["assumed_zero"])
    facts = sec.companyfacts(raw["cik"])
    prof = profile_check(facts, inp)
    sc = score_company(inp)
    liq_full = []
    # liquidity rows need >=5 fiscal years
    liq = liquidity_rows(facts, inp, sc["derived"])
    inp_alt = alt_inputs(inp, liq)
    sc_alt = score_company(inp_alt)
    res = {"ticker": ticker, "name": raw["name"], "cik": raw["cik"], "profile": "STANDARD", "profile_check": prof,
           "fiscal_years": dict(zip(inp.fy, inp.end)), "price": {"current": pr["current"], "date": pr["current_date"]},
           "buffett_quality": model_json(sc["buffett_quality"]), "buffett_price": sc["buffett_price"],
           "graham_quality": model_json(sc["graham_quality"]), "graham_price": sc["graham_price"],
           "liquidity": liq, "alt": {"buffett_quality": model_json(sc_alt["buffett_quality"]), "graham_quality": model_json(sc_alt["graham_quality"])},
           "data_problems": inp.data_problems, "flags": inp.flags,
           "tag_log": raw["tag_log"], "financials": {k: dict(zip(inp.fy, v)) for k, v in inp.f.items()},
           "derived": {k: dict(zip(inp.fy, v)) for k, v in sc["derived"].items() if isinstance(v, list) and k not in ("roic", "nd_ebitda", "int_cov")}}
    (OUT / f"{ticker}.json").write_text(json.dumps(jsonable(res), indent=1, ensure_ascii=False), encoding="utf-8")
    return {"res": res, "inp": inp, "sc": sc, "sc_alt": sc_alt, "prof": prof, "liq": liq}


# ------------------------------------------------------------------ report
def bn(x, nd=2):
    return "n/a" if x is None else f"{x / 1e9:,.{nd}f}"


def pc(x, nd=1):
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def fx(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def item_cell(it):
    s = it.state
    if s == "not_applicable":
        return "n/a"
    if s == "missing":
        return "MISS"
    if s == "ai_pending":
        return "AI"
    return f"{it.points:.2f}"


def build(runs, failures):
    L = [f"# Managed-care diagnostic run (STANDARD profile, v1.0 general rules) - {date.today().isoformat()}\n",
         "Companies: UNH, ELV, CI, HUM, CNC, MOH. No rule changes; no DB; no AI calls (AI items stay `ai_pending`, excluded from validity and coverage). "
         "SEC annual XBRL (fiscal years from 10-K filings), yfinance prices. Alternative current ratio and all liquidity diagnostics are display only.\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    T = list(runs)
    # 1 profile check
    L.append("## 1. Profile check (INSURANCE test: insurance liabilities / total liabilities >= 50%)\n")
    L.append("Insurance liabilities = claims/medical costs payable + unearned premiums + future policy benefits + policyholder contract deposits + "
             "separate-accounts liability + market-risk-benefit liability (standard us-gaap tags, latest fiscal year-end; USD bn).\n")
    L.append("| Company | FY | Total liabilities | Insurance liabilities | Ratio | INSURANCE test (>=50%) | Profile | Missing components |")
    L.append("|---|---|---:|---:|---:|---|---|---|")
    for t in T:
        p = runs[t]["prof"]
        flag = "" if p["passes_insurance_test"] is False else " **FLAG**"
        L.append(f"| {t} | {runs[t]['inp'].fy[-1]} | {bn(p['total_liabilities'])} | {bn(p['insurance_liabilities'])} | {pc(p['ratio'])} | "
                 f"{'fails (<50%)' if p['passes_insurance_test'] is False else 'PASSES'}{flag} | STANDARD | {', '.join(p['missing_components']) or '-'} |")
    L.append("\nComponents and tags used:\n")
    L.append("| Company | " + " | ".join(INS_COMPONENTS) + " |")
    L.append("|---|" + "---:|" * len(INS_COMPONENTS))
    for t in T:
        c = runs[t]["prof"]["components"]
        L.append(f"| {t} | " + " | ".join(("-" if c[n]["value"] is None else f"{bn(c[n]['value'])} (`{c[n]['tag']}`)") for n in INS_COMPONENTS) + " |")
    notes = [t for t in T if runs[t]["prof"]["missing_components"] and "claims / medical costs payable" in runs[t]["prof"]["missing_components"]]
    if notes:
        L.append("\n" + ", ".join(notes) + ": the claims liability is not tagged with a standard us-gaap tag in the annual data, so the ratio is a **lower bound** "
                 "(see open issues).")
    flagged = [t for t in T if runs[t]["prof"]["passes_insurance_test"] is not False]
    L.append("\n**All six fail the INSURANCE test and land in STANDARD.**" if not flagged else "\n**Companies that pass the test (flag): " + ", ".join(flagged) + "**")
    # 2 scoring
    L.append("\n## 2. Quality and price scoring (STANDARD)\n")
    L.append("| Company | Buffett quality | Range | Coverage | Status | Graham quality | Range | Coverage | Status | Price | Buffett value | Buffett price score | Graham value | Graham price score |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in T:
        sc = runs[t]["sc"]
        bq, gq, bp, gp = sc["buffett_quality"], sc["graham_quality"], sc["buffett_price"], sc["graham_price"]

        def rg(m):
            return "withheld" if m.min_score is None else f"{m.min_score:.1f}-{m.max_score:.1f}"

        def pv(p, k):
            return fx(p.get(k)) if p.get("state") in (None, "valued", "computed", "ok") and p.get(k) is not None else f"n/a ({p.get('state') or p.get('reason', '')})"

        def ps(p):
            x = p.get("price_score")
            return "n/a" if not isinstance(x, dict) or x.get("points") is None else f"{x['points']:.1f}"
        L.append(f"| {t} | {fx(bq.score, 1)} | {rg(bq)} | {pc(bq.coverage, 0)} | {bq.status} | {fx(gq.score, 1)} | {rg(gq)} | {pc(gq.coverage, 0)} | {gq.status} | "
                 f"{fx(runs[t]['inp'].price_current)} | {pv(bp, 'fair_value')} | {ps(bp)} | {pv(gp, 'value') if gp.get('value') is not None else pv(gp, 'fair_value')} | {ps(gp)} |")
    L.append("\n**Criterion totals** (points / maximum of the criterion; `MISS`/`AI` items are not in the total; coverage = share of points observed)\n")
    for key, label in (("buffett_quality", "Buffett"), ("graham_quality", "Graham")):
        cids = [c.id for c in runs[T[0]]["sc"][key].criteria]
        L.append(f"**{label}**\n")
        L.append("| Company | " + " | ".join(f"{label[0]}{cid}" for cid in cids) + " |")
        L.append("|---|" + "---:|" * len(cids))
        for t in T:
            m = runs[t]["sc"][key]
            cells = []
            for c in m.criteria:
                mx = sum(i.max_pts for i in c.items if i.state != "not_applicable")
                obs = sum((i.points or 0.0) for i in c.items if i.state in ("score", "true_zero"))
                na = [i for i in c.items if i.state == "not_applicable"]
                cells.append(f"{obs:.1f}/{mx:g}" + ("" if c.valid else " INVALID") + (f" ({len(na)} n/a)" if na else ""))
            L.append(f"| {t} | " + " | ".join(cells) + " |")
        L.append("")
    L.append("### All sub-item scores\n")
    L.append("`n/a` = not applicable; `MISS` = missing data; `AI` = ai_pending; max points in the header.\n")
    for key, label in (("buffett_quality", "Buffett"), ("graham_quality", "Graham")):
        for c0 in runs[T[0]]["sc"][key].criteria:
            hdr = [(c0.id, i.id, i.max_pts, i.name) for i in c0.items]
            L.append(f"**{label} {c0.id} {c0.name}**\n")
            L.append("| Company | " + " | ".join(f"{c0.id}.{iid} {nm[:28]} ({mx:g})" for _, iid, mx, nm in hdr) + " |")
            L.append("|---|" + "---:|" * len(hdr))
            for t in T:
                c = next(x for x in runs[t]["sc"][key].criteria if x.id == c0.id)
                cm = {i.id: i for i in c.items}
                L.append(f"| {t} | " + " | ".join(item_cell(cm[iid]) for _, iid, _, _ in hdr) + " |")
            L.append("")
    L.append("### Not-applicable items (with reason)\n")
    for t in T:
        out = []
        for key, label in (("buffett_quality", "B"), ("graham_quality", "G")):
            for c in runs[t]["sc"][key].criteria:
                for i in c.items:
                    if i.state == "not_applicable":
                        out.append(f"{label}{c.id}.{i.id} {i.name}: {i.note or ''}")
        L.append(f"- **{t}**: " + ("; ".join(out) if out else "none"))
    L.append("\n### Missing / pending items\n")
    for t in T:
        out = []
        for key, label in (("buffett_quality", "B"), ("graham_quality", "G")):
            for c in runs[t]["sc"][key].criteria:
                for i in c.items:
                    if i.state == "missing":
                        out.append(f"{label}{c.id}.{i.id} {i.name}")
        inv = [f"B{c.id}" if False else c for c in []]
        L.append(f"- **{t}**: missing: {', '.join(out) or 'none'}; invalid criteria: "
                 f"{', '.join(['B' + c['id'] for c in runs[t]['res']['buffett_quality']['invalid_criteria']] + ['G' + c['id'] for c in runs[t]['res']['graham_quality']['invalid_criteria']]) or 'none'}")
    # 3 liquidity
    L.append("\n## 3. Liquidity diagnostics (display only, not scored)\n")
    L.append("USD bn except ratios. CL = current liabilities. Medical costs payable = claims liability tag; unearned = unearned premiums / revenues tag. "
             "Alternative current ratio = (current assets + long-term marketable debt securities) / current liabilities.\n")
    for t in T:
        liq = runs[t]["liq"]
        L.append(f"### {t}\n")
        L.append("| FY | Current assets | Current liabilities | Current ratio | Working capital | Medical costs payable (% CL) | Unearned (% CL) | Cash + ST investments | "
                 "LT marketable debt securities | Alt. current ratio | Alt. working capital |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for r in liq:
            L.append(f"| {r['fy']} | {bn(r['cur_assets'])} | {bn(r['cur_liab'])} | {fx(r['current_ratio'])} | {bn(r['working_capital'])} | "
                     f"{bn(r['claims'])} ({pc(r['claims_pct_cl'])}) | {bn(r['unearned'])} ({pc(r['unearned_pct_cl'])}) | {bn(r['cash_sti'])} | "
                     f"{bn(r['lt_debt_sec'])} | {fx(r['alt_current_ratio'])} | {bn(r['alt_working_capital'])} |")
        last = liq[-1]
        tags = {}
        for r in liq:
            tags.setdefault((r["claims_tag"], r["unearned_tag"], r["lt_debt_tag"], r["lt_debt_note"]), []).append(r["fy"][2:])
        L.append("\nTags used (claims / unearned / LT marketable debt / treatment): " + "; ".join(
            f"`{k[0]}` / `{k[1]}` / `{k[2]}` / {k[3]} ({','.join(v)})" for k, v in tags.items()) + "\n")
    # 4 before/after
    L.append("## 4. Graham 3.2, Graham 3.3.2, Buffett 3.6.3: reported vs alternative current ratio (diagnostic only)\n")
    L.append("Alternative = long-term marketable debt securities added to current assets in every year; nothing else changes.\n")
    L.append("| Company | G3.2.1 current ratio (7) | G3.2.3 consistency (5) | G3.2 total (15) | G3.3.2 LT debt/WC (4) | B3.6.3 liquidity (1.5) |")
    L.append("|---|---|---|---|---|---|")
    for t in T:
        def cmp(key, cid, iid):
            a = next(i for c in runs[t]["sc"][key].criteria if c.id == cid for i in c.items if i.id == iid)
            b = next(i for c in runs[t]["sc_alt"][key].criteria if c.id == cid for i in c.items if i.id == iid)
            return item_cell(a), item_cell(b)
        a1, b1 = cmp("graham_quality", "3.2", "1")
        a3, b3 = cmp("graham_quality", "3.2", "3")
        ga, gb = cmp("graham_quality", "3.3", "2")
        ba, bb = cmp("buffett_quality", "3.6", "3")

        def tot(sc, key):
            c = next(c for c in sc[key].criteria if c.id == "3.2")
            return sum((i.points or 0.0) for i in c.items if i.state in ("score", "true_zero"))
        L.append(f"| {t} | {a1} -> {b1} | {a3} -> {b3} | {tot(runs[t]['sc'], 'graham_quality'):.2f} -> {tot(runs[t]['sc_alt'], 'graham_quality'):.2f} | "
                 f"{ga} -> {gb} | {ba} -> {bb} |")
    L.append("\nCurrent ratio, latest FY: reported vs alternative, and the metric values behind the items:\n")
    L.append("| Company | Current ratio | Alt. current ratio | Working capital (bn) | Alt. working capital (bn) | LT debt (bn) | LT debt / WC | LT debt / alt. WC |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for t in T:
        last = runs[t]["liq"][-1]
        ltd = runs[t]["inp"].series("debt_lt")[-1]
        wc, awc = last["working_capital"], last["alt_working_capital"]
        L.append(f"| {t} | {fx(last['current_ratio'])} | {fx(last['alt_current_ratio'])} | {bn(wc)} | {bn(awc)} | {bn(ltd)} | "
                 f"{'WC<=0' if wc is None or wc <= 0 else fx((ltd or 0) / wc)} | {'WC<=0' if awc is None or awc <= 0 else fx((ltd or 0) / awc)} |")
    # gross margin + fair value inputs
    L.append("\n## 5. Gross margin and Buffett fair-value inputs\n")
    L.append("| Company | Gross profit tag | Cost of revenue | Gross margin (latest) | Buffett 3.2 gross-margin item | Revenue (latest, bn) |")
    L.append("|---|---|---|---|---|---:|")
    for t in T:
        inp, sc = runs[t]["inp"], runs[t]["sc"]
        gp = inp.series("gross_profit")[-1]
        cr = inp.series("cost_of_revenue")[-1]
        gm = sc["derived"]["gross_margin"][-1]
        b32 = next(c for c in sc["buffett_quality"].criteria if c.id == "3.2")
        gmi = b32.items[0]
        lg = runs[t]["res"]["tag_log"]
        gtag = (lg.get("gross_profit", {}).get(inp.fy[-1]) or {}).get("tag")
        ctag = (lg.get("cost_of_revenue", {}).get(inp.fy[-1]) or {}).get("tag")
        state = "not applicable" if gmi.state == "not_applicable" else ("derived/scored" if gmi.state == "score" else gmi.state)
        L.append(f"| {t} | {gtag or 'none'} | {ctag or 'none'} ({bn(cr)}) | {pc(gm)} | {gmi.name}: {state}{' - ' + gmi.note if gmi.note else ''} | {bn(inp.series('revenue')[-1])} |")
    L.append("\nBuffett price inputs (owner-earnings base, growth gate, cash and debt bridge):\n")
    L.append("| Company | State | Owner-earnings base (median of last 5, bn) | OE last 5 (bn) | Growth median-vs-median | Growth gate | Stage-1 growth used | Excess cash less debt (bn) | Fair value | Price | Discount |")
    L.append("|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|")
    for t in T:
        bp = runs[t]["sc"]["buffett_price"]
        gate = bp.get("growth_gate") or {}
        oe5 = ", ".join(bn(x, 1) for x in bp.get("owner_earnings_last5", []))
        L.append(f"| {t} | {bp.get('state', '')} | {bn(bp.get('oe_base'))} | {oe5} | {pc(bp.get('growth_before_gate'))} | "
                 f"{'passed' if gate.get('passed') else 'FAILED: ' + '; '.join(gate.get('failing', []))} | {pc(bp.get('stage1_growth'))} | "
                 f"{bn(bp.get('excess_cash_less_debt'))} | {fx(bp.get('fair_value'))} | {fx(runs[t]['inp'].price_current)} | "
                 f"{pc((bp.get('price_score') or {}).get('discount'))} |")
    L.append("\nFlags: " + "; ".join(f"{t}: {', '.join(runs[t]['sc']['buffett_price'].get('flags', [])) or '-'}" for t in T) + "\n")
    L.append("Evidence behind the distortion review (latest fiscal year, USD bn):\n")
    L.append("| Company | Equity | Operating invested capital | ROIC 5y median (B3.4.1) | LT marketable debt (alt.) | Claims liability | Current liabilities | Cash + STI | Financial debt | Net debt | Receivables used by quick ratio |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for t in T:
        inp, sc, liq = runs[t]["inp"], runs[t]["sc"], runs[t]["liq"][-1]
        inv = None
        a_, c_, s_, cl_, dc_ = (inp.series(k)[-1] for k in ("assets", "cash", "sti", "cur_liab", "debt_current"))
        if None not in (a_, c_, cl_, dc_):
            inv = a_ - (c_ + (s_ or 0.0)) - (cl_ - dc_)
        b34 = next(c for c in sc["buffett_quality"].criteria if c.id == "3.4").items[0]
        L.append(f"| {t} | {bn(inp.series('equity')[-1])} | {bn(inv)} | {pc(b34.metric)} | {bn(liq['lt_debt_sec'])} | {bn(liq['claims'])} | "
                 f"{bn(liq['cur_liab'])} | {bn(liq['cash_sti'])} | {bn(sc['derived']['fin_debt'][-1])} | {bn(sc['derived']['net_debt'][-1])} | "
                 f"{bn(inp.series('receivables')[-1])} |")
    L.append("\n(Full Buffett price dictionaries are in each `<TICKER>.json`.)\n")
    ip = ROOT / "scripts" / "managed_care_findings.md"
    L.append("## 6. Sub-items that look structurally distorted for managed care\n")
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(findings not written yet)")
    L.append("\n## Data problems\n")
    for t in T:
        L.append(f"- **{t}**: " + ("; ".join(runs[t]["res"]["data_problems"]) if runs[t]["res"]["data_problems"] else "none"))
    (OUT / "summary_managed_care.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    sec = SecClient()
    runs, failures = {}, []
    for t in COMPANIES:
        try:
            runs[t] = run_one(sec, t)
            print(f"{t}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    if runs:
        build(runs, failures)
    print(f"SEC requests this run: {sec.requests_made}")


if __name__ == "__main__":
    main(sys.argv[1:])

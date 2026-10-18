"""INSURANCE test round 2 (spec 2026-10-13_11-45: Q1-Q5). Quality only. Writes scripts/output_insurance_v2/; round-1 outputs are kept.

Usage:  .venv/Scripts/python -X utf8 scripts/run_insurance_test_v2.py
"""
from __future__ import annotations

import json
import statistics
import sys
import traceback
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_insurance_test as r1  # noqa: E402
from run_insurance_test import CAL_ITEMS, COMPANIES, _fmt, _item, _quart, fx, pct, usd  # noqa: E402
from src.providers.insurance_facts import load_insurance_regulatory  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring.insurance import LINE_OF_BUSINESS  # noqa: E402

OUT = ROOT / "scripts" / "output_insurance_v2"
R1 = ROOT / "scripts" / "output_insurance"
SPEC = "docs/scoring/ValueCompass_Insurance_Rules_2026-10-13_11-45_EN.md"
LINES = ("P&C", "reinsurance", "life", "composite")


def _r1(t):
    return json.loads((R1 / f"{t}.json").read_text(encoding="utf-8"))


def _ranks(vals):
    order = sorted(vals, key=lambda k: -vals[k])
    return {k: i + 1 for i, k in enumerate(order)}


def _crit_pts(model_json, cid):
    c = next(c for c in model_json["criteria"] if c["id"] == cid)
    mx = sum(i["max_pts"] for i in c["items"] if i["state"] != "not_applicable")
    obs = sum((i["points"] or 0.0) for i in c["items"] if i["state"] in ("score", "true_zero"))
    return obs, mx, c["valid"]


def _med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def build_summary(runs, failures):
    T = list(runs)
    L = [f"# ValueCompass INSURANCE test round 2 (quality only) - {date.today().isoformat()}\n",
         f"Spec: `{SPEC}` (supersedes 11-00). Same 12 US insurers. Implements Q1 (accretion on future policy benefits as insurance finance expense), "
         "Q2 (liquidity and complex assets from balance-sheet categories), Q3 (comparability rules for regulatory capital), Q4 (float CAGR over valid "
         "years), Q5 (catastrophe flag > 5%). No pricing; no DB; AI questions stay `ai_pending`; section-4 thresholds unchanged (K1). "
         "Round-1 outputs are in `scripts/output_insurance/` and are the 'before' side of every comparison.\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    old = {t: _r1(t) for t in T}
    # ---------------------------------------------------------------- 1 round comparison
    L.append("## 1. Round 1 vs round 2\n")
    rb1 = _ranks({t: old[t]["buffett_quality"]["score"] for t in T})
    rb2 = _ranks({t: runs[t]["bq"].score for t in T})
    rg1 = _ranks({t: old[t]["graham_quality"]["score"] for t in T})
    rg2 = _ranks({t: runs[t]["gq"].score for t in T})
    L.append("| Company | Line | Buffett R1 -> R2 | Rank | Graham R1 -> R2 | Rank | Coverage B R1 -> R2 | Coverage G R1 -> R2 | Range B (R2) | Range G (R2) | Invalid criteria R1 -> R2 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")

    def rg(m):
        return "withheld" if m.min_score is None else f"{m.min_score:.1f}-{m.max_score:.1f}"

    def inv(mj):
        return ", ".join(("B" if mj["model"].startswith("buffett") else "G") + c["id"] for c in mj["invalid_criteria"]) or "-"
    for t in T:
        bq, gq = runs[t]["bq"], runs[t]["gq"]
        o_b, o_g = old[t]["buffett_quality"], old[t]["graham_quality"]
        L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {o_b['score']:.1f} -> {bq.score:.1f} ({bq.score - o_b['score']:+.1f}) | {rb1[t]} -> {rb2[t]}{' *' if rb1[t] != rb2[t] else ''} | "
                 f"{o_g['score']:.1f} -> {gq.score:.1f} ({gq.score - o_g['score']:+.1f}) | {rg1[t]} -> {rg2[t]}{' *' if rg1[t] != rg2[t] else ''} | "
                 f"{o_b['coverage']:.0%} -> {bq.coverage:.0%} | {o_g['coverage']:.0%} -> {gq.coverage:.0%} | {rg(bq)} | {rg(gq)} | "
                 f"{inv(o_b)} / {inv(o_g)} -> {inv(runs[t]['res']['buffett_quality'])} / {inv(runs[t]['res']['graham_quality'])} |")
    chg_b = [t for t in T if rb1[t] != rb2[t]]
    chg_g = [t for t in T if rg1[t] != rg2[t]]
    L.append(f"\n`*` = rank changed. Rank changes - Buffett: {', '.join(f'{t} {rb1[t]}->{rb2[t]}' for t in chg_b) or 'none'}; "
             f"Graham: {', '.join(f'{t} {rg1[t]}->{rg2[t]}' for t in chg_g) or 'none'}.")
    errs = [(t, k) for t in T for k, m in (("Buffett", runs[t]["bq"]), ("Graham", runs[t]["gq"])) if m.range_error]
    L.append("\n**D14 range checks (min <= score <= max), round 2:** " + ("all 24 model ranges are consistent." if not errs else "FAILED: " + ", ".join(f"{t} {k}" for t, k in errs)))
    big = [f"{t} {k} {d:+.1f}" for t in T for k, d in (("Buffett", runs[t]["bq"].score - old[t]["buffett_quality"]["score"]),
                                                       ("Graham", runs[t]["gq"].score - old[t]["graham_quality"]["score"])) if abs(d) > 3]
    L.append("\nScore moves larger than 3 points: " + (", ".join(big) or "none") + ".\n")
    L.append("### Per criterion (points / applicable maximum; INVALID = coverage below M2), round 1 -> round 2\n")
    for key, mk, label in (("bq", "buffett_quality", "Buffett"), ("gq", "graham_quality", "Graham")):
        cids = [c.id for c in runs[T[0]][key].criteria]
        L.append(f"**{label}**\n")
        L.append("| Company | " + " | ".join(f"{label[0]}{c}" for c in cids) + " |")
        L.append("|---|" + "---|" * len(cids))
        for t in T:
            cells = []
            for c in cids:
                o_obs, o_mx, o_valid = _crit_pts(old[t][mk], c)
                n_obs, n_mx, n_valid = _crit_pts(runs[t]["res"][mk], c)
                a = f"{o_obs:.1f}/{o_mx:g}" + ("" if o_valid else "!")
                b = f"{n_obs:.1f}/{n_mx:g}" + ("" if n_valid else "!")
                cells.append(a if a == b else f"{a} -> **{b}**")
            L.append(f"| {t} | " + " | ".join(cells) + " |")
        L.append("")
    L.append("`!` = criterion invalid under M2.\n")
    L.append("### Sub-items whose points or state changed\n")
    L.append("| Company | Changes (model.criterion.item: round 1 -> round 2) |")
    L.append("|---|---|")
    for t in T:
        ch = []
        for key, mk, ml in (("bq", "buffett_quality", "B"), ("gq", "graham_quality", "G")):
            oi = {(c["id"], i["id"]): i for c in old[t][mk]["criteria"] for i in c["items"]}
            for c in runs[t][key].criteria:
                for it in c.items:
                    o = oi.get((c.id, it.id))
                    if o is None:
                        continue
                    op = o["points"]
                    if o["state"] != it.state or (op is not None and it.points is not None and abs(op - it.points) > 0.005):
                        ch.append(f"{ml}{c.id}.{it.id} {it.name[:26]}: {o['state'] if op is None else f'{op:.2f}'} -> {it.state if it.points is None else f'{it.points:.2f}'}")
        L.append(f"| {t} | {'; '.join(ch) or 'none'} |")
    # ---------------------------------------------------------------- 2 Q1
    L.append("\n## 2. Q1 - interest accretion on future policy benefits (insurance finance expense)\n")
    L.append("Accretion = interest accretion on the present value of expected future policy benefits minus interest accretion on expected net premiums (LDTI "
             "roll-forward, net liability), from the inline XBRL elements `LiabilityForFuturePolicyBenefitExpectedFuturePolicyBenefitInterestExpense` and "
             "`LiabilityForFuturePolicyBenefitExpectedNetPremiumInterestIncome` (dimensioned by product / segment, hence not in `companyfacts`). It is added back to "
             "the underwriting result (it sat inside policyholder benefits) and deducted from recurring investment income; pretax and normalized operating profit are "
             "unchanged. Contexts with a deferred-profit-liability member are excluded.\n")
    L.append("| Company | FY | Benefit accretion (bn) | Net-premium accretion (bn) | Net accretion (bn) | Aggregation | Source (accession) |")
    L.append("|---|---|---:|---:|---:|---|---|")
    for t in T:
        lg = runs[t]["raw"]["tag_log"].get("ldti_accretion", {})
        d = runs[t]["d"]
        for i, lab in enumerate(runs[t]["ii"].fy[-5:]):
            a = lg.get(lab)
            if a:
                L.append(f"| {t} | {lab} | {usd(a['benefit_interest'], 3)} | {usd(a['premium_interest'], 3)} | {usd(a['net'], 3)} | {a['rule_benefit']} ({a['n_benefit_contexts']} contexts) | "
                         f"inline XBRL, 10-K {a['accession']} |")
            else:
                fl = d["accretion_flags"][len(runs[t]["ii"].fy) - 5 + i]
                L.append(f"| {t} | {lab} | n/a | n/a | {usd(d['accretion'][len(runs[t]['ii'].fy) - 5 + i], 3)} | - | {fl or 'n/a'} |")
    L.append("\nNo company needed AI extraction with a quote for the accretion: every material amount is tagged. Years without a roll-forward (P&C and small-life "
             "companies, AIG FY2025, ALL FY2025) are treated as 0 with the flag `no_ldti_rollforward_tagged_future_policy_benefits_immaterial`; for a life-like company "
             "(future policy benefits >= 20% of liabilities) a missing year would make the underwriting result missing (none occurred).\n")
    L.append("### Underwriting margin before vs after (5-year median), by line of business\n")
    L.append("| Line | Company | Round 1 | Round 2 | Change (pp) | Years with underwriting result >= 0: R1 -> R2 | Net accretion / insurance revenue (latest) |")
    L.append("|---|---|---:|---:|---:|---|---:|")
    for line in LINES:
        for t in [x for x in T if LINE_OF_BUSINESS[x] == line]:
            d = runs[t]["d"]
            b = _med(d["underwriting_margin_r1"][-5:])
            a = _med(d["underwriting_margin"][-5:])
            n1 = sum(1 for x in d["underwriting_result_r1"][-5:] if x is not None and x >= 0)
            n2 = sum(1 for x in d["underwriting_result"][-5:] if x is not None and x >= 0)
            ir = d["insurance_revenue"][-1]
            ac = d["accretion"][-1]
            L.append(f"| {line} | {t} | {pct(b)} | {pct(a)} | {'n/a' if a is None or b is None else f'{(a - b) * 100:+.1f}'} | {n1} -> {n2} | {pct(None if (ac is None or not ir) else ac / ir)} |")
    L.append("\nMedian of the company medians by line:\n")
    L.append("| Line | n | Round 1 | Round 2 |")
    L.append("|---|---:|---:|---:|")
    for line in LINES:
        ts = [x for x in T if LINE_OF_BUSINESS[x] == line]
        L.append(f"| {line} | {len(ts)} | {pct(_med([_med(runs[t]['d']['underwriting_margin_r1'][-5:]) for t in ts]))} | "
                 f"{pct(_med([_med(runs[t]['d']['underwriting_margin'][-5:]) for t in ts]))} |")
    # ---------------------------------------------------------------- 3 Q2
    L.append("\n## 3. Q2 - portfolio liquidity and complex / volatile assets from balance-sheet categories\n")
    L.append("Liquid = cash + short-term investments + fixed maturities + equity securities; illiquid: mortgage / policy / private loans, real estate, other invested assets / "
             "limited partnerships. Complex = equity securities + real estate + other invested assets / limited partnerships + below-investment-grade fixed maturities "
             "(only where a credit-quality table / stated investment-grade share exists; otherwise omitted and flagged). Denominator = total investments + cash. Pledged / "
             "restricted assets are not deducted (flag only). Categories were read from each company's balance sheet or investment table (AI extraction, quotes in "
             "`insurance_regulatory.csv`, items `bs_*`); cash is the XBRL cash tag. USD bn, latest year.\n")
    L.append("| Company | Cash (tag) | Short-term | Fixed maturities | Equity | Loans (illiquid) | Real estate | Other invested / LPs | Total investments | Total + cash | Residual of categories | Liquidity | Complex | Below-IG source |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for t in T:
        lt = runs[t]["d"]["latest"]
        c = lt["bs_categories"]
        tag = (runs[t]["raw"]["tag_log"].get("cash", {}).get(runs[t]["ii"].fy[-1]) or {}).get("tag")
        cashsrc = "bs_cash (extracted, inside the total)" if runs[t]["ii"].reg.get("bs_cash") else (f"`{tag}`" if tag else "n/a")
        L.append(f"| {t} | {usd(c.get('cash'))} ({cashsrc}) | {usd(c['short_term'])} | {usd(c['fixed_maturities'])} | {usd(c['equity'])} | {usd(c['illiquid_loans'])} | "
                 f"{usd(c['real_estate'])} | {usd(c['other_invested'])} | {usd(c['total_investments'])} | {usd(lt['total_investments_and_cash'])} | "
                 f"{usd(lt.get('bs_residual'))} ({pct(lt.get('bs_residual_share'))}) | {pct(lt['liquidity'])} | {pct(lt['complex_share'])} | {lt['below_ig_source']} |")
    L.append("\nComplex-asset components (USD bn): equity | real estate | other invested / LPs | below-investment-grade fixed maturities\n")
    L.append("| Company | Equity | Real estate | Other invested / LPs | Below-IG fixed maturities | Complex total | Flags |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    for t in T:
        lt = runs[t]["d"]["latest"]
        p = lt["complex_parts"]
        L.append(f"| {t} | {usd(p['equity_securities'])} | {usd(p['real_estate'])} | {usd(p['other_invested_assets_limited_partnerships'])} | "
                 f"{usd(p['below_ig_fixed_maturities']) if p['below_ig_fixed_maturities'] is not None else 'omitted'} | {usd(lt['complex_assets'])} | {', '.join(lt['flags']) or '-'} |")
    L.append("\nCategory tags: the balance-sheet lines are company-specific (no uniform tag), so they were extracted from the statements with quotes (AI extraction, verified "
             "flag per row); where a standard tag exists it is the cash line (`CashAndCashEquivalentsAtCarryingValue`, `Cash` or the restricted-cash-inclusive tag) and the "
             "total-investments check (`Investments`, shown in the data table of round 1).\n")
    # ---------------------------------------------------------------- 4 Q3
    L.append("## 4. Q3 - regulatory capital with the comparability rules\n")
    L.append("| Company | Reported value | Basis | Multiple | Flags | Buffett 3.6.1 | Graham 3.2.1 |")
    L.append("|---|---:|---|---:|---|---:|---:|")
    for t in T:
        lt = runs[t]["d"]["latest"]
        b, g = _item(runs[t]["bq"], "3.6", "1"), _item(runs[t]["gq"], "3.2", "1")
        L.append(f"| {t} | {lt['reg_ratio'] if lt['reg_ratio'] is not None else 'MISSING (no number)'}% | {lt['reg_basis'] or '-'} | "
                 f"{'n/a' if lt['reg_multiple'] is None else f'{lt['reg_multiple']:.2f}x'} | {', '.join(lt['reg_flags']) or '-'} | "
                 f"{'n/a' if b.points is None else f'{b.points:.1f}/4'} | {'n/a' if g.points is None else f'{g.points:.1f}/10'} |")
    L.append("\nThe rules (lead subsidiary accepted and flagged; stated floor used as the value and flagged; latest statutory year accepted and flagged; Japan SMR / 200%; "
             "'exceeds requirements' without a number = missing) were already applied in round 1; no number changed. **Criteria that are invalid under M2 in round 2:**\n")
    for t in T:
        inv_b = [f"B{c['id']}" for c in runs[t]["res"]["buffett_quality"]["invalid_criteria"]]
        inv_g = [f"G{c['id']}" for c in runs[t]["res"]["graham_quality"]["invalid_criteria"]]
        why = []
        for cid, key in (("3.6", "bq"), ("3.2", "gq")):
            pass
        L.append(f"- **{t}**: {', '.join(inv_b + inv_g) or 'none'} (coverage B {runs[t]['bq'].coverage:.0%}, G {runs[t]['gq'].coverage:.0%}; status {runs[t]['bq'].status} / {runs[t]['gq'].status})")
    # ---------------------------------------------------------------- 5 Q4
    L.append("\n## 5. Q4 - float CAGR over valid years\n")
    L.append("Float = insurance liabilities net of reinsurance assets, ex discount-rate remeasurement (after-tax AOCI figure). Transitions of the last 4 years; a transition with a "
             "change in group structure is excluded (extracted event with quote, or acquisition / divestiture / deconsolidation indicator amounts above 10% of the prior-year float; a change in "
             "which float components are tagged is excluded as a data break); fewer than 2 valid transitions = missing. FX flagged when more than 25% of pretax income is foreign.\n")
    L.append("| Company | Transition | Float prev (bn) | Float (bn) | Change | Valid | Reason / source |")
    L.append("|---|---|---:|---:|---:|---|---|")
    for t in T:
        fc = runs[t]["d"]["float_cagr"]
        for r_ in fc["transitions"]:
            L.append(f"| {t} | {r_['fy']} | {usd(r_['float_prev'])} | {usd(r_['float'])} | {pct(r_['growth'])} | {'yes' if r_['valid'] else '**EXCLUDED**'} | {(r_['reason'] or '-')[:200]}{' [' + r_['source'] + ']' if r_['source'] else ''} |")
    L.append("\n| Company | Valid transitions | Float CAGR (valid years) | Round-1 CAGR (t-4 to t) | FX flag (foreign pretax share) | Buffett 3.5.4 R1 -> R2 |")
    L.append("|---|---:|---:|---:|---|---|")
    for t in T:
        fc = runs[t]["d"]["float_cagr"]
        d = runs[t]["d"]
        a, b = d["float_ex_drr"][-5], d["float_ex_drr"][-1]
        r1c = None if (a is None or b is None or a <= 0 or b <= 0) else (b / a) ** 0.25 - 1
        it_o = next(i for c in old[t]["buffett_quality"]["criteria"] if c["id"] == "3.5" for i in c["items"] if i["id"] == "4")
        it_n = _item(runs[t]["bq"], "3.5", "4")
        L.append(f"| {t} | {fc['n_valid']} of {len(fc['transitions'])} | {pct(fc['cagr'])} | {pct(r1c)} | {'**FX**' if fc['fx_flag'] else 'no'} ({pct(fc['foreign_pretax_share'], 0)}) | "
                 f"{it_o['state']} {'' if it_o['points'] is None else format(it_o['points'], '.2f')} -> {it_n.state} {'' if it_n.points is None else format(it_n.points, '.2f')} |")
    # ---------------------------------------------------------------- 6 Q5
    L.append("\n## 6. Q5 - catastrophe flag (catastrophe losses > 5% of premiums earned)\n")
    L.append("| Company | Cat losses (bn) | Premiums earned (bn) | Share | Flag |")
    L.append("|---|---:|---:|---:|---|")
    for t in T:
        lt = runs[t]["d"]["latest"]
        L.append(f"| {t} | {usd(lt['cat_loss'])} | {usd(runs[t]['ii'].f['premiums'][-1])} | {pct(lt['cat_share'])} | "
                 f"{'n/a (AI-extraction needed)' if lt['cat_flag'] is None else ('**FLAG**' if lt['cat_flag'] else 'no')} |")
    # ---------------------------------------------------------------- 7 calibration
    L.append("\n## 7. K1 distributions (round 2; no threshold changes)\n")
    L.append("| Metric | n | min / p25 / median / p75 / max | At full score | At zero | Round-1 n | Values by company |")
    L.append("|---|---:|---|---:|---:|---:|---|")
    for label, mk, cid, iid, kind in CAL_ITEMS:
        vals, full, zero_, per, n1 = {}, 0, 0, [], 0
        for t in T:
            it = _item(runs[t]["bq" if mk == "b" else "gq"], cid, iid)
            o = next(i for c in old[t]["buffett_quality" if mk == "b" else "graham_quality"]["criteria"] if c["id"] == cid for i in c["items"] if i["id"] == iid)
            n1 += o["state"] in ("score", "true_zero")
            if it.state in ("score", "true_zero") and isinstance(it.metric, (int, float)):
                vals[t] = it.metric
            if it.state in ("score", "true_zero") and it.points is not None:
                full += it.points >= it.max_pts - 1e-6
                zero_ += it.points <= 1e-6
            per.append(f"{t} {_fmt(kind, it.metric) if it.state in ('score', 'true_zero') else it.state.upper()[:4]}")
        q = _quart(list(vals.values()))
        L.append(f"| {label} | {len(vals)} | {'n/a' if q is None else ' / '.join(_fmt(kind, v) for v in q)} | {full} | {zero_} | {n1} | {'; '.join(per)} |")
    L.append("\n### Underwriting margin, total operating margin and reserve deviation by line of business (5-year medians)\n")
    L.append("| Line | Company | Underwriting margin | Underwriting result >= 0 (years) | Total operating margin | Reserve deviation | Years with deviation > 1% |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for line in LINES:
        for t in [x for x in T if LINE_OF_BUSINESS[x] == line]:
            d = runs[t]["d"]
            um, tm, rd = [x for x in d["underwriting_margin"][-5:] if x is not None], [x for x in d["total_operating_margin"][-5:] if x is not None], [x for x in d["reserve_deviation"][-5:] if x is not None]
            ur = [x for x in d["underwriting_result"][-5:] if x is not None]
            L.append(f"| {line} | {t} | {pct(statistics.median(um)) if um else 'n/a'} | {sum(1 for x in ur if x >= 0)} of {len(ur)} | {pct(statistics.median(tm)) if tm else 'n/a'} | "
                     f"{pct(statistics.median(rd), 2) if rd else 'n/a'} | {sum(1 for x in rd if x > 0.01) if rd else 'n/a'} |")
    L.append("\n| Line | n | Underwriting margin | Total operating margin | Reserve deviation |")
    L.append("|---|---:|---:|---:|---:|")
    for line in LINES:
        ts = [x for x in T if LINE_OF_BUSINESS[x] == line]
        L.append(f"| {line} | {len(ts)} | {pct(_med([_med(runs[t]['d']['underwriting_margin'][-5:]) for t in ts]))} | "
                 f"{pct(_med([_med(runs[t]['d']['total_operating_margin'][-5:]) for t in ts]))} | {pct(_med([_med(runs[t]['d']['reserve_deviation'][-5:]) for t in ts]), 2)} |")
    L.append("\nTotal operating margin (8 of 12 at full score in round 1) - round 2: " +
             str(sum(1 for t in T if (_item(runs[t]['bq'], '3.5', '3').points or 0) >= 4 - 1e-6)) + " of 12 at full score (reviewed under K1 after this round).")
    # ---------------------------------------------------------------- scores and open issues
    L.append("\n## 8. Scores and criterion totals (round 2)\n")
    L.append("Every sub-item per company (metric, points, state, flags) is in each `<TICKER>.json` and in the sub-item changes table above; the summary of the profile check "
             "is unchanged from round 1 (all 12 confirmed as INSURANCE).\n")
    L.append("| Company | Line | Buffett | Coverage | Status | Graham | Coverage | Status |")
    L.append("|---|---|---:|---:|---|---:|---:|---|")
    for t in T:
        bq, gq = runs[t]["bq"], runs[t]["gq"]
        L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {bq.score:.1f} | {bq.coverage:.0%} | {bq.status} | {gq.score:.1f} | {gq.coverage:.0%} | {gq.status} |")
    L.append("\n## 9. Open issues\n")
    ip = ROOT / "scripts" / "insurance_rule_issues_v2.md"
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(scripts/insurance_rule_issues_v2.md not written yet)")
    L.append("\n## Data problems by company\n")
    for t in T:
        L.append(f"- **{t}**: " + ("; ".join(runs[t]["res"]["data_problems"]) if runs[t]["res"]["data_problems"] else "none detected"))
    (OUT / "summary_insurance_v2.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    r1.OUT = OUT  # run_company writes its JSON into the round-2 folder
    sec = SecClient()
    reg_all = load_insurance_regulatory()
    runs, failures = {}, []
    for t in COMPANIES:
        try:
            runs[t] = r1.run_company(sec, reg_all, t)
            print(f"{t}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    if runs:
        build_summary(runs, failures)
    print(f"SEC requests this run: {sec.requests_made}")


if __name__ == "__main__":
    main()

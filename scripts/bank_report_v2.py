"""summary_banks_v2.md for the bank regression round (spec 2026-10-12_21-05)."""
from __future__ import annotations

import json
import statistics
from datetime import date
from pathlib import Path

from run_scoring_test import cell, model_cell, pct

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "output_banks"
ROUND1 = ROOT / "scripts" / "output_banks_round1"
RULE_ISSUES = ROOT / "scripts" / "bank_rule_issues_v2.md"
SPEC = "docs/scoring/ValueCompass_Bank_Rules_2026-10-12_21-05_EN.md"


def _v(x, nd=2):
    return "n/a" if x is None else (x if isinstance(x, str) else f"{x:,.{nd}f}")


def _pct(x, nd=1):
    return "n/a" if x is None or isinstance(x, str) else f"{x * 100:.{nd}f}%"


def _ps(p):
    ps = (p or {}).get("price_score") or {}
    return "n/a" if ps.get("points") is None else f"{ps['points']:.1f}"


def _buy(b):
    b = b or {}
    if b.get("state") == "computed":
        return f"{b['buy_price']:.2f}"
    if b.get("state") == "not_suitable":
        return "not suitable"
    if b:
        info = b.get("informational_buy_price_ignoring_coverage")
        return "none (coverage)" + (f"; info {info:.2f}" if info else "")
    return "-"


def _flags(res, k=6):
    out = []
    for key in ("buffett_quality", "graham_quality"):
        for c in res[key]["criteria"]:
            for it in c["items"]:
                for fl in it["flags"]:
                    tag = fl.split(" (")[0]
                    if tag not in out and tag not in ("partial_window", "D2", "D7", "D8", "D6", "thresholds_to_recalibrate_D11",
                                                       "temporary_thresholds_D11", "ppnr_as_reported_one_offs_not_adjusted",
                                                       "pretax_earning_power_test_D1"):
                        out.append(tag)
    for fl in res["buffett_price"].get("flags", []):
        tag = fl.split(" (")[0]
        if tag not in out:
            out.append(tag)
    return out[:k]


def _rng(mj):
    if mj.get("range_min") is None:
        return "withheld (check failed)" if mj.get("range_error") else "n/a"
    return f"{mj['range_min']:.1f}-{mj['range_max']:.1f}"


def _quart(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    if len(vals) < 2:
        return (vals[0],) * 5
    q = statistics.quantiles(vals, n=4, method="inclusive")
    return vals[0], q[0], q[1], q[2], vals[-1]


def build_summary_v2(rows, reg_all, failures, banks):
    L = []
    L.append(f"# ValueCompass BANK regression round (v2) - {date.today().isoformat()}\n")
    L.append(f"Spec: `{SPEC}` (supersedes the 13-10 file; adds D10-D15 and bank pricing v2). All 12 banks are recomputed under this "
             "single version. Data: SEC XBRL (10 fiscal years), FY2025 10-K text extraction plus the D12 public LCR disclosures "
             "(`scripts/bank_regulatory.csv`, quotes verified), yfinance prices. No DB; AI questions stay `ai_pending` "
             "(excluded from validity and coverage, widening the range only). Shared coverage code now implements D14 for all profiles.\n")
    if failures:
        L.append("**Failed banks:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")

    # ------------------------------------------------------------------ (a) results
    L.append("## a. Results (four scores, coverage, valid ranges, flags)\n")
    L.append("Range = D14 range over the same valid criteria as the score (`withheld` if min <= score <= max fails).\n")
    L.append("| Bank | Path | Buffett quality | Range | Coverage | Buffett value v2 / price | Price score | Buy price | "
             "Graham quality | Range | Coverage | Graham value (10y EPS) | Price score | Buy price | Main flags |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        bqj, gqj = res["buffett_quality"], res["graham_quality"]
        bval = _v(bp.get("fair_value")) if bp.get("state") == "valued" else f"cannot be valued ({bp.get('reason', '')})"
        gval = _v(gp.get("value")) if gp.get("state") == "valued" else f"cannot be valued ({gp.get('reason', '')})"
        L.append(f"| {res['ticker']} | {res['path']['path']} | {_v(bqj['score'], 1)} ({bqj['status']}) | {_rng(bqj)} | {_pct(bqj['coverage'], 0)} | "
                 f"{bval} / {_v(res['price']['current'])} | {_ps(bp)} | {_buy(bp.get('buy_price'))} | "
                 f"{_v(gqj['score'], 1)} ({gqj['status']}) | {_rng(gqj)} | {_pct(gqj['coverage'], 0)} | {gval} | {_ps(gp)} | "
                 f"{_buy(gp.get('buy_price'))} | {', '.join(_flags(res))} |")
    errs = [(res['ticker'], m) for res, *_ in rows for m in ("buffett_quality", "graham_quality") if res[m].get("range_error")]
    L.append("\n**D14 range checks:** " + ("all 24 model ranges satisfy min <= score <= max." if not errs else
                                           "FAILED for " + ", ".join(f"{t} {m}" for t, m in errs)))
    L.append("\n**Invalid / pending criteria**\n")
    for res, *_ in rows:
        inv = [f"B{c['id']}" for c in res["buffett_quality"]["invalid_criteria"]] + [f"G{c['id']}" for c in res["graham_quality"]["invalid_criteria"]]
        L.append(f"- {res['ticker']}: invalid: {', '.join(inv) or 'none'}; pending (all-AI): "
                 f"{', '.join(['B' + c for c in res['buffett_quality']['pending_criteria']]) or 'none'}")

    # ------------------------------------------------------------------ (b) round 1 -> round 2
    L.append("\n## b. Round 1 -> round 2 (per bank)\n")
    L.append("Round 1 = the 13-10 specification. Buffer: lower ratio vs the single supplied requirement -> D10 (min over approaches of ratio - reported "
             "requirement). Problem loans: NPL rate (nonaccrual + 90+ accruing) -> D11 nonaccrual rate. Deposit funding: without -> with repo (D15).\n")
    L.append("| Bank | Buffett quality | Graham quality | Capital buffer (pp) | NPL rate -> nonaccrual rate | ACL/NPL -> ACL/nonaccrual | "
             "Coverage Buffett | Coverage Graham | Deposit funding | LCR |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        t = res["ticker"]
        f1 = ROUND1 / f"{t}.json"
        if not f1.exists():
            continue
        o = json.loads(f1.read_text(encoding="utf-8"))
        ol, nl = o["latest"], res["latest"]
        o_rate = None if not ol.get("npl") or not ol.get("loans_latest") else ol["npl"] / ol["loans_latest"]
        o_cov = None if not ol.get("npl") or ol.get("acl") is None else ol["acl"] / ol["npl"]
        o_df_series = o["derived"].get("deposit_funding", {})
        o_df = list(o_df_series.values())[-1] if o_df_series else None
        o_lcr = ol.get("lcr")
        L.append(f"| {t} | {_v(o['buffett_quality']['score'], 1)} -> {_v(res['buffett_quality']['score'], 1)} | "
                 f"{_v(o['graham_quality']['score'], 1)} -> {_v(res['graham_quality']['score'], 1)} | "
                 f"{_v(ol.get('capital_buffer'))} -> {_v(nl.get('capital_buffer'))} ({nl.get('approach')}) | "
                 f"{_pct(o_rate, 2)} -> {_pct(nl.get('nonaccrual_rate'), 2)} | "
                 f"{'n/a' if o_cov is None else f'{o_cov:.0%}'} -> {'n/a' if nl.get('acl_to_nonaccrual') is None else f'{nl['acl_to_nonaccrual']:.0%}'} | "
                 f"{_pct(o['buffett_quality']['coverage'], 0)} -> {_pct(res['buffett_quality']['coverage'], 0)} | "
                 f"{_pct(o['graham_quality']['coverage'], 0)} -> {_pct(res['graham_quality']['coverage'], 0)} | "
                 f"{_pct(o_df, 1)} -> {_pct(nl.get('deposit_funding'), 1)} | {o_lcr} -> {nl['lcr']} |")

    # ------------------------------------------------------------------ (c) valuation comparison
    L.append("\n## c. Valuation comparison per bank\n")
    L.append("Buffett v1 = single-stage justified P/TBV (13-10 file); v2 = two-stage excess-returns on total TCE (base case). Sensitivity = min-max of "
             "{base, ROTCE erosion to 10% over 10 years, ROTCE +1pp, ROTCE -1pp}. Graham 3y = Graham Number with 3-year EPS (v1); 10y = 10-year EPS (v2). "
             "Price scores use the Buffett / classic Graham scales. Implied return = discount rate that equates the model value with the price.\n")
    L.append("| Bank | Price | TBVPS | P/TBV | Buffett v1 | Buffett v2 | Sensitivity range | Justified P/TBV v2 (v1) | Graham 3y EPS | Graham 10y EPS | "
             "Price score B v1 / v2 | Price score G 3y / 10y | Implied return v2 (v1) | Implied ROTCE v2 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        v1, g3 = bp["v1_single_stage"], gp["v1_3y_eps"]
        tb = d["tbvps"][-1]
        sr = bp.get("sensitivity_range")
        jp2 = bp.get("justified_ptbv")
        jp1 = v1.get("justified_ptbv")
        ir2, ir1 = bp.get("implied_return"), v1.get("implied_return")
        irs = (_pct(ir2, 1) if isinstance(ir2, float) else (ir2 or "n/a"))
        irot = bp.get("implied_rotce")
        L.append(f"| {res['ticker']} | {_v(res['price']['current'])} | {_v(tb)} | "
                 f"{'n/a' if not tb else f'{res['price']['current'] / tb:.2f}x'} | {_v(v1.get('fair_value'))} | {_v(bp.get('fair_value'))} | "
                 f"{'n/a' if not sr else f'{sr[0]:,.1f} - {sr[1]:,.1f}'} | {'n/a' if jp2 is None else f'{jp2:.2f}x'} "
                 f"({'n/a' if jp1 is None else f'{jp1:.2f}x'}) | {_v(g3.get('value'))} | {_v(gp.get('value'))} | "
                 f"{_ps(v1)} / {_ps(bp)} | {_ps(g3)} / {_ps(gp)} | {irs} ({_pct(ir1, 1)}) | "
                 f"{_pct(irot, 1) if isinstance(irot, float) else (irot or 'n/a')} |")
    L.append("\n**Two-stage inputs**\n")
    L.append("| Bank | TCE0 (bn) | ROTCE_norm | Payout | Stage-1 growth g1 | Growth gate | PV of residual income (bn) | PV terminal value (bn) | Erosion | +1pp | -1pp |")
    L.append("|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|")
    for res, bi, d, bq, bp, gq, gp in rows:
        if bp.get("state") != "valued":
            L.append(f"| {res['ticker']} | {_v(bp.get('tce0', 0) / 1e9 if bp.get('tce0') else None)} | cannot be valued: {bp.get('reason')} |  |  |  |  |  |  |  |  |")
            continue
        sn = bp["sensitivity"]
        gate = bp["growth_gate"]
        L.append(f"| {res['ticker']} | {bp['tce0'] / 1e9:,.1f} | {_pct(bp['rotce_norm'])} | {_pct(bp['payout'], 0)} | {_pct(bp['g1'])} | "
                 f"{'pass' if gate['passed'] else 'FAIL: ' + '; '.join(gate['failing'])} | {bp['pv_residual_income'] / 1e9:,.1f} | "
                 f"{bp['pv_terminal_value'] / 1e9:,.1f} | {sn['erosion']:,.1f} | {sn['rotce_plus_1pp']:,.1f} | {sn['rotce_minus_1pp']:,.1f} |")

    # ------------------------------------------------------------------ (d) calibration data
    L.append("\n## d. Calibration data\n")
    L.append("Values are the latest-year (or 5-year median) metric the scorecard uses. The last block lists the annual values behind the "
             "time-series metrics.\n")
    metrics = []
    for res, bi, d, bq, bp, gq, gp in rows:
        lt = d["latest"]
        ro = [x for x in d["rotce"][-5:] if x is not None]
        roa = [x for x in d["roa"][-5:] if x is not None]
        ppnr = [x for x in d["ppnr"][-5:] if x is not None]
        loans = d["loans"][-1]
        stress = None if (len(ppnr) < 3 or not loans) else statistics.median(ppnr) / (0.03 * loans)
        nco = [x for x in d["nco_rate"] if x is not None]
        metrics.append({"t": res["ticker"], "rotce": statistics.median(ro) if len(ro) >= 3 else None,
                        "roa": statistics.median(roa) if len(roa) >= 3 else None, "buffer": lt["capital_buffer"],
                        "nonaccrual": lt["nonaccrual_rate"], "coverage": lt["acl_to_nonaccrual"],
                        "dfund": lt.get("deposit_funding") if res["path"]["path"] != "1b" else None, "stress": stress,
                        "worst_nco": max(nco) if nco else None, "n_nco": len(nco), "ro_list": ro, "roa_list": roa,
                        "nco_list": [(bi.fy[i], d["nco_rate"][i]) for i in range(bi.n) if d["nco_rate"][i] is not None]})
    cols = [("rotce", "ROTCE 5y median", lambda x: _pct(x, 1)), ("roa", "ROA 5y median", lambda x: _pct(x, 2)),
            ("buffer", "Capital buffer (pp, D10)", lambda x: _v(x)), ("nonaccrual", "Nonaccrual rate", lambda x: _pct(x, 2)),
            ("coverage", "ACL / nonaccrual", lambda x: 'n/a' if x is None else f'{x:.0%}'),
            ("dfund", "Deposit funding (D15)", lambda x: _pct(x, 1)), ("stress", "Stress coverage (x)", lambda x: _v(x)),
            ("worst_nco", "Worst NCO rate", lambda x: _pct(x, 2))]
    L.append("| Bank | " + " | ".join(c[1] for c in cols) + " | NCO years |")
    L.append("|---|" + "---:|" * (len(cols) + 1))
    for m in metrics:
        L.append(f"| {m['t']} | " + " | ".join(c[2](m[c[0]]) for c in cols) + f" | {m['n_nco']} |")
    L.append("| **min / p25 / median / p75 / max** | " + " | ".join(
        (lambda q: "n/a" if q is None else " / ".join(c[2](v) for v in q))(_quart([m[c[0]] for m in metrics])) for c in cols) + " | |")
    thr = {"rotce": (0.06, 0.12, 0.18), "roa": (0.005, 0.0125), "buffer": (0.0, 2.5, 3.0), "nonaccrual": (0.005, 0.03),
           "coverage": (0.75, 1.5, 2.0), "dfund": (0.5, 0.8), "stress": (0.5, 1.0), "worst_nco": (0.005, 0.03)}
    L.append("\n**Banks at / beyond the current full-score threshold** (how much each threshold separates banks)\n")
    full = {"rotce": (lambda x: x >= 0.18, ">= 18%"), "roa": (lambda x: x >= 0.0125, ">= 1.25%"), "buffer": (lambda x: x >= 3.0, ">= 3 pp (Graham; Buffett 2.5)"),
            "nonaccrual": (lambda x: x <= 0.005, "<= 0.5%"), "coverage": (lambda x: x >= 1.5, ">= 150% (Buffett; Graham 200%)"),
            "dfund": (lambda x: x >= 0.8, ">= 80%"), "stress": (lambda x: x >= 1.0, ">= 1.0x"), "worst_nco": (lambda x: x <= 0.005, "<= 0.5%")}
    for k, (fn, label) in full.items():
        have = [m for m in metrics if m[k] is not None]
        hit = [m["t"] for m in have if fn(m[k])]
        L.append(f"- **{dict((c[0], c[1]) for c in cols)[k]}** ({label}): {len(hit)} of {len(have)} banks - {', '.join(hit) or 'none'}")
    L.append("\n**Annual values**\n")
    L.append("| Bank | ROTCE (last 5 FY, oldest first) | ROA (last 5 FY) | NCO rate by year (all available years) |")
    L.append("|---|---|---|---|")
    for m in metrics:
        L.append(f"| {m['t']} | " + ", ".join(f"{x * 100:.1f}%" for x in m["ro_list"]) + " | " + ", ".join(f"{x * 100:.2f}%" for x in m["roa_list"]) +
                 " | " + ", ".join(f"{fy[2:]}:{r * 100:.2f}%" for fy, r in m["nco_list"]) + " |")

    # ------------------------------------------------------------------ D13 / D15 / D10 / D12 detail
    L.append("\n## Decision detail\n")
    L.append("### D13 - banks that need FR Y-9C for charge-off history (not implemented; kept as is)\n")
    L.append("| Bank | NCO-rate years | Effect on Graham 3.3 #1 | Effect on Buffett 3.6 #2 |")
    L.append("|---|---:|---|---|")
    for m in metrics:
        n = m["n_nco"]
        eff = "missing (needs 6+ years)" if n < 6 else ("capped at 3 of 5 points (6-9 years)" if n < 10 else "full history")
        e2 = "missing (needs 3 of the last 5 years)" if len([1 for fy, r in m["nco_list"][-5:]]) < 3 else "computed"
        L.append(f"| {m['t']} | {n} | {eff} | {e2} |")
    L.append("\n### D15 - balance-sheet lines in the deposit-funding denominator (each counted once, latest year, USD mm)\n")
    L.append("| Bank | Deposits | Repo / securities lending | Short-term borrowings | Long-term debt (incl. FHLB where not separate) | Deposit funding | Lines included (notes) |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        lt = d["latest"]
        if res["path"]["path"] == "1b":
            L.append(f"| {res['ticker']} | path 1b: deposit funding and stability not applicable | | | | n/a | |")
            continue
        ro = lt.get("funding_roles") or {}
        lines = "; ".join(f"{x['line']}" + (f" [{x['note']}]" if x['note'] else "") for x in lt.get("funding_lines", []))
        L.append(f"| {res['ticker']} | {ro.get('deposits', 0) / 1e6:,.0f} | {ro.get('repo', 0) / 1e6:,.0f} | {ro.get('short_term', 0) / 1e6:,.0f} | "
                 f"{ro.get('long_term', 0) / 1e6:,.0f} | {_pct(lt.get('deposit_funding'), 1)} | {lines} |")
    L.append("\n### D10 - required CET1 per approach (as reported; fallback = Federal Reserve table value where only the SCB is reported)\n")
    L.append("| Bank | Standardized ratio / requirement / buffer | Advanced ratio / requirement / buffer | Binding approach | Buffer used | Round-1 buffer | Source of requirement |")
    L.append("|---|---|---|---|---:|---:|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        lt = d["latest"]
        bb = lt["buffer_by_approach"]
        reg = reg_all.get(res["ticker"], {})
        src = []
        for a in ("standardized", "advanced"):
            r_ = reg.get(f"cet1_required_{a}")
            if r_:
                src.append(f"{a[:3]}: " + ("FALLBACK Fed table (bank reports SCB only)" if "FALLBACK" in r_["note"] else "reported"))
        L.append(f"| {res['ticker']} | {_v(lt['cet1_std'])} / {_v(lt['required_std'])} / {_v(bb.get('standardized'))} | "
                 f"{_v(lt['cet1_adv'])} / {_v(lt['required_adv'])} / {_v(bb.get('advanced'))} | {lt['approach']} | {_v(lt['capital_buffer'])} | "
                 f"{_v(lt['buffer_round1'])} | {'; '.join(src)} |")
    L.append("\n### D12 - LCR\n")
    L.append("| Bank | LCR used | Treatment | Source |")
    L.append("|---|---|---|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        lt = d["latest"]
        lcr = lt["lcr"]
        tr = {"NA": "not applicable (exemption evidenced in the 10-K)", "MISSING": "MISSING (no numeric value found)"}.get(lcr, "scored")
        L.append(f"| {res['ticker']} | {lcr} | {tr} | {lt.get('lcr_source')} {('- ' + lt['lcr_note']) if lt.get('lcr_note') else ''} |")

    # ------------------------------------------------------------------ heat-map
    L.append("\n## Sub-item heat-map\n")
    L.append("`AI` = ai_pending, `n/a` = not applicable, `MISS` = missing data, `0•` = true zero.\n")
    for key, label, groups in (("buffett_quality", "Buffett", [("3.1", "3.2", "3.3", "3.4"), ("3.5", "3.6", "3.7", "3.8")]),
                               ("graham_quality", "Graham", [("3.1", "3.2", "3.3", "3.4"), ("3.5", "3.6", "3.7", "3.8")])):
        for grp in groups:
            cols_ = []
            for c in rows[0][0][key]["criteria"]:
                if c["id"] in grp:
                    for it in c["items"]:
                        cols_.append((c["id"], it["id"], it["max_pts"]))
            L.append(f"\n**{label} quality {grp[0]}-{grp[-1]}**\n")
            L.append("| Bank | " + " | ".join(f"{a}.{b} ({m:g})" for a, b, m in cols_) + " |")
            L.append("|---|" + "---:|" * len(cols_))
            for res, *_ in rows:
                cmap = {(c["id"], it["id"]): it for c in res[key]["criteria"] for it in c["items"]}
                L.append(f"| {res['ticker']} | " + " | ".join(cell(cmap[(a, b)]) for a, b, _ in cols_) + " |")

    # ------------------------------------------------------------------ extraction rows added this round
    L.append("\n## Extraction rows added or changed this round (exact quotes; the full table is `scripts/bank_regulatory.csv`)\n")
    L.append("| Bank | Item | Value | Unit | Source | Exact quote | Verified | Note |")
    L.append("|---|---|---:|---|---|---|---|---|")
    for t in banks:
        for item, r_ in reg_all.get(t, {}).items():
            if item.startswith(("cet1_required_", "funding:")) or item == "lcr_q4_average":
                q = r_["quote"].replace("|", "\\|")
                L.append(f"| {t} | {item} | {r_['value']} | {r_['unit']} | {r_['section']} | {q} | {'yes' if r_['verified'] else 'NO'} | {r_['note']} |")

    L.append("\n## e. Data problems\n")
    for res, *_ in rows:
        L.append(f"\n**{res['ticker']}**\n")
        L += [f"- {x}" for x in res["data_problems"]] if res["data_problems"] else ["- none detected"]
    L.append("\n## Rule issues\n")
    L.append(RULE_ISSUES.read_text(encoding="utf-8") if RULE_ISSUES.exists() else "(scripts/bank_rule_issues_v2.md not written yet)")
    (OUT / "summary_banks_v2.md").write_text("\n".join(L) + "\n", encoding="utf-8")

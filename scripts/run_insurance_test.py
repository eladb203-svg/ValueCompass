"""First INSURANCE test round (spec 2026-10-13_11-00): quality only, no pricing. 12 US insurers, SEC XBRL + 10-K text extraction.

Usage:  .venv/Scripts/python -X utf8 scripts/run_insurance_test.py [TICKER ...]
Outputs (untracked): scripts/output_insurance/<TICKER>.json and summary_insurance.md. No DB, no AI calls (AI questions stay ai_pending).
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

from run_scoring_test import jsonable, model_json  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.insurance_facts import INS_FIELDS, build_insurance_series, load_insurance_regulatory  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring import insurance as INS
from src.scoring.router import INS_I, default_tables, insurance_liabilities_ratio, sic_set
from router_runner import route_company  # noqa: E402
from src.scoring.insurance import LINE_OF_BUSINESS, InsuranceInputs, score_insurance  # noqa: E402

OUT = ROOT / "scripts" / "output_insurance"
COMPANIES = ["CB", "TRV", "PGR", "ALL", "WRB", "CINF", "RNR", "MET", "PRU", "AFL", "AIG", "HIG"]
SPEC = "docs/scoring/ValueCompass_Insurance_Rules_2026-10-13_11-00_EN.md"
INSURANCE_SIC = tuple(sorted(str(x) for x in sic_set(default_tables(), INS_I)))   # from the router's SIC table (Part B.1)
MODEL_VERSION = "insurance-rules-2026-10-13_11-00 on general model 1.0 + D14 + C13 (default ON)"


# ------------------------------------------------------------------ helpers
def usd(x, nd=2):
    return "n/a" if x is None else f"{x / 1e9:,.{nd}f}"


def pct(x, nd=1):
    return "n/a" if x is None or isinstance(x, str) else f"{x * 100:.{nd}f}%"


def fx(x, nd=2):
    return "n/a" if x is None or isinstance(x, str) else f"{x:,.{nd}f}"


def profile_check(raw, ii):
    f, n = raw["f"], len(raw["labels"])
    i = n - 1
    liab = f["liabilities"][i]
    claims = f["claims_gross"][i] if f["claims_gross"][i] is not None else f["claims_net"][i]
    comps = {"claims liability (LIC)": claims, "future policy benefits": f["fpb"][i], "policyholder account balances": f["pab"][i],
             "unearned premiums": f["unearned"][i], "separate accounts liability": f["separate_accounts"][i],
             "market risk benefit liability": f["mrb_liability"][i]}
    tot, ratio, _missing = insurance_liabilities_ratio(comps, liab)   # the router's ratio (single implementation)
    industry = str(raw.get("sic")) in INSURANCE_SIC
    return {"total_liabilities": liab, "components": comps, "insurance_liabilities": tot, "ratio": ratio, "sic": raw.get("sic"),
            "sic_description": raw.get("sic_description"), "industry_is_insurance": industry,
            "is_insurance": bool(industry and ratio is not None and ratio >= INS.INSURANCE_TEST),
            "missing_components": [k for k, v in comps.items() if v is None]}


def run_company(sec, reg_all, t):
    raw = build_insurance_series(sec, t, price_provider.get_splits(t))
    pr = price_provider.load_prices(t, raw["ends"], raw["labels"])
    ii = InsuranceInputs(ticker=t, name=raw["name"], fy=raw["labels"], end=raw["ends"], f=raw["f"], reg=reg_all.get(t, {}),
                         price_current=pr["current"], price_avg=pr["avg"], first_annual_report=raw["first_annual_report"], as_of=date.today(),
                         flags=list(raw["flags"]), data_problems=list(raw["problems"]) + list(pr["notes"]), tag_log=raw["tag_log"])
    prof = profile_check(raw, ii)
    rr = route_company(sec, t, f=raw["f"], labels=raw["labels"], ends=raw["ends"])
    sc = score_insurance(ii)
    d, bq, gq = sc["derived"], sc["buffett_quality"], sc["graham_quality"]
    res = {"ticker": t, "name": raw["name"], "cik": raw["cik"], "profile": "INSURANCE", "line_of_business": LINE_OF_BUSINESS[t],
           "profile_check": prof, "profile_router": rr.to_jsonable(), "scoring_model_version": MODEL_VERSION, "as_of": date.today(),
           "fiscal_years": dict(zip(ii.fy, ii.end)), "financials": {k: dict(zip(ii.fy, v)) for k, v in ii.f.items()},
           "derived": {k: dict(zip(ii.fy, v)) for k, v in d.items() if isinstance(v, list) and len(v) == ii.n},
           "latest": d["latest"], "buffett_quality": model_json(bq), "graham_quality": model_json(gq),
           "tag_log_per_field_per_year": raw["tag_log"], "extraction_rows": {k: v for k, v in ii.reg.items()},
           "flags": ii.flags, "data_problems": list(dict.fromkeys(ii.data_problems))}
    (OUT / f"{t}.json").write_text(json.dumps(jsonable(res), indent=1, ensure_ascii=False), encoding="utf-8")
    return {"res": res, "ii": ii, "d": d, "bq": bq, "gq": gq, "prof": prof, "raw": raw}


def _item(model, cid, iid):
    return next(i for c in model.criteria if c.id == cid for i in c.items if i.id == iid)


def _cell(it):
    if it.state == "not_applicable":
        return "n/a"
    if it.state == "missing":
        return "MISS"
    if it.state == "ai_pending":
        return "AI"
    return f"{it.points:.2f}"


def _tagsum(ii, field, raw):
    lg = raw["tag_log"].get(field, {})
    tags = {}
    for lab in ii.fy[-5:]:
        tg = (lg.get(lab) or {}).get("tag")
        tags.setdefault(tg or "-", []).append(lab[2:])
    if list(tags) == ["-"]:
        return "AI-extraction needed"
    out = []
    for k, v in tags.items():
        short = k if len(k) < 58 else k[:55] + "..."
        out.append(f"`{short}`" + ("" if len(tags) == 1 else f" ({','.join(v)})") if k != "-" else f"AI-extraction needed ({','.join(v)})")
    return "; ".join(out)


def _quart(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    if len(vals) < 2:
        return (vals[0],) * 5
    q = statistics.quantiles(vals, n=4, method="inclusive")
    return vals[0], q[0], q[1], q[2], vals[-1]


# ------------------------------------------------------------------ report
CAL_ITEMS = [  # (label, model, criterion, item, formatter)
    ("Operating ROE, 5y median", "b", "3.4", "1", "pct"), ("Worst-year operating ROE", "b", "3.4", "2", "pct"),
    ("Underwriting margin, 5y median", "b", "3.5", "1", "pct"), ("Years with underwriting result >= 0 (of 5)", "b", "3.5", "2", "num"),
    ("Total operating margin, 5y median", "b", "3.5", "3", "pct"), ("Float CAGR (cost-free condition applied)", "b", "3.5", "4", "pct"),
    ("Regulatory capital multiple (Buffett 3.6.1)", "b", "3.6", "1", "x"), ("Reserve deviation, 5y median (Buffett 3.6.2)", "b", "3.6", "2", "pct2"),
    ("Financial leverage (Buffett 3.6.3)", "b", "3.6", "3", "pct"), ("Regulatory capital multiple (Graham 3.2.1)", "g", "3.2", "1", "x"),
    ("Portfolio liquidity (Graham 3.2.2)", "g", "3.2", "2", "pct"), ("Reserve deviation, 5y median (Graham 3.3.1)", "g", "3.3", "1", "pct2"),
    ("Financial leverage (Graham 3.3.2)", "g", "3.3", "2", "pct"), ("Adjusted TBVPS CAGR (Graham 3.7.1)", "g", "3.7", "1", "pct"),
    ("Investment-grade share of fixed income (Graham 3.7.2)", "g", "3.7", "2", "pct"), ("Complex / volatile assets (Graham 3.7.3)", "g", "3.7", "3", "pct"),
    ("Reliance on non-recurring gains (Graham 3.8.1)", "g", "3.8", "1", "pct"), ("Margin transitions without a >2pp fall (Graham 3.8.2)", "g", "3.8", "2", "num"),
    ("Dilution t vs t-4 (Graham 3.8.3)", "g", "3.8", "3", "pct"),
]


def _fmt(kind, v):
    if v is None or isinstance(v, str):
        return "n/a"
    return {"pct": pct(v, 1), "pct2": pct(v, 2), "x": f"{v:.2f}x", "num": f"{v:.1f}"}[kind]


def build_summary(runs, failures):
    T = list(runs)
    L = [f"# ValueCompass INSURANCE test round 1 (quality only) - {date.today().isoformat()}\n",
         f"Spec: `{SPEC}`. 12 US insurers; SEC XBRL (10 fiscal years, FY2025 10-K) + extraction from the 10-K text (`scripts/insurance_regulatory.csv`, "
         "exact quotes, verified flag, location). No pricing; no DB; AI questions stay `ai_pending` (ignored by validity and coverage, widen the "
         "range only). Step 0 applied: C13 is ON by default, C12 removed from scoring (alternative current ratio display-only), segment-sum "
         "convention for the claims liability approved (flagged); thresholds of section 4 are used as written (K1: no threshold changes).\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    # ---------------------------------------------------------------- 1 profile
    L.append("## 1. Profile check (insurance liabilities / total liabilities, latest year; test: industry Insurance and ratio >= 50%)\n")
    L.append("Insurance liabilities = claims liability (gross, else net) + future policy benefits + policyholder account balances + unearned premiums + "
             "separate-accounts liability + market-risk-benefit liability (standard us-gaap tags; USD bn; components not tagged for a company are absent from its sum).\n")
    L.append("| Company | Line | SIC | FY | Total liabilities | Insurance liabilities | Ratio | INSURANCE | Components not tagged |")
    L.append("|---|---|---|---|---:|---:|---:|---|---|")
    for t in T:
        p = runs[t]["prof"]
        L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {p['sic']} | {runs[t]['ii'].fy[-1]} | {usd(p['total_liabilities'])} | {usd(p['insurance_liabilities'])} | "
                 f"{pct(p['ratio'])} | {'**confirmed**' if p['is_insurance'] else '**NOT CONFIRMED**'} | {', '.join(p['missing_components']) or '-'} |")
    bad = [t for t in T if not runs[t]["prof"]["is_insurance"]]
    L.append("\n" + ("All 12 companies pass (industry = Insurance and ratio >= 50%)." if not bad else "Not confirmed: " + ", ".join(bad) + "."))
    # ---------------------------------------------------------------- 2 data
    L.append("\n## 2. Data: tag used per input (last 5 fiscal years; `AI-extraction needed` = no tag in that year)\n")
    L.append("Full per company-year tag logs are in each `<TICKER>.json` (`tag_log_per_field_per_year`). Reserve development has no uniform tag (I20): "
             "each company's chain result is shown.\n")
    groups = [("Income statement", ["revenue_total", "premiums", "policy_fees", "nii", "gains_realized", "mrb_change", "benefits", "total_expenses",
                                    "interest_credited", "interest_expense", "goodwill_impairment", "pretax", "tax", "net_income", "eps", "shares_dil",
                                    "dividends", "buybacks"]),
              ("Reserve development (I20)", ["prior_year_dev", "ldti_remeasurement", "fpb_adverse_development"]),
              ("Balance sheet", ["equity", "preferred", "goodwill", "intangibles", "claims_gross", "claims_net", "fpb", "pab", "unearned", "reins_unpaid",
                                 "reins_prepaid", "investments", "cash", "debt_total", "debt_lt", "debt_st", "debt_junior_sub", "shares_out"]),
              ("AOCI components", ["aoci_afs_tag", "aoci_total"])]
    for gname, fields in groups:
        L.append(f"### {gname}\n")
        L.append("| Input | " + " | ".join(T) + " |")
        L.append("|---|" + "---|" * len(T))
        for fld in fields:
            L.append(f"| `{fld}` | " + " | ".join(_tagsum(runs[t]["ii"], fld, runs[t]["raw"]) for t in T) + " |")
        L.append("")
    L.append("### AOCI rate-driven components removed from equity (inline XBRL equity statement; USD bn, latest year) and their member names\n")
    L.append("| Company | AFS unrealized | Discount-rate remeasurement | Own-credit (MRB) | Source / members |")
    L.append("|---|---:|---:|---:|---|")
    for t in T:
        ii, raw = runs[t]["ii"], runs[t]["raw"]
        lg = raw["tag_log"].get("aoci", {}).get(ii.fy[-1], {})
        mem = lg.get("members") or {}
        L.append(f"| {t} | {usd(ii.f['aoci_afs'][-1])} | {usd(ii.f['aoci_drr'][-1])} | {usd(ii.f['aoci_credit'][-1])} | "
                 f"{lg.get('source', 'AI-extraction needed (not itemized)')}" + (": " + "; ".join(f"{k}: {', '.join(v)}" for k, v in mem.items()) if mem else "") + " |")
    L.append("\n### Items extracted from the 10-K text (insurance_regulatory.csv)\n")
    L.append("| Company | Item | Period | Value | Unit | Verified | Quote (location in the section column of the CSV) |")
    L.append("|---|---|---|---:|---|---|---|")
    for t in T:
        for item, r_ in runs[t]["ii"].reg.items():
            q = r_["quote"].replace("|", "\\|")
            L.append(f"| {t} | {item} | {r_['period']} | {r_['value']} | {r_['unit']} | {'yes' if r_['verified'] else 'NO'} | {q[:230]} |")
    L.append("\n### Inputs for which no extraction was made in this round (shown as missing in the scores)\n")
    L.append("Regulatory capital ratio: see rows above (MISSING = the filing gives no number). **Not extracted for any company (AI-extraction needed):** "
             "liquid-asset components (government / agency bonds, publicly traded investment-grade corporate bonds, listed equities, pledged / restricted "
             "assets, total investments + cash), complex / volatile asset components (alternatives, real estate, below-investment-grade and unrated "
             "fixed income, remaining Level 3), investment-grade share for WRB and PGR, LDTI remeasurement movement tables for PRU, prior-year development "
             "for TRV and PRU where untagged, financial debt where no total tag exists.\n")
    # ---------------------------------------------------------------- 3 scores
    L.append("\n## 3. Scores\n")
    L.append("| Company | Line | Buffett quality | Range | Coverage | Status | Graham quality | Range | Coverage | Status | Invalid criteria (B / G) |")
    L.append("|---|---|---:|---|---:|---|---:|---|---:|---|---|")
    for t in T:
        bq, gq = runs[t]["bq"], runs[t]["gq"]

        def rg(m):
            return "withheld" if m.min_score is None else f"{m.min_score:.1f}-{m.max_score:.1f}"
        L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {fx(bq.score, 1)} | {rg(bq)} | {pct(bq.coverage, 0)} | {bq.status} | {fx(gq.score, 1)} | {rg(gq)} | "
                 f"{pct(gq.coverage, 0)} | {gq.status} | {', '.join('B' + c['id'] for c in runs[t]['res']['buffett_quality']['invalid_criteria']) or '-'} / "
                 f"{', '.join('G' + c['id'] for c in runs[t]['res']['graham_quality']['invalid_criteria']) or '-'} |")
    errs = [(t, k) for t in T for k, m in (("Buffett", runs[t]["bq"]), ("Graham", runs[t]["gq"])) if m.range_error]
    L.append("\n**D14 range checks (min <= score <= max):** " + ("all 24 model ranges are consistent." if not errs else "FAILED: " + ", ".join(f"{t} {k}" for t, k in errs)))
    L.append("\n### Criterion totals (points / maximum of the applicable items; INVALID = coverage below M2)\n")
    for key, label, cid_list in (("bq", "Buffett", [c.id for c in runs[T[0]]["bq"].criteria]), ("gq", "Graham", [c.id for c in runs[T[0]]["gq"].criteria])):
        L.append(f"**{label}**\n")
        L.append("| Company | " + " | ".join(f"{label[0]}{c}" for c in cid_list) + " |")
        L.append("|---|" + "---:|" * len(cid_list))
        for t in T:
            cells = []
            for c in runs[t][key].criteria:
                mx = sum(i.max_pts for i in c.items if i.state != "not_applicable")
                obs = sum((i.points or 0.0) for i in c.items if i.state in ("score", "true_zero"))
                cells.append(f"{obs:.1f}/{mx:g}" + ("" if c.valid else " INVALID") + ("" if not c.items or any(i.state != 'ai_pending' for i in c.items) else " (all AI)"))
            L.append(f"| {t} | " + " | ".join(cells) + " |")
        L.append("")
    L.append("### Every sub-item per company: metric value, points / maximum, state, flags\n")
    for t in T:
        L.append(f"#### {t} ({LINE_OF_BUSINESS[t]}) - Buffett {fx(runs[t]['bq'].score, 1)}, Graham {fx(runs[t]['gq'].score, 1)}\n")
        L.append("| Model | Item | Name | Metric | Points / max | State | Flags / reason |")
        L.append("|---|---|---|---|---:|---|---|")
        for key, label in (("bq", "B"), ("gq", "G")):
            for c in runs[t][key].criteria:
                for it in c.items:
                    mv = it.metric
                    mtxt = "-" if mv is None else (f"{mv:.4g}" if isinstance(mv, (int, float)) else str(mv))
                    fl = ", ".join(it.flags[:5]) + ((" / " + it.note.replace("|", "/")) if it.note else "")
                    L.append(f"| {label} | {c.id}.{it.id} | {it.name} | {mtxt} | {'-' if it.points is None else f'{it.points:.2f}'} / {it.max_pts:g} | {it.state} | {fl[:240]} |")
        L.append("")
    L.append("### Not applicable and missing items (reasons)\n")
    for t in T:
        out = []
        for key, label in (("bq", "B"), ("gq", "G")):
            for c in runs[t][key].criteria:
                for it in c.items:
                    if it.state in ("not_applicable", "missing"):
                        out.append(f"{label}{c.id}.{it.id} {it.name} [{it.state}]: {it.note or ''}")
        L.append(f"- **{t}**: " + (" ; ".join(out) if out else "none"))
    # ---------------------------------------------------------------- 4 calibration
    L.append("\n## 4. Calibration data (K1; no threshold changes)\n")
    L.append("Per metric: value per company, distribution over the companies with a value (min / p25 / median / p75 / max), and the number of companies "
             "at the full score and at zero.\n")
    L.append("| Metric | n | min / p25 / median / p75 / max | At full score | At zero | Values by company |")
    L.append("|---|---:|---|---:|---:|---|")
    cal_vals = {}
    for label, mk, cid, iid, kind in CAL_ITEMS:
        vals, full, zero_, per = {}, 0, 0, []
        for t in T:
            it = _item(runs[t]["bq" if mk == "b" else "gq"], cid, iid)
            if it.state in ("score", "true_zero") and isinstance(it.metric, (int, float)):
                vals[t] = it.metric
            if it.state in ("score", "true_zero") and it.points is not None:
                full += it.points >= it.max_pts - 1e-6
                zero_ += it.points <= 1e-6
            per.append(f"{t} {_fmt(kind, it.metric) if it.state in ('score', 'true_zero') else it.state.upper()[:4]}")
        cal_vals[label] = vals
        q = _quart(list(vals.values()))
        L.append(f"| {label} | {len(vals)} | {'n/a' if q is None else ' / '.join(_fmt(kind, v) for v in q)} | {full} | {zero_} | {'; '.join(per)} |")
    L.append("\n### Underwriting margin, total operating margin and reserve deviation by line of business\n")
    L.append("| Line | Company | Underwriting margin (5y median) | Underwriting result >= 0 (years of 5) | Total operating margin (5y median) | Reserve deviation (5y median) | Years with deviation > 1% |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for line in ("P&C", "reinsurance", "life", "composite"):
        for t in [x for x in T if LINE_OF_BUSINESS[x] == line]:
            d = runs[t]["d"]
            um, tm, rd = [x for x in d["underwriting_margin"][-5:] if x is not None], [x for x in d["total_operating_margin"][-5:] if x is not None], \
                         [x for x in d["reserve_deviation"][-5:] if x is not None]
            ur = [x for x in d["underwriting_result"][-5:] if x is not None]
            L.append(f"| {line} | {t} | {pct(statistics.median(um)) if um else 'n/a'} | {sum(1 for x in ur if x >= 0)} of {len(ur)} | "
                     f"{pct(statistics.median(tm)) if tm else 'n/a'} | {pct(statistics.median(rd), 2) if rd else 'n/a'} | {sum(1 for x in rd if x > 0.01) if rd else 'n/a'} |")
    L.append("\nPer-line distribution (median of the company medians):\n")
    L.append("| Line | n | Underwriting margin | Total operating margin | Reserve deviation |")
    L.append("|---|---:|---:|---:|---:|")
    for line in ("P&C", "reinsurance", "life", "composite"):
        ts = [x for x in T if LINE_OF_BUSINESS[x] == line]

        def med(key):
            vv = [statistics.median([y for y in runs[t]["d"][key][-5:] if y is not None]) for t in ts if any(y is not None for y in runs[t]["d"][key][-5:])]
            return statistics.median(vv) if vv else None
        L.append(f"| {line} | {len(ts)} | {pct(med('underwriting_margin'))} | {pct(med('total_operating_margin'))} | {pct(med('reserve_deviation'), 2)} |")
    # ---------------------------------------------------------------- 5 diagnostics
    L.append("\n## 5. Diagnostics (display only)\n")
    L.append("### Operating ROE vs reported ROE (last 5 years)\n")
    L.append("| Company | Operating ROE by year | Median | Reported ROE (net income / average reported equity) by year | Median | Median gap (operating - reported) |")
    L.append("|---|---|---:|---|---:|---:|")
    for t in T:
        d = runs[t]["d"]
        o, r_ = d["operating_roe"][-5:], d["reported_roe"][-5:]
        ov, rv = [x for x in o if x is not None], [x for x in r_ if x is not None]
        mo, mr = (statistics.median(ov) if ov else None), (statistics.median(rv) if rv else None)
        L.append(f"| {t} | {', '.join(pct(x) for x in o)} | {pct(mo)} | {', '.join(pct(x) for x in r_)} | {pct(mr)} | "
                 f"{'n/a' if mo is None or mr is None else f'{(mo - mr) * 100:+.1f} pp'} |")
    L.append("\n### Adjusted equity vs reported equity (latest year, USD bn)\n")
    L.append("| Company | Reported equity | - Preferred | - AFS unrealized (AOCI) | - Discount-rate remeasurement | - Own credit (MRB) | = Adjusted equity | Adjusted / reported | Flags |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for t in T:
        ii, d = runs[t]["ii"], runs[t]["d"]
        e = ii.f["equity"][-1]
        ae = d["adjusted_equity"][-1]
        L.append(f"| {t} | {usd(e)} | {usd(ii.f['preferred'][-1])} | {usd(ii.f['aoci_afs'][-1])} | {usd(ii.f['aoci_drr'][-1])} | {usd(ii.f['aoci_credit'][-1])} | "
                 f"{usd(ae)} | {pct(None if (e is None or ae is None or not e) else ae / e, 0)} | {', '.join(d['adj_equity_flags'][-1]) or '-'} |")
    L.append("\n### Float with and without the discount-rate adjustment (USD bn; the AOCI figure is after tax - the pretax amount was not extracted)\n")
    L.append("| Company | Float t-4 reported | Float t reported | CAGR reported | Float t-4 ex-DRR | Float t ex-DRR | CAGR ex-DRR | Flags (latest) |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for t in T:
        d = runs[t]["d"]
        a, b, c_, e = d["float_reported"][-5], d["float_reported"][-1], d["float_ex_drr"][-5], d["float_ex_drr"][-1]

        def cg(x, y):
            return None if (x is None or y is None or x <= 0 or y <= 0) else (y / x) ** 0.25 - 1
        L.append(f"| {t} | {usd(a)} | {usd(b)} | {pct(cg(a, b))} | {usd(c_)} | {usd(e)} | {pct(cg(c_, e))} | {', '.join(d['float_flags'][-1]) or '-'} |")
    L.append("\n### Cost-free float condition (Buffett 3.5.4: 5-year sum of underwriting results >= 0 AND >= 3 of 5 years >= 0)\n")
    L.append("| Company | Underwriting result by year (USD bn) | 5y sum | Years >= 0 | Condition | Float CAGR scored |")
    L.append("|---|---|---:|---:|---|---|")
    for t in T:
        d = runs[t]["d"]
        ur = d["underwriting_result"][-5:]
        kn = [x for x in ur if x is not None]
        cond = None if len(kn) < 3 else (sum(kn) >= 0 and sum(1 for x in kn if x >= 0) >= 3)
        it = _item(runs[t]["bq"], "3.5", "4")
        L.append(f"| {t} | {', '.join(usd(x) for x in ur)} | {usd(sum(kn)) if kn else 'n/a'} | {sum(1 for x in kn if x >= 0)} of {len(kn)} | "
                 f"{'n/a' if cond is None else ('PASS' if cond else 'FAIL')} | {_cell(it)} ({it.state}) |")
    L.append("\n### Catastrophe-loss flags (I19; flag when >= 5% of premiums earned - interpretation of 'material')\n")
    L.append("| Company | Cat losses 2025 (USD bn) | Premiums earned (USD bn) | Share | Flag | Source |")
    L.append("|---|---:|---:|---:|---|---|")
    for t in T:
        lt = runs[t]["d"]["latest"]
        r_ = runs[t]["ii"].reg.get("cat_loss_latest")
        L.append(f"| {t} | {usd(lt['cat_loss'])} | {usd(runs[t]['ii'].f['premiums'][-1])} | {pct(lt['cat_share'])} | "
                 f"{'n/a (AI-extraction needed)' if lt['cat_flag'] is None else ('**FLAG**' if lt['cat_flag'] else 'no')} | {(r_['note'] if r_ else '-')[:110]} |")
    L.append("\n### ALM disclosures found (risk flag only in v1)\n")
    L.append("| Company | Disclosure found | First match (quote) |")
    L.append("|---|---|---|")
    for t in T:
        r_ = runs[t]["ii"].reg.get("alm_disclosed")
        L.append(f"| {t} | {r_['value'] if r_ else 'AI-extraction needed'} | {(r_['quote'][:260].replace('|', '/')) if r_ else '-'} |")
    L.append("\n### Other revenue not in insurance revenue (share of total revenue, latest year) and tax rate used\n")
    L.append("| Company | Other revenue (bn) | Share of revenue | Tax rate used (latest) | Non-recurring gains (bn) | Normalized operating profit pretax (bn) | Pretax (bn) |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for t in T:
        d, ii = runs[t]["d"], runs[t]["ii"]
        orv, rev = d["other_revenue"][-1], ii.f["revenue_total"][-1]
        L.append(f"| {t} | {usd(orv)} | {pct(None if (orv is None or not rev) else orv / rev)} | {pct(d['tax_rate'][-1], 0)} | {usd(d['non_recurring_gains'][-1])} | "
                 f"{usd(d['nop_pretax'][-1])} | {usd(ii.f['pretax'][-1])} |")
    # ---------------------------------------------------------------- 6 open issues
    L.append("\n## 6. Open issues and definitions that could not be computed as written\n")
    ip = ROOT / "scripts" / "insurance_rule_issues.md"
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(scripts/insurance_rule_issues.md not written yet)")
    L.append("\n## Data problems by company\n")
    for t in T:
        L.append(f"- **{t}**: " + ("; ".join(runs[t]["res"]["data_problems"]) if runs[t]["res"]["data_problems"] else "none detected"))
    (OUT / "summary_insurance.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = {a.upper() for a in argv}
    sec = SecClient()
    reg_all = load_insurance_regulatory()
    runs, failures = {}, []
    for t in COMPANIES:
        if wanted and t not in wanted:
            continue
        try:
            runs[t] = run_company(sec, reg_all, t)
            print(f"{t}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    if runs:
        build_summary(runs, failures)
    print(f"SEC requests this run: {sec.requests_made}")


if __name__ == "__main__":
    main(sys.argv[1:])

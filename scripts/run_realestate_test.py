"""INCOME_REAL_ESTATE first test round (spec 2026-10-14_10-05). Quality only, no pricing. Writes scripts/output_realestate/ (summary + one JSON per company).

Usage:  .venv/Scripts/python -X utf8 scripts/run_realestate_test.py   (set CURL_CA_BUNDLE / SSL_CERT_FILE / REQUESTS_CA_BUNDLE to an ASCII-path CA file for yfinance)
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
from src.providers.realestate_facts import (ASSET_TYPE, NOI_METHOD, RE_FIELDS, RENTAL_PROXY, UTILIZATION, build_realestate_series,  # noqa: E402
                                            load_realestate_extracted)
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring.realestate import REInputs, score_realestate  # noqa: E402

OUT = ROOT / "scripts" / "output_realestate"
COMPANIES = ["O", "PLD", "SPG", "FRT", "BXP", "ARE", "EQR", "AVB", "EQIX", "AMT", "PSA", "WELL"]
SPEC = "docs/scoring/ValueCompass_RealEstate_Rules_2026-10-14_10-05_EN.md"
EXTRACTED_ITEMS = ["reported_ffo", "maintenance_capex", "ti_lc_income_preserving", "same_property_noi_growth", "occupancy", "largest_tenant_share", "committed_undrawn_facilities",
                   "unencumbered_noi_share", "secured_debt", "acquisition_yield", "development_yield", "fair_value_real_estate", "jv_noi_share"]
# fields reported per company-year in the data section (XBRL tag or "AI-extraction needed")
DATA_FIELDS = ["total_revenue", "rental_revenue", "other_property_revenue", "prop_opex", "noi_reported", "net_income", "pref_div", "interest_expense", "interest_capitalized", "income_tax",
               "da_total", "re_depr", "gains_sale", "impairment", "debt_extinguishment", "transaction_costs", "straight_line", "maint_capex", "shares_dil", "shares_out", "dividends",
               "debt_total", "cash", "sti", "mat_year1", "mat_year2", "re_net", "re_gross", "assets"]


def f(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def pc(x, nd=1):
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def bn(x, nd=2):
    return "n/a" if x is None else f"{x / 1e9:,.{nd}f}"


def run_company(sec, reg_all, t):
    splits = price_provider.get_splits(t)
    raw = build_realestate_series(sec, t, splits)
    pr = price_provider.load_prices(t, raw["ends"], raw["labels"])
    price, pdate, pnote = pr["current"], str(pr.get("current_date")), []
    if price is None or price != price:  # NaN last row: use the last valid close of the cached history
        import csv as _csv
        rows = [r for r in _csv.DictReader((ROOT / "scripts" / "cache" / "prices" / f"{t}.csv").open(encoding="utf-8")) if r["close"] not in ("", "nan")]
        price, pdate = (float(rows[-1]["close"]), rows[-1]["date"]) if rows else (None, None)
        pnote.append(f"price: last row was NaN; last valid close {price} on {pdate} used")
    if pdate and (date.today() - date.fromisoformat(pdate[:10])).days > 10:
        pnote.append(f"price is stale: {pdate} (more than 10 days old)")
    ri = REInputs(ticker=t, name=raw["name"], fy=raw["labels"], end=raw["ends"], f=raw["f"], reg=reg_all.get(t, {}), asset_type=ASSET_TYPE[t], utilization=UTILIZATION[t],
                  noi_method=NOI_METHOD[t], rental_proxy_note=RENTAL_PROXY.get(t, ""), price_current=price, price_date=pdate, price_avg=pr["avg"],
                  first_annual_report=raw["first_annual_report"], as_of=date.today(), flags=list(raw["flags"]), data_problems=list(raw["problems"]) + list(pr["notes"]) + pnote, tag_log=raw["tag_log"])
    sc = score_realestate(ri)
    d, bq, gq = sc["derived"], sc["buffett_quality"], sc["graham_quality"]
    res = {"ticker": t, "name": raw["name"], "cik": raw["cik"], "profile": "INCOME_REAL_ESTATE", "asset_type": ASSET_TYPE[t], "spec": SPEC, "as_of": date.today(),
           "price": {"current": price, "date": pdate, "source": pr["source"]}, "fiscal_years": dict(zip(ri.fy, ri.end)),
           "financials": {k: dict(zip(ri.fy, v)) for k, v in ri.f.items()}, "derived": {k: (dict(zip(ri.fy, v)) if isinstance(v, list) and len(v) == ri.n else v) for k, v in d.items()},
           "buffett_quality": model_json(bq), "graham_quality": model_json(gq), "tag_log_per_field_per_year": raw["tag_log"], "flags": ri.flags,
           "data_problems": list(dict.fromkeys(ri.data_problems))}
    (OUT / f"{t}.json").write_text(json.dumps(jsonable(res), indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return {"res": res, "ri": ri, "d": d, "bq": bq, "gq": gq, "raw": raw}


def _item(model, cid, iid):
    return next((i for c in model.criteria if c.id == cid for i in c.items if i.id == iid), None)


def _tagsum(ri, field, n=5):
    lg = ri.tag_log.get(field, {})
    tags = {}
    for lab in ri.fy[-n:]:
        tg = (lg.get(lab) or {}).get("tag")
        tags.setdefault(tg or "AI-extraction needed", []).append(lab[2:])
    out = []
    for k, v in tags.items():
        short = k if len(k) < 70 else k[:67] + "..."
        out.append(f"`{short}`" + ("" if len(tags) == 1 else f" ({','.join(v)})") if k != "AI-extraction needed" else f"AI-extraction needed ({','.join(v)})" if len(tags) > 1 else "AI-extraction needed")
    return "; ".join(out)


def _q(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    if len(vals) < 2:
        return (vals[0],) * 5
    q = statistics.quantiles(vals, n=4, method="inclusive")
    return vals[0], q[0], q[1], q[2], vals[-1]


SEC4 = [("B", "3.4", "1", "Incremental spread (check)", "pp"), ("B", "3.4", "2", "Same-property NOI growth", "pct"), ("B", "3.4", "3", "NOI margin (check)", "pct"),
        ("B", "3.5", "1", "OE per share CAGR", "pct"), ("B", "3.5", "2", "OE per share stability (declines of 4)", "n"), ("B", "3.6", "1", "Net debt / EBITDAre", "x"),
        ("B", "3.6", "2", "Fixed-charge coverage", "x"), ("B", "3.6", "3", "Economic LTV", "pct"), ("G", "3.2", "1", "Fixed-charge coverage (Graham)", "x"),
        ("G", "3.2", "2", "Near-term debt coverage", "x"), ("G", "3.3", "1", "Net debt / EBITDAre (Graham)", "x"), ("G", "3.3", "2", "Financial flexibility (check)", "pct"),
        ("G", "3.3", "3", "Stressed economic LTV", "pct"), ("G", "3.7", "1", "Utilization", "pct"), ("G", "3.7", "2", "Property income resilience (declines of 4)", "n"),
        ("G", "3.7", "3", "Tenant concentration", "pct"), ("G", "3.8", "1", "OE stability (declines of 4)", "n"), ("G", "3.8", "2", "Reported vs economic gap", "pct"),
        ("G", "3.8", "3", "Per-share capital discipline", "pct")]


def fmt_metric(v, kind):
    if v is None:
        return "n/a"
    return {"pct": pc(v), "pp": pc(v), "x": f"{v:.2f}x", "n": f"{v:.1f}"}[kind]


def build_summary(runs, failures, sec):
    T = list(runs)
    L = [f"# ValueCompass INCOME_REAL_ESTATE first test round (quality only) - {date.today().isoformat()}\n",
         f"Spec: `{SPEC}`. 12 US REITs by asset type (table A). No pricing, no DB, no AI / text extraction (items found only in text are `AI-extraction needed`; `scripts/realestate_extracted.csv` "
         f"has the loader and the item list but no rows yet). SEC requests this run: {sec.requests_made}. Prices: latest close from the existing price provider, "
         f"date(s): {', '.join(sorted({runs[t]['ri'].price_date for t in T}))}.\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    # ---------------------------------------------------------------- 1 profile
    L.append("## 1. Profile check (latest year)\n")
    L.append("| Company | Asset type | Investment property (USD bn) | Total assets (USD bn) | Property / assets | Rental revenue / total revenue | Result | Notes |")
    L.append("|---|---|---:|---:|---:|---:|---|---|")
    for t in T:
        ri, d = runs[t]["ri"], runs[t]["d"]
        pcx = d["profile_check"]
        res = "INCOME_REAL_ESTATE confirmed" if pcx["confirmed"] else ("**FAILS** the test" if pcx["confirmed"] is False else "**undetermined**")
        why = []
        if pcx["asset_ok"] is False:
            why.append(f"investment property is {pc(pcx['investment_property_share'], 0)} of assets (< 50%)")
        if pcx["rental_ok"] is False:
            why.append(f"rental revenue is {pc(pcx['rental_revenue_share'], 0)} of revenue (< 50%)")
        L.append(f"| {t} | {ri.asset_type} | {bn(ri.series('re_net')[-1], 1)} | {bn(ri.series('assets')[-1], 1)} | {pc(pcx['investment_property_share'], 0)} | {pc(pcx['rental_revenue_share'], 0)} | {res} | "
                 f"{'; '.join(why + pcx['notes']) or '-'} |")
    L.append("\n`EQIX` / `AMT` / `WELL` are the cases the spec expects to need a decision: EQIX data-center revenue is not tagged as lease income (rental share undetermined), AMT's tower assets are "
             "mostly PP&E and intangibles rather than investment property, WELL's operating (RIDEA) segment is large. Scoring below treats all 12 as INCOME_REAL_ESTATE as instructed; the flags "
             "are in the table.\n")
    # ---------------------------------------------------------------- 2 data
    L.append("## 2. Data: tag used per company-year (last 5 fiscal years) or `AI-extraction needed`\n")
    L.append("Standard-taxonomy tags come from SEC companyfacts; `ixbrl:` = company-extension element read from the 10-K inline XBRL; `SUM:` = components added; `assumed_zero` = absent, "
             "treated as 0 and flagged (T10). Items found only in text are listed in section 2b.\n")
    for t in T:
        ri = runs[t]["ri"]
        L.append(f"### {t} - {ri.name}\n")
        L.append("| Field | Tag used (FY2021-FY2025) |")
        L.append("|---|---|")
        for fld in DATA_FIELDS:
            L.append(f"| {fld} | {_tagsum(ri, fld)} |")
        L.append("")
    L.append("### 2b. Items that need text extraction (all `AI-extraction needed` in this round)\n")
    L.append("| Item | Used by |")
    L.append("|---|---|")
    for it, use in [("reported NAREIT FFO", "FFO reconciliation (difference in % per year)"), ("maintenance capex; income-preserving TI/LC", "owner earnings (otherwise FFO_PROXY) - PSA's maintenance capex is XBRL-tagged"),
                    ("same-property NOI growth", "Buffett 3.4.2, NOI_PROXY, Graham 3.7.2"), ("occupancy / mapped metric", "Graham 3.7.1"), ("largest tenant share", "Graham 3.7.3"),
                    ("committed undrawn facilities", "NTDC, Graham 3.2.2"), ("unencumbered NOI; secured debt", "Graham 3.3.2"),
                    ("acquisition / development yields", "Buffett 3.4.1 direct incremental return"), ("disclosed fair value of real estate", "economic LTV, stressed LTV"),
                    ("JV share (NOI, debt, value)", "proportionate net debt and FFO JV adjustment")]:
        L.append(f"| {it} | {use} |")
    # ---------------------------------------------------------------- 3 computed
    L.append("\n## 3. Computed metrics per company-year\n")
    for t in T:
        d, ri = runs[t]["d"], runs[t]["ri"]
        L.append(f"### {t} ({ri.asset_type}) - NOI basis: {d['noi_basis'][-1] or 'not computable'}\n")
        L.append("| FY | NOI (bn) | NOI margin | FFO uniform (bn) | Reported FFO | Reconciliation | Normalized FFO (bn) | nFFO / share | OE basis | OE or proxy / share | EBITDAre (bn) | Net debt (bn) | ND / EBITDAre | FCC | NTDC | Reported-basis leverage |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|")
        for i in range(ri.n - 5, ri.n):
            L.append(f"| {ri.fy[i]} | {bn(d['noi'][i])} | {pc(d['noi_margin'][i])} | {bn(d['ffo'][i])} | {'AI-extraction needed' if d['reported_ffo'][i] is None else bn(d['reported_ffo'][i])} | "
                     f"{'n/a' if d['ffo_reconciliation_pct'][i] is None else pc(d['ffo_reconciliation_pct'][i])} | {bn(d['norm_ffo'][i])} | {f(d['nffo_ps'][i])} | {d['oe_basis'][i] or 'n/a'} | "
                     f"{f(d['oe_ps'][i])} | {bn(d['ebitdare'][i])} | {bn(d['net_debt'][i])} | {f(d['nd_ebitdare'][i])} | {f(d['fcc'][i])} | "
                     f"{'n/a' if d['ntdc'][i] is None else ('no maturities' if d['ntdc'][i] > 1e9 else f(d['ntdc'][i]))} | {pc(d['reported_leverage'][i])} |")
        fl = sorted({x for fl_ in d["ffo_flags"][-5:] for x in fl_})
        w = d["wacc"]
        inc = d["incremental"]
        L.append(f"\nFFO flags: {', '.join(fl) or 'none'}. WACC proxy: {pc(w['value'], 2) if w['value'] is not None else 'n/a'}"
                 + (f" (Kd {pc(w['kd'], 2)}, debt weight {pc(w['weight_debt'], 0)}, market cap {bn(w['market_cap'], 1)}bn at USD {f(w['price'])} on {w['price_date']})" if w["value"] is not None else "")
                 + f". Incremental return: {pc(inc['value'], 2) if inc['value'] is not None else 'n/a'} ({inc.get('basis') or inc.get('reason')}). Economic LTV: "
                 f"{'n/a (no economic value basis; no proxy)' if d['economic_ltv'][-1] is None else pc(d['economic_ltv'][-1])}; stressed LTV: {'n/a (not computable as written)' if d['stressed_ltv'] is None else pc(d['stressed_ltv'])}. "
                 f"Write-downs 5y: {bn(d['writedowns_5y'])}bn ({pc(d['writedowns_share_of_property'])} of property).\n")
    # ---------------------------------------------------------------- 4 scores
    L.append("## 4. Scores (M1-M9, D14)\n")
    L.append("| Company | Asset type | Buffett | Range | Coverage | Status | Graham | Range | Coverage | Status | Graham observed points | D14 |")
    L.append("|---|---|---:|---|---:|---|---:|---|---:|---|---:|---|")
    rg = lambda m: "withheld" if m.min_score is None else f"{m.min_score:.1f}-{m.max_score:.1f}"  # noqa: E731
    sc_ = lambda m: "n/a" if m.score is None else f"{m.score:.1f}"  # noqa: E731
    for t in T:
        bq, gq = runs[t]["bq"], runs[t]["gq"]
        L.append(f"| {t} | {runs[t]['ri'].asset_type} | {sc_(bq)} | {rg(bq)} | {bq.coverage:.0%} | {bq.status} | {sc_(gq)} | {rg(gq)} | {gq.coverage:.0%} | {gq.status} | {gq.observed_points:.1f} | "
                 f"{'FAIL' if (bq.range_error or gq.range_error) else 'ok'} |")
    errs = [(t, k) for t in T for k, m in (("Buffett", runs[t]["bq"]), ("Graham", runs[t]["gq"])) if m.range_error]
    L.append("\n**D14 range checks (min <= score <= max):** " + ("all 24 model ranges are consistent." if not errs else "FAILED: " + ", ".join(f"{t} {k}" for t, k in errs)))
    L.append("\n### 4b. Every sub-item per company (value, points / max, state, metric_basis)\n")
    for t in T:
        L.append(f"#### {t}\n")
        L.append("| Item | Name | Metric | Points / max | State | metric_basis | Reason / flags |")
        L.append("|---|---|---|---:|---|---|---|")
        for tag, m in (("B", runs[t]["bq"]), ("G", runs[t]["gq"])):
            for c in m.criteria:
                for i in c.items:
                    mb = (i.inputs or {}).get("metric_basis") if isinstance(i.inputs, dict) else None
                    why = (i.note or "") + (" [" + ", ".join(i.flags) + "]" if i.flags else "")
                    mv = "" if i.metric is None else (f"{i.metric:.4g}" if isinstance(i.metric, (int, float)) else str(i.metric))
                    pts = "n/a" if i.points is None else f"{i.points:.2f}"
                    L.append(f"| {tag}{c.id}.{i.id} | {i.name} | {mv} | {pts} / {i.max_pts:g} | {i.state} | {mb or '-'} | {why.strip() or '-'} |")
        L.append("")
    L.append("### 4c. Not applicable vs missing (by criterion)\n")
    L.append("| Company | Not applicable | Missing (reason in 4b) | AI pending |")
    L.append("|---|---|---|---|")
    for t in T:
        na, ms, ap = [], [], []
        for tag, m in (("B", runs[t]["bq"]), ("G", runs[t]["gq"])):
            for c in m.criteria:
                for i in c.items:
                    key = f"{tag}{c.id}.{i.id}"
                    (na if i.state == "not_applicable" else ms if i.state == "missing" else ap if i.state == "ai_pending" else []).append(key)
        L.append(f"| {t} | {', '.join(na) or '-'} | {', '.join(ms) or '-'} | {len(ap)} items |")
    # ---------------------------------------------------------------- 5 K1
    L.append("\n## 5. K1 calibration data (no threshold changes)\n")
    L.append("Distribution of each section-4 metric over the companies where it is computed (min / p25 / median / p75 / max) and the counts at the full and zero score. Thresholds marked "
             "`(check)` in the spec are highlighted.\n")
    L.append("| Metric | Sub-item | n computed | Min / p25 / median / p75 / max | At full score | At zero | Missing |")
    L.append("|---|---|---:|---|---:|---:|---:|")
    for tag, cid, iid, name, kind in SEC4:
        vals, full, zero_, miss_ = [], 0, 0, 0
        for t in T:
            it = _item(runs[t]["bq"] if tag == "B" else runs[t]["gq"], cid, iid)
            if it is None:
                continue
            if it.state in ("score", "true_zero") and it.points is not None:
                if it.metric is not None and isinstance(it.metric, (int, float)) and abs(it.metric) < 1e9:
                    vals.append(it.metric)
                full += 1 if it.points >= it.max_pts - 1e-6 else 0
                zero_ += 1 if it.points == 0 else 0
            elif it.state == "missing":
                miss_ += 1
        q = _q(vals)
        hl = "**" if "(check)" in name else ""
        L.append(f"| {hl}{name}{hl} | {tag}{cid}.{iid} | {len(vals)} | {'n/a' if q is None else ' / '.join(fmt_metric(v, kind) for v in q)} | {full} | {zero_} | {miss_} |")
    L.append("\nThe distributions are computed only from what the XBRL layer can supply; extraction-dependent metrics (same-property NOI growth, occupancy, tenant share, financial flexibility, "
             "incremental spread, economic and stressed LTV, NTDC) have no sample yet, so K1 cannot say anything about those thresholds in this round.")
    # ---------------------------------------------------------------- 7 open
    L.append("\n## 6. Israeli feasibility (optional, no scoring)\n")
    ip2 = ROOT / "scripts" / "realestate_israeli_feasibility.md"
    L.append(ip2.read_text(encoding="utf-8") if ip2.exists() else "(not written yet)")
    L.append("\n## 7. Open issues and definitions that could not be computed as written\n")
    ip = ROOT / "scripts" / "realestate_rule_issues.md"
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(scripts/realestate_rule_issues.md not written yet)")
    L.append("\n## Data problems by company\n")
    for t in T:
        L.append(f"- **{t}**: " + ("; ".join(runs[t]["res"]["data_problems"])[:900] if runs[t]["res"]["data_problems"] else "none detected"))
    (OUT / "summary_realestate.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sec = SecClient()
    reg_all = load_realestate_extracted()
    runs, failures = {}, []
    for t in COMPANIES:
        try:
            runs[t] = run_company(sec, reg_all, t)
            print(f"{t}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    if runs:
        build_summary(runs, failures, sec)
    print("SEC requests:", sec.requests_made)


if __name__ == "__main__":
    main()

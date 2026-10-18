"""INCOME_REAL_ESTATE round 5 (RE23; spec 2026-10-14_20-55). Quality only. Writes scripts/output_realestate_v5/. Round-1 outputs are kept.

Usage:  .venv/Scripts/python -X utf8 scripts/run_realestate_v2.py   (CA bundle env vars for yfinance as in round 1)
Companies failing the profile test (RE10 / RE11) are scored under the general model v1.1 (STANDARD) and reported separately.
"""
from __future__ import annotations

import csv
import json
import sys
import traceback
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import run_realestate_test as rt  # noqa: E402  (helpers: formatting, SEC4 table, tag summaries)
import run_scoring_test as rs  # noqa: E402
from run_realestate_test import DATA_FIELDS, SEC4, _item, _q, _tagsum, bn, f, fmt_metric, pc  # noqa: E402
from run_scoring_test import jsonable, model_json  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.realestate_facts import ASSET_TYPE, NOI_METHOD, UTILIZATION, build_realestate_series, load_realestate_extracted  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring.realestate import REInputs, score_realestate  # noqa: E402

COMPANIES = ["O", "PLD", "SPG", "FRT", "BXP", "ARE", "EQR", "EQIX", "AMT", "PSA", "WELL"]  # AVB dropped: merged into Vivmark Residential (VMRK) with EQR on 2026-08-18
OUT = ROOT / "scripts" / "output_realestate_v5"
VMRK_NOTE = "EQR and AVB merged into Vivmark Residential (NYSE: VMRK, from 2026-08-18; each AVB share -> 2.793 EQR shares; EQR 8-K exhibit 99.1): AVB is delisted and dropped; EQR keeps its FY2025 financials, market capitalization uses the VMRK price"
SPEC = "docs/scoring/ValueCompass_RealEstate_Rules_2026-10-14_20-20_EN.md"
CSV = ROOT / "scripts" / "realestate_extracted.csv"


def build_ri(sec, reg_all, t):
    raw = build_realestate_series(sec, t, price_provider.get_splits(t))
    pr = price_provider.load_prices(t, raw["ends"], raw["labels"])
    price, pdate, pnote = pr["current"], str(pr.get("current_date")), []
    if price is None or price != price:
        rows = [r for r in csv.DictReader((ROOT / "scripts" / "cache" / "prices" / f"{t}.csv").open(encoding="utf-8")) if r["close"] not in ("", "nan")]
        price, pdate = (float(rows[-1]["close"]), rows[-1]["date"]) if rows else (None, None)
        pnote.append(f"price: last row was NaN; last valid close {price} on {pdate} used")
    if pdate and (date.today() - date.fromisoformat(pdate[:10])).days > 10:
        pnote.append(f"price is stale: {pdate} (more than 10 days old); a refresh was attempted (yfinance: no data, ticker reported as possibly delisted)")
    if t == "EQR":
        try:
            import yfinance as yf
            h = yf.Ticker("VMRK").history(period="1mo", auto_adjust=False)
            price, pdate = float(h["Close"].iloc[-1]), h.index[-1].date().isoformat()
            pnote = [f"price: VMRK (Vivmark Residential, successor of EQR) close {price:.2f} on {pdate} used for the market capitalization (EQR share = 1 VMRK share)"]
        except Exception as exc:  # noqa: BLE001
            pnote.append(f"VMRK price not retrievable ({type(exc).__name__}); EQR last close used")
    ri = REInputs(ticker=t, name=raw["name"], fy=raw["labels"], end=raw["ends"], f=raw["f"], reg=reg_all.get(t, {}), asset_type=ASSET_TYPE[t], utilization=UTILIZATION[t],
                  noi_method=NOI_METHOD[t], price_current=price, price_date=pdate, price_avg=pr["avg"], first_annual_report=raw["first_annual_report"], as_of=date.today(),
                  flags=list(raw["flags"]), data_problems=list(raw["problems"]) + list(pr["notes"]) + pnote, tag_log=raw["tag_log"])
    return ri, raw


def run_ire(ri, raw, sc):
    d, bq, gq = sc["derived"], sc["buffett_quality"], sc["graham_quality"]
    res = {"ticker": ri.ticker, "name": ri.name, "cik": raw["cik"], "profile": "INCOME_REAL_ESTATE", "asset_type": ri.asset_type, "spec": SPEC, "as_of": date.today(),
           "price": {"current": ri.price_current, "date": ri.price_date}, "fiscal_years": dict(zip(ri.fy, ri.end)),
           "financials": {k: dict(zip(ri.fy, v)) for k, v in ri.f.items()},
           "derived": {k: (dict(zip(ri.fy, v)) if isinstance(v, list) and len(v) == ri.n else v) for k, v in d.items()},
           "buffett_quality": model_json(bq), "graham_quality": model_json(gq), "tag_log_per_field_per_year": raw["tag_log"], "flags": ri.flags,
           "data_problems": list(dict.fromkeys(ri.data_problems))}
    (OUT / f"{ri.ticker}.json").write_text(json.dumps(jsonable(res), indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return res


def csv_stats():
    rows = [r for r in csv.DictReader(CSV.open(encoding="utf-8")) if r["ticker"] and not r["ticker"].startswith("#")]
    by = defaultdict(Counter)
    for r in rows:
        status = "not disclosed" if r["value"] == "not disclosed" else ("not extracted" if r["value"] == "not extracted" else ("extracted+verified" if r["verified"] == "true" else "extracted, UNVERIFIED"))
        by[r["ticker"]][status] += 1
    return rows, by


def build_summary(runs, standard, failures, sec, s3a_md):
    T = list(runs)
    allri = {**{t: runs[t]["ri"] for t in runs}, **{t: standard[t]["ri"] for t in standard}}
    L = [f"# ValueCompass INCOME_REAL_ESTATE round 2 (quality only) - {date.today().isoformat()}\n",
         f"Spec: `{SPEC}` (RE10-RE14, S3a). Text extraction into `scripts/realestate_extracted.csv` from the 10-Ks (FY2021 / FY2023 / FY2025 filings, which carry two to three years each) and, where the 10-K lacks the item, "
         "the 8-K earnings release / supplemental exhibits. No pricing, no DB, no AI scoring questions (AI items stay `ai_pending`). Round-1 outputs are kept in `scripts/output_realestate/`. "
         f"Sample change: {VMRK_NOTE}. Prices: latest close from the price provider (dates in section 8). SEC requests this run: {sec.requests_made}.\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    # ---------------------------------------------------------------- 1 profile
    L.append("## 1. Profile results (RE10, RE11) and S3a borderline flags\n")
    L.append("| Company | Asset type | Property / assets (basis) | Rental revenue / total revenue (basis) | Result | Borderline (S3a) |")
    L.append("|---|---|---|---|---|---|")
    for t in COMPANIES:
        ri = allri.get(t)
        if ri is None:
            continue
        pcx = (runs[t]["d"] if t in runs else standard[t]["d"])["profile_check"]
        bl = "; ".join(f"{k}: {pc(v['value'])} vs {pc(v['threshold'], 0)} ({v['distance_pp']:+.1f}pp)" for k, v in pcx["borderline_tests"].items()) or "-"
        L.append(f"| {t} | {ri.asset_type} | {pc(pcx['investment_property_share'])} ({pcx['basis']['property']}) | {pc(pcx['rental_revenue_share'])} ({pcx['basis']['rental']}) | "
                 f"**{pcx['assignment']}** | {bl} |")
    L.append("\nRE11 numbers (extracted, with quotes in the CSV): EQR - rental income is the only revenue line (3.09bn = total revenues), investment property 19.4bn of 20.7bn assets; EQIX - colocation 6.475bn of 9.217bn revenue (70%; "
             "space and power under lease, lease and non-lease components combined as one lease component), PP&E 23.6bn of 40.1bn assets (59%); AMT - property revenue 10.305bn of 10.645bn (97%) but property and equipment is 20.4bn of "
             "63.2bn assets (32%; goodwill and acquired tenant-related intangibles are outside the real-estate test) -> fails; WELL - lease income 18% of revenue -> fails. Failing companies are STANDARD (section 7).\n")
    L.append("### S3a over the other profile samples (bank, insurance, managed care)\n")
    L.append(s3a_md)
    # ---------------------------------------------------------------- 2 extraction
    rows, by = csv_stats()
    L.append("\n## 2. Extraction (`scripts/realestate_extracted.csv`)\n")
    L.append(f"{len(rows)} rows. Status per company: extracted + verified (the value string is inside the exact quote), not disclosed (absence regex with the search scope in the quote), "
             "not extracted (the item exists in a source that was not searched in this time-boxed round - **not** the same as not disclosed).\n")
    L.append("| Company | Extracted + verified | Not disclosed | Not extracted | Unverified |")
    L.append("|---|---:|---:|---:|---:|")
    for t in COMPANIES:
        c = by.get(t, Counter())
        L.append(f"| {t} | {c['extracted+verified']} | {c['not disclosed']} | {c['not extracted']} | {c['extracted, UNVERIFIED']} |")
    L.append("\nItems not extracted or not disclosed (company / item / years: reason):\n")
    for r in rows:
        if r["value"] in ("not disclosed", "not extracted"):
            L.append(f"- {r['ticker']} / {r['item']} / {r['year']}: {r['value']} - {r['quote'][:230]}")
    # ---------------------------------------------------------------- 3 FFO reconciliation
    L.append("\n## 3. FFO reconciliation: uniform formula vs reported NAREIT FFO (and NOI vs company-reported NOI)\n")
    L.append("RE17: our FFO = net income attributable to common + real-estate-related D&A from the company's FFO reconciliation (incl. the share of unconsolidated JVs; priority 1; else the real-estate D&A tag, else total D&A flagged) "
             "- gains on sale of real estate and of investments in real-estate entities (RE12) + impairments - preferred dividends + the reconciliation's OP-unit / noncontrolling and JV impairment-gain adjustments. "
             "Reported FFO is the company's NAREIT-defined measure as extracted; a difference above 10% is flagged **>10%**.")
    L.append("| Company | " + " | ".join(f"FY{y}" for y in range(2021, 2026)) + " | Main reasons for the gap |")
    L.append("|---|" + "---|" * 5 + "---|")
    why = {"O": "no JV / preferred adjustments", "PLD": "reported includes the proportionate share of unconsolidated co-investment ventures (our FFO is consolidated only)", "SPG": "reported FFO is the Operating Partnership's (OP units) incl. share of unconsolidated entities",
           "FRT": "close definition; OP units", "BXP": "reported diluted FFO attributable to BXP, Inc. incl. JV share", "ARE": "diluted share basis; impairments / non-RE investment adjustments",
           "EQR": "reported includes OP units (about 4%)", "AVB": "unconsolidated entity adjustments", "EQIX": "JV adjustments; non-real-estate D&A inside total D&A", "PSA": "FY2022 PS Business Parks gain excluded by RE12; JV adjustments"}
    for t in T:
        d, ri = runs[t]["d"], runs[t]["ri"]
        cells = []
        for y in range(2021, 2026):
            lab = f"FY{y}"
            i = ri.fy.index(lab) if lab in ri.fy else None
            if i is None or d["ffo_reconciliation_pct"][i] is None:
                cells.append("AI-extraction n/a" if (i is not None and d["reported_ffo"][i] is None) else "n/a")
            else:
                cells.append(f"{d['ffo_reconciliation_pct'][i] * 100:+.1f}%{' **>10%**' if d['ffo_gap_flag_over_10pct'][i] else ''} ({bn(d['ffo'][i], 2)} vs {bn(d['reported_ffo'][i], 2)})")
        L.append(f"| {t} | " + " | ".join(cells) + f" | {why.get(t, '')} |")
    L.append("\n### NOI: computed by us (RE13) vs company-reported NOI (reconciliation input only, latest year)\n")
    L.append("| Company | Our NOI (bn) | Reported NOI (bn) | Difference | NOI margin (ours) | Basis |")
    L.append("|---|---:|---:|---:|---:|---|")
    for t in T:
        d = runs[t]["d"]
        L.append(f"| {t} | {bn(d['noi'][-1])} | {bn(d['noi_reported'][-1]) if d['noi_reported'][-1] is not None else 'n/a'} | "
                 f"{'n/a' if d['noi_reconciliation_pct'][-1] is None else pc(d['noi_reconciliation_pct'][-1])} | {pc(d['noi_margin'][-1])} | {d['noi_basis'][-1] or 'not computable'} |")
    # ---------------------------------------------------------------- 3b incremental return (RE18, RE22)
    L.append("\n## 3b. Incremental return, WACC proxy and spread (RE18 / RE22); Buffett 3.4 validity under M2\n")
    L.append("Direct = weighted stabilized yield + 5-year median same-property NOI growth; NOI_PROXY = computed when no yield is disclosed, valid only if net growth capital >= 5% of the economic "
             "property value, otherwise of gross real estate at cost (materiality test only, never scored; RE22).\n")
    L.append("| Company | Basis | Incremental return | WACC proxy | Spread | Why not computed / validity test | B3.4 sub-items (points / max) | B3.4 valid (M2) | B3.4 coverage of weight |")
    L.append("|---|---|---:|---:|---:|---|---|---|---:|")
    for t in T:
        d, bq = runs[t]["d"], runs[t]["bq"]
        inc, w = d["incremental"], d["wacc"]
        c = next(c for c in bq.criteria if c.id == "3.4")
        subs = ", ".join(f"{i.id}: " + ("n/a" if i.points is None else f"{i.points:.1f}") + f"/{i.max_pts:g}" + ("" if i.state in ("score", "true_zero") else f" ({i.state})") for i in c.items)
        spread = None if (inc["value"] is None or w["value"] is None) else inc["value"] - w["value"]
        basis = inc["basis"] or "missing"
        why = inc.get("reason") or (f"base {inc.get('property_base_kind')}: net growth capital {bn(inc.get('net_growth_capital'), 2)}bn vs {bn(inc.get('property_base'), 1)}bn" if basis == "NOI_PROXY" else "")
        L.append(f"| {t} | {basis} | {pc(inc['value'], 2)} | {pc(w['value'], 2)} | {pc(spread, 2)} | {why} | {subs} | {'valid' if c.valid else 'INVALID'} | {c.computed_share:.0%} |")
    n_dir = sum(1 for t in T if runs[t]["d"]["incremental"]["basis"] == "direct")
    n_px = sum(1 for t in T if runs[t]["d"]["incremental"]["basis"] == "NOI_PROXY")
    L.append(f"\nIncremental return available for {n_dir + n_px} of {len(T)} companies ({n_dir} direct, {n_px} NOI_PROXY, {len(T) - n_dir - n_px} missing).")
    # ---------------------------------------------------------------- 4 OE basis
    L.append("\n## 4. Owner-earnings basis per company (OE vs FFO_PROXY)\n")
    L.append("| Company | " + " | ".join(f"FY{y}" for y in range(2021, 2026)) + " | Maintenance capex years | TI/LC years | Straight-line tagged years |")
    L.append("|---|" + "---|" * 5 + "---|---|---|")
    for t in T:
        d, ri = runs[t]["d"], runs[t]["ri"]
        cells = [(d["oe_basis"][ri.fy.index(f"FY{y}")] or "n/a") if f"FY{y}" in ri.fy else "n/a" for y in range(2021, 2026)]
        mc = sum(1 for x in d["maint_capex"][-5:] if x is not None)
        tl = sum(1 for x in d["tilc_pres"][-5:] if x is not None)
        sl = sum(1 for x in ri.series("straight_line")[-5:] if x is not None)
        L.append(f"| {t} | " + " | ".join(cells) + f" | {mc} of 5 | {tl} of 5 | {sl} of 5 |")
    L.append("\nOE needs normalized FFO, the straight-line rent adjustment, maintenance capex and income-preserving TI/LC in the same year; with any of them missing the year is an FFO_PROXY (growth / stability sub-items only).")
    # ---------------------------------------------------------------- 5 scores
    L.append("\n## 5. Scores (M1-M9, D14), INCOME_REAL_ESTATE companies\n")
    L.append("| Company | Asset type | Buffett | Range | Coverage | Status | Graham | Range | Coverage | Status | D14 |")
    L.append("|---|---|---:|---|---:|---|---:|---|---:|---|---|")
    rg = lambda m: "withheld" if m.min_score is None else f"{m.min_score:.1f}-{m.max_score:.1f}"  # noqa: E731
    sc_ = lambda m: "n/a" if m.score is None else f"{m.score:.1f}"  # noqa: E731
    for t in T:
        bq, gq = runs[t]["bq"], runs[t]["gq"]
        L.append(f"| {t} | {runs[t]['ri'].asset_type} | {sc_(bq)} | {rg(bq)} | {bq.coverage:.0%} | {bq.status} | {sc_(gq)} | {rg(gq)} | {gq.coverage:.0%} | {gq.status} | {'FAIL' if (bq.range_error or gq.range_error) else 'ok'} |")
    errs = [(t, k) for t in T for k, m in (("Buffett", runs[t]["bq"]), ("Graham", runs[t]["gq"])) if m.range_error]
    L.append("\n**D14 range checks (min <= score <= max):** " + (f"all {2 * len(T)} model ranges are consistent." if not errs else "FAILED: " + ", ".join(f"{t} {k}" for t, k in errs)))
    r1 = {}
    for t in T:
        p = ROOT / "scripts" / "output_realestate_v4" / f"{t}.json"
        if p.exists():
            j = json.loads(p.read_text(encoding="utf-8"))
            r1[t] = (j["buffett_quality"]["score"], j["buffett_quality"]["coverage"], j["graham_quality"]["coverage"])
    L.append("\nRound 4 -> round 5 (Buffett score; coverage Buffett / Graham): " + "; ".join(
        f"{t} {('n/a' if r1[t][0] is None else format(r1[t][0], '.1f'))} -> {sc_(runs[t]['bq'])}, {r1[t][1]:.0%} -> {runs[t]['bq'].coverage:.0%} / {r1[t][2]:.0%} -> {runs[t]['gq'].coverage:.0%}" for t in T if t in r1) + ".")
    L.append("\n### 5b. Every sub-item per company (value, points / max, state, metric_basis)\n")
    for t in T:
        L.append(f"#### {t}\n")
        L.append("| Item | Name | Metric | Points / max | State | metric_basis | Reason / flags |")
        L.append("|---|---|---|---:|---|---|---|")
        for tag, m in (("B", runs[t]["bq"]), ("G", runs[t]["gq"])):
            for c in m.criteria:
                for i in c.items:
                    mb = (i.inputs or {}).get("metric_basis") if isinstance(i.inputs, dict) else None
                    why_ = (i.note or "") + (" [" + ", ".join(i.flags) + "]" if i.flags else "")
                    mv = "" if i.metric is None else (f"{i.metric:.4g}" if isinstance(i.metric, (int, float)) else str(i.metric))
                    pts = "n/a" if i.points is None else f"{i.points:.2f}"
                    L.append(f"| {tag}{c.id}.{i.id} | {i.name} | {mv} | {pts} / {i.max_pts:g} | {i.state} | {mb or '-'} | {why_.strip() or '-'} |")
        L.append("")
    L.append("### 5c. Not applicable vs missing (by item)\n")
    L.append("| Company | Not applicable | Missing | AI pending |")
    L.append("|---|---|---|---|")
    for t in T:
        na, ms, ap = [], [], []
        for tag, m in (("B", runs[t]["bq"]), ("G", runs[t]["gq"])):
            for c in m.criteria:
                for i in c.items:
                    key = f"{tag}{c.id}.{i.id}"
                    (na if i.state == "not_applicable" else ms if i.state == "missing" else ap if i.state == "ai_pending" else []).append(key)
        L.append(f"| {t} | {', '.join(na) or '-'} | {', '.join(ms) or '-'} | {len(ap)} items |")
    # ---------------------------------------------------------------- 6 K1
    L.append("\n## 6. K1 calibration data (no threshold changes)\n")
    L.append("Distribution of each section-4 metric over the INCOME_REAL_ESTATE companies where it is computed (min / p25 / median / p75 / max) and the counts at the full and zero score. "
             "**Highlighted: incremental spread, NOI margin, financial flexibility** (thresholds marked `check` in the spec).\n")
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
    L.append("\nHighlight readings: see the issues list (section 9) for what the sample can and cannot say about incremental spread, NOI margin and financial flexibility.")
    # ---------------------------------------------------------------- 7 standard
    L.append("\n## 7. Companies failing the profile test: scored under the general model v1.1 (STANDARD), reported separately\n")
    if standard:
        L.append("| Company | Reason | Buffett quality | Coverage / status | Graham quality | Coverage / status | Buffett value | Graham value (Graham Number G2-C) | Price |")
        L.append("|---|---|---:|---|---:|---|---:|---:|---:|")
        for t, s_ in standard.items():
            res, bq, bp, gq, gp = s_["out"]
            gv = gp.get("value")
            L.append(f"| {t} | {s_['reason']} | {sc_(bq)} | {bq.coverage:.0%} / {bq.status} | {sc_(gq)} | {gq.coverage:.0%} / {gq.status} | {f(bp.get('fair_value'))} | {f(gv)} | {f(s_['ri'].price_current)} |")
        L.append("\nThe general-model numbers are the production v1.1 rules (C13 ON, G1-B, G2-C, D14). Whether a real-estate operating company should instead get a dedicated rule is an open decision (section 9).")
    else:
        L.append("(none)")
    # ---------------------------------------------------------------- 8 prices / data
    L.append("\n## 8. Prices and data problems\n")
    for t in COMPANIES:
        ri = allri.get(t)
        if ri:
            L.append(f"- **{t}**: price {f(ri.price_current)} on {ri.price_date}" + ("; " + "; ".join(x for x in ri.data_problems if x.startswith(("price", "debt_total", "total_revenue"))) if ri.data_problems else ""))
    L.append("\n## 9. Open issues\n")
    ip = ROOT / "scripts" / "realestate_rule_issues_v5.md"
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(scripts/realestate_rule_issues_v5.md not written yet)")
    (OUT / "summary_realestate_v5.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sec = SecClient()
    reg_all = load_realestate_extracted()
    runs, standard, failures = {}, {}, []
    rs.OUT = OUT
    for t in COMPANIES:
        try:
            ri, raw = build_ri(sec, reg_all, t)
            sc = score_realestate(ri)
            pcx = sc["derived"]["profile_check"]
            if pcx["assignment"] == "INCOME_REAL_ESTATE" or pcx["assignment"] == "undetermined":
                runs[t] = {"ri": ri, "d": sc["derived"], "bq": sc["buffett_quality"], "gq": sc["graham_quality"], "res": run_ire(ri, raw, sc), "raw": raw}
                print(f"{t}: INCOME_REAL_ESTATE")
            else:
                out = rs.run_company(sec, t, "STANDARD", "failed the INCOME_REAL_ESTATE profile test (RE10 / RE11)")
                reason = "lease / rental revenue " + pc(pcx["rental_revenue_share"], 0) + " of revenue" if pcx["rental_ok"] is False else "real estate leased to tenants " + pc(pcx["investment_property_share"], 0) + " of assets"
                standard[t] = {"ri": ri, "d": sc["derived"], "out": out[0:1] + (out[3], out[4], out[5], out[6]) if out else None, "reason": reason}
                standard[t]["out"] = (out[0], out[3], out[4], out[5], out[6])
                print(f"{t}: STANDARD ({reason})")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    s3a_p = OUT / "s3a_other_profiles.md"
    s3a_md = s3a_p.read_text(encoding="utf-8") if s3a_p.exists() else "(run scripts/run_s3a_flags.py first)"
    if runs:
        build_summary(runs, standard, failures, sec, s3a_md)
    print("SEC requests:", sec.requests_made)


if __name__ == "__main__":
    main()

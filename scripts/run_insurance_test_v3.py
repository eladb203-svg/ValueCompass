"""INSURANCE test round 3 (spec 2026-10-13_12-05, Q6: cost of float vs the government bond yield). Quality only. Writes scripts/output_insurance_v3/.

Usage:  .venv/Scripts/python -X utf8 scripts/run_insurance_test_v3.py
Round-1 / round-2 outputs are kept (scripts/output_insurance, scripts/output_insurance_v2).
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
from run_insurance_test import COMPANIES, _item, _quart, pct, usd  # noqa: E402
from run_insurance_test_v2 import LINES, _crit_pts, _med, _ranks  # noqa: E402
from src.providers.insurance_facts import load_gov_yields, load_insurance_regulatory  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring.insurance import LINE_OF_BUSINESS, InsuranceInputs  # noqa: E402

OUT = ROOT / "scripts" / "output_insurance_v3"
R2 = ROOT / "scripts" / "output_insurance_v2"
SPEC = "docs/scoring/ValueCompass_Insurance_Rules_2026-10-13_12-05_EN.md"
# currency of the float: the statements of all 12 companies are in USD; AFL's float is economically yen (user ruling for this round)
FLOAT_CURRENCY = {"AFL": "JPY"}
YIELDS = load_gov_yields()


def _make_inputs(*a, **kw):
    ii = InsuranceInputs(*a, **kw)
    cur = FLOAT_CURRENCY.get(ii.ticker, "USD")
    ii.yield_currency, ii.gov_yield = cur, dict(YIELDS[cur]["yields"])
    ii.yield_source = f"{YIELDS[cur]['source']} (table {YIELDS[cur]['version']}, retrieved {YIELDS[cur]['retrieved']})"
    return ii


def _rg(m):
    return "withheld" if m.min_score is None else f"{m.min_score:.1f}-{m.max_score:.1f}"


def _p2(x, nd=2):
    return "n/a" if x is None else f"{x * 100:.{nd}f}%"


def build_summary(runs, failures):
    T = list(runs)
    old = {t: json.loads((R2 / f"{t}.json").read_text(encoding="utf-8")) for t in T}
    L = [f"# ValueCompass INSURANCE test round 3 (quality only) - {date.today().isoformat()}\n",
         f"Spec: `{SPEC}` (supersedes 11-45). Q6: Buffett 3.5.1, 3.5.2 and the condition of 3.5.4 now measure the **cost of float against the government bond yield** "
         "instead of the underwriting margin (kept as a display field). Everything else is as in round 2; section-4 thresholds unchanged (K1). No pricing; no DB; "
         "AI questions stay `ai_pending`. Earlier outputs are kept (`output_insurance`, `output_insurance_v2`).\n"]
    if failures:
        L.append("**Failed:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    # ---------------------------------------------------------------- yields
    L.append("## 1. Government yield constants (versioned table `scripts/gov_yields.csv`, built by `scripts/build_gov_yields.py`)\n")
    L.append("Annual average of the daily 10-year yield. USD: Board of Governors of the Federal Reserve (H.15) series DGS10 via FRED. JPY: Japan Ministry of Finance JGB 10-year "
             "(official daily history); cross-check with the OECD monthly series on FRED agrees within 0.02pp. Both series were fetched; nothing is estimated. "
             f"Version {YIELDS['USD']['version']}, retrieved {YIELDS['USD']['retrieved']}.\n")
    L.append("| Currency | " + " | ".join(str(y) for y in range(2016, 2026)) + " | Used for |")
    L.append("|---|" + "---:|" * 10 + "---|")
    for cur in ("USD", "JPY"):
        used = ", ".join(t for t in COMPANIES if FLOAT_CURRENCY.get(t, "USD") == cur)
        L.append(f"| {cur} | " + " | ".join(f"{YIELDS[cur]['yields'][y] * 100:.2f}%" for y in range(2016, 2026)) + f" | {used} |")
    L.append("\nCurrency choice: all 12 sets of statements are in USD, so the USD Treasury yield is used for 11 companies; **AFL uses the JGB yield (its float is mostly yen-denominated, "
             "as instructed)**. The cost of float is a ratio, so it is currency-neutral. MET, PRU, AIG and CB also hold material non-USD float; they are compared with the USD yield "
             "(flagged in the open issues).\n")
    # ---------------------------------------------------------------- per company-year
    L.append("## 2. Cost of float per company-year (USD bn; cost = -underwriting result / average float)\n")
    L.append("Underwriting result as in round 2 (with the Q1 accretion adjustment). Average float = mean of the beginning and end of year float (ex discount-rate remeasurement). "
             "Cost gap = cost of float - yield. `n/a` = missing (reason in the last column).\n")
    L.append("| Company | Line | FY | Underwriting result | Average float | Cost of float | Yield | Cost gap | Cost / yield | Below yield | Note |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---|---|")
    for t in T:
        d, ii = runs[t]["d"], runs[t]["ii"]
        for i in range(ii.n - 5, ii.n):
            c, y = d["cost_of_float"][i], d["gov_yield_yr"][i]
            L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {ii.fy[i]} | {usd(d['underwriting_result'][i], 2)} | {usd(d['avg_float'][i], 1)} | {_p2(c)} | {_p2(y)} | "
                     f"{_p2(d['cost_gap'][i])} | {'n/a' if d['cost_ratio'][i] is None else format(d['cost_ratio'][i], '.2f')} | "
                     f"{'n/a' if (c is None or y is None) else ('yes' if c < y else 'no')} | {d['cost_flags'][i] or ''} |")
    L.append("\n### Items 3.5.1 / 3.5.2 / 3.5.4 per company\n")
    L.append("| Company | Currency | 5y median cost / yield | 3.5.1 (6) | Years below yield | 3.5.2 (3) | Cumulative cost vs cumulative yield | 3.5.4 condition | 3.5.4 (2) | Underwriting margin (display, 5y median) |")
    L.append("|---|---|---:|---:|---:|---:|---|---|---:|---:|")
    for t in T:
        d, bq = runs[t]["d"], runs[t]["bq"]
        i1, i2, i4 = _item(bq, "3.5", "1"), _item(bq, "3.5", "2"), _item(bq, "3.5", "4")
        cond = i4.inputs.get("cheap_float_condition")
        cum = (f"{_p2(i4.inputs['cumulative_cost'])} vs {_p2(i4.inputs['cumulative_yield'])}" if "cumulative_cost" in i4.inputs else "n/a")
        L.append(f"| {t} | {runs[t]['ii'].yield_currency} | {'n/a' if i1.metric is None else format(i1.metric, '.2f')} | {'n/a' if i1.points is None else format(i1.points, '.2f')} | "
                 f"{'n/a' if i2.metric is None else format(i2.metric, '.1f')} | {'n/a' if i2.points is None else format(i2.points, '.2f')} | {cum} | "
                 f"{'n/a' if cond is None else ('PASS' if cond else 'FAIL')} | {'n/a' if i4.points is None else format(i4.points, '.2f')} ({i4.state}) | "
                 f"{_p2(_med(d['underwriting_margin'][-5:]), 1)} |")
    # ---------------------------------------------------------------- round 2 vs round 3
    L.append("\n## 3. Round 2 vs round 3\n")
    rb2 = _ranks({t: old[t]["buffett_quality"]["score"] for t in T})
    rb3 = _ranks({t: runs[t]["bq"].score for t in T})
    rg2 = _ranks({t: old[t]["graham_quality"]["score"] for t in T})
    rg3 = _ranks({t: runs[t]["gq"].score for t in T})
    L.append("| Company | Line | Buffett R2 -> R3 | Rank | Graham R2 -> R3 | Rank | Coverage B R2 -> R3 | Coverage G R2 -> R3 | Range B (R3) | Range G (R3) | Invalid criteria R2 -> R3 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")

    def inv(mj):
        return ", ".join(("B" if mj["model"].startswith("buffett") else "G") + c["id"] for c in mj["invalid_criteria"]) or "-"
    for t in T:
        bq, gq = runs[t]["bq"], runs[t]["gq"]
        o_b, o_g = old[t]["buffett_quality"], old[t]["graham_quality"]
        L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {o_b['score']:.1f} -> {bq.score:.1f} ({bq.score - o_b['score']:+.1f}) | {rb2[t]} -> {rb3[t]}{' *' if rb2[t] != rb3[t] else ''} | "
                 f"{o_g['score']:.1f} -> {gq.score:.1f} ({gq.score - o_g['score']:+.1f}) | {rg2[t]} -> {rg3[t]}{' *' if rg2[t] != rg3[t] else ''} | "
                 f"{o_b['coverage']:.0%} -> {bq.coverage:.0%} | {o_g['coverage']:.0%} -> {gq.coverage:.0%} | {_rg(bq)} | {_rg(gq)} | "
                 f"{inv(o_b)} / {inv(o_g)} -> {inv(runs[t]['res']['buffett_quality'])} / {inv(runs[t]['res']['graham_quality'])} |")
    chg_b = [f"{t} {rb2[t]}->{rb3[t]}" for t in T if rb2[t] != rb3[t]]
    chg_g = [f"{t} {rg2[t]}->{rg3[t]}" for t in T if rg2[t] != rg3[t]]
    L.append(f"\n`*` = rank changed. Rank changes - Buffett: {', '.join(chg_b) or 'none'}; Graham: {', '.join(chg_g) or 'none'} (Graham has no Q6 item and is unchanged).")
    errs = [(t, k) for t in T for k, m in (("Buffett", runs[t]["bq"]), ("Graham", runs[t]["gq"])) if m.range_error]
    L.append("\n**D14 range checks (min <= score <= max), round 3:** " + ("all 24 model ranges are consistent." if not errs else "FAILED: " + ", ".join(f"{t} {k}" for t, k in errs)))
    big = [f"{t} Buffett {runs[t]['bq'].score - old[t]['buffett_quality']['score']:+.1f}" for t in T if abs(runs[t]["bq"].score - old[t]["buffett_quality"]["score"]) > 3]
    L.append("\nBuffett moves larger than 3 points: " + (", ".join(big) or "none") + ".\n")
    L.append("### Per criterion (points / applicable maximum; `!` = invalid under M2), round 2 -> round 3 (Buffett; Graham is unchanged)\n")
    cids = [c.id for c in runs[T[0]]["bq"].criteria]
    L.append("| Company | " + " | ".join(f"B{c}" for c in cids) + " |")
    L.append("|---|" + "---|" * len(cids))
    for t in T:
        cells = []
        for c in cids:
            o_obs, o_mx, o_valid = _crit_pts(old[t]["buffett_quality"], c)
            n_obs, n_mx, n_valid = _crit_pts(runs[t]["res"]["buffett_quality"], c)
            a = f"{o_obs:.1f}/{o_mx:g}" + ("" if o_valid else "!")
            b = f"{n_obs:.1f}/{n_mx:g}" + ("" if n_valid else "!")
            cells.append(a if a == b else f"{a} -> **{b}**")
        L.append(f"| {t} | " + " | ".join(cells) + " |")
    gchg = [t for t in T if abs(runs[t]["gq"].score - old[t]["graham_quality"]["score"]) > 0.005]
    L.append("\nGraham score changes: " + (", ".join(gchg) or "none") + ".\n")
    L.append("### Buffett 3.5 sub-items, round 2 -> round 3\n")
    L.append("| Company | 3.5.1 | 3.5.2 | 3.5.3 | 3.5.4 | 3.5 total |")
    L.append("|---|---|---|---|---|---|")
    for t in T:
        cells, tot2, tot3 = [], 0.0, 0.0
        for iid in ("1", "2", "3", "4"):
            o = next(i for c in old[t]["buffett_quality"]["criteria"] if c["id"] == "3.5" for i in c["items"] if i["id"] == iid)
            n = _item(runs[t]["bq"], "3.5", iid)
            op, np_ = o["points"], n.points
            tot2 += op or 0.0
            tot3 += np_ or 0.0
            cells.append(f"{o['state'] if op is None else f'{op:.2f}'} -> {n.state if np_ is None else f'{np_:.2f}'}")
        L.append(f"| {t} | " + " | ".join(cells) + f" | {tot2:.1f} -> {tot3:.1f} |")
    # ---------------------------------------------------------------- K1
    L.append("\n## 4. K1 distribution of the cost of float by line of business (no threshold change)\n")
    L.append("5-year values per company (cost of float and the cost gap against the yield; the yearly detail is in section 2).\n")
    L.append("| Line | Company | Cost of float, 5y median | Yield, 5y median | Cost gap, 5y median | Cost / yield, 5y median | Years below yield | Cumulative cost vs yield | 3.5.1 | 3.5.2 |")
    L.append("|---|---|---:|---:|---:|---:|---:|---|---:|---:|")
    allc = {}
    for line in LINES:
        for t in [x for x in T if LINE_OF_BUSINESS[x] == line]:
            d = runs[t]["d"]
            cost = [x for x in d["cost_of_float"][-5:] if x is not None]
            yl = [x for x, c in zip(d["gov_yield_yr"][-5:], d["cost_of_float"][-5:]) if x is not None and c is not None]
            gp = [x for x in d["cost_gap"][-5:] if x is not None]
            cr = [x for x in d["cost_ratio"][-5:] if x is not None]
            nb = sum(1 for c, y in zip(cost, yl) if c < y)
            i1, i2 = _item(runs[t]["bq"], "3.5", "1"), _item(runs[t]["bq"], "3.5", "2")
            allc[t] = statistics.median(cost) if cost else None
            L.append(f"| {line} | {t} | {_p2(statistics.median(cost)) if cost else 'n/a'} | {_p2(statistics.median(yl)) if yl else 'n/a'} | {_p2(statistics.median(gp)) if gp else 'n/a'} | "
                     f"{format(statistics.median(cr), '.2f') if cr else 'n/a'} | {nb} of {len(cost)} | {_p2(sum(cost))} vs {_p2(sum(yl))} | "
                     f"{'n/a' if i1.points is None else format(i1.points, '.2f')} | {'n/a' if i2.points is None else format(i2.points, '.2f')} |")
    L.append("\n| Line | n | min / median / max of the company 5y-median cost of float | Median cost gap | Companies at full 3.5.1 (cost <= 0) | Companies at zero 3.5.1 (cost >= yield) |")
    L.append("|---|---:|---|---:|---:|---:|")
    for line in LINES:
        ts = [x for x in T if LINE_OF_BUSINESS[x] == line]
        vals = [allc[t] for t in ts if allc[t] is not None]
        gaps = [statistics.median([x for x in runs[t]["d"]["cost_gap"][-5:] if x is not None]) for t in ts if any(x is not None for x in runs[t]["d"]["cost_gap"][-5:])]
        full = sum(1 for t in ts if (_item(runs[t]["bq"], "3.5", "1").points or 0) >= 6 - 1e-6)
        zero = sum(1 for t in ts if _item(runs[t]["bq"], "3.5", "1").points == 0)
        rng = "n/a" if not vals else f"{_p2(min(vals))} / {_p2(statistics.median(vals))} / {_p2(max(vals))}"
        L.append(f"| {line} | {len(ts)} | {rng} | {_p2(statistics.median(gaps)) if gaps else 'n/a'} | {full} | {zero} |")
    q = _quart([v for v in allc.values() if v is not None])
    L.append("\nAll 12 companies (5y-median cost of float): " + ("n/a" if q is None else " / ".join(_p2(v) for v in q)) +
             f" (min / p25 / median / p75 / max); at full score 3.5.1: {sum(1 for t in T if (_item(runs[t]['bq'], '3.5', '1').points or 0) >= 6 - 1e-6)}, at zero: "
             f"{sum(1 for t in T if _item(runs[t]['bq'], '3.5', '1').points == 0)}.")
    L.append("\nUnderwriting margin, round 2 vs the cost-of-float view (5y medians): the lines now sit on one scale.\n")
    L.append("| Line | Company | Underwriting margin | Cost of float | Underwriting result >= 0 (years) | Years cost below yield |")
    L.append("|---|---|---:|---:|---:|---:|")
    for line in LINES:
        for t in [x for x in T if LINE_OF_BUSINESS[x] == line]:
            d = runs[t]["d"]
            ur = [x for x in d["underwriting_result"][-5:] if x is not None]
            nb = sum(1 for c, y in zip(d["cost_of_float"][-5:], d["gov_yield_yr"][-5:]) if c is not None and y is not None and c < y)
            L.append(f"| {line} | {t} | {_p2(_med(d['underwriting_margin'][-5:]), 1)} | {_p2(allc[t])} | {sum(1 for x in ur if x >= 0)} of {len(ur)} | {nb} |")
    L.append("\n## 5. Scores (round 3)\n")
    L.append("| Company | Line | Buffett | Range | Coverage | Status | Graham | Range | Coverage | Status |")
    L.append("|---|---|---:|---|---:|---|---:|---|---:|---|")
    for t in T:
        bq, gq = runs[t]["bq"], runs[t]["gq"]
        L.append(f"| {t} | {LINE_OF_BUSINESS[t]} | {bq.score:.1f} | {_rg(bq)} | {bq.coverage:.0%} | {bq.status} | {gq.score:.1f} | {_rg(gq)} | {gq.coverage:.0%} | {gq.status} |")
    L.append("\n## 6. Open issues\n")
    ip = ROOT / "scripts" / "insurance_rule_issues_v3.md"
    L.append(ip.read_text(encoding="utf-8") if ip.exists() else "(scripts/insurance_rule_issues_v3.md not written yet)")
    L.append("\n## Data problems by company\n")
    for t in T:
        L.append(f"- **{t}**: " + ("; ".join(runs[t]["res"]["data_problems"]) if runs[t]["res"]["data_problems"] else "none detected"))
    (OUT / "summary_insurance_v3.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    r1.OUT = OUT
    r1.InsuranceInputs = _make_inputs
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

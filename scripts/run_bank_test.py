"""BANK profile test round: 12 banks, SEC XBRL + extracted FY2025 regulatory items + yfinance prices. No DB, no AI.

Usage: .venv/Scripts/python scripts/run_bank_test.py [TICKER ...]
Outputs (untracked): scripts/output_banks/<TICKER>.json and scripts/output_banks/summary_banks.md
"""
from __future__ import annotations

import csv
import json
import sys
import traceback
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from bank_report_v2 import build_summary_v2  # noqa: E402
from run_scoring_test import cell, fnum, jsonable, model_cell, model_json, pct  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.bank_facts import build_bank_series, load_regulatory  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring.bank import BankInputs, bank_path, score_bank  # noqa: E402

OUT = ROOT / "scripts" / "output_banks"
RULE_ISSUES = ROOT / "scripts" / "bank_rule_issues.md"
MODEL_VERSION = "bank-rules-2026-10-12_22-35 (D10-D15, V1-V11, pricing v2) on general model 1.0 (2026-10-11_22-30) + D14 range fix"

# ticker -> required CET1 (Federal Reserve, effective Oct 1 2025; minimum + SCB + G-SIB surcharge), given by the user
BANKS = {"JPM": 11.5, "BAC": 10.0, "C": 11.6, "WFC": 8.5, "USB": 7.1, "PNC": 7.0, "TFC": 7.0, "MTB": 7.2,
         "FITB": 7.7, "KEY": 7.7, "FLG": 7.0, "GS": 10.9}


def run_bank(sec, reg_all, ticker):
    splits = price_provider.get_splits(ticker)
    raw = build_bank_series(sec, ticker, splits)
    pr = price_provider.load_prices(ticker, raw["ends"], raw["labels"])
    reg = reg_all.get(ticker, {})
    f = raw["f"]
    # profile path (computed from the data; GS is expected to be 1b)
    assets, equity, deposits = f["assets"][-1], f["equity"][-1], f["deposits"][-1]
    loans = f["loans"][-1]
    if loans is None and "loans_2025" in reg:
        loans = reg["loans_2025"]["value"] * 1e6
    liabilities = None if (assets is None or equity is None) else assets - equity
    lcr = reg.get("lcr_q4_average", {}).get("value")
    path = bank_path(raw["sic"], deposits, liabilities, loans, assets, "cet1_ratio_standardized" in reg or "cet1_ratio_advanced" in reg,
                     isinstance(lcr, float))
    bi = BankInputs(ticker=ticker, name=raw["name"], path=path["path"] or "unassigned", fy=raw["labels"], end=raw["ends"], f=f,
                    reg=reg, required_cet1=BANKS[ticker], price_current=pr["current"], price_avg=pr["avg"],
                    first_annual_report=raw["first_annual_report"], as_of=date.today(), flags=list(raw["flags"]),
                    data_problems=list(raw["problems"]) + list(pr["notes"]), tag_log=raw["tag_log"])
    if path["path"] is None:
        res = {"ticker": ticker, "state": "sector_not_supported_v1", "reason": "bank profile path not assigned", "path": path}
        (OUT / f"{ticker}.json").write_text(json.dumps(jsonable(res), indent=1), encoding="utf-8")
        return None
    sc = score_bank(bi)
    d, bq, bp, gq, gp = sc["derived"], sc["buffett_quality"], sc["buffett_price"], sc["graham_quality"], sc["graham_price"]
    lt = d["latest"]
    # approach-matched buffer (display): Citi's Standardized requirement is 11.6, Advanced 10.5
    extra = {}
    if ticker == "C" and lt.get("cet1_std") is not None and lt.get("cet1_adv") is not None:
        extra["approach_matched_buffer"] = {"standardized_13.18_vs_11.6": lt["cet1_std"] - 11.6,
                                            "advanced_11.93_vs_10.5": lt["cet1_adv"] - 10.5}
    for k, v in lt.get("flags", []) and {"flags": lt["flags"]}.items():
        bi.data_problems += [f"latest-year resolution: {x}" for x in v]
    if lt.get("unmapped_loan_lines"):
        bi.data_problems.append(f"unmapped loan lines: {lt['unmapped_loan_lines']}")
    if lt.get("loans_mapped_share") is not None and not 0.97 <= lt["loans_mapped_share"] <= 1.03:
        bi.data_problems.append(f"mapped loan lines = {lt['loans_mapped_share']:.1%} of total loans")
    result = {
        "ticker": ticker, "name": raw["name"], "cik": raw["cik"], "profile": "BANK", "path": path,
        "scoring_model_version": MODEL_VERSION, "as_of": date.today(), "required_cet1": BANKS[ticker],
        "price": {"current": pr["current"], "current_date": pr["current_date"], "source": pr["source"],
                  "annual_average": dict(zip(bi.fy, pr["avg"])), "splits": pr["splits"]},
        "first_annual_report": raw["first_annual_report"], "fiscal_years": dict(zip(bi.fy, bi.end)),
        "financials": {k: dict(zip(bi.fy, v)) for k, v in f.items()},
        "derived": {k: dict(zip(bi.fy, v)) for k, v in d.items() if isinstance(v, list)},
        "latest": lt, "extra": extra,
        "buffett_quality": model_json(bq), "buffett_price": bp, "graham_quality": model_json(gq), "graham_price": gp,
        "flags": bi.flags, "data_problems": list(dict.fromkeys(bi.data_problems)),
        "data_source": {"sec_companyfacts": f"CIK{raw['cik']}", "tag_log_per_field_per_year": raw["tag_log"],
                        "regulatory_csv_rows": {k: v for k, v in reg.items()}},
    }
    (OUT / f"{ticker}.json").write_text(json.dumps(jsonable(result), indent=1, ensure_ascii=False), encoding="utf-8")
    return result, bi, d, bq, bp, gq, gp


def _fmt_money(x):
    return "n/a" if x is None else f"{x / 1e9:,.1f}"


def _val(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def _buy(b):
    b = b or {}
    if b.get("state") == "computed":
        return f"{b['buy_price']:.2f}"
    if b.get("state") == "not_suitable":
        return "not suitable (<55)"
    if b:
        info = b.get("informational_buy_price_ignoring_coverage")
        return "none (" + b.get("reason", "") + ")" + (f"; info only: {info:.2f}" if info else "")
    return "-"


def _ps(p):
    ps = (p or {}).get("price_score") or {}
    return "n/a" if ps.get("points") is None else f"{ps['points']:.1f} (disc {pct(ps['discount'])})"


def build_summary(rows, failures, reg_all):
    L = []
    L.append(f"# ValueCompass BANK test round - {date.today().isoformat()}\n")
    L.append(f"Scoring: `{MODEL_VERSION}`. Spec: `docs/scoring/ValueCompass_Bank_Rules_2026-10-12_13-10_EN.md` (extends the v1.0 general "
             "model; the general model is unchanged). Data: SEC companyfacts XBRL (10 fiscal years), FY2025 10-K text extraction "
             "(`scripts/bank_regulatory.csv`, 213 verified rows with exact quotes), prices from yfinance. No DB. AI questions are "
             "`ai_pending` (excluded from validity and coverage, shown in the min-max range, as in the test rounds). "
             "Required CET1 per bank was supplied (Federal Reserve, effective Oct 1 2025).\n")
    if failures:
        L.append("**Failed banks:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    L.append("## 1. Results per bank\n")
    L.append("### Buffett (BANK)\n")
    L.append("| Bank | Path | Price | TBVPS | P/TBV | ROTCE 5y median (norm.) | Quality (normalized) | Fair value (justified P/TBV) | "
             "Price score | Buy price | Implied return | Implied ROTCE |")
    L.append("|---|---|---:|---:|---:|---|---|---|---|---|---|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        t = res["ticker"]
        rotce = f"{pct(bp.get('rotce_median'), 1)} ({pct(bp.get('rotce_norm'), 1)})" if bp.get("rotce_median") is not None else "n/a"
        fv = _val(bp.get("fair_value")) if bp.get("state") == "valued" else f"cannot be valued: {bp.get('reason', '')}"
        ir = pct(bp.get("implied_return"), 1) if bp.get("implied_return") is not None else "-"
        irot = pct(bp.get("implied_rotce"), 1) if bp.get("implied_rotce") is not None else "-"
        tb = d["tbvps"][-1]
        ptbv = bp.get("price_to_tbv")
        L.append(f"| {t} | {res['path']['path']} | {_val(res['price']['current'])} | {_val(tb)} | "
                 f"{'-' if ptbv is None else f'{ptbv:.2f}x'} | {rotce} | {model_cell(res['buffett_quality'])} | {fv} | {_ps(bp)} | "
                 f"{_buy(bp.get('buy_price'))} | {ir} | {irot} |")
    L.append("\n### Graham (BANK)\n")
    L.append("| Bank | Quality (normalized) | Graham Number on tangible book | Price score | Buy price |")
    L.append("|---|---|---|---|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        val = _val(gp.get("value")) if gp.get("state") == "valued" else f"cannot be valued: {gp.get('reason', '')}"
        L.append(f"| {res['ticker']} | {model_cell(res['graham_quality'])} | {val} | {_ps(gp)} | {_buy(gp.get('buy_price'))} |")
    L.append("\n### Invalid / pending criteria\n")
    for res, *_ in rows:
        inv = [f"B{c['id']}" for c in res["buffett_quality"]["invalid_criteria"]] + [f"G{c['id']}" for c in res["graham_quality"]["invalid_criteria"]]
        pend = [f"B{c}" for c in res["buffett_quality"]["pending_criteria"]] + [f"G{c}" for c in res["graham_quality"]["pending_criteria"]]
        L.append(f"- {res['ticker']}: invalid: {', '.join(inv) or 'none'}; pending: {', '.join(pend) or 'none'}")

    L.append("\n### Key inputs (latest FY)\n")
    L.append("| Bank | Latest FY | Bank revenue (bn) | Net income (bn) | TCE (bn) | Loans (bn) | CET1 std / adv | Binding (approach) | Required | Buffer (pp) | "
             "LCR | NPL rate | ACL/NPL | NCO rate 5y median | Worst NCO rate | HHI | CRE / total capital |")
    L.append("|---|---|---:|---:|---:|---:|---|---|---:|---:|---|---|---|---|---|---|---|")
    for res, bi, d, bq, bp, gq, gp in rows:
        lt = d["latest"]
        npl_rate = None if not lt["npl"] or not lt["loans_latest"] else lt["npl"] / lt["loans_latest"]
        cov = None if not lt["npl"] or lt["acl"] is None else lt["acl"] / lt["npl"]
        rates = [x for x in d["nco_rate"] if x is not None]
        r5 = [x for x in d["nco_rate"][-5:] if x is not None]
        cats = lt["loan_categories"]
        tot = sum(cats.values())
        hhi = None if not tot else sum((v / tot) ** 2 for v in cats.values())
        cre_tc = None if not lt.get("total_capital") or not tot else cats["commercial_real_estate"] / lt["total_capital"]
        L.append(f"| {res['ticker']} | {bi.fy[-1]} | {_fmt_money(d['revenue'][-1])} | {_fmt_money(bi.series('net_income')[-1])} | "
                 f"{_fmt_money(d['tce'][-1])} | {_fmt_money(lt['loans_latest'])} | "
                 f"{'-' if lt['cet1_std'] is None else lt['cet1_std']} / {'-' if lt['cet1_adv'] is None else lt['cet1_adv']} | "
                 f"{'-' if lt['cet1_ratio'] is None else lt['cet1_ratio']} ({lt['approach']}) | {lt['required_cet1']} | "
                 f"{'-' if lt['capital_buffer'] is None else f'{lt['capital_buffer']:.2f}'} | {lt['lcr']} | "
                 f"{pct(npl_rate, 2)} | {'-' if cov is None else f'{cov:.0%}'} | "
                 f"{pct(sorted(r5)[len(r5) // 2], 2) if r5 else '-'} ({len(r5)}y) | {pct(max(rates), 2) if rates else '-'} ({len(rates)}y) | "
                 f"{'-' if hhi is None else f'{hhi:.3f}'} | {'-' if cre_tc is None else f'{cre_tc:.0%}'} |")

    L.append("\n### Profile assignment\n")
    L.append("| Bank | SIC | Deposits / liabilities | Loans / assets | Path |")
    L.append("|---|---|---:|---:|---|")
    for res, *_ in rows:
        p = res["path"]
        L.append(f"| {res['ticker']} | {p['sic']} | {pct(p['deposits_to_liabilities'], 1)} | {pct(p['loans_to_assets'], 1)} | {p['path']} |")

    L.append("\n## 2. Sub-item heat-map\n")
    L.append("`AI` = ai_pending, `n/a` = not applicable, `MISS` = missing data, `0•` = true zero. Maximum points in the header.\n")
    for key, label, groups in (("buffett_quality", "Buffett", [("3.1", "3.2", "3.3", "3.4"), ("3.5", "3.6", "3.7", "3.8")]),
                               ("graham_quality", "Graham", [("3.1", "3.2", "3.3", "3.4"), ("3.5", "3.6", "3.7", "3.8")])):
        for grp in groups:
            cols = []
            for c in rows[0][0][key]["criteria"]:
                if c["id"] in grp:
                    for it in c["items"]:
                        cols.append((c["id"], it["id"], it["max_pts"]))
            L.append(f"\n**{label} quality {grp[0]}-{grp[-1]} (BANK)**\n")
            L.append("| Bank | " + " | ".join(f"{a}.{b} ({m:g})" for a, b, m in cols) + " |")
            L.append("|---|" + "---:|" * len(cols))
            for res, *_ in rows:
                cmap = {(c["id"], it["id"]): it for c in res[key]["criteria"] for it in c["items"]}
                L.append(f"| {res['ticker']} | " + " | ".join(cell(cmap[(a, b)]) for a, b, _ in cols) + " |")

    L.append("\n## 3. Extraction table (FY2025 10-K text; exact quotes from the converted filing text)\n")
    L.append("Amounts in USD millions unless the unit says otherwise (some banks report in billions: see note). `verified` = the extracted "
             "number occurs inside the quote.\n")
    L.append("| Bank | Item | Value | Unit | 10-K section | Exact quote | Verified | Note |")
    L.append("|---|---|---:|---|---|---|---|---|")
    for t in BANKS:
        for item, r_ in reg_all.get(t, {}).items():
            q = r_["quote"].replace("|", "\\|")
            L.append(f"| {t} | {item} | {r_['value']} | {r_['unit']} | {r_['section']} | {q} | {'yes' if r_['verified'] else 'NO'} | {r_['note']} |")

    L.append("\n## 4. Data problems\n")
    for res, bi, *_ in rows:
        L.append(f"\n**{res['ticker']}**\n")
        probs = res["data_problems"]
        L += [f"- {x}" for x in probs] if probs else ["- none detected"]
    L.append("\n## 5. Rule issues\n")
    L.append(RULE_ISSUES.read_text(encoding="utf-8") if RULE_ISSUES.exists() else "(scripts/bank_rule_issues.md not written yet)")
    (OUT / "summary_banks.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = {a.upper() for a in argv}
    sec = SecClient()
    reg_all = load_regulatory()
    rows, failures = [], []
    for t in BANKS:
        if wanted and t not in wanted:
            continue
        try:
            r = run_bank(sec, reg_all, t)
            if r is None:
                print(f"{t}: not scored (sector_not_supported_v1)")
                continue
            rows.append(r)
            print(f"{t}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((t, f"{type(e).__name__}: {e}"))
            print(f"{t}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    if rows:
        build_summary_v2(rows, reg_all, failures, list(BANKS))
    print(f"SEC requests this run: {sec.requests_made}")


if __name__ == "__main__":
    main(sys.argv[1:])

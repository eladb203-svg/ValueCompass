"""HISTORICAL (2026-10-14): G3 (no debt subtraction) was rejected; flag removed 2026-10-14 (v1.2); the output of this regression is kept in scripts/output_v12_g3*/.
G3 regression (general model, flag OFF in production): Buffett value with vs without the financial-debt subtraction, on the 20 STANDARD/TECH companies.
Cached data only, no DB, no AI. Writes scripts/output_v12_g3/summary_v12_g3.md and g3.json."""
from __future__ import annotations

raise SystemExit("HISTORICAL: the g3 / g3c_unlevered flags no longer exist; outputs are kept in scripts/output_v12_g3/ and scripts/output_v12_g3c/.")


import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_scoring_test import COMPANIES  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.sec_companyfacts import SecClient, build_inputs  # noqa: E402
from src.scoring.candidates import candidates  # noqa: E402
from src.scoring.inputs import CompanyInputs  # noqa: E402
from src.scoring.profiles import score_company  # noqa: E402

OUT = ROOT / "scripts" / "output_v12_g3"
MC = ["UNH", "ELV", "CI", "HUM", "CNC", "MOH"]
UNIVERSE = [(t, p) for t, p, _ in COMPANIES] + [(t, "STANDARD") for t in MC]
NL = "\n"


def f(x, nd=2):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def pc(x):
    return "n/a" if x is None else f"{x:+.1%}"


def buy(b):
    if not b:
        return None
    return b.get("buy_price") if b.get("state") == "computed" else None


def snap(sc):
    bp = sc["buffett_price"]
    return {"state": bp.get("state"), "value": bp.get("fair_value"), "modeled_value": bp.get("fair_value") if bp.get("fair_value") is not None else bp.get("modeled_value_nonpositive"),
            "price_score": (bp.get("price_score") or {}).get("points"), "buy": buy(bp.get("buy_price")), "buy_state": (bp.get("buy_price") or {}).get("state"),
            "base": bp.get("oe_base"), "reason": bp.get("reason"), "growth": bp.get("stage1_growth")}


def main():
    sec = SecClient()
    res = {}
    for t, prof in UNIVERSE:
        raw = build_inputs(sec, t, prof, price_provider.get_splits(t))
        pr = price_provider.load_prices(t, raw["ends"], raw["labels"])
        inp = CompanyInputs(ticker=t, name=raw["name"], profile=prof, fy=raw["labels"], end=raw["ends"], f=raw["f"], sbc_state=raw["sbc_state"],
                            price_current=pr["current"], price_avg=pr["avg"], first_annual_report=raw["first_annual_report"], as_of=date.today(),
                            flags=list(raw["flags"]), data_problems=list(raw["problems"]) + list(pr["notes"]), tag_log=raw["tag_log"], assumed_zero=raw["assumed_zero"])
        cur = score_company(inp)
        with candidates(g3_no_debt=True):
            cand = score_company(inp)
        d = cur["derived"]
        oe = d["owner_earnings"][-1]
        base = cur["buffett_price"].get("oe_base")
        intr = inp.series("interest_expense")[-1]
        cash, debt = d["cash_sti"][-1], d["fin_debt"][-1]
        nd = None if cash is None or debt is None else debt - cash
        den = base if base else oe
        res[t] = {"profile": prof, "price": pr["current"], "current": snap(cur), "g3": snap(cand), "interest_expense": intr, "oe_latest": oe, "oe_base": base,
                  "interest_pct_oe": None if intr is None or not den or den <= 0 else intr / den, "net_debt": nd,
                  "net_debt_to_oe": None if nd is None or not den or den <= 0 else nd / den, "shares": inp.series("shares")[-1]}
        print(t, "ok")

    L = [f"# G3 regression: Buffett value with vs without the financial-debt subtraction - {date.today().isoformat()}" + NL,
         "General model v1.1, 20 STANDARD / TECH companies (14 round companies + 6 managed care), cached data, flag `g3_no_debt` ON only inside this run (production default OFF). "
         "Current: value = (PV of owner-earnings flows + discounted terminal + cash and short-term investments - financial debt) / diluted shares. "
         "Candidate: the same without the debt subtraction (owner earnings are CFO-based, i.e. after interest). Everything else (base, growth, gate, 10% discount, quality score, margin of safety) is unchanged. "
         "Interest = income-statement interest expense (the ETL has no cash-paid interest tag), as % of the owner-earnings base (5-year median, rolled forward when G1 allows). Net debt = financial debt - cash and short-term investments. "
         "Companies whose value changes by more than 15% are marked **>15%**." + NL,
         "| Company | Price | Value now | Value G3 | Change | Price score now | Price score G3 | Buy price now | Buy price G3 | Interest / OE | Net debt / OE | Flag |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    flagged = []
    for t, r in res.items():
        a, b = r["current"], r["g3"]
        va, vb = a["value"], b["value"]
        ch = None if va is None or vb is None or va == 0 else vb / va - 1
        mark = ""
        if ch is not None and abs(ch) > 0.15:
            mark = "**>15%**"
            flagged.append(t)
        elif (va is None) != (vb is None):
            mark = "**state change**"
            flagged.append(t)
        r["change"] = ch
        L.append(f"| {t} | {f(r['price'])} | {f(va) if va is not None else a['state'] + (' (' + f(a['modeled_value']) + ')' if a['modeled_value'] is not None else '')} | "
                 f"{f(vb) if vb is not None else b['state'] + (' (' + f(b['modeled_value']) + ')' if b['modeled_value'] is not None else '')} | {pc(ch)} | {f(a['price_score'])} | {f(b['price_score'])} | "
                 f"{f(a['buy']) if a['buy'] is not None else (a['buy_state'] or 'n/a')} | {f(b['buy']) if b['buy'] is not None else (b['buy_state'] or 'n/a')} | {pc(r['interest_pct_oe']).replace('+', '')} | "
                 f"{f(r['net_debt_to_oe'], 1) + 'x' if r['net_debt_to_oe'] is not None else 'n/a'} | {mark} |")
    L.append(NL + f"**Flagged (value change above 15% or a change of state):** {', '.join(flagged) if flagged else 'none'}. Companies compared: {len(res)}.")
    (OUT / "summary_v12_g3.md").write_text(NL.join(L) + NL, encoding="utf-8")
    (OUT / "g3.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"SEC requests: {sec.requests_made}")


if __name__ == "__main__":
    main()

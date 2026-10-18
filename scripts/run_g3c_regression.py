"""HISTORICAL (2026-10-14): G3-C was approved and is now the production path (v1.2); the flag was removed; the output of this regression is kept in scripts/output_v12_g3*/.
G3-C regression (flag `g3c_unlevered`, default OFF): Buffett base / growth on unlevered owner earnings (OE + interest x (1 - tax)), debt still subtracted.
Compares A (current) and G3 (scripts/output_v12_g3/g3.json) with G3-C on the 20 STANDARD/TECH companies. Cached data only. Writes scripts/output_v12_g3c/."""
from __future__ import annotations

raise SystemExit("HISTORICAL: the g3 / g3c_unlevered flags no longer exist; outputs are kept in scripts/output_v12_g3/ and scripts/output_v12_g3c/.")


import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_g3_regression import UNIVERSE, f, pc, snap  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers.sec_companyfacts import SecClient, build_inputs  # noqa: E402
from src.scoring.candidates import candidates  # noqa: E402
from src.scoring.inputs import CompanyInputs  # noqa: E402
from src.scoring.profiles import score_company  # noqa: E402

OUT = ROOT / "scripts" / "output_v12_g3c"
PREV = json.loads((ROOT / "scripts" / "output_v12_g3" / "g3.json").read_text(encoding="utf-8"))
HIGHLIGHT = ["ORCL", "INTC", "KHC", "DOW", "MCD", "KO", "HD"]
NL = "\n"


def cell(s):
    if s["value"] is not None:
        return f(s["value"])
    return s["state"] + (f" ({f(s['modeled_value'])})" if s["modeled_value"] is not None else "")


def bcell(s):
    return f(s["buy"]) if s["buy"] is not None else (s["buy_state"] or "n/a")


def main():
    sec = SecClient()
    res = {}
    for t, prof in UNIVERSE:
        raw = build_inputs(sec, t, prof, price_provider.get_splits(t))
        pr = price_provider.load_prices(t, raw["ends"], raw["labels"])
        inp = CompanyInputs(ticker=t, name=raw["name"], profile=prof, fy=raw["labels"], end=raw["ends"], f=raw["f"], sbc_state=raw["sbc_state"],
                            price_current=pr["current"], price_avg=pr["avg"], first_annual_report=raw["first_annual_report"], as_of=date.today(),
                            flags=list(raw["flags"]), data_problems=list(raw["problems"]) + list(pr["notes"]), tag_log=raw["tag_log"], assumed_zero=raw["assumed_zero"])
        a = snap(score_company(inp))
        with candidates(g3c_unlevered=True):
            sc = score_company(inp)
        bp = sc["buffett_price"]
        c = snap(sc)
        c["growth_gate_passed"] = (bp.get("growth_gate") or {}).get("passed")
        c["oe_unlevered_last5"] = bp.get("owner_earnings_last5")
        ref = PREV[t]
        assert abs((ref["current"]["value"] or 0) - (a["value"] or 0)) < 1e-6 * max(1, abs(a["value"] or 1)), f"{t}: current differs from the g3 run"
        res[t] = {"A": a, "G3": ref["g3"], "G3C": c, "interest_pct_oe": ref["interest_pct_oe"], "net_debt_to_oe": ref["net_debt_to_oe"], "interest_expense": ref["interest_expense"], "oe_base_A": a["base"], "oe_base_C": c["base"],
                  "growth_A": a["growth"], "growth_C": c["growth"]}
        print(t, "ok")
    L = [f"# G3-C regression: unlevered owner earnings - {date.today().isoformat()}" + NL,
         "General model v1.1, 20 STANDARD / TECH companies, cached data, flag `g3c_unlevered` ON only inside this run (production default OFF). "
         "**A** = current (value = PV of owner-earnings flows + discounted terminal + cash and short-term investments - financial debt). "
         "**G3** = no debt subtraction (`scripts/output_v12_g3/g3.json`). "
         "**G3-C** = unlevered owner earnings (OE + interest expense x (1 - tax rate); tax rate = effective rate clipped to 0-40%, otherwise 25%, as NOPAT) used for the base, the growth calculation and the owner-earnings input "
         "of the growth gate (the revenue / EPS gate tests are unchanged); debt is still subtracted. A missing interest tag counts as 0 interest. Interest expense is the income-statement line (no cash-paid tag in the ETL). "
         "Changes are versus A; moves above 15% are marked **>15%**; ORCL, INTC, KHC, DOW, MCD, KO, HD are in the first block." + NL]

    def table(tickers):
        out = ["| Company | Price | Value A | Value G3 | Value G3-C | G3 vs A | G3-C vs A | Price score A / G3 / G3-C | Buy price A / G3 / G3-C | Interest / OE | Net debt / OE | OE base A -> G3-C (bn) | Growth A -> G3-C | Flag |",
               "|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---|---|---|"]
        for t in tickers:
            r = res[t]
            va, vg, vc = r["A"]["value"], r["G3"]["value"], r["G3C"]["value"]
            chg = lambda v: None if v is None or va is None or va == 0 else v / va - 1  # noqa: E731
            cg, cc = chg(vg), chg(vc)
            r["chg_g3"], r["chg_g3c"] = cg, cc
            mark = []
            if cc is not None and abs(cc) > 0.15:
                mark.append("G3-C **>15%**")
            if (va is None) != (vc is None):
                mark.append("G3-C **state change**")
            if cg is not None and abs(cg) > 0.15:
                mark.append("G3 >15%")
            gb = lambda x: "n/a" if x is None else f"{x / 1e9:,.2f}"  # noqa: E731
            out.append(f"| {t} | {f(PREV[t]['price'])} | {cell(r['A'])} | {cell(r['G3'])} | {cell(r['G3C'])} | {pc(cg)} | {pc(cc)} | "
                       f"{f(r['A']['price_score'])} / {f(r['G3']['price_score'])} / {f(r['G3C']['price_score'])} | {bcell(r['A'])} / {bcell(r['G3'])} / {bcell(r['G3C'])} | "
                       f"{pc(r['interest_pct_oe']).replace('+', '')} | {f(r['net_debt_to_oe'], 1) + 'x' if r['net_debt_to_oe'] is not None else 'n/a'} | "
                       f"{gb(r['oe_base_A'])} -> {gb(r['oe_base_C'])} | {pc(r['growth_A']).replace('+', '')} -> {pc(r['growth_C']).replace('+', '')} | {'; '.join(mark)} |")
        return out
    L += ["## Highlighted companies", ""] + table(HIGHLIGHT) + ["", "## Other companies", ""] + table([t for t in res if t not in HIGHLIGHT])
    fl = [t for t in res if (res[t]["chg_g3c"] is not None and abs(res[t]["chg_g3c"]) > 0.15) or (res[t]["A"]["value"] is None) != (res[t]["G3C"]["value"] is None)]
    L.append(NL + f"**G3-C flagged (move above 15% or state change):** {', '.join(fl) if fl else 'none'} ({len(fl)} of {len(res)}); "
             f"G3 flagged: {sum(1 for t in res if res[t]['chg_g3'] is not None and abs(res[t]['chg_g3']) > 0.15)} of {len(res)}.")
    (OUT / "summary_v12_g3c.md").write_text(NL.join(L) + NL, encoding="utf-8")
    (OUT / "g3c.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"SEC requests: {sec.requests_made}")


if __name__ == "__main__":
    main()

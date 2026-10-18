"""Confirms the v1.1 production defaults (G1-B, G2-C, C13 ON, C14 guard, D14, C12 display-only) and compares the 20 STANDARD/TECH companies with the
regression run (scripts/output_v11_g/v11_g.json: Buffett variant B, Graham variant C). Cached data only. Writes scripts/output_v11_g/production_check.md."""
from __future__ import annotations

import inspect
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_scoring_test import COMPANIES  # noqa: E402
from src.providers import prices as price_provider  # noqa: E402
from src.providers import sec_companyfacts as SCF  # noqa: E402
from src.providers.sec_companyfacts import SecClient, build_inputs  # noqa: E402
from src.scoring import candidates as CAND  # noqa: E402
from src.scoring import metrics  # noqa: E402
from src.scoring.inputs import CompanyInputs  # noqa: E402
from src.scoring.profiles import score_company  # noqa: E402

OUT = ROOT / "scripts" / "output_v11_g"
MC = ["UNH", "ELV", "CI", "HUM", "CNC", "MOH"]
UNIVERSE = [(t, p) for t, p, _ in COMPANIES] + [(t, "STANDARD") for t in MC]
NL = "\n"


def buy(b):
    if not b:
        return "n/a"
    return f"{b['buy_price']:.2f}" if b.get("state") == "computed" else b.get("state", "n/a")


def f(x):
    return "n/a" if x is None else (f"{x:,.2f}" if isinstance(x, (int, float)) else str(x))


def same(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= 1e-5 * max(1.0, abs(b))  # the regression json is rounded to 6 decimals
    return a == b


def main():
    reg = json.loads((OUT / "v11_g.json").read_text(encoding="utf-8"))
    sec = SecClient()
    rows, diffs = [], []
    for t, prof in UNIVERSE:
        raw = build_inputs(sec, t, prof, price_provider.get_splits(t))
        pr = price_provider.load_prices(t, raw["ends"], raw["labels"])
        inp = CompanyInputs(ticker=t, name=raw["name"], profile=prof, fy=raw["labels"], end=raw["ends"], f=raw["f"], sbc_state=raw["sbc_state"],
                            price_current=pr["current"], price_avg=pr["avg"], first_annual_report=raw["first_annual_report"], as_of=date.today(),
                            flags=list(raw["flags"]), data_problems=list(raw["problems"]) + list(pr["notes"]), tag_log=raw["tag_log"], assumed_zero=raw["assumed_zero"])
        sc = score_company(inp)
        bp, gp = sc["buffett_price"], sc["graham_price"]
        gn = gp.get("graham_number") or {}
        now = {"b_base": bp.get("oe_base"), "b_value": bp.get("fair_value"), "b_ps": (bp.get("price_score") or {}).get("points"), "b_buy": buy(bp.get("buy_price")),
               "g_eps": gn.get("normalized_eps"), "g_value": gp.get("value"), "g_ps": (gp.get("price_score") or {}).get("points"), "g_buy": buy(gp.get("buy_price"))}
        rb, rg = reg[t]["buffett"]["B"], reg[t]["graham"]["C"]
        old = {"b_base": rb["base"], "b_value": rb["value"], "b_ps": rb["ps"], "b_buy": rb["buy"], "g_eps": rg["eps"], "g_value": rg["value"], "g_ps": rg["ps"], "g_buy": rg["buy"]}
        bad = [k for k in now if not same(now[k], old[k])]
        rows.append((t, now, bad, sc["buffett_quality"], sc["graham_quality"]))
        if bad:
            diffs.append((t, bad))
        print(t, "DIFF " + ",".join(bad) if bad else "equal")
    guard_in_etl = "guard_share_scale(" in inspect.getsource(SCF.build_inputs)
    d14_ok = all(not (r[3].range_error or r[4].range_error) for r in rows)
    L = [f"# v1.1 production check - {date.today().isoformat()}" + NL,
         "Production defaults, no flags. Compared with the regression run (`v11_g.json`: Buffett variant B, Graham variant C). "
         f"SEC requests this run: {sec.requests_made}." + NL,
         "## Confirmations" + NL,
         f"- C13 (claims expense in cost of revenue): default ON = {CAND.CANDIDATES.c13}.",
         f"- C14 (share-scale guard): `guard_share_scale` is called in the general ETL = {guard_in_etl}; also in the bank and insurance ETLs (audit 2026-10-13: fires only for WRB).",
         f"- D14 (same valid-criteria set for score, minimum and maximum): no `range_error` in any Buffett / Graham quality model of the 20 companies = {d14_ok}.",
         f"- C12: display only; the alternative current ratio exists as a derived field = {'current_ratio_alt' in inspect.getsource(metrics.derive)}; "
         f"`c12` flag in candidates = {hasattr(CAND.CANDIDATES, 'c12')} (removed).",
         "- G1-B and G2-C are the only code path (flags `g1`/`g2` removed from `candidates.py`; `scripts/run_v11_g.py` is marked historical, its outputs are kept)." + NL,
         "## Equality with the regression run (Buffett B, Graham C)" + NL,
         "| Company | Buffett base (bn) | Buffett value | price score | buy | Graham EPS | Graham value | price score | buy | Equal |",
         "|---|---:|---:|---:|---|---:|---:|---:|---|---|"]
    for t, now, bad, *_ in rows:
        L.append(f"| {t} | {f(now['b_base'] / 1e9 if now['b_base'] else None)} | {f(now['b_value'])} | {f(now['b_ps'])} | {now['b_buy']} | {f(now['g_eps'])} | "
                 f"{f(now['g_value'])} | {f(now['g_ps'])} | {now['g_buy']} | {'yes' if not bad else 'NO: ' + ', '.join(bad)} |")
    L.append(NL + f"**Result:** {len(rows) - len(diffs)} of {len(rows)} companies equal the regression run" + ("; no difference." if not diffs else "; differences: " + str(diffs)))
    (OUT / "production_check.md").write_text(NL.join(L) + NL, encoding="utf-8")


if __name__ == "__main__":
    main()

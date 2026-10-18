"""v1.2 G3-C confirmation: production values of the 20 STANDARD / TECH companies vs the G3-C column of the regression (scripts/output_v12_g3c/g3c.json, 1e-5 relative),
plus the implied return / reverse DCF before (A, ir_before.json) and after. Cached data only. Writes scripts/output_v12_g3c/confirm_v12.md."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from run_scoring_test import COMPANIES  # noqa: E402
from src.providers import prices as pp  # noqa: E402
from src.providers.sec_companyfacts import SecClient, build_inputs  # noqa: E402
from src.scoring.inputs import CompanyInputs  # noqa: E402
from src.scoring.profiles import score_company  # noqa: E402

OUT = ROOT / "scripts" / "output_v12_g3c"
MC = ["UNH", "ELV", "CI", "HUM", "CNC", "MOH"]
UNIVERSE = [(t, p) for t, p, _ in COMPANIES] + [(t, "STANDARD") for t in MC]
reg = json.loads((OUT / "g3c.json").read_text(encoding="utf-8"))
before = json.loads((OUT / "ir_before.json").read_text(encoding="utf-8"))
NL = "\n"


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= 1e-5 * max(1.0, abs(b))


def ir(x):
    return x["implied_return"] if x and x.get("state") == "solved" else (x or {}).get("state", "n/a")


def pc(x):
    return f"{x:.2%}" if isinstance(x, float) else str(x)


sec = SecClient()
rows, diffs = [], []
for t, prof in UNIVERSE:
    raw = build_inputs(sec, t, prof, pp.get_splits(t))
    pr = pp.load_prices(t, raw["ends"], raw["labels"])
    inp = CompanyInputs(ticker=t, name=raw["name"], profile=prof, fy=raw["labels"], end=raw["ends"], f=raw["f"], sbc_state=raw["sbc_state"], price_current=pr["current"], price_avg=pr["avg"],
                        first_annual_report=raw["first_annual_report"], as_of=date.today(), flags=list(raw["flags"]), data_problems=list(raw["problems"]) + list(pr["notes"]),
                        tag_log=raw["tag_log"], assumed_zero=raw["assumed_zero"])
    bp = score_company(inp)["buffett_price"]
    rc = reg[t]["G3C"]
    bu = bp.get("buy_price") or {}
    now = {"value": bp.get("fair_value") if bp.get("fair_value") is not None else bp.get("modeled_value_nonpositive"), "price_score": (bp.get("price_score") or {}).get("points"),
           "buy": bu.get("buy_price") if bu.get("state") == "computed" else None}
    old = {"value": rc["modeled_value"], "price_score": rc["price_score"], "buy": rc["buy"]}
    bad = [k for k in now if not close(now[k], old[k])]
    if bad:
        diffs.append((t, bad, now, old))
    ia, ic = before[t]["A"], before[t]["C"]
    rows.append((t, bp, ia, ic, bad))
    print(t, "DIFF " + ",".join(bad) if bad else "equal")
L = [f"# v1.2 G3-C production confirmation - {date.today().isoformat()}" + NL,
     f"Production path (no flags) vs the G3-C column of the regression (`g3c.json`), 1e-5 relative tolerance; SEC requests this run: {sec.requests_made}. "
     f"**Result: {len(rows) - len(diffs)} of {len(rows)} companies equal the regression (value, price score, buy price)**" + ("; no difference." if not diffs else f"; differences: {diffs}") + NL,
     "## Implied return and implied growth (reverse DCF), before (v1.1, levered base) and after (v1.2, unlevered base)" + NL,
     "Both solve the same unlevered DCF for the price: implied return = the discount rate at which the value equals the price; implied growth = the stage-1 growth at which the value equals the price (both with debt subtracted and excess cash added)." + NL,
     "| Company | Implied return before | after | Change (pp) | Implied growth before | after |", "|---|---:|---:|---:|---:|---:|"]
for t, bp, ia, ic, bad in rows:
    b, a = ir((ia["implied_return"] or {})), ir(bp.get("implied_return"))
    gb = (ia["reverse_dcf"] or {}).get("implied_growth") if (ia["reverse_dcf"] or {}).get("state") == "solved" else (ia["reverse_dcf"] or {}).get("state", "n/a")
    rd = bp.get("reverse_dcf") or {}
    ga = rd.get("implied_growth") if rd.get("state") == "solved" else rd.get("state", "n/a")
    ch = f"{(a - b) * 100:+.2f}" if isinstance(a, float) and isinstance(b, float) else "n/a"
    L.append(f"| {t} | {pc(b)} | {pc(a)} | {ch} | {pc(gb)} | {pc(ga)} |")
(OUT / "confirm_v12.md").write_text(NL.join(L) + NL, encoding="utf-8")

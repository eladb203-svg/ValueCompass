"""Scoring test round: 12 US non-financial companies, real SEC + price data, no DB, no AI.

Usage:  .venv/Scripts/python scripts/run_scoring_test.py [TICKER ...]
Outputs (untracked): scripts/output/<TICKER>.json and scripts/output/summary.md
"""
from __future__ import annotations

import dataclasses
import json
import math
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.providers import prices as price_provider  # noqa: E402
from src.providers.sec_companyfacts import SecClient, build_inputs  # noqa: E402
from src.scoring.buffett import buffett_price, buffett_quality  # noqa: E402
from src.scoring.graham import graham_price, graham_quality  # noqa: E402
from src.scoring.inputs import CompanyInputs  # noqa: E402
from src.scoring.metrics import median  # noqa: E402
from src.scoring.profiles import score_company  # noqa: E402
from router_runner import route_company  # noqa: E402
from ai_runner import attach_ai  # noqa: E402

OUT = ROOT / "scripts" / "output"
RULE_ISSUES = ROOT / "scripts" / "rule_issues.md"

COMPANIES = [  # (ticker, note): the profile comes from the router (src/scoring/router.py), not from this list
    ("MSFT", "high quality"),
    ("ORCL", "negative-ish equity + buybacks"),
    ("AVGO", "heavy acquisitions"),
    ("CRM", "high SBC"),
    ("UBER", "loss-to-profit turnaround"),
    ("KO", "stable dividend compounder"),
    ("MCD", "negative equity + buybacks"),
    ("HD", "buybacks / leverage"),
    ("NUE", "cyclical"),
    ("DOW", "cyclical / spin-off"),
    ("INTC", "weak / deteriorating"),
    ("KHC", "mediocre / impairments"),
    ("ADBE", "high-quality software"),
    ("INTU", "high-quality software"),
]
MODEL_VERSION = "2026-10-11_14-35"


# ------------------------------------------------------------------ serialization
def jsonable(o):
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return jsonable(dataclasses.asdict(o))
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, float):
        if math.isnan(o):
            return "nan"
        if math.isinf(o):
            return "inf" if o > 0 else "-inf"
        return round(o, 6)
    return o


def model_json(m):
    return {
        "model": m.name, "score": m.score, "status": m.status, "coverage": m.coverage,
        "observed_points": m.observed_points, "range_min": m.min_score, "range_max": m.max_score,
        "range_error": m.range_error,
        "buy_price_allowed": m.buy_price_allowed, "invalid_criteria": m.invalid_criteria,
        "pending_criteria": m.pending_criteria,
        "unknown_items": m.unknown_items,
        "criteria": [{
            "id": c.id, "name": c.name, "weight": c.weight, "valid": c.valid, "normalized": c.normalized,
            "observed_points": c.observed, "computed_share": c.computed_share, "range_min": c.min_score,
            "range_max": c.max_score, "covered_points": c.covered_pts,
            "items": [dataclasses.asdict(i) for i in c.items],
        } for c in m.criteria],
    }


# ------------------------------------------------------------------ run one company
def run_company(sec, ticker, why):
    rr = route_company(sec, ticker)
    profile = rr.profile
    splits = price_provider.get_splits(ticker)
    raw = build_inputs(sec, ticker, profile, splits)
    pr = price_provider.load_prices(ticker, raw["ends"], raw["labels"])
    inp = CompanyInputs(
        ticker=ticker, name=raw["name"], profile=profile, fy=raw["labels"], end=raw["ends"], f=raw["f"],
        sbc_state=raw["sbc_state"], price_current=pr["current"], price_avg=pr["avg"],
        first_annual_report=raw["first_annual_report"], as_of=date.today(), flags=list(raw["flags"]),
        data_problems=list(raw["problems"]), tag_log=raw["tag_log"], assumed_zero=raw["assumed_zero"])
    inp.data_problems += pr["notes"]
    attach_ai(inp, ticker)
    sc = score_company(inp)
    if sc["state"] != "scored":
        (OUT / f"{ticker}.json").write_text(json.dumps(jsonable({
            "ticker": ticker, "profile": profile, "state": sc["state"], "reason": sc["reason"]}), indent=1),
            encoding="utf-8")
        return None
    d, bq, bp, gq, gp = sc["derived"], sc["buffett_quality"], sc["buffett_price"], sc["graham_quality"], sc["graham_price"]
    _flag_assumed_zero(inp, bq, gq)
    _collect_problems(inp, d, bq, gq, bp, gp)
    result = {
        "ticker": ticker, "name": raw["name"], "cik": raw["cik"], "profile": profile, "profile_reason": why, "profile_router": rr.to_jsonable(),
        "scoring_model_version": MODEL_VERSION, "as_of": date.today(),
        "price": {"current": pr["current"], "current_date": pr["current_date"], "source": pr["source"],
                  "annual_average": dict(zip(inp.fy, pr["avg"])), "splits": pr["splits"]},
        "first_annual_report": raw["first_annual_report"],
        "fiscal_years": dict(zip(inp.fy, inp.end)),
        "financials": {k: dict(zip(inp.fy, v)) for k, v in inp.f.items()},
        "sbc_state": dict(zip(inp.fy, inp.sbc_state)),
        "derived": {k: dict(zip(inp.fy, v)) for k, v in d.items() if k not in ("roic", "nd_ebitda", "int_cov")},
        "derived_roic": dict(zip(inp.fy, d["roic"])),
        "derived_nd_ebitda": dict(zip(inp.fy, d["nd_ebitda"])),
        "derived_interest_coverage": dict(zip(inp.fy, d["int_cov"])),
        "buffett_quality": model_json(bq), "buffett_price": bp,
        "graham_quality": model_json(gq), "graham_price": gp,
        "flags": inp.flags, "data_problems": inp.data_problems,
        "data_source": {"sec_companyfacts": f"CIK{raw['cik']}", "used_tags": raw["used_tags"],
                        "tag_log_per_field_per_year": raw["tag_log"]},
    }
    (OUT / f"{ticker}.json").write_text(json.dumps(jsonable(result), indent=1, ensure_ascii=False), encoding="utf-8")
    return result, inp, d, bq, bp, gq, gp


ASSUMED_ZERO_USERS = {  # (criterion, item) -> fields whose assumed zeros feed it
    "buffett": {("3.6", "1"): ["customer_funds_excluded"], ("3.6", "3"): ["customer_funds_excluded"], ("3.7", "1"): ["buybacks"], ("3.7", "3"): ["acquisitions", "acquisitions_proxy_goodwill"],
                ("3.7", "2"): ["shares_out_cover_page"], ("3.7", "4"): ["dividends", "buybacks"]},
    "graham": {("3.2", "1"): ["customer_funds_excluded"], ("3.2", "2"): ["customer_funds_excluded"],
               ("3.2", "3"): ["customer_funds_excluded"], ("3.3", "2"): ["customer_funds_excluded"], ("3.5", "1"): ["dividends"], ("3.5", "2"): ["dividends", "dps_derived"], ("3.5", "3"): ["dividends"],
               ("3.8", "2"): ["shares_out_cover_page"],
               ("3.5", "4"): ["dividends"], ("3.7", "1"): ["goodwill", "intangibles"],
               ("3.7", "3"): ["goodwill", "intangibles"]},
}


def _flag_assumed_zero(inp, bq, gq):
    for key, model in (("buffett", bq), ("graham", gq)):
        for c in model.criteria:
            for it in c.items:
                fields = ASSUMED_ZERO_USERS[key].get((c.id, it.id), [])
                window = set(inp.fy[-10:] if (key, c.id) == ("graham", "3.5") else inp.fy[-5:])
                hit = [f"{fl}:{lab}" for fl in fields for lab in inp.assumed_zero.get(fl, []) if lab in window]
                if hit:
                    kinds = {fl.split(":")[0] for fl in hit}
                    tag = "assumed_zero"
                    if kinds <= {"acquisitions_proxy_goodwill"}:
                        tag = "acquisitions_proxy_goodwill"
                    elif kinds <= {"dps_derived"}:
                        tag = "dps_derived"
                    elif kinds <= {"shares_out_cover_page"}:
                        tag = "shares_out_cover_page"
                    elif kinds <= {"customer_funds_excluded"}:
                        tag = "customer_funds_excluded"
                    it.flags.append(tag + " (" + ", ".join(hit) + ")")


CLARIFICATIONS = """## Clarifications applied

Rulings on the spec for this round (not new rules):

1. **ai_pending** is a temporary state: it is excluded from the M2 validity check and from coverage (treated like
   not-applicable there) and appears only in the min-max range. A criterion made only of AI items is "pending":
   neutral for score and coverage, shown in the range. (In production, AI "insufficient evidence" stays missing and M2 applies.)
2. **Invested capital** everywhere = equity + financial debt - cash - short-term investments (same as net debt in 3.6).
   The cash-only variant was dropped.
3. **"5 years ago"** everywhere = first year of the 5-year window (t-4): dilution (Buffett 3.7 #2, Graham 3.8 #2,
   Graham Tech gate) and change in net debt/EBITDA (Buffett 3.8 #4).
4. **DCF with a negative starting base:** stage-1 growth is clipped to 0% and flagged (same treatment for the Graham Tech
   growth multiple, taken at growth <= 0%).
5. **Gross profit:** if the GrossProfit tag is missing, it is derived as Revenues - CostOfRevenue (logged per year); not
   applicable only if it cannot be derived.
6. **Absent line items** (buybacks, acquisitions, dividends, impairments, goodwill, intangibles, short-term investments)
   are 0 only for years where the parent statement was retrieved (cash-flow: CFO present; balance sheet: total assets
   present), flagged `assumed_zero`; if the statement itself is missing for that year the value stays missing.
"""


def _collect_problems(inp, d, bq, gq, bp, gp):
    p = inp.data_problems
    for i, lab in enumerate(inp.fy):
        for f in d["roic"][i].get("flags", []):
            if f != "no_prior_year_balance_sheet":
                p.append(f"ROIC {lab}: {f}")
        if d["roic"][i].get("roic") is not None and d["roic"][i].get("tax_rate") is not None:
            pass
    eq = inp.series("equity")
    neg = [l for l, e in zip(inp.fy, eq) if e is not None and e <= 0]
    if neg:
        p.append(f"negative/zero equity in {', '.join(neg)}")
    for l, m in zip(inp.fy, d["maint_capex_flag"]):
        if m:
            p.append(f"{l}: maintenance capex flag(s): {m}")
            break
    for model in (bq, gq):
        for c in model.criteria:
            for it in c.items:
                for fl in it.flags:
                    if any(k in fl for k in ("assumed", "fallback", "derived")):
                        p.append(f"{model.name} {c.id}.{it.id}: {fl}")
    p[:] = list(dict.fromkeys(p))


# ------------------------------------------------------------------ summary
def fmt_money(x):
    return "n/a" if x is None else f"{x / 1e9:,.1f}"


def fnum(x, nd=1):
    return "-" if x is None else f"{x:,.{nd}f}"


def pct(x, nd=0):
    return "-" if x is None else f"{x * 100:.{nd}f}%"


def cell(it):
    if it["state"] == "score":
        return f"{it['points']:.1f}"
    if it["state"] == "true_zero":
        return "0•"
    return {"ai_pending": "AI", "not_applicable": "n/a", "missing": "MISS"}[it["state"]]


def _rng(mj):
    if mj.get("range_min") is None or mj.get("range_max") is None:
        return "range n/a"
    return f"{mj['range_min']:.0f}-{mj['range_max']:.0f}"


def model_cell(mj):
    if mj["score"] is None:
        return f"missing (cov {pct(mj['coverage'])}, range {_rng(mj)})"
    return f"{mj['score']:.1f} [{_rng(mj)}] cov {pct(mj['coverage'])} {mj['status']}"


def price_cells(pr, price_score_key="price_score"):
    ps = pr.get(price_score_key, {})
    fv = pr.get("fair_value") if "fair_value" in pr else pr.get("value")
    score = "n/a" if ps.get("points") is None else f"{ps['points']:.1f} (disc {pct(ps['discount'])})"
    bp = pr.get("buy_price") or {}
    if bp.get("state") == "computed":
        buy = f"{bp['buy_price']:.2f}"
    elif bp.get("state") == "not_suitable":
        buy = "not suitable (<55)"
    elif bp:
        info = bp.get("informational_buy_price_ignoring_coverage")
        buy = "none (" + bp.get("reason", "") + ")" + (f"; info only: {info:.2f}" if info else "")
    else:
        buy = "-"
    state = pr.get("state")
    fv_s = f"{fv:.2f}" if fv is not None else f"cannot be valued: {pr.get('reason', '')}"
    return fv_s, score, buy, state


def top_flags(results_item, k=4):
    out = []
    for key in ("buffett_quality", "graham_quality"):
        for c in results_item[key]["criteria"]:
            for it in c["items"]:
                for fl in it["flags"]:
                    if fl not in out and "partial_window" not in fl:
                        out.append(fl)
    out += [f for f in results_item["flags"] if f not in out]
    for key in ("buffett_price", "graham_price"):
        for fl in results_item[key].get("flags", []):
            if fl not in out:
                out.append(fl)
    return out[:k]


CHANGES = """## Changes after round 1

Approved after review of round 1 (rulings and data fixes, recorded as applied):

**A. Methodology**

1. **Owner-earnings base** = median of the last 5 fiscal years (was the 3-year average). All 5 years are required (M6).
2. **Stage-1 growth** = median OE of the last 5 years vs. median OE of the previous 5 years, annualized over 5 years,
   clipped to 0%-12%. With fewer than 10 years of owner earnings: R14 smoothed growth, flagged `growth_fallback_r14`.
   A previous-5 median <= 0 gives a growth that cannot be measured: clipped to 0% and flagged.
3. **Reverse DCF** (display only, no score): the stage-1 growth at which the Buffett fair value equals the current price
   (bisection on [-20%, 50%], same 10% discount rate, fade and terminal growth). `out of range` when no solution exists.

**B. Data fixes**

4. **Acquisitions:** when the acquisitions cash tag is absent for a year, `GoodwillAcquiredDuringPeriod` is used as a
   lower-bound proxy (`acquisitions_proxy_goodwill`). `assumed_zero` remains only when neither exists and the cash-flow
   statement was retrieved.
5. **Dilution tests** (Buffett 3.7 #2, Graham 3.8 #2, Graham Tech gate) use period-end shares outstanding
   (`CommonStockSharesOutstanding`; cover-page `dei` count when missing, flagged `shares_out_cover_page`; weighted diluted
   only as a flagged last resort). Per-share values (EPS, fair value per share, BVPS) keep weighted diluted shares.
6. **Dividends per share:** when the DPS tag is missing, dividends paid / weighted-average basic shares (`dps_derived`).
7. **D&A:** the cash-flow total tags (`DepreciationDepletionAndAmortization`, `DepreciationAmortizationAndAccretionNet`,
   `DepreciationAndAmortization`, `DepreciationAmortizationAndOther`) are preferred over the derived Depreciation +
   Amortization sum. A total tag below 50% of the derived sum is treated as a component and rejected. Tags used per
   company are listed below.
8. **Confirmed:** "5-year" = 5 fiscal years, 4 intervals; "5 years ago" = t-4.
"""


CHANGES3 = """## Changes after round 2

Approved after review of round 2 (round 3 run). Companies added: **ADBE** and **INTU** (TECH_ASSET_LIGHT).

1. **Growth eligibility gate (Buffett price).** Stage-1 growth is allowed only if (a) revenue rose in at least 3 of the
   last 4 transitions, AND (b) diluted EPS fell by more than 10% in at most 1 of the last 4 transitions, AND (c) diluted
   EPS was positive in all of the last 5 years. Otherwise stage-1 growth = 0% (fade and terminal unchanged), flagged
   `growth_gate_failed` with the failing condition(s). Missing data in the window counts as a failure of that condition.
2. **Finance-lease amortization in D&A.** `FinanceLeaseRightOfUseAssetAmortization` is added to the D&A that is assembled
   from components (Depreciation + AmortizationOfIntangibleAssets) when the tag exists, flagged
   `includes_finance_lease_amortization`; this also feeds maintenance capex (Buffett 3.5 #4 and owner earnings). It is
   NOT added on top of a cash-flow total D&A tag, which already contains it. Lease liabilities stay excluded from debt.
3. **Implied return** (labelled "Implied long-term annual return at current price (model value assumptions)" from round 5; display only, no score): the discount rate at which the Buffett fair value equals the current
   price, using the company's actual stage-1 growth after the gate; bisection on [0%, 30%] (the search starts just above
   the 2.5% terminal growth, where the Gordon terminal value is defined). `out of range` otherwise. The reverse-DCF
   implied growth is kept.
"""


CHANGES5 = """## Changes after round 4

Final refinements before v1.0 (round 5 run, from cache; no new SEC fetches).

1. **Deferred revenue at cost basis (TECH_ASSET_LIGHT only).** Current liabilities include current deferred revenue /
   contract liabilities x (1 - gross margin) instead of excluding it entirely (30% when the gross margin is not
   available, flagged `deferred_revenue_default_30pct`). The gross margin used is that fiscal year's own (for the latest
   year this is the latest gross margin). The same adjusted working capital is used everywhere for the profile:
   Graham 3.2 (current ratio, quick ratio, consistency), Graham 3.3 #2 and Buffett 3.6 #3, flagged
   `deferred_revenue_cost_basis`. STANDARD companies are unchanged.
2. **Graham Tech multiple cap is continuous (R4):** quality <= 70 -> 15x, 85 -> 18x, >= 95 -> 22x (was 25x before round 6), linear in between
   (replaces the 70 / 85 steps). The final multiple is still the lower of the growth multiple and the cap.
3. **Customer funds:** customer-funds assets and the matching customer-funds liabilities are removed from both current
   assets and current liabilities, flagged `customer_funds_excluded`. Only for companies that report
   `FundsHeldForClients` (INTU). Where that tag is absent in a year (INTU after FY2021: extension tags), restricted cash
   (`RestrictedCashAndCashEquivalents`) is used as a lower-bound proxy and the matching liability is assumed equal.
4. **Label:** implied return is now labelled "Implied long-term annual return at current price (model value
   assumptions)".
"""


CHANGES4 = """## Changes after round 3

Approved before freezing v1.0 (round 4 run, from cache; no new SEC fetches).

**A. Methodology**

1. **Roll-forward owner-earnings base.** base = median OE of the last 5 years x (1 + stage-1 growth after the gate)^2
   (the 5-year median sits at t-2). Gate-failed companies (growth 0%) are unchanged. Reverse DCF and implied return
   use the rolled base.
2. **TECH_ASSET_LIGHT only:** current deferred revenue / contract liabilities (`ContractWithCustomerLiabilityCurrent`,
   `DeferredRevenueCurrent`) are excluded from current liabilities in Graham 3.2 (current ratio, quick ratio,
   consistency; working capital in the consistency test) and Buffett 3.6 #3, flagged `deferred_revenue_excluded`.
   STANDARD companies are unchanged. (Superseded in round 5: deferred revenue is now included at cost basis, see
   "Changes after round 4"; Graham 3.3 #2 now uses the same adjusted working capital.)
3. **Graham 3.7 #3:** tangible BVPS <= 0 at the start of the window and > 0 at the end = full points; <= 0 at the end = 0.
   This was already the behavior (flag `tbvps_first_year_nonpositive_improved`); it is now covered by a unit test.

**B. Data rules**

4. **Cash:** restricted / customer funds are excluded from cash when the cash figure comes from the restricted-cash-
   inclusive tag (`CashCashEquivalentsRestrictedCash...` minus `RestrictedCashAndCashEquivalents`, else
   `FundsHeldForClients`), flagged `customer_funds_excluded`. Where the primary cash tag is used, it already excludes
   customer funds and nothing is subtracted.
5. **Cost of revenue:** when neither `CostOfRevenue` nor `CostOfGoodsAndServicesSold` exists, it is derived as the sum of
   its components (`CostOfGoodsSold` + `CostOfServices` + the two amortization lines), flagged `cost_of_revenue_derived`.
   Both the goods and the services line must exist; a lone `CostOfGoodsSold` is used as the total (goods-only company);
   otherwise gross profit stays not applicable.

**C. Scope**

6. **Profile guard:** methodology_profile BANK / INSURANCE / INCOME_REAL_ESTATE is not scored; the output state is
   `sector_not_supported_v1` (no such company in the test set; unit-tested).
"""


def _fmtv(v):
    if isinstance(v, float):
        if v != v:
            return "nan"
        if v in (float("inf"), float("-inf")):
            return "inf" if v > 0 else "-inf"
        return f"{v:,.4g}" if abs(v) < 1000 else f"{v:,.0f}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_fmtv(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_fmtv(x)}" for k, x in v.items()) + "}"
    return str(v)


def _buy(pr):
    b = pr.get("buy_price") or {}
    if b.get("state") == "computed":
        return f"{b['buy_price']:.2f}"
    return b.get("state", "-") if b else "-"


def _fmt_ps(x):
    p_ = (x.get("price_score") or {}).get("points")
    return "n/a" if p_ is None else f"{p_:.1f}"


def round3_tables(rows):
    L = ["\n### Growth gate, implied return and implied growth (round 3)\n",
         "| Ticker | Gate | Failing condition(s) | Growth before gate | Stage-1 growth used | OE base (bn) | "
         "Implied long-term annual return at current price (model value assumptions) | Implied growth (reverse DCF) |",
         "|---|---|---|---:|---:|---:|---|---|"]
    for res, *_ in rows:
        bp = res["buffett_price"]
        gate = bp.get("growth_gate")
        if gate is None:
            L.append(f"| {res['ticker']} | n/a | {bp.get('reason', '')} | - | - | - | - | - |")
            continue
        ir = bp.get("implied_return") or {}
        irs = (f"{ir['implied_return'] * 100:.1f}%" if ir.get("state") == "solved"
               else (ir.get("note", "-") if ir else "-"))
        gb, g1 = bp.get("growth_before_gate"), bp.get("stage1_growth")
        L.append(f"| {res['ticker']} | {'PASS' if gate['passed'] else 'FAIL'} | "
                 f"{'; '.join(gate['failing']) or '-'} | {'-' if gb is None else f'{gb * 100:.1f}%'} | "
                 f"{'-' if g1 is None else f'{g1 * 100:.1f}%'} | {bp['oe_base'] / 1e9:.1f} | {irs} | {rd_cell(bp)} |")
    return L


def results_tables(rows):
    def gps(x):
        p_ = (x.get("price_score") or {}).get("points")
        return "n/a" if p_ is None else f"{p_:.1f}"

    def gval(x):
        v = x.get("value")
        return "n/a" if v is None else f"{v:.2f}"
    L = ["\n### Round 5 results (all companies)\n",
         "| Ticker | Buffett quality | Gate | OE base before -> after roll-forward (bn) | Stage-1 growth | Fair value | "
         "Price score | Buy price | Implied growth | Implied long-term annual return at current price (model value assumptions) | "
         "Graham quality | Graham value | Graham price score |",
         "|---|---|---|---|---:|---|---|---|---|---|---|---|---|"]
    for res, *_ in rows:
        bp, gp = res["buffett_price"], res["graham_price"]
        gate = bp.get("growth_gate")
        ir = bp.get("implied_return") or {}
        irs = f"{ir['implied_return'] * 100:.1f}%" if ir.get("state") == "solved" else (ir.get("note", "-") if ir else "-")
        g1 = bp.get("stage1_growth")
        if bp.get("oe_base") is not None:
            base_s = f"{bp['oe_base_median'] / 1e9:.1f} -> {bp['oe_base'] / 1e9:.1f}"
        else:
            base_s = "-"
        L.append(f"| {res['ticker']} | {_q(res['buffett_quality'])} | "
                 f"{'n/a' if gate is None else ('PASS' if gate['passed'] else 'FAIL')} | {base_s} | "
                 f"{'-' if g1 is None else f'{g1 * 100:.1f}%'} | {_val(bp, 'fair_value')} | {gps(bp)} | {_buy(bp)} | "
                 f"{rd_cell(bp)} | {irs} | {_q(res['graham_quality'])} | {gval(gp)} | {gps(gp)} |")
    L.append("\n### Round 4 -> round 5\n")
    L.append("| Ticker | Buffett quality | Fair value | Price score | Buy price | Graham quality | Graham value | "
             "Graham price score | Graham 3.2 | Buffett 3.6 #3 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for res, *_ in rows:
        f = ROOT / "scripts" / "output_round4" / f"{res['ticker']}.json"
        if not f.exists():
            continue
        old = json.loads(f.read_text(encoding="utf-8"))
        bo, bn, go, gn = old["buffett_price"], res["buffett_price"], old["graham_price"], res["graham_price"]

        def crit(r, key, cid):
            c = next(c for c in r[key]["criteria"] if c["id"] == cid)
            return c

        def item(r, key, cid, iid):
            return next(i for i in crit(r, key, cid)["items"] if i["id"] == iid)
        g32o, g32n = crit(old, "graham_quality", "3.2")["normalized"], crit(res, "graham_quality", "3.2")["normalized"]
        b363o, b363n = item(old, "buffett_quality", "3.6", "3")["points"], item(res, "buffett_quality", "3.6", "3")["points"]
        L.append(f"| {res['ticker']} | {_q(old['buffett_quality'])} -> {_q(res['buffett_quality'])} | "
                 f"{_val(bo, 'fair_value')} -> {_val(bn, 'fair_value')} | {gps(bo)} -> {gps(bn)} | "
                 f"{_buy(bo)} -> {_buy(bn)} | {_q(old['graham_quality'])} -> {_q(res['graham_quality'])} | "
                 f"{gval(go)} -> {gval(gn)} | {gps(go)} -> {gps(gn)} | {g32o:.1f} -> {g32n:.1f} | "
                 f"{b363o:.2f} -> {b363n:.2f} |")
    intu = next((r[0] for r in rows if r[0]["ticker"] == "INTU"), None)
    if intu:
        cm = {i["id"]: i for c in intu["buffett_quality"]["criteria"] if c["id"] == "3.2" for i in c["items"]}
        L.append("\n**INTU gross-margin sub-items after the change:** 1a = " + cm["1a"]["state"] + ", 1b = "
                 + cm["1b"]["state"] + " - " + (cm["1a"]["note"] or "") + " (after FY2017 INTU reports its product and "
                 "service cost lines with extension tags that companyfacts does not expose, so no complete cost of "
                 "revenue can be derived).")
    cf = [r[0]["ticker"] for r in rows if any(
        "customer_funds_excluded" in v.get("tag", "") for v in
        r[0]["data_source"]["tag_log_per_field_per_year"]["cash"].values() if v.get("tag"))]
    L.append("\n**Cash adjusted for customer/restricted funds (`customer_funds_excluded`):** "
             + (", ".join(cf) if cf else "none") + ".")
    cfx = [r[0]["ticker"] for r in rows if any(
        v.get("customer_funds_excluded") for v in r[0]["data_source"]["tag_log_per_field_per_year"]["cur_assets"].values())]
    L.append("\n**Customer funds removed from current assets and current liabilities (`customer_funds_excluded`):** "
             + (", ".join(cfx) if cfx else "none") + ".")
    return L


def breakdown(res):
    L = [f"\n#### {res['ticker']} - {res['name']} ({res['profile']})\n"]
    for key, label in (("buffett_quality", "Buffett quality"), ("graham_quality", "Graham quality")):
        m = res[key]
        L.append(f"\n**{label}**: score {_fmtv(m['score'])} [range {m['range_min']:.1f}-{m['range_max']:.1f}], "
                 f"coverage {m['coverage'] * 100:.0f}% ({m['status']}); pending criteria: "
                 f"{', '.join(m['pending_criteria']) or 'none'}; invalid: "
                 f"{', '.join(c['id'] for c in m['invalid_criteria']) or 'none'}\n")
        for c in m["criteria"]:
            L.append(f"\n*{c['id']} {c['name']}* - normalized {_fmtv(c['normalized'])} / {c['weight']:g}, "
                     f"range {c['range_min']:.1f}-{c['range_max']:.1f}, valid {c['valid']}\n")
            L.append("| # | Sub-item | State | Points | Metric | Flags / note |")
            L.append("|---|---|---|---:|---|---|")
            for it in c["items"]:
                pts = "-" if it["points"] is None else f"{it['points']:.2f}"
                mv = _fmtv(it["metric"]) if it["metric"] is not None else ""
                L.append(f"| {it['id']} | {it['name']} | {it['state']} | {pts} / {it['max_pts']:g} | "
                         f"{it['metric_label']} {mv} | {'; '.join(it['flags'])} {it['note']} |")
    bp = res["buffett_price"]
    L.append("\n**Buffett price**\n")
    for k in ("state", "reason", "oe_base", "base_method", "growth_method", "growth_detail", "growth_before_gate",
              "growth_gate", "stage1_growth", "excess_cash_less_debt", "fair_value", "price_current", "price_score",
              "buy_price", "reverse_dcf", "implied_return", "flags", "owner_earnings_last5", "sbc_states_last5"):
        if k in bp:
            L.append(f"- {k}: {_fmtv(bp[k])}")
    gp = res["graham_price"]
    L.append("\n**Graham price**\n")
    for k in ("method", "state", "reason", "value", "price_current", "price_score", "buy_price", "graham_number",
              "graham_tech", "flags"):
        if k in gp:
            L.append(f"- {k}: {_fmtv(gp[k])}")
    return L


def _load_round1(ticker):
    f = ROOT / "scripts" / "output_round1" / f"{ticker}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _q(mj):
    return "-" if mj["score"] is None else f"{mj['score']:.1f}"


def _val(pr, key):
    v = pr.get(key)
    return "n/a" if v is None else f"{v:.2f}"


def changes_table(rows):
    L = ["\n### What changed vs. round 1 (before -> after)\n",
         "| Ticker | Buffett quality | Buffett fair value | Buffett price score | Graham quality | Graham value | Notes |",
         "|---|---|---|---|---|---|---|"]
    for res, *_ in rows:
        old = _load_round1(res["ticker"])
        if not old:
            continue
        bp, bo = res["buffett_price"], old["buffett_price"]
        gp, go = res["graham_price"], old["graham_price"]

        def ps(x):
            p_ = x.get("price_score", {}).get("points")
            return "n/a" if p_ is None else f"{p_:.1f}"
        notes = []
        if bp.get("state") != bo.get("state"):
            notes.append(f"Buffett valuation {bo.get('state')} -> {bp.get('state')}")
        if gp.get("state") != go.get("state"):
            notes.append(f"Graham valuation {go.get('state')} -> {gp.get('state')}")
        L.append(f"| {res['ticker']} | {_q(old['buffett_quality'])} -> {_q(res['buffett_quality'])} | "
                 f"{_val(bo, 'fair_value')} -> {_val(bp, 'fair_value')} | {ps(bo)} -> {ps(bp)} | "
                 f"{_q(old['graham_quality'])} -> {_q(res['graham_quality'])} | "
                 f"{_val(go, 'value')} -> {_val(gp, 'value')} | {'; '.join(notes)} |")
    return L


def da_table(rows):
    L = ["\n### D&A tag used per company (item 7)\n", "| Ticker | Tags used (years) |", "|---|---|"]
    for res, *_ in rows:
        cnt = {}
        for v in res["data_source"]["tag_log_per_field_per_year"]["da"].values():
            t = v.get("tag") or "none"
            cnt[t] = cnt.get(t, 0) + 1
        L.append(f"| {res['ticker']} | " + "; ".join(f"{t} ({n})" for t, n in cnt.items()) + " |")
    return L


def rd_cell(bp):
    rd = bp.get("reverse_dcf") or {}
    if rd.get("state") == "solved":
        return f"{rd['implied_growth'] * 100:.1f}%"
    if rd.get("state") == "out_of_range":
        return "out of range (" + rd["note"] + ")"
    return "-"


def build_summary(rows, failures):
    L = []
    L.append(f"# ValueCompass scoring test round - {date.today().isoformat()}\n")
    L.append(f"Scoring rules version `{MODEL_VERSION}` (EN). Data: SEC companyfacts XBRL (10-K, last 10 FY), "
             "prices from yfinance. No DB, no AI (every AI sub-item is `ai_pending`). "
             "Score format: `score [min-max range] cov coverage status`. Coverage/validity follow M1-M9 literally.\n")
    if failures:
        L.append("**Failed companies:** " + "; ".join(f"{t}: {e}" for t, e in failures) + "\n")
    L.append(CLARIFICATIONS)
    L.append(CHANGES)
    L += da_table(rows)
    L.append("")
    L.append(CHANGES3)
    L += round3_tables(rows)
    L.append("")
    L.append(CHANGES4)
    L.append(CHANGES5)
    L += results_tables(rows)
    L.append("")
    L.append("## 1. Company results\n")
    L.append("### Buffett\n")
    L.append("| Ticker | Profile | Price | Quality (normalized) | OE base (bn) | Stage-1 growth | Fair value | "
             "Reverse-DCF implied growth | Price score | Buy price |")
    L.append("|---|---|---:|---|---:|---:|---|---|---|---|")
    for r in rows:
        res = r[0]
        fv, ps, buy, _ = price_cells(res["buffett_price"])
        bpr = res["buffett_price"]
        oeb = bpr.get("oe_base")
        g1 = bpr.get("stage1_growth")
        L.append(f"| {res['ticker']} | {res['profile']} | {fnum(res['price']['current'], 2)} | "
                 f"{model_cell(res['buffett_quality'])} | {'-' if oeb is None else f'{oeb / 1e9:.1f}'} | "
                 f"{'-' if g1 is None else f'{g1 * 100:.1f}%'} | {fv} | {rd_cell(bpr)} | {ps} | {buy} |")
    L.append("\n### Graham\n")
    L.append("| Ticker | Method | Quality (normalized) | Value | Price score | Buy price |")
    L.append("|---|---|---|---|---|---|")
    for r in rows:
        res = r[0]
        gp = res["graham_price"]
        fv, ps, buy, _ = price_cells(gp)
        L.append(f"| {res['ticker']} | {gp['method']} | {model_cell(res['graham_quality'])} | {fv} | {ps} | {buy} |")
    L.append("\n### Main flags\n")
    for r in rows:
        res = r[0]
        fl = top_flags(res)
        L.append(f"- **{res['ticker']}** ({res['profile_reason']}): " + ("; ".join(fl) if fl else "none"))
    L.append("\n### Invalid / pending criteria\n")
    L.append("Invalid = < 70% of code-decidable points computed (M2). Pending = made only of AI items (excluded, shown in range).\n")
    for r in rows:
        res = r[0]
        inv = [f"B{c['id']}" for c in res["buffett_quality"]["invalid_criteria"]] + \
              [f"G{c['id']}" for c in res["graham_quality"]["invalid_criteria"]]
        pend = [f"B{c}" for c in res["buffett_quality"]["pending_criteria"]] + \
               [f"G{c}" for c in res["graham_quality"]["pending_criteria"]]
        L.append(f"- {res['ticker']}: invalid: " + (", ".join(inv) if inv else "none") +
                 "; pending: " + (", ".join(pend) if pend else "none"))
    L.append("\n### Key inputs (latest FY, USD billions unless noted)\n")
    L.append("| Ticker | Latest FY | Revenue | Net income | CFO | Capex | FCF | SBC | EBIT | Fin. debt | Cash+STI | "
             "Equity | Dil. shares (bn) | EPS | 5y median ROIC | ND/EBITDA |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for res, inp, d, *_ in rows:
        g = inp.series
        roics = [x["roic"] for x in d["roic"][-5:]]
        nd = d["nd_ebitda"][-1]
        L.append(f"| {inp.ticker} | {inp.fy[-1]} | {fmt_money(g('revenue')[-1])} | {fmt_money(g('net_income')[-1])} | "
                 f"{fmt_money(g('cfo')[-1])} | {fmt_money(g('capex')[-1])} | {fmt_money(d['fcf'][-1])} | "
                 f"{fmt_money(g('sbc')[-1])} | {fmt_money(g('ebit')[-1])} | {fmt_money(d['fin_debt'][-1])} | "
                 f"{fmt_money(d['cash_sti'][-1])} | {fmt_money(g('equity')[-1])} | "
                 f"{'-' if g('shares')[-1] is None else f'{g('shares')[-1] / 1e9:.2f}'} | "
                 f"{fnum(g('eps')[-1], 2)} | {pct(median([r for r in roics if r is not None]), 1)} | "
                 f"{'-' if nd[1] is None else (nd[0] if nd[1] in (float('inf'),) else f'{nd[1]:.2f}')} |")

    L.append("\n## 2. Sub-item heat-map\n")
    L.append("Values are points earned. `AI` = ai_pending, `n/a` = not applicable, `MISS` = missing data, "
             "`0•` = true zero (data shows weakness). Maximum points in the column header.\n")
    for key, label, groups in (("buffett_quality", "Buffett", [("3.1", "3.2", "3.3", "3.4"), ("3.5", "3.6", "3.7", "3.8")]),
                               ("graham_quality", "Graham", [("3.1", "3.2", "3.3", "3.4"), ("3.5", "3.6", "3.7", "3.8")])):
        for grp in groups:
            cols = []
            for c in rows[0][0][key]["criteria"]:
                if c["id"] in grp:
                    for it in c["items"]:
                        cols.append((c["id"], it["id"], it["max_pts"]))
            L.append(f"\n**{label} quality {grp[0]}-{grp[-1]}**\n")
            L.append("| Ticker | " + " | ".join(f"{a}.{b} ({m:g})" for a, b, m in cols) + " |")
            L.append("|---|" + "---:|" * len(cols))
            for r in rows:
                res = r[0]
                cmap = {(c["id"], it["id"]): it for c in res[key]["criteria"] for it in c["items"]}
                L.append(f"| {res['ticker']} | " + " | ".join(cell(cmap[(a, b)]) for a, b, _ in cols) + " |")

    L.append("\n## 2b. Full breakdown - new companies (ADBE, INTU)\n")
    for r in rows:
        if r[0]["ticker"] in ("ADBE", "INTU"):
            L += breakdown(r[0])
    L.append("\n## 3. Data problems\n")
    for r in rows:
        res = r[0]
        L.append(f"\n**{res['ticker']}**\n")
        probs = res["data_problems"]
        L += [f"- {x}" for x in probs] if probs else ["- none detected"]
    L.append("\n## 4. Rule issues\n")
    if RULE_ISSUES.exists():
        L.append(RULE_ISSUES.read_text(encoding="utf-8"))
    else:
        L.append("(scripts/rule_issues.md not written yet)")
    (OUT / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = {a.upper() for a in argv}
    sec = SecClient()
    rows, failures = [], []
    for ticker, why in COMPANIES:
        if wanted and ticker not in wanted:
            continue
        try:
            r_ = run_company(sec, ticker, why)
            if r_ is None:
                print(f"{ticker}: not scored (sector_not_supported_v1)")
                continue
            rows.append(r_)
            print(f"{ticker}: ok")
        except Exception as e:  # noqa: BLE001
            failures.append((ticker, f"{type(e).__name__}: {e}"))
            print(f"{ticker}: FAILED {type(e).__name__}: {e}")
            traceback.print_exc()
    if rows:
        build_summary(rows, failures)
    print(f"SEC requests made this run: {sec.requests_made}")


if __name__ == "__main__":
    main(sys.argv[1:])

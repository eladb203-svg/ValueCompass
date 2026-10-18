"""Graham quality (3.1-3.8) and Graham price (Graham Number + Graham Tech)."""
from __future__ import annotations

import math

from .buffett import _buy_price, _dilution_item, dilution
from .common import L, growth_item, miss, paired_totals, tail, thresholded, zero
from .coverage import (ModelResult, ai_pending, evaluate_criterion, evaluate_model, scored)
from .interpolate import describe, interpolate
from .metrics import (INF, clean, count_scaled, fell_more_than, growth_or_floor, mean, rose,
                      running_peak_drawdowns, smoothed_growth, three_vs_three_growth)

MODEL = "graham_quality"


# ---------------------------------------------------------------- 3.1
def c31(inp, d):
    items = []
    a1 = [(100e6, 0), (300e6, 1.5), (750e6, 3)]
    rev = inp.series("revenue")[-1]
    items.append(miss("1", "Company size", 3, "latest revenue missing", a1) if rev is None else
                 thresholded("1", "Company size", 3, rev, a1, "", "latest revenue USD",
                             {"revenue": rev, "fx": "USD, R15 not exercised"}))
    a2 = [(3, 0), (5, 1.5), (10, 3)]
    if inp.first_annual_report is None or inp.as_of is None:
        items.append(miss("2", "Proven operating history", 3, "first annual report date unknown", a2))
    else:
        yrs = (inp.as_of - inp.first_annual_report).days / 365.25
        items.append(thresholded("2", "Proven operating history", 3, yrs, a2, "",
                                 "years since earliest 10-K filing",
                                 {"first_annual_report": str(inp.first_annual_report)},
                                 ["predecessor_history_not_checked"]))
    items.append(ai_pending("3", "No dependence on one product, customer or market", 2, note="AI question"))
    items.append(ai_pending("4", "Proven business position in its industry", 2, note="AI question"))
    return items


# ---------------------------------------------------------------- 3.2
def c32(inp, d):
    items = []
    cr, wc = d["current_ratio"], d["working_capital"]
    dra = (["deferred_revenue_cost_basis"] + (["deferred_revenue_default_30pct"] if d["dr_default30"][-1] else [])
           if d["dr_adjusted"][-1] else [])
    a1 = [(0.8, 0), (1.0, 2), (1.5, 4.5), (2.0, 7)]
    items.append(miss("1", "Current ratio, current", 7, "current assets/liabilities missing", a1) if cr[-1] is None else
                 thresholded("1", "Current ratio, current", 7, cr[-1], a1, "", "current ratio", {}, dra))
    a2 = [(0.5, 0), (1.0, 3)]
    q = d["quick_ratio"][-1]
    items.append(miss("2", "Quick ratio, current", 3, "cash/receivables/current liabilities missing", a2) if q is None
                 else thresholded("2", "Quick ratio, current", 3, q, a2, "", "(cash+STI+receivables)/CL", {}, dra))
    a3 = [(2, 0), (3, 2), (4, 3.5), (5, 5)]
    flags = [None if (c is None or w is None) else (c >= 1.5 and w > 0) for c, w in zip(L(cr), L(wc))]
    cnt, nv, part = count_scaled(flags, 5)
    items.append(miss("3", "Liquidity consistency", 5, "fewer than 3 years", a3) if cnt is None else
                 thresholded("3", "Liquidity consistency", 5, cnt, a3, "", "years CR>=1.5 and WC>0 (of 5)",
                             {"current_ratio": L(cr)},
                             (["partial_window"] if part else []) +
                             (["deferred_revenue_cost_basis"] if any(L(d["dr_adjusted"])) else [])))
    return items


# ---------------------------------------------------------------- 3.3
def c33(inp, d):
    items = []
    debt, eq = d["fin_debt"][-1], inp.series("equity")[-1]
    a1 = [(0.3, 5), (0.5, 4), (1.0, 2), (2.0, 0)]
    ins = {"fin_debt": debt, "equity": eq}
    if debt is None:
        items.append(miss("1", "Debt to equity, current", 5, "financial debt missing", a1, inputs=ins))
    elif debt <= 0:
        items.append(scored("1", "Debt to equity, current", 5, 5, metric=0.0, metric_label="debt/equity",
                            thresholds=describe(a1), inputs=ins, note="no debt = 5"))
    elif eq is None:
        items.append(miss("1", "Debt to equity, current", 5, "equity missing", a1, inputs=ins))
    elif eq <= 0:
        items.append(zero("1", "Debt to equity, current", 5, None, a1, "", "debt/equity", ins,
                          ["equity_nonpositive_with_debt"]))
    else:
        items.append(thresholded("1", "Debt to equity, current", 5, debt / eq, a1, "", "debt/equity", ins))
    a2 = [(0.5, 4), (1.0, 2.5), (2.0, 0)]
    ltd, wc = inp.series("debt_lt")[-1], d["working_capital"][-1]
    dra33 = ["deferred_revenue_cost_basis"] if d["dr_adjusted"][-1] else []
    ins = {"long_term_debt": ltd, "working_capital": wc}
    if ltd is None:
        items.append(miss("2", "Long-term debt to working capital, current", 4, "long-term debt missing", a2,
                          inputs=ins))
    elif ltd <= 0:
        items.append(scored("2", "Long-term debt to working capital, current", 4, 4, metric=0.0,
                            metric_label="LT debt / WC", thresholds=describe(a2), inputs=ins,
                            note="no long-term debt = 4"))
    elif wc is None:
        items.append(miss("2", "Long-term debt to working capital, current", 4, "working capital missing", a2,
                          inputs=ins))
    elif wc <= 0:
        items.append(zero("2", "Long-term debt to working capital, current", 4, None, a2, "", "LT debt / WC",
                          ins, ["working_capital_nonpositive_with_lt_debt"] + dra33))
    else:
        items.append(thresholded("2", "Long-term debt to working capital, current", 4, ltd / wc, a2, "",
                                 "LT debt / WC", ins, dra33))
    a3 = [(2, 0), (5, 2), (10, 3)]
    st, r = d["int_cov"][-1]
    ins = {"ebit": inp.series("ebit")[-1], "interest_expense": inp.series("interest_expense")[-1], "state": st}
    if st == "missing":
        items.append(miss("3", "Interest coverage, current", 3, "EBIT, debt or interest expense missing", a3,
                          inputs=ins))
    elif st in ("no_debt", "zero_interest"):
        items.append(scored("3", "Interest coverage, current", 3, 3, metric="inf", metric_label="EBIT/interest",
                            thresholds=describe(a3), inputs=ins,
                            flags=["assumed_zero_interest_tag_absent"] if st == "zero_interest" else [],
                            note=st))
    elif st == "ebit_nonpositive":
        items.append(zero("3", "Interest coverage, current", 3, None, a3, "", "EBIT/interest", ins,
                          ["ebit_nonpositive_with_debt"]))
    else:
        items.append(thresholded("3", "Interest coverage, current", 3, r, a3, "", "EBIT/interest", ins))
    a4 = [(2, 0), (3, 1), (4, 2), (5, 3)]
    flags = []
    for fd, e, (s2, r2) in zip(L(d["fin_debt"]), L(inp.series("equity")), L(d["int_cov"])):
        if fd is None or s2 == "missing" or (fd > 0 and e is None):
            flags.append(None)
            continue
        ok1 = fd <= 0 or (e > 0 and fd / e <= 1.0)
        ok2 = s2 in ("no_debt", "zero_interest") or (s2 == "ratio" and r2 >= 5)
        flags.append(ok1 and ok2)
    cnt, nv, part = count_scaled(flags, 5)
    items.append(miss("4", "Consistency", 3, "fewer than 3 years", a4) if cnt is None else
                 thresholded("4", "Consistency", 3, cnt, a4, "", "years D/E<=1.0 and coverage>=5 (of 5)",
                             {"flags": flags}, ["partial_window"] if part else []))
    return items


# ---------------------------------------------------------------- 3.4
def c34(inp, d):
    items = []
    ni, eps = tail(inp.series("net_income")), tail(inp.series("eps"))
    nv = clean(ni)
    partial = ["partial_history"] if len(ni) < 10 else []
    a1 = [(0.6, 0), (0.7, 3), (0.8, 5), (0.9, 7), (1.0, 9)]
    if len(nv) < 5:
        items.append(miss("1", "Profitable years", 9, "fewer than 5 years of net income", a1))
    else:
        share = sum(1 for x in nv if x > 0) / len(nv)
        items.append(thresholded("1", "Profitable years", 9, share, a1, "", "share of years NI>0",
                                 {"net_income": ni}, partial))
    a2 = [(0, 4), (1 / 9, 3), (2 / 9, 1.5), (3 / 9, 0)]
    fl = [fell_more_than(a, b, 0.20) for a, b in zip(eps[:-1], eps[1:])]
    v = [x for x in fl if x is not None]
    if len(clean(eps)) < 5 or not v:
        items.append(miss("2", "Frequency of declines", 4, "fewer than 5 years of EPS", a2))
    else:
        share = sum(1 for x in v if x) / len(v)
        items.append(thresholded("2", "Frequency of declines", 4, share, a2, "",
                                 "share of transitions with EPS fall >20%",
                                 {"eps": eps, "falls": sum(1 for x in v if x), "transitions": len(v)}, partial))
    a3 = [(0.10, 2), (0.50, 0)]
    dd = running_peak_drawdowns(eps)
    vd = [x for x in dd if x is not None]
    if len(clean(eps)) < 5:
        items.append(miss("3", "Depth of the largest decline", 2, "fewer than 5 years of EPS", a3))
    elif not vd:
        items.append(miss("3", "Depth of the largest decline", 2, "no positive EPS peak exists", a3,
                          inputs={"eps": eps}))
    else:
        items.append(thresholded("3", "Depth of the largest decline", 2, max(vd), a3, "",
                                 "max drawdown from running EPS peak", {"eps": eps, "drawdowns": dd}, partial))
    return items


# ---------------------------------------------------------------- 3.5
def c35(inp, d):
    names = [("1", "Continuity", 4), ("2", "No cuts", 2), ("3", "Earnings coverage", 2), ("4", "Cash-flow coverage", 2)]
    div, dps, ni = tail(inp.series("dividends")), tail(inp.series("dps")), tail(inp.series("net_income"))
    has = []
    for a, b in zip(div, dps):
        if a is None and b is None:
            has.append(None)
        else:
            has.append(bool((a or 0) > 0 or (b or 0) > 0))
    if has and has[-1] is False:
        return [zero(i, n, m, None, None, "", "", {}, ["does not meet Graham's dividend requirement"],
                     "no dividend in latest year -> criterion = 0 (data, not missing)") for i, n, m in names]
    items = []
    a1 = [(2, 0), (5, 1.5), (10, 4)]
    if not has or has[-1] is None:
        items.append(miss("1", "Continuity", 4, "latest-year dividend data missing", a1))
    else:
        run = 0
        for h in reversed(has):
            if h:
                run += 1
            else:
                break
        items.append(thresholded("1", "Continuity", 4, min(run, 10), a1, "", "consecutive years with dividend",
                                 {"has_dividend_by_year": has}))
    a2 = [(0, 2), (1, 1), (2, 0)]
    fl = [fell_more_than(a, b, 0.10) for a, b in zip(dps[:-1], dps[1:])]
    v = [x for x in fl if x is not None]
    if len(v) < 3:
        items.append(miss("2", "No cuts", 2, "dividend per share missing for most years", a2))
    else:
        items.append(thresholded("2", "No cuts", 2, sum(1 for x in v if x), a2, "", "DPS cuts >10%",
                                 {"dps": dps}, ["partial_history"] if len(v) < 9 else []))
    a3 = [(0.6, 2), (0.8, 1), (1.0, 0)]
    for id_, nm, denom in (("3", "Earnings coverage", "ni"), ("4", "Cash-flow coverage", "fcf")):
        s_div, s_den, n = paired_totals(inp.series("dividends"),
                                        inp.series("net_income") if denom == "ni" else d["fcf"])
        if s_div is None:
            items.append(miss(id_, nm, 2, "fewer than 3 paired years", a3))
        elif s_den <= 0:
            items.append(zero(id_, nm, 2, None, a3, "", f"sum dividends / sum {denom}",
                              {"sum_dividends": s_div, f"sum_{denom}": s_den}, [f"total_{denom}_nonpositive"]))
        else:
            items.append(thresholded(id_, nm, 2, s_div / s_den, a3, "", f"sum dividends / sum {denom} (5y)",
                                     {"sum_dividends": s_div, f"sum_{denom}": s_den, "years": n}))
    return items


# ---------------------------------------------------------------- 3.6
def c36(inp, d):
    items = []
    eps = tail(inp.series("eps"))
    g = three_vs_three_growth(eps)
    a1 = [(0, 0), (0.04, 5), (0.10, 9)]
    ins = {"eps": eps, "start_avg": g["start_avg"], "end_avg": g["end_avg"], "n": g["n"]}
    if g["kind"] == "insufficient":
        items.append(miss("1", "Long-term growth (Graham's test)", 9, "fewer than 6 years of EPS", a1, inputs=ins))
    elif g["kind"] == "start_nonpositive":
        items.append(zero("1", "Long-term growth (Graham's test)", 9, None, a1, "", "3v3 EPS growth", ins,
                          ["start_average_nonpositive"], "starting average <= 0 = 0"))
    elif g["kind"] == "negative_end":
        items.append(zero("1", "Long-term growth (Graham's test)", 9, None, a1, "", "3v3 EPS growth", ins,
                          ["ending_average_nonpositive"]))
    else:
        items.append(thresholded("1", "Long-term growth (Graham's test)", 9, g["value"], a1, "",
                                 f"annualized 3v3 EPS growth over {g['n'] - 3} periods", ins,
                                 ["partial_history"] if g["n"] < 10 else []))
    a2 = [(0.4, 0), (0.6, 1.5), (0.8, 3)]
    fl = [rose(a, b) for a, b in zip(eps[:-1], eps[1:])]
    v = [x for x in fl if x is not None]
    if len(clean(eps)) < 6 or not v:
        items.append(miss("2", "Consistency of growth", 3, "fewer than 6 years of EPS", a2))
    else:
        items.append(thresholded("2", "Consistency of growth", 3, sum(1 for x in v if x) / len(v), a2, "",
                                 "share of transitions with EPS rise", {"eps": eps}))
    a3 = [(0, 0), (0.05, 3)]
    items.append(growth_item("3", "Growth continues", 3, smoothed_growth(L(inp.series("eps"))), a3,
                             "smoothed EPS growth (5y)", turnaround_half=False, start_nonpos_zero=True))
    return items


# ---------------------------------------------------------------- 3.7
def c37(inp, d):
    items = []
    eq, gw, intg = inp.series("equity"), inp.series("goodwill"), inp.series("intangibles")
    a1 = [(0, 0), (0.5, 2), (0.8, 4)]
    te = d["tangible_equity"][-1]
    ins = {"equity": eq[-1], "goodwill": gw[-1], "intangibles": intg[-1], "tangible_equity": te}
    if eq[-1] is None or te is None:
        items.append(miss("1", "Tangible equity", 4, "equity missing", a1, inputs=ins))
    elif eq[-1] <= 0:
        items.append(zero("1", "Tangible equity", 4, None, a1, "", "tangible equity / equity", ins,
                          ["equity_nonpositive"]))
    else:
        items.append(thresholded("1", "Tangible equity", 4, te / eq[-1], a1, "", "tangible equity / equity", ins))
    a2 = [(3, 0), (4, 1.5), (5, 3)]
    flags = [None if e is None else e > 0 for e in L(eq)]
    cnt, nv, part = count_scaled(flags, 5)
    items.append(miss("2", "Equity stability", 3, "fewer than 3 years", a2) if cnt is None else
                 thresholded("2", "Equity stability", 3, cnt, a2, "", "years with positive equity (of 5)",
                             {"equity": L(eq)}, ["partial_window"] if part else []))
    a3 = [(-0.20, 0), (0.0, 3)]
    tb = d["tbvps"]
    first, last = (tb[-5] if inp.n >= 5 else None), tb[-1]
    ins = {"tbvps_first": first, "tbvps_latest": last}
    if first is None or last is None:
        items.append(miss("3", "Trend of tangible equity per share", 3, "tangible BVPS missing", a3, inputs=ins))
    elif last <= 0:
        items.append(zero("3", "Trend of tangible equity per share", 3, None, a3, "", "TBVPS change", ins,
                          ["tbvps_nonpositive_latest"]))
    elif first <= 0:
        items.append(scored("3", "Trend of tangible equity per share", 3, 3, metric=None,
                            metric_label="TBVPS change", thresholds=describe(a3), inputs=ins,
                            flags=["tbvps_first_year_nonpositive_improved"],
                            note="first year <= 0, latest > 0: change not measurable, counted as improvement"))
    else:
        items.append(thresholded("3", "Trend of tangible equity per share", 3, last / first - 1, a3, "",
                                 "TBVPS latest vs first year of 5-year period", ins))
    return items


# ---------------------------------------------------------------- 3.8
def c38(inp, d):
    items = []
    a1 = [(0.5, 0), (0.9, 3)]
    sf, sn, n = paired_totals(d["fcf"], inp.series("net_income"))
    if sf is None:
        items.append(miss("1", "FCF supports net income", 3, "fewer than 3 paired years", a1))
    elif sn <= 0:
        items.append(zero("1", "FCF supports net income", 3, None, a1, "", "sum FCF / sum NI",
                          {"sum_fcf": sf, "sum_ni": sn}, ["total_net_income_nonpositive"]))
    else:
        items.append(thresholded("1", "FCF supports net income", 3, sf / sn, a1, "", "sum FCF / sum NI (5y)",
                                 {"sum_fcf": sf, "sum_ni": sn, "years": n}))
    items.append(_dilution_item("2", "No dilution", 2, inp))
    items.append(ai_pending("3", "No dependence on one-time items", 2, note="AI question"))
    a4 = [(0.03, 2), (0.10, 0)]
    ge, go = smoothed_growth(L(inp.series("eps"))), smoothed_growth(L(inp.series("ebit")))
    ins = {"eps": ge, "operating_income": go}
    if ge["kind"] == "insufficient" or go["kind"] == "insufficient":
        items.append(miss("4", "EPS not inflated", 2, "EPS or operating income missing in first/last two years",
                          a4, inputs=ins))
    elif go["start_avg"] <= 0:
        items.append(zero("4", "EPS not inflated", 2, None, a4, "", "EPS growth - op income growth", ins,
                          ["starting_operating_income_nonpositive"]))
    elif ge["kind"] == "turnaround":
        items.append(zero("4", "EPS not inflated", 2, None, a4, "", "EPS growth - op income growth", ins,
                          ["eps_start_nonpositive_gap_treated_as_max"],
                          "EPS grew from <=0: growth undefined; gap treated as >=10pp (assumption)"))
    else:
        gap = growth_or_floor(ge) - growth_or_floor(go)
        items.append(thresholded("4", "EPS not inflated", 2, gap, a4, "", "smoothed EPS growth minus smoothed "
                                 "op income growth", ins))
    a5 = [(0, 1), (0.10, 0)]
    ac = L(d["accruals"])
    v = clean(ac)
    items.append(miss("5", "Net income vs cash flow gap", 1, "fewer than 3 years", a5, inputs={"accruals": ac})
                 if len(v) < 3 else
                 thresholded("5", "Net income vs cash flow gap", 1, sum(v) / len(v), a5, "",
                             "avg annual accruals / avg total assets", {"accruals": ac},
                             ["partial_window"] if len(v) < 5 else []))
    return items


CRITERIA = [
    ("3.1", "Company size and business stability", c31),
    ("3.2", "Financial condition and liquidity", c32),
    ("3.3", "Low debt and balance-sheet conservatism", c33),
    ("3.4", "Earnings stability", c34),
    ("3.5", "Dividend history", c35),
    ("3.6", "Moderate earnings growth", c36),
    ("3.7", "Quality of equity and assets", c37),
    ("3.8", "Earnings quality and dilution", c38),
]


def graham_quality(inp, d) -> ModelResult:
    return evaluate_model(MODEL, [evaluate_criterion(i, n, fn(inp, d)) for i, n, fn in CRITERIA])


# ================================================================ price
CLASSIC_PRICE = [(-0.25, 0), (-0.20, 0.5), (0.0, 2.5), (0.15, 4.5), (0.25, 6.5), (0.40, 8.5), (0.50, 10)]
TECH_PRICE = [(-0.25, 0), (-0.20, 0.5), (0.0, 2.5), (0.10, 4.5), (0.20, 6.5), (0.30, 8.5), (0.40, 10)]
CLASSIC_MARGIN = [(55, 0.50), (70, 0.35), (85, 0.30), (100, 0.25)]
TECH_MARGIN = [(55, 0.40), (70, 0.30), (85, 0.25), (100, 0.20)]
TECH_CAP = [(70, 15), (85, 18), (95, 22)]
TECH_MULTIPLE = [(0.0, 12), (0.05, 15), (0.10, 18), (0.15, 22), (0.20, 25)]


def graham_number(inp, d) -> dict:
    """Classic Graham Number with display-only checks."""
    # v1.1 G2: normalized EPS = 7-10 year average diluted EPS (Graham, Security Analysis); >= 7 years required, loss years included
    e10 = [x for x in L(inp.series("eps"), 10) if x is not None]
    bvps = d["bvps"][-1]
    out: dict = {}
    if len(e10) < 7 or bvps is None:
        return {"state": "cannot_be_valued", "reason": f"only {len(e10)} years of EPS (need 7+) or BVPS missing"}
    ne = sum(e10) / len(e10)
    out.update({"normalized_eps": ne, "bvps": bvps, "eps_years": len(e10), "loss_years": sum(1 for x in e10 if x < 0)})
    if ne <= 0 or bvps <= 0:
        return {**out, "state": "cannot_be_valued", "reason": "normalized EPS <= 0 or BVPS <= 0"}
    gn = math.sqrt(22.5 * ne * bvps)
    out.update({"state": "valued", "value": gn,
                "conservatism_check_display_only": min(gn, 15 * ne, 1.5 * bvps)})
    ca, tl, sh = inp.series("cur_assets")[-1], inp.series("liabilities")[-1], inp.series("shares")[-1]
    if None not in (ca, tl, sh) and sh:
        ncav = (ca - tl) / sh
        out["ncav_per_share"] = ncav
        out["net_net_test"] = None if inp.price_current is None else (ncav > 0 and inp.price_current < 2 / 3 * ncav)
    return out


def graham_tech(inp, d, quality: ModelResult) -> dict:
    out: dict = {"flags": []}
    af = L(d["adj_fcf"])
    states = list(inp.sbc_state)[-5:]
    out["sbc_states_last5"] = states
    out["adjusted_fcf_last5"] = af
    if any(s == "reported_none" for s in states):
        out["flags"].append("assumed reported_none - needs verification")
    if any(x is None for x in af[-3:]):
        return {**out, "state": "cannot_be_valued", "reason": "adjusted FCF input missing in last 3 years"}
    base = sum(af[-3:]) / 3
    out["base"] = base
    if base <= 0:
        return {**out, "state": "cannot_be_valued", "reason": "adjusted FCF base <= 0"}
    sh = inp.series("shares")
    dl = dilution(inp)
    if dl["value"] is not None:
        out["dilution"] = dl
        if dl["value"] >= 0.10:
            return {**out, "state": "cannot_be_valued",
                    "reason": f"dilution >= 10% over 5 years ({dl['value']:.1%}, {dl['basis']})"}
    g = smoothed_growth(af)
    out["growth_detail"] = g
    if g["kind"] == "insufficient":
        return {**out, "state": "cannot_be_valued", "reason": "adjusted FCF growth not computable"}
    if g["kind"] == "growth":
        gv = g["value"]
    else:
        gv = 0.0
        out["flags"].append(f"growth_not_measurable ({g['kind']}): multiple taken at growth<=0% (12x) (assumption)")
    mult_growth = interpolate(gv, TECH_MULTIPLE)
    q = quality.score
    if q is None:
        return {**out, "state": "cannot_be_valued", "reason": "no Graham quality score for multiple cap"}
    cap = interpolate(q, TECH_CAP)  # continuous (R4): <=70 -> 15, 85 -> 18, >=95 -> 25
    if quality.status != "full":
        out["flags"].append(f"quality cap taken from {quality.status} score (coverage {quality.coverage:.0%})")
    mult = min(mult_growth, cap)
    cash_sti, debt = d["cash_sti"][-1], d["fin_debt"][-1]
    if cash_sti is None or debt is None or sh[-1] is None:
        return {**out, "state": "cannot_be_valued", "reason": "cash, debt or shares missing"}
    value = (base * mult + cash_sti - debt) / sh[-1]
    return {**out, "state": "valued", "value": value, "growth_multiple": mult_growth, "quality_cap": cap,
            "final_multiple": mult, "quality_score_used": q}


def graham_price(inp, d, quality: ModelResult) -> dict:
    gn = graham_number(inp, d)
    tech = graham_tech(inp, d, quality)
    tech_profile = inp.profile == "TECH_ASSET_LIGHT"
    out: dict = {"model": "graham_price", "profile": inp.profile,
                 "method": "graham_tech" if tech_profile else "graham_number",
                 "graham_number": gn, "graham_tech": tech, "flags": []}
    primary = tech if tech_profile else gn
    anchors_p = TECH_PRICE if tech_profile else CLASSIC_PRICE
    anchors_m = TECH_MARGIN if tech_profile else CLASSIC_MARGIN
    if primary["state"] != "valued":
        return {**out, "state": "cannot_be_valued", "reason": primary.get("reason"), "value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    value, price = primary["value"], inp.price_current
    out.update({"state": "valued", "value": value, "price_current": price})
    if price is None:
        out["price_score"] = {"state": "missing", "points": None, "reason": "no current price"}
    else:
        disc = (value - price) / value
        out["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, anchors_p),
                              "anchors": describe(anchors_p)}
    out["buy_price"] = _buy_price(value, quality, anchors_m)
    return out

"""Buffett quality (3.1-3.8) and Buffett price (DCF fair value, price score, buy price)."""
from __future__ import annotations

from typing import Optional

from .common import L, growth_item, miss, paired_totals, thresholded, zero
from .coverage import (ModelResult, ai_pending, evaluate_criterion, evaluate_model, not_applicable,
                       scored)
from .interpolate import describe, interpolate
from .metrics import (effective_tax_rate, INF, clean, clip, count_scaled, fell_more_than, median, rose, smoothed_growth,
                      cagr, safe_div)

MODEL = "buffett_quality"

# ---------------------------------------------------------------- 3.1
Q31 = [
    ("1", "Is it clear what the company sells?"),
    ("2", "Is it clear who the customers are?"),
    ("3", "Are the revenue sources simple to understand?"),
    ("4", "Are the main risks clear?"),
    ("5", "Can the business be explained in one sentence?"),
]


def c31(inp, d):
    return [ai_pending(i, n, 2, note="AI question (not run in this round)") for i, n in Q31]


# ---------------------------------------------------------------- 3.2 Moat
def c32(inp, d):
    items = []
    gm, om = L(d["gross_margin"]), L(d["op_margin"])
    gp_any = any(x is not None for x in L(d.get("gross_profit_eff", inp.series("gross_profit"))))
    a1a, a1b = [(0.20, 0), (0.40, 1.0)], [(0.03, 1.5), (0.10, 0)]
    a2a, a2b = [(0.04, 1.5), (0.12, 0)], [(-0.05, 0), (-0.01, 1.0)]
    gv = clean(gm)
    if not gp_any:
        why = "no reported GrossProfit tag in any year (R9); derived gross profit NOT used"
        items.append(_na("1a", "Gross margin level", 1.0, why))
        items.append(_na("1b", "Gross margin stability", 1.5, why))
    elif len(gv) < 3:
        items.append(miss("1a", "Gross margin level", 1.0, "fewer than 3 years of gross margin", a1a))
        items.append(miss("1b", "Gross margin stability", 1.5, "fewer than 3 years of gross margin", a1b))
    else:
        items.append(thresholded("1a", "Gross margin level", 1.0, median(gv), a1a, "", "5y median gross margin",
                                 {"gross_margin": gm}))
        items.append(thresholded("1b", "Gross margin stability", 1.5, max(gv) - min(gv), a1b, "",
                                 "gross margin range (max-min)", {"gross_margin": gm}))
    ov = clean(om)
    if len(ov) < 3:
        items.append(miss("2a", "Operating margin stability", 1.5, "fewer than 3 years of operating margin", a2a))
        items.append(miss("2b", "No operating margin erosion", 1.0, "fewer than 3 years of operating margin", a2b))
    else:
        items.append(thresholded("2a", "Operating margin stability", 1.5, max(ov) - min(ov), a2a, "",
                                 "operating margin range", {"op_margin": om}))
        if om[-1] is None:
            items.append(miss("2b", "No operating margin erosion", 1.0, "latest operating margin missing", a2b))
        else:
            diff = om[-1] - median(ov)
            items.append(thresholded("2b", "No operating margin erosion", 1.0, diff, a2b, "",
                                     "latest minus 5y median op margin", {"op_margin": om}))
    # 3: persistent ROIC
    ro = [r["roic"] for r in _roic_window(d)]
    flags = [None if r is None else r >= 0.12 for r in ro]
    cnt, nv, part = count_scaled(flags, 5)
    a3 = [(1, 0), (2, 0.5), (3, 1), (4, 1.5), (5, 2)]
    if cnt is None:
        items.append(miss("3", "Persistent ROIC", 2.0, "fewer than 3 years of ROIC", a3, inputs={"roic": ro}))
    else:
        items.append(thresholded("3", "Persistent ROIC", 2.0, cnt, a3, "", "years with ROIC>=12% (of 5)",
                                 {"roic": ro}, ["partial_window"] if part else []))
    items.append(ai_pending("4", "Stable competitive position", 2.0, note="AI question"))
    items.append(ai_pending("5", "Clear moat", 1.0, note="AI question x0.5"))
    return items


def _na(id, name, mx, why):
    return not_applicable(id, name, mx, note=why, flags=["no_gross_profit_reported"])


def _roic_window(d):
    r = d["roic"]
    pad = [{"roic": None, "flags": []}] * max(0, 5 - len(r))
    return (pad + r)[-5:]


# ---------------------------------------------------------------- 3.3
def c33(inp, d):
    items = []
    ni, eps, rev = L(inp.series("net_income")), L(inp.series("eps")), L(inp.series("revenue"))
    a1 = [(2, 0), (3, 2), (4, 4), (5, 6)]
    cnt, nv, part = count_scaled([None if x is None else x > 0 for x in ni], 5)
    items.append(miss("1", "Positive net income in most years", 6, "fewer than 3 years", a1) if cnt is None else
                 thresholded("1", "Positive net income in most years", 6, cnt, a1, "", "years NI>0 (of 5)",
                             {"net_income": ni}, ["partial_window"] if part else []))
    a2 = [(0, 4), (1, 3), (2, 1.5), (3, 0)]
    fl = [fell_more_than(a, b, 0.10) for a, b in zip(eps[:-1], eps[1:])]
    cnt, nv, part = count_scaled(fl, 4)
    items.append(miss("2", "Stable EPS", 4, "fewer than 3 EPS transitions", a2) if cnt is None else
                 thresholded("2", "Stable EPS", 4, cnt, a2, "", "EPS falls >10% (of 4 transitions)",
                             {"eps": eps}, ["partial_window"] if part else []))
    a3 = [(0, 0), (0.05, 3)]
    g = cagr(rev[0], rev[-1], 4)
    if rev[0] is None or rev[-1] is None:
        items.append(miss("3", "Revenue growth", 3, "first or last revenue of the 5-year window missing", a3))
    elif g is None:
        items.append(zero("3", "Revenue growth", 3, None, a3, "", "revenue CAGR", {"revenue": rev},
                          ["revenue_nonpositive"]))
    else:
        items.append(thresholded("3", "Revenue growth", 3, g, a3, "", "revenue CAGR (4 periods across 5 FYs)",
                                 {"revenue": rev}))
    a4 = [(0, 0), (0.5, 2)]
    nv_ = clean(ni)
    if len(nv_) < 3:
        items.append(miss("4", "No exceptionally weak year", 2, "fewer than 3 years", a4))
    else:
        med = median(nv_)
        if med <= 0:
            items.append(zero("4", "No exceptionally weak year", 2, med, a4, "", "weakest NI / median NI",
                              {"net_income": ni}, ["median_net_income_nonpositive"]))
        else:
            items.append(thresholded("4", "No exceptionally weak year", 2, min(nv_) / med, a4, "",
                                     "weakest NI / median NI", {"net_income": ni}))
    return items


# ---------------------------------------------------------------- 3.4
def c34(inp, d):
    a = [(0, 0), (0.06, 4.5), (0.10, 8.5), (0.15, 12.5), (0.20, 15)]
    w = _roic_window(d)
    ro = [r["roic"] for r in w]
    flags = sorted({f for r in w for f in r.get("flags", []) if f != "no_prior_year_balance_sheet"})
    ni, eq = inp.series("net_income"), inp.series("equity")
    roe = [safe_div(ni[i], (eq[i] + eq[i - 1]) / 2) if i and eq[i] is not None and eq[i - 1] is not None else None
           for i in range(inp.n)]
    inputs = {"roic_by_year": ro, "roe_displayed_not_scored": L(roe)}
    vals = clean(ro)
    if len(vals) < 3:
        return [miss("1", "ROIC level (5y median)", 15, "fewer than 3 years of ROIC", a, inputs=inputs, flags=flags)]
    m = median(vals)
    if m <= 0:
        return [zero("1", "ROIC level (5y median)", 15, m, a, "", "5y median ROIC", inputs, flags)]
    return [thresholded("1", "ROIC level (5y median)", 15, m, a, "", "5y median ROIC", inputs, flags)]


# ---------------------------------------------------------------- 3.5
def c35(inp, d):
    items = []
    fcf, fm = L(d["fcf"]), L(d["fcf_margin"])
    a1 = [(2, 0), (3, 2), (4, 3.5), (5, 5)]
    cnt, nv, part = count_scaled([None if x is None else x > 0 for x in fcf], 5)
    items.append(miss("1", "Positive FCF in most years", 5, "fewer than 3 years", a1) if cnt is None else
                 thresholded("1", "Positive FCF in most years", 5, cnt, a1, "", "years FCF>0 (of 5)",
                             {"fcf": fcf}, ["partial_window"] if part else []))
    a2a = [(0, 0), (0.15, 2)]
    v = clean(fm)
    items.append(miss("2a", "FCF margin level", 2, "fewer than 3 years", a2a) if len(v) < 3 else
                 thresholded("2a", "FCF margin level", 2, median(v), a2a, "", "5y median FCF margin",
                             {"fcf_margin": fm}))
    a2b = [(0, 2), (1, 1.5), (2, 0.75), (3, 0)]
    fl = [None if (a is None or b is None) else (b - a) < -0.05 for a, b in zip(fm[:-1], fm[1:])]
    cnt, nv, part = count_scaled(fl, 4)
    items.append(miss("2b", "FCF margin stability", 2, "fewer than 3 transitions", a2b) if cnt is None else
                 thresholded("2b", "FCF margin stability", 2, cnt, a2b, "", "margin falls >5pp (of 4)",
                             {"fcf_margin": fm}, ["partial_window"] if part else []))
    sf, sn, n1 = paired_totals(d["fcf"], inp.series("net_income"))
    a3 = [(0.40, 0), (0.70, 3)]
    if sf is None:
        items.append(miss("3", "FCF vs net income", 3, "fewer than 3 paired years", a3))
    elif sn <= 0:
        items.append(zero("3", "FCF vs net income", 3, None, a3, "", "sum FCF / sum NI",
                          {"sum_fcf": sf, "sum_ni": sn}, ["total_net_income_nonpositive"]))
    else:
        items.append(thresholded("3", "FCF vs net income", 3, sf / sn, a3, "", "sum FCF / sum NI (5y)",
                                 {"sum_fcf": sf, "sum_ni": sn, "years": n1},
                                 ["partial_window"] if n1 < 5 else []))
    sm, sn2, n2 = paired_totals(d["maint_capex"], inp.series("net_income"))
    a4 = [(0.25, 3), (0.75, 0)]
    mflags = sorted({x for f in L(d["maint_capex_flag"]) if f for x in f.split("; ")})
    if sm is None:
        items.append(miss("4", "Maintenance capex not excessive", 3, "fewer than 3 paired years", a4))
    elif sn2 <= 0:
        items.append(zero("4", "Maintenance capex not excessive", 3, None, a4, "", "sum maint capex / sum NI",
                          {"sum_maint_capex": sm, "sum_ni": sn2}, ["total_net_income_nonpositive"] + mflags))
    else:
        items.append(thresholded("4", "Maintenance capex not excessive", 3, sm / sn2, a4, "",
                                 "sum maint capex / sum NI (5y)",
                                 {"sum_maint_capex": sm, "sum_ni": sn2, "years": n2},
                                 mflags + (["partial_window"] if n2 < 5 else [])))
    return items


# ---------------------------------------------------------------- 3.6
def c36(inp, d):
    items = []
    nd, ic = d["nd_ebitda"], d["int_cov"]
    a1 = [(1.0, 3), (2.0, 2.25), (4.0, 0)]
    st, r = nd[-1]
    ins = {"net_debt": d["net_debt"][-1], "ebitda": d["ebitda"][-1], "state": st}
    if st == "missing":
        items.append(miss("1", "Net debt / EBITDA, current", 3, "net debt or EBITDA missing", a1, inputs=ins))
    elif st == "net_cash":
        items.append(scored("1", "Net debt / EBITDA, current", 3, 3, metric=r, metric_label="ND/EBITDA",
                            thresholds=describe(a1), inputs=ins, note="net cash = 3"))
    elif st == "ebitda_nonpositive":
        items.append(zero("1", "Net debt / EBITDA, current", 3, None, a1, "", "ND/EBITDA", ins,
                          ["ebitda_nonpositive_with_net_debt"]))
    else:
        items.append(thresholded("1", "Net debt / EBITDA, current", 3, r, a1, "", "ND/EBITDA", ins))
    a2 = [(1.5, 0), (5, 2.25), (10, 3)]
    st, r = ic[-1]
    ins = {"ebit": inp.series("ebit")[-1], "interest_expense": inp.series("interest_expense")[-1],
           "fin_debt": d["fin_debt"][-1], "state": st}
    if st == "missing":
        items.append(miss("2", "Interest coverage, current", 3, "EBIT, debt or interest expense missing", a2,
                          inputs=ins))
    elif st in ("no_debt", "zero_interest"):
        items.append(scored("2", "Interest coverage, current", 3, 3, metric="inf", metric_label="EBIT/interest",
                            thresholds=describe(a2), inputs=ins,
                            flags=["assumed_zero_interest_tag_absent"] if st == "zero_interest" else [],
                            note=st))
    elif st == "ebit_nonpositive":
        items.append(zero("2", "Interest coverage, current", 3, None, a2, "", "EBIT/interest", ins,
                          ["ebit_nonpositive_with_debt"]))
    else:
        items.append(thresholded("2", "Interest coverage, current", 3, r, a2, "", "EBIT/interest", ins))
    a3 = [(0.7, 0), (1.0, 0.75), (1.5, 1.5)]
    cr = d["current_ratio"][-1]
    dra = (["deferred_revenue_cost_basis"] + (["deferred_revenue_default_30pct"] if d["dr_default30"][-1] else [])
           if d["dr_adjusted"][-1] else [])
    items.append(miss("3", "Liquidity, current", 1.5, "current assets/liabilities missing", a3) if cr is None else
                 thresholded("3", "Liquidity, current", 1.5, cr, a3, "", "current ratio", {}, dra))
    a4 = [(2, 0), (3, 1), (4, 1.75), (5, 2.5)]
    flags = []
    for (s1, r1), (s2, r2) in zip(L(nd), L(ic)):
        if s1 == "missing" or s2 == "missing":
            flags.append(None)
            continue
        ok1 = s1 == "net_cash" or (s1 == "ratio" and r1 <= 2)
        ok2 = s2 in ("no_debt", "zero_interest") or (s2 == "ratio" and r2 >= 5)
        flags.append(ok1 and ok2)
    cnt, nv, part = count_scaled(flags, 5)
    items.append(miss("4", "Balance-sheet consistency", 2.5, "fewer than 3 years", a4) if cnt is None else
                 thresholded("4", "Balance-sheet consistency", 2.5, cnt, a4, "",
                             "years with ND/EBITDA<=2 and coverage>=5 (of 5)",
                             {"flags": flags}, ["partial_window"] if part else []))
    return items


# ---------------------------------------------------------------- 3.7
def c37(inp, d):
    items = []
    # 1 relative buyback valuation
    a1 = [(0.9, 2), (1.0, 1.5), (1.2, 0)]
    pe, bb = L(d["pe"]), L(inp.series("buybacks"))
    prices = L(inp.price_avg or [None] * inp.n)
    if all(p is None for p in prices):
        items.append(miss("1", "Relative buyback valuation", 2, "no annual average prices available", a1))
    else:
        bb_years = [(p, b) for p, b in zip(pe, bb) if b is not None and b > 0]
        valid = [(p, b) for p, b in bb_years if p is not None]
        med = median(pe)
        ins = {"pe_by_year": pe, "buybacks": bb, "median_pe": med}
        if not bb_years:
            items.append(not_applicable("1", "Relative buyback valuation", 2, note="no buybacks in the 5 years",
                                        inputs=ins))
        elif not valid:
            items.append(not_applicable("1", "Relative buyback valuation", 2, inputs=ins,
                                        note="buybacks only in years with EPS<=0 (no valid year)"))
        elif len(clean(pe)) < 3 or med is None:
            items.append(miss("1", "Relative buyback valuation", 2, "fewer than 3 valid P/E years", a1, inputs=ins))
        else:
            wavg = sum(p * b for p, b in valid) / sum(b for _, b in valid)
            items.append(thresholded("1", "Relative buyback valuation", 2, wavg / med, a1, "",
                                     "buyback-weighted P/E / median P/E", {**ins, "weighted_pe": wavg}))
    # 2 dilution
    items.append(_dilution_item("2", "No meaningful dilution", 2, inp))
    # 3 M&A
    acq, fcf = L(inp.series("acquisitions")), L(d["fcf"])
    sa, sf, n = paired_totals(acq, fcf)
    if sa is None:
        items.append(miss("3", "M&A created value", 2, "acquisitions or FCF missing"))
    else:
        ins = {"sum_acquisitions": sa, "sum_fcf": sf}
        if sa <= 0:
            items.append(scored("3", "M&A created value", 2, 2, metric=0.0, metric_label="acq/FCF",
                                thresholds="<=10% = 2, above: AI", inputs=ins, note="no acquisitions"))
        elif sf <= 0:
            items.append(ai_pending("3", "M&A created value", 2, metric="inf", metric_label="acq/FCF",
                                    inputs=ins, flags=["fcf_total_nonpositive_gate_open"],
                                    note="acquisitions with FCF<=0: gate treated as >10% -> AI question"))
        elif sa / sf <= 0.10:
            items.append(scored("3", "M&A created value", 2, 2, metric=sa / sf, metric_label="acq/FCF",
                                thresholds="<=10% = 2, above: AI", inputs=ins))
        else:
            items.append(ai_pending("3", "M&A created value", 2, metric=sa / sf, metric_label="acq/FCF",
                                    inputs=ins, note="acquisitions > 10% of FCF: AI question required"))
    # 4 distributions
    a4 = [(1.0, 2), (1.5, 0)]
    dist = [None if (x is None or y is None) else x + y
            for x, y in zip(L(inp.series("dividends")), L(inp.series("buybacks")))]
    sd, sf2, n = paired_totals(dist, d["fcf"])
    if sd is None:
        items.append(miss("4", "Distributions supported by cash flow", 2, "fewer than 3 paired years", a4))
    else:
        ins = {"sum_distributions": sd, "sum_fcf": sf2}
        if sd <= 0:
            items.append(scored("4", "Distributions supported by cash flow", 2, 2, metric=0.0,
                                metric_label="(div+buybacks)/FCF", thresholds=describe(a4), inputs=ins,
                                note="no distributions = 2"))
        elif sf2 <= 0:
            items.append(zero("4", "Distributions supported by cash flow", 2, None, a4, "",
                              "(div+buybacks)/FCF", ins, ["total_fcf_nonpositive_treated_as_ge_150pct"]))
        else:
            items.append(thresholded("4", "Distributions supported by cash flow", 2, sd / sf2, a4, "",
                                     "(div+buybacks)/FCF (5y)", ins))
    items.append(ai_pending("5", "Transparent, conservative, consistent management", 2, note="AI question"))
    return items


def dilution(inp) -> dict:
    """Share-count change latest vs t-4 on period-end shares outstanding.

    Falls back to weighted-average diluted shares (flagged) when a period-end count is missing.
    Returns {value, latest, base, flags} or {value: None, reason}.
    """
    if inp.n < 5:
        return {"value": None, "reason": "fewer than 5 years of data"}
    out = inp.series("shares_out")
    if out[-1] is not None and out[-5] is not None:
        return {"value": out[-1] / out[-5] - 1, "latest": out[-1], "base": out[-5],
                "basis": "period_end_shares_outstanding", "flags": []}
    w = inp.series("shares")
    if w[-1] is not None and w[-5] is not None:
        return {"value": w[-1] / w[-5] - 1, "latest": w[-1], "base": w[-5],
                "basis": "weighted_average_diluted", "flags": ["dilution_fallback_weighted_diluted"]}
    return {"value": None, "reason": "share counts for latest year or t-4 missing"}


def _dilution_item(id, name, mx, inp):
    a = [(0.0, 2), (0.10, 0)]
    dl = dilution(inp)
    if dl["value"] is None:
        return miss(id, name, mx, dl["reason"], a)
    return thresholded(id, name, mx, dl["value"], a, "", "share-count change vs first year of 5-year window (t-4)",
                       {"shares_latest": dl["latest"], "shares_t_minus_4": dl["base"], "basis": dl["basis"]},
                       dl["flags"])


# ---------------------------------------------------------------- 3.8
def c38(inp, d):
    items = []
    rev = L(inp.series("revenue"))
    a1 = [(1, 0), (2, 1), (3, 2), (4, 3)]
    cnt, nv, part = count_scaled([rose(a, b) for a, b in zip(rev[:-1], rev[1:])], 4)
    items.append(miss("1", "Consistency of revenue growth", 3, "fewer than 3 transitions", a1) if cnt is None else
                 thresholded("1", "Consistency of revenue growth", 3, cnt, a1, "", "revenue rises (of 4)",
                             {"revenue": rev}, ["partial_window"] if part else []))
    a = [(0, 0), (0.10, 3)]
    items.append(growth_item("2", "EPS growth", 3, smoothed_growth(L(inp.series("eps"))), a, "smoothed EPS growth"))
    items.append(growth_item("3", "FCF growth", 3, smoothed_growth(L(d["fcf"])), a, "smoothed FCF growth"))
    # 4 growth without excessive debt
    a4 = [(0.5, 2), (2.0, 0)]
    nd = d["nd_ebitda"]
    if inp.n < 5:
        items.append(miss("4", "Growth without excessive debt", 2, "fewer than 5 years of data", a4))
    else:
        (s1, r1), (s0, r0) = nd[-1], nd[-5]
        ins = {"latest": [s1, r1], "t_minus_4": [s0, r0]}
        if "missing" in (s1, s0):
            items.append(miss("4", "Growth without excessive debt", 2, "ND/EBITDA missing at one point", a4,
                              inputs=ins))
        elif s1 == "net_cash" and s0 == "net_cash":
            items.append(scored("4", "Growth without excessive debt", 2, 2, metric=None,
                                metric_label="change in ND/EBITDA", thresholds=describe(a4), inputs=ins,
                                note="net cash at both points = 2"))
        elif r1 == INF and r0 == INF:
            items.append(zero("4", "Growth without excessive debt", 2, None, a4, "", "change in ND/EBITDA", ins,
                              ["ebitda_nonpositive_with_net_debt_at_both_points"]))
        elif r1 == INF:
            items.append(zero("4", "Growth without excessive debt", 2, None, a4, "", "change in ND/EBITDA", ins,
                              ["ebitda_nonpositive_with_net_debt_latest"]))
        elif r0 == INF:
            items.append(scored("4", "Growth without excessive debt", 2, 2, metric=None,
                                metric_label="change in ND/EBITDA", thresholds=describe(a4), inputs=ins,
                                flags=["ebitda_nonpositive_with_net_debt_5y_ago"],
                                note="improved from an undefined (EBITDA<=0) start"))
        else:
            items.append(thresholded("4", "Growth without excessive debt", 2, r1 - r0, a4, "",
                                     "change in ND/EBITDA (latest - t-4)", ins))
    # 5 margins maintained
    a5 = [(0.01, 2), (0.05, 0)]
    nm = L(d["net_margin"])
    if any(x is None for x in (nm[0], nm[1], nm[3], nm[4])):
        items.append(miss("5", "Margins maintained", 2, "net margin missing in first/last two years", a5))
    else:
        decline = (nm[0] + nm[1]) / 2 - (nm[3] + nm[4]) / 2
        items.append(thresholded("5", "Margins maintained", 2, decline, a5, "",
                                 "decline in net margin, avg first 2 -> last 2", {"net_margin": nm}))
    items.append(ai_pending("6", "Growth is sustainable", 2, note="AI question"))
    return items


CRITERIA = [
    ("3.1", "Simple, understandable business", c31),
    ("3.2", "Moat", c32),
    ("3.3", "Consistent profitability", c33),
    ("3.4", "High return on capital", c34),
    ("3.5", "FCF / owner earnings", c35),
    ("3.6", "Strong balance sheet, reasonable debt", c36),
    ("3.7", "Management and capital allocation", c37),
    ("3.8", "Quality, sustainable growth", c38),
]


def buffett_quality(inp, d) -> ModelResult:
    return evaluate_model(MODEL, [evaluate_criterion(i, n, fn(inp, d)) for i, n, fn in CRITERIA])


# ================================================================ price
STAGE1_CAP = (0.0, 0.12)
TERMINAL_G = 0.025
DISCOUNT = 0.10
PRICE_ANCHORS = [(-0.25, 0), (-0.20, 0.5), (0.0, 2.5), (0.10, 4.5), (0.20, 6.5), (0.30, 8.5), (0.40, 10)]
MARGIN_ANCHORS = [(55, 0.40), (70, 0.30), (85, 0.20), (100, 0.15)]


def dcf_fair_value(base: float, g1: float, excess_cash_less_debt: float, shares: float,
                   terminal_g: float = TERMINAL_G, r: float = DISCOUNT) -> dict:
    """Two-stage DCF: years 1-5 grow at g1, years 6-10 fade linearly to terminal_g, then Gordon."""
    cf, pv, rows = base, 0.0, []
    for k in range(1, 11):
        g = g1 if k <= 5 else g1 + (terminal_g - g1) * (k - 5) / 5
        cf *= 1 + g
        disc = cf / (1 + r) ** k
        pv += disc
        rows.append({"year": k, "growth": g, "cash_flow": cf, "pv": disc})
    tv = cf * (1 + terminal_g) / (r - terminal_g)
    pv_tv = tv / (1 + r) ** 10
    equity_value = pv + pv_tv + excess_cash_less_debt
    return {"pv_cash_flows": pv, "terminal_value": tv, "pv_terminal_value": pv_tv,
            "equity_value": equity_value, "fair_value_per_share": equity_value / shares, "years": rows}


def required_margin(score: float, anchors) -> float:
    return interpolate(score, anchors)


def buffett_price(inp, d, quality: ModelResult) -> dict:
    out: dict = {"model": "buffett_price", "flags": []}
    cannot = lambda why: {**out, "state": "cannot_be_valued", "reason": why,  # noqa: E731
                          "fair_value": None, "price_score": {"state": "not_applicable", "points": None},
                          "buy_price": None}
    # v1.2 G3-C: unlevered owner earnings = OE + interest expense x (1 - tax rate); the base, growth and gate input use this series, debt is subtracted in the value
    ie, tx, pt = inp.series("interest_expense"), inp.series("tax"), inp.series("pretax")
    oe_series = [None if o is None else o + (i or 0.0) * (1 - effective_tax_rate(t_, p_)[0]) for o, i, t_, p_ in zip(d["owner_earnings"], ie, tx, pt)]
    if any(i is None for i in ie[-5:]):
        out["flags"].append("G3C_interest_expense_missing_counted_as_0")
    oe = L(oe_series)
    sbc_states = list(inp.sbc_state)[-5:]
    out["sbc_states_last5"] = sbc_states
    out["owner_earnings_last5"] = oe  # unlevered (v1.2 G3-C)
    out["owner_earnings_levered_last5"] = L(d["owner_earnings"])
    out["maint_capex_flags"] = sorted({x for f in L(d["maint_capex_flag"]) if f for x in f.split("; ")})
    out["flags"] += out["maint_capex_flags"]
    if any(s == "reported_none" for s in sbc_states):
        out["flags"].append("assumed reported_none - needs verification")
    if any(x is None for x in oe):
        miss_why = []
        if any(s_ == "not_found" for s_ in sbc_states):
            miss_why.append("SBC not found")
        return cannot("owner-earnings input missing in the last 5 years (median base needs all 5)"
                      + (f" ({', '.join(miss_why)})" if miss_why else ""))
    base = median(oe)
    out["oe_base_median"] = base
    out["base_method"] = "median of last 5 fiscal years (t-2), rolled forward 2 years at the stage-1 growth only when the latest owner earnings >= the median (v1.1 G1)"
    if base <= 0:
        return cannot("owner-earnings base <= 0")
    oe_all = oe_series
    prev5 = oe_all[-10:-5] if len(oe_all) >= 10 else []
    if len(prev5) == 5 and all(x is not None for x in prev5):
        m_prev = median(prev5)
        out["growth_detail"] = {"kind": "median_vs_median", "median_last5": base, "median_prev5": m_prev}
        out["growth_method"] = "median(last 5) vs median(previous 5), annualized over 5 years"
        if m_prev > 0:
            graw = (base / m_prev) ** (1 / 5) - 1
            g1 = clip(graw, *STAGE1_CAP)
            if g1 != graw:
                out["flags"].append(f"growth_clipped ({graw:.1%} -> {g1:.1%})")
        else:
            g1 = 0.0
            out["flags"].append("growth_not_measurable (previous-5 median <= 0): stage-1 growth set to lower clip 0% "
                                "(assumption)")
    else:
        g = smoothed_growth(oe)
        out["growth_detail"] = g
        out["growth_method"] = "R14 smoothed growth (fewer than 10 years of owner earnings)"
        out["flags"].append("growth_fallback_r14")
        if g["kind"] == "insufficient":
            return cannot("owner earnings missing in first/last two years of the 5-year window (growth not computable)")
        if g["kind"] == "growth":
            g1 = clip(g["value"], *STAGE1_CAP)
            if g1 != g["value"]:
                out["flags"].append(f"growth_clipped ({g['value']:.1%} -> {g1:.1%})")
        else:
            g1 = 0.0
            out["flags"].append(f"growth_not_measurable ({g['kind']}): stage-1 growth set to lower clip 0% (assumption)")
    out["growth_before_gate"] = g1
    gate = growth_gate(inp)
    out["growth_gate"] = gate
    if not gate["passed"]:
        out["flags"].append("growth_gate_failed (" + "; ".join(gate["failing"]) + ")")
        g1 = 0.0
    out["stage1_growth"] = g1
    base = out["oe_base_median"] * (1 + g1) ** 2  # the 5-year median sits at t-2: roll it forward to t
    # v1.1 G1: roll the median forward only when the latest owner earnings are at or above the 5-year median; otherwise the base is the median itself
    if oe[-1] < out["oe_base_median"]:
        base = out["oe_base_median"]
        out["flags"].append("G1_no_roll_latest_owner_earnings_below_5y_median")
    out["base"] = base
    out["oe_base"] = base
    cash_sti, debt, shares = d["cash_sti"][-1], d["fin_debt"][-1], inp.series("shares")[-1]
    if cash_sti is None or debt is None or shares is None:
        return cannot("cash, debt or diluted shares missing")
    excess = cash_sti - debt
    out["excess_cash_less_debt"] = excess
    dcf = dcf_fair_value(base, g1, excess, shares)
    out["dcf"] = dcf
    fv = dcf["fair_value_per_share"]
    out["state"] = "valued"
    out["fair_value"] = fv
    price = inp.price_current
    out["price_current"] = price
    if fv <= 0:  # C15: a value <= 0 is never displayed; price score 0, no buy price
        out["modeled_value_nonpositive"] = fv
        out["state"] = "cannot_be_valued"
        out["reason"] = "cannot be valued (debt exceeds modeled value)"
        out["fair_value"] = None
        out["price_score"] = {"state": "score", "points": 0.0, "reason": "C15: fair value <= 0 -> price score 0"}
        out["buy_price"] = None
        out["flags"].append("C15_fair_value_nonpositive_cannot_be_valued")
        return out
    if price is None:
        out["price_score"] = {"state": "missing", "points": None, "reason": "no current price"}
    else:
        disc = (fv - price) / fv
        out["price_score"] = {"state": "score", "discount": disc,
                              "points": interpolate(disc, PRICE_ANCHORS), "anchors": describe(PRICE_ANCHORS)}
    out["buy_price"] = _buy_price(fv, quality, MARGIN_ANCHORS)
    out["reverse_dcf"] = reverse_dcf(base, excess, shares, price)
    out["implied_return"] = implied_return(base, g1, excess, shares, price)
    return out


def growth_gate(inp) -> dict:
    """Stage-1 growth eligibility (Buffett price): all of
    (a) revenue rose in >= 3 of the last 4 transitions,
    (b) diluted EPS fell by more than 10% in <= 1 of the last 4 transitions,
    (c) diluted EPS positive in all of the last 5 years.
    Missing data in the window counts as a failure of that condition.
    """
    rev, eps = L(inp.series("revenue")), L(inp.series("eps"))
    failing: list = []
    rises = [rose(a, b) for a, b in zip(rev[:-1], rev[1:])]
    if any(x is None for x in rises):
        failing.append("a: revenue data missing in the last 5 years")
        n_rise = None
    else:
        n_rise = sum(1 for x in rises if x)
        if n_rise < 3:
            failing.append(f"a: revenue rose in only {n_rise} of 4 transitions")
    falls = [fell_more_than(a, b, 0.10) for a, b in zip(eps[:-1], eps[1:])]
    if any(x is None for x in falls):
        failing.append("b: EPS data missing in the last 5 years")
        n_fall = None
    else:
        n_fall = sum(1 for x in falls if x)
        if n_fall > 1:
            failing.append(f"b: EPS fell >10% in {n_fall} of 4 transitions")
    if any(x is None for x in eps):
        failing.append("c: EPS data missing in the last 5 years")
        n_pos = None
    else:
        n_pos = sum(1 for x in eps if x > 0)
        if n_pos < 5:
            failing.append(f"c: EPS positive in only {n_pos} of 5 years")
    return {"passed": not failing, "failing": failing,
            "revenue_rises": n_rise, "eps_falls_gt10": n_fall, "eps_positive_years": n_pos}


def implied_return(base: float, g1: float, excess: float, shares: float, price,
                   lo: float = 0.0, hi: float = 0.30) -> dict:
    """Discount rate at which fair value equals the price (display only). Fair value falls as the rate rises.

    The Gordon terminal value needs r > terminal growth, so the search starts just above 2.5%.
    """
    if price is None:
        return {"state": "no_price"}
    lo_eff = max(lo, TERMINAL_G + 1e-4)

    def gap(r):
        return dcf_fair_value(base, g1, excess, shares, r=r)["fair_value_per_share"] - price
    if gap(lo_eff) < 0:
        return {"state": "out_of_range", "note": f"implied return below {lo_eff:.1%}"}
    if gap(hi) > 0:
        return {"state": "out_of_range", "note": f"implied return above {hi:.0%}"}
    a, b = lo_eff, hi
    for _ in range(80):
        mid = (a + b) / 2
        if gap(mid) > 0:
            a = mid
        else:
            b = mid
    return {"state": "solved", "implied_return": (a + b) / 2}


def reverse_dcf(base: float, excess: float, shares: float, price, lo: float = -0.20, hi: float = 0.50) -> dict:
    """Stage-1 growth at which Buffett fair value equals the price (display only). Bisection on [lo, hi]."""
    if price is None:
        return {"state": "no_price"}

    def gap(g):
        return dcf_fair_value(base, g, excess, shares)["fair_value_per_share"] - price
    glo, ghi = gap(lo), gap(hi)
    if glo > 0:
        return {"state": "out_of_range", "note": f"implied growth below {lo:.0%}"}
    if ghi < 0:
        return {"state": "out_of_range", "note": f"implied growth above {hi:.0%}"}
    a, b = lo, hi
    for _ in range(80):
        mid = (a + b) / 2
        if gap(mid) < 0:
            a = mid
        else:
            b = mid
    return {"state": "solved", "implied_growth": (a + b) / 2}


def _buy_price(value: float, quality: ModelResult, anchors) -> dict:
    """M7: only with fair value and quality coverage >= 80%. Below 55: do not buy."""
    q = quality.score
    res: dict = {"quality_score": q, "quality_coverage": quality.coverage, "quality_status": quality.status}
    if q is None:
        return {**res, "state": "not_computed", "reason": "no quality score"}
    margin = interpolate(max(q, 55), anchors)
    informational = None if q < 55 else value * (1 - margin)
    if quality.status != "full":
        return {**res, "state": "not_computed",
                "reason": f"quality coverage {quality.coverage:.0%} below 80% (M5/M7)",
                "informational_buy_price_ignoring_coverage": informational,
                "informational_margin": None if q < 55 else margin}
    if q < 55:
        return {**res, "state": "not_suitable", "reason": "quality score below 55: do not buy"}
    return {**res, "state": "computed", "margin_of_safety": margin, "buy_price": value * (1 - margin)}

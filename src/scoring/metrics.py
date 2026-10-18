"""Pure metric functions shared by the Buffett and Graham models."""
from __future__ import annotations

import statistics
from typing import Optional, Sequence

Num = Optional[float]
INF = float("inf")


# ---------------------------------------------------------------- basic helpers
def clean(xs: Sequence[Num]) -> list:
    return [x for x in xs if x is not None]


def median(xs: Sequence[Num]) -> Num:
    c = clean(xs)
    return statistics.median(c) if c else None


def mean(xs: Sequence[Num]) -> Num:
    c = clean(xs)
    return sum(c) / len(c) if c else None


def safe_div(a: Num, b: Num) -> Num:
    if a is None or b is None or b == 0:
        return None
    return a / b


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def last_n(xs: Sequence[Num], n: int) -> list:
    """Last n entries, left-padded with None so positions stay fiscal-year aligned."""
    xs = list(xs)
    return ([None] * (n - len(xs)) + xs) if len(xs) < n else xs[-n:]


def add(*vals: Num) -> Num:
    return None if any(v is None for v in vals) else sum(vals)


def sub(a: Num, b: Num) -> Num:
    return None if a is None or b is None else a - b


def total(xs: Sequence[Num], min_n: int = 1) -> Num:
    c = clean(xs)
    return sum(c) if len(c) >= min_n else None


def count_scaled(flags: Sequence[Optional[bool]], target: int, min_valid: int = 3):
    """Count True flags; if fewer than target are known, scale up to the target window.

    Returns (scaled_count, n_valid, partial). scaled_count is None when n_valid < min_valid.
    """
    valid = [f for f in flags if f is not None]
    if len(valid) < min_valid:
        return None, len(valid), False
    cnt = sum(1 for f in valid if f)
    if len(valid) == target:
        return float(cnt), len(valid), False
    return cnt * target / len(valid), len(valid), True


# ---------------------------------------------------------------- transitions
def fell_more_than(prev: Num, cur: Num, thr: float) -> Optional[bool]:
    """True if the value fell by more than thr (fraction) relative to |prev|."""
    if prev is None or cur is None:
        return None
    if prev == 0:
        return cur < 0
    return (cur - prev) / abs(prev) < -thr


def rose(prev: Num, cur: Num) -> Optional[bool]:
    if prev is None or cur is None:
        return None
    return cur > prev


def transition_flags(series: Sequence[Num], fn) -> list:
    """Apply fn(prev, cur) to consecutive pairs."""
    return [fn(a, b) for a, b in zip(series[:-1], series[1:])]


# ---------------------------------------------------------------- growth
def cagr(first: Num, last: Num, periods: int) -> Num:
    if first is None or last is None or periods <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / periods) - 1.0


def smoothed_growth(vals5: Sequence[Num]) -> dict:
    """R14: average of last 2 vs average of first 2 of a 5-year window, annualized over 3 years.

    kind: growth | turnaround (start<=0<end) | negative_end (end<=0) | insufficient
    """
    v = list(vals5)
    if len(v) != 5 or any(x is None for x in (v[0], v[1], v[3], v[4])):
        return {"kind": "insufficient", "value": None, "start_avg": None, "end_avg": None}
    s, e = (v[0] + v[1]) / 2, (v[3] + v[4]) / 2
    if e <= 0:
        kind, val = "negative_end", None
    elif s <= 0:
        kind, val = "turnaround", None
    else:
        kind, val = "growth", (e / s) ** (1 / 3) - 1
    return {"kind": kind, "value": val, "start_avg": s, "end_avg": e}


def three_vs_three_growth(vals: Sequence[Num]) -> dict:
    """Graham 3.6: avg of first 3 vs avg of last 3, annualized over n-3 periods."""
    v = clean(vals)
    n = len(v)
    if n < 6:
        return {"kind": "insufficient", "value": None, "n": n, "start_avg": None, "end_avg": None}
    s, e = sum(v[:3]) / 3, sum(v[-3:]) / 3
    if s <= 0:
        return {"kind": "start_nonpositive", "value": None, "n": n, "start_avg": s, "end_avg": e}
    if e <= 0:
        return {"kind": "negative_end", "value": None, "n": n, "start_avg": s, "end_avg": e}
    return {"kind": "growth", "value": (e / s) ** (1 / (n - 3)) - 1, "n": n, "start_avg": s, "end_avg": e}


def growth_or_floor(g: dict, floor: float = -1.0) -> Num:
    """Growth value for gap computations: negative_end -> floor (-100%), else value."""
    if g["kind"] == "growth":
        return g["value"]
    if g["kind"] == "negative_end":
        return floor
    return None


# ---------------------------------------------------------------- drawdown
def running_peak_drawdowns(eps: Sequence[Num]) -> list:
    """Graham 3.4 #3. peak = highest EPS up to t; drawdown = (peak-EPS_t)/peak when peak>0;
    EPS_t <= 0 -> 100%. Years before any positive peak -> None."""
    out, peak = [], None
    for x in eps:
        if x is None:
            out.append(None)
            continue
        peak = x if peak is None else max(peak, x)
        if peak <= 0:
            out.append(None)
        elif x <= 0:
            out.append(1.0)
        else:
            out.append((peak - x) / peak)
    return out


# ---------------------------------------------------------------- ROIC (Buffett 3.4)
def effective_tax_rate(tax: Num, pretax: Num):
    """Clip to 0-40%. Pre-tax loss / missing data: 25%. Returns (rate, [flags])."""
    if tax is None or pretax is None:
        return 0.25, ["tax_rate_25_missing_input"]
    if pretax <= 0:
        return 0.25, ["tax_rate_25_pretax_loss"]
    r = tax / pretax
    if r < 0:
        return 0.0, [f"tax_rate_clipped_to_0 (raw {r:.1%})"]
    if r > 0.40:
        return 0.40, [f"tax_rate_clipped_to_40 (raw {r:.1%})"]
    return r, []


def fin_debt(debt_current: Num, debt_lt: Num) -> Num:
    return add(debt_current, debt_lt)


def invested_capital(equity: Num, debt: Num, cash: Num, sti: Num = None) -> Num:
    """Equity + financial debt - cash - short-term investments (ruling: same as net debt)."""
    if equity is None or debt is None or cash is None:
        return None
    return equity + debt - cash - (sti or 0.0)


def operating_invested_capital(assets: Num, cash: Num, sti: Num, cur_liab: Num, debt_current: Num) -> Num:
    """Total assets - cash & short-term investments - non-debt current liabilities."""
    if assets is None or cash is None or cur_liab is None or debt_current is None:
        return None
    return assets - (cash + (sti or 0.0)) - (cur_liab - debt_current)


def _avg2(a: Num, b: Num) -> Num:
    return None if a is None or b is None else (a + b) / 2


def roic_year(ebit: Num, pretax: Num, tax: Num, bs0: dict, bs1: dict) -> dict:
    """ROIC for one year from beginning (bs0) and end (bs1) balance-sheet dicts.

    bs keys: equity, debt (financial), cash, sti, assets, cur_liab, debt_current.
    """
    flags: list = []
    if ebit is None:
        return {"roic": None, "flags": ["ebit_missing"]}
    rate, tf = effective_tax_rate(tax, pretax)
    flags += tf
    nopat = ebit * (1 - rate)
    ic0 = invested_capital(bs0.get("equity"), bs0.get("debt"), bs0.get("cash"), bs0.get("sti"))
    ic1 = invested_capital(bs1.get("equity"), bs1.get("debt"), bs1.get("cash"), bs1.get("sti"))
    ic = _avg2(ic0, ic1)
    out = {"nopat": nopat, "tax_rate": rate, "invested_capital_avg": ic}
    if ic is None:
        return {**out, "roic": None, "flags": flags + ["invested_capital_missing"]}
    if ic > 0:
        return {**out, "roic": nopat / ic, "flags": flags}
    # fallback: operating invested capital
    flags.append("roic_fallback_operating_ic")
    oic0 = operating_invested_capital(bs0.get("assets"), bs0.get("cash"), bs0.get("sti"),
                                      bs0.get("cur_liab"), bs0.get("debt_current"))
    oic1 = operating_invested_capital(bs1.get("assets"), bs1.get("cash"), bs1.get("sti"),
                                      bs1.get("cur_liab"), bs1.get("debt_current"))
    oic = _avg2(oic0, oic1)
    out["operating_ic_avg"] = oic
    if oic is not None and oic > 0:
        return {**out, "roic": nopat / oic, "flags": flags}
    flags.append("roic_fallback_fixed (20% if NOPAT>0 else 0%)")
    return {**out, "roic": 0.20 if nopat > 0 else 0.0, "flags": flags}


# ---------------------------------------------------------------- leverage / coverage
def nd_ebitda_state(net_debt: Num, ebitda: Num):
    """(state, ratio). states: net_cash | ebitda_nonpositive | ratio | missing."""
    if net_debt is None or ebitda is None:
        return "missing", None
    if net_debt <= 0:
        return "net_cash", (net_debt / ebitda if ebitda > 0 else 0.0)
    if ebitda <= 0:
        return "ebitda_nonpositive", INF
    return "ratio", net_debt / ebitda


def interest_coverage_state(ebit: Num, interest: Num, debt: Num, interest_tag_known: bool):
    """(state, ratio). states: no_debt | zero_interest | ebit_nonpositive | ratio | missing."""
    if debt is None or ebit is None:
        return "missing", None
    if debt <= 0:
        return "no_debt", INF
    if ebit <= 0:
        return "ebit_nonpositive", (ebit / interest if interest else -INF)
    if interest is None:
        return ("zero_interest", INF) if not interest_tag_known else ("missing", None)
    if interest <= 0:
        return "zero_interest", INF
    return "ratio", ebit / interest


def accrual_ratio(net_income: Num, cfo: Num, assets_begin: Num, assets_end: Num) -> Num:
    avg = _avg2(assets_begin, assets_end)
    if net_income is None or cfo is None or avg is None or avg == 0:
        return None
    return (net_income - cfo) / avg


# ---------------------------------------------------------------- per-year derived series
def derive(inp) -> dict:
    """Per-year derived series aligned with inp.fy. Pure function of CompanyInputs.f."""
    n = inp.n
    g = inp.series
    rev, gp, ebit, ni, eps = g("revenue"), g("gross_profit"), g("ebit"), g("net_income"), g("eps")
    cfo, capex, sbc, da = g("cfo"), g("capex"), g("sbc"), g("da")
    cash, sti = g("cash"), g("sti")
    dcur, dlt = g("debt_current"), g("debt_lt")
    eq, ca, cl, ta = g("equity"), g("cur_assets"), g("cur_liab"), g("assets")
    rec, gw, intg, sh = g("receivables"), g("goodwill"), g("intangibles"), g("shares")
    acq_am = g("acq_amort")

    from .candidates import CANDIDATES  # v1.1 candidates, C13 ON by default

    # C13 (candidate): claims/benefits expense is part of the cost of revenue where gross profit is derived or missing
    gp_eff = list(gp)
    if CANDIDATES.c13:
        claims = g("claims_expense")
        glog = getattr(inp, "tag_log", {}).get("gross_profit", {})
        for i in range(n):
            reported = gp[i] is not None and not str((glog.get(inp.fy[i]) or {}).get("tag") or "").startswith("DERIVED")
            if not reported and claims[i] is not None and rev[i] is not None:
                gp_eff[i] = rev[i] - ((g("cost_of_revenue")[i] or 0.0) + claims[i])
    gp = gp_eff

    d: dict = {}
    d["gross_profit_eff"] = gp_eff
    d["fin_debt"] = [fin_debt(a, b) for a, b in zip(dcur, dlt)]
    d["cash_sti"] = [add(c, s) for c, s in zip(cash, sti)]
    d["net_debt"] = [sub(fd, cs) for fd, cs in zip(d["fin_debt"], d["cash_sti"])]
    d["ebitda"] = [add(e, a) for e, a in zip(ebit, da)]
    d["fcf"] = [sub(c, x) for c, x in zip(cfo, capex)]
    d["gross_margin"] = [safe_div(a, b) for a, b in zip(gp, rev)]
    d["op_margin"] = [safe_div(a, b) for a, b in zip(ebit, rev)]
    d["net_margin"] = [safe_div(a, b) for a, b in zip(ni, rev)]
    d["fcf_margin"] = [safe_div(a, b) for a, b in zip(d["fcf"], rev)]
    # TECH_ASSET_LIGHT: deferred revenue is a liability that costs only (1 - gross margin) to settle, so current
    # liabilities include deferred revenue x (1 - gross margin) instead of the full amount (30% when the gross
    # margin is unavailable). Applies to all liquidity / working-capital metrics of the profile.
    dr = g("deferred_rev_current")
    tech = getattr(inp, "profile", None) == "TECH_ASSET_LIGHT"
    cl_adj, dr_adj, dr_def = [], [], []
    for c, x, gm_ in zip(cl, dr, d["gross_margin"]):
        if c is None or x is None or not tech:
            cl_adj.append(c)
            dr_adj.append(False)
            dr_def.append(False)
            continue
        incl = 0.30 if gm_ is None else 1.0 - clip(gm_, 0.0, 1.0)
        cl_adj.append(c - x * (1.0 - incl))
        dr_adj.append(True)
        dr_def.append(gm_ is None)
    d["dr_adjusted"], d["dr_default30"], d["current_liabilities_adj"] = dr_adj, dr_def, cl_adj
    d["current_ratio"] = [safe_div(a, b) for a, b in zip(ca, cl_adj)]
    d["working_capital"] = [sub(a, b) for a, b in zip(ca, cl_adj)]
    d["working_capital_raw"] = [sub(a, b) for a, b in zip(ca, cl)]  # unadjusted, kept for reference only
    d["quick_ratio"] = [safe_div(add(c, s, r), l) for c, s, r, l in zip(cash, sti, rec, cl_adj)]
    # DISPLAY ONLY (C12 was rejected for scoring): the same ratios with non-current marketable debt securities (explicit tag, else
    # the AFS-total-less-current-investments estimate) added as liquid assets. Never read by any scoring function.
    expl, derv = g("lt_mdebt_explicit"), g("lt_mdebt_derived")
    lt_md = [(e if e is not None else (dv or 0.0)) for e, dv in zip(expl, derv)]
    d["lt_mdebt_used"] = lt_md
    ca_l = [None if a is None else a + m for a, m in zip(ca, lt_md)]
    d["current_ratio_alt"] = [safe_div(a, b) for a, b in zip(ca_l, cl_adj)]
    d["working_capital_alt"] = [sub(a, b) for a, b in zip(ca_l, cl_adj)]
    d["quick_ratio_alt"] = [safe_div(None if None in (c, s, r) else c + s + r + m, l) for c, s, r, m, l in zip(cash, sti, rec, lt_md, cl_adj)]
    # maintenance capex = D&A - amortization of acquired intangibles (when separate)
    maint, maint_flag = [], []
    da_tags = [(inp.tag_log.get("da", {}).get(lab, {}) or {}).get("tag") for lab in inp.fy]
    for a, am, tg in zip(da, acq_am, da_tags):
        if a is None:
            maint.append(None)
            maint_flag.append(None)
            continue
        flags = []
        if am is None:
            maint.append(a)
            flags.append("includes_acquisition_amortization")
        else:
            maint.append(a - am)
        if tg and "FinanceLease" in str(tg):
            flags.append("includes_finance_lease_amortization")
        maint_flag.append("; ".join(flags) or None)
    d["maint_capex"], d["maint_capex_flag"] = maint, maint_flag
    d["owner_earnings"] = [None if (c is None or s is None or m is None) else c - s - m
                           for c, s, m in zip(cfo, sbc, maint)]
    d["adj_fcf"] = [None if (c is None or x is None or s is None) else c - x - s
                    for c, x, s in zip(cfo, capex, sbc)]
    d["tangible_equity"] = [None if e is None else e - (w or 0.0) - (i or 0.0)
                            for e, w, i in zip(eq, gw, intg)]
    d["bvps"] = [safe_div(e, s) for e, s in zip(eq, sh)]
    d["tbvps"] = [safe_div(e, s) for e, s in zip(d["tangible_equity"], sh)]
    prices = inp.price_avg or [None] * n
    d["pe"] = [None if (p is None or e is None or e <= 0) else p / e for p, e in zip(prices, eps)]
    d["accruals"] = [accrual_ratio(ni[i], cfo[i], ta[i - 1] if i else None, ta[i]) for i in range(n)]
    d["nd_ebitda"] = [nd_ebitda_state(a, b) for a, b in zip(d["net_debt"], d["ebitda"])]
    tag_known = any(x is not None for x in g("interest_expense"))
    d["int_cov"] = [interest_coverage_state(e, i, fd, tag_known)
                    for e, i, fd in zip(ebit, g("interest_expense"), d["fin_debt"])]
    d["roic"] = []
    for i in range(n):
        if i == 0:
            d["roic"].append({"roic": None, "flags": ["no_prior_year_balance_sheet"]})
            continue

        def bs(k):
            return {"equity": eq[k], "debt": d["fin_debt"][k], "cash": cash[k], "sti": sti[k],
                    "assets": ta[k], "cur_liab": cl[k], "debt_current": dcur[k]}
        r = roic_year(ebit[i], g("pretax")[i], g("tax")[i], bs(i - 1), bs(i))
        d["roic"].append(r)
    return d

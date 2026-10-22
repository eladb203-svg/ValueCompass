"""INSURANCE profile quality scoring (docs/scoring/ValueCompass_Insurance_Rules_2026-10-13_11-00_EN.md), pure functions.

One set of metrics for all lines of business. Code computes every metric and score; items found only in text are read from the extracted
CSV (``reg``) by the caller. Missing-data policy M1-M9 and D14 come from ``coverage``. No pricing in this round (spec section 6).
Definitions that cannot be computed as written are returned as ``missing`` with the reason (never invented).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from . import bank as BK
from . import buffett as B
from . import graham as G
from .common import L, growth_item, miss, tail, thresholded, zero
from .ai_items import ai_item
from .coverage import (ModelResult, ai_pending, evaluate_criterion, evaluate_model, not_applicable, scored)
from .interpolate import describe, interpolate
from .metrics import clean, count_scaled, median, rose, safe_div, smoothed_growth

log = logging.getLogger("valuecompass.insurance")

PROFILE = "INSURANCE"
LINE_OF_BUSINESS = {"CB": "P&C", "TRV": "P&C", "PGR": "P&C", "ALL": "P&C", "WRB": "P&C", "CINF": "P&C", "RNR": "reinsurance",
                    "MET": "life", "PRU": "life", "AFL": "life", "AIG": "composite", "HIG": "composite"}
CAT_MATERIAL_SHARE = 0.05  # Q5: flag when catastrophe losses EXCEED 5% of premiums earned (I19)
from .router import INSURANCE_SHARE as INSURANCE_TEST  # noqa: E402  (row 2 threshold lives in the router)


@dataclass
class InsuranceInputs:
    ticker: str
    name: str
    fy: list
    end: list
    f: dict
    reg: dict  # extracted items (scripts/insurance_regulatory.csv)
    price_current: Optional[float] = None
    price_entity_issue: Optional[str] = None  # C16
    ai_answers: dict = field(default_factory=dict)  # AI answers by skill id (code stage K5a); empty = the AI sub-items stay ai_pending
    price_avg: list = field(default_factory=list)
    first_annual_report: Optional[date] = None
    as_of: Optional[date] = None
    flags: list = field(default_factory=list)
    data_problems: list = field(default_factory=list)
    tag_log: dict = field(default_factory=dict)
    profile: str = PROFILE
    gov_yield: dict = field(default_factory=dict)  # {calendar year: annual-average 10-year government yield as a fraction}, in `yield_currency`
    yield_currency: str = "USD"
    yield_source: str = ""

    @property
    def n(self) -> int:
        return len(self.fy)

    def series(self, name: str) -> list:
        return self.f.get(name) or [None] * self.n


def _usd(reg, item):
    r = reg.get(item)
    if not r or not isinstance(r["value"], (int, float)):
        return None
    return r["value"] * 1e6 if r["unit"] == "USD mm" else r["value"]


def _add(*xs):
    return None if any(x is None for x in xs) else sum(xs)


# ---------------------------------------------------------------- derived per-year series (section 3)
def derive_insurance(ii: InsuranceInputs) -> dict:
    n, g = ii.n, ii.series
    d: dict = {"flags": {}}
    prem, fees, rev = g("premiums"), g("policy_fees"), g("revenue_total")
    d["fees_missing"] = all(x is None for x in fees)
    d["insurance_revenue"] = [None if p is None else p + (x or 0.0) for p, x in zip(prem, fees)]
    gains, mrb = g("gains_realized"), g("mrb_change")
    d["gains_pl"] = gains
    d["mrb_pl"] = [(x if x is not None else 0.0) for x in mrb]
    d["non_recurring_gains"] = [None if a is None else a + b for a, b in zip(gains, d["mrb_pl"])]
    d["operating_revenue"] = [None if (r is None or a is None) else r - a for r, a in zip(rev, gains)]
    d["other_revenue"] = [None if None in (r, p, nn, a) else r - p - (x or 0.0) - nn - a
                          for r, p, x, nn, a in zip(rev, prem, fees, g("nii"), gains)]
    # tax rate: effective clipped to 0-40% on positive pretax, otherwise 25%
    pre, tax = g("pretax"), g("tax")
    d["tax_rate"] = [0.25 if (p is None or t is None or p <= 0) else min(0.40, max(0.0, t / p)) for p, t in zip(pre, tax)]
    gw_imp = g("goodwill_impairment")
    # Rulebook C.B3.4-INS (H-02): goodwill impairment is added back (a non-operating charge), as BANK V5
    d["nop_pretax"] = [None if (p is None or gg is None) else p - gg + (w or 0.0) for p, gg, w in zip(pre, d["non_recurring_gains"], gw_imp)]
    d["nop_after_tax"] = [None if x is None else x * (1 - r) for x, r in zip(d["nop_pretax"], d["tax_rate"])]
    d["total_operating_margin"] = [safe_div(a, b) for a, b in zip(d["nop_pretax"], d["operating_revenue"])]
    d["net_margin"] = [safe_div(a, b) for a, b in zip(g("net_income"), d["operating_revenue"])]
    # underwriting result (identity form): insurance revenue - (total expenses - interest on debt - interest credited), MRB remeasurement removed
    te, ie, ic = g("total_expenses"), g("interest_expense"), g("interest_credited")
    uw_r1 = [None if (r is None or e is None) else r - (e - (i or 0.0) - (c or 0.0)) - m
             for r, e, i, c, m in zip(d["insurance_revenue"], te, ie, ic, d["mrb_pl"])]
    d["underwriting_result_r1"] = uw_r1  # round-1 definition (no accretion adjustment), kept for the before / after comparison
    d["underwriting_margin_r1"] = [safe_div(a, b) for a, b in zip(uw_r1, d["insurance_revenue"])]
    # Q1: interest accretion on the liability for future policy benefits (LDTI roll-forward, net of the accretion on net premiums) is an
    # insurance finance expense: out of claims / benefits (underwriting result goes up), into recurring investment income (goes down)
    acc_src, liab_s, fpb_s = g("ldti_accretion_net"), g("liabilities"), g("fpb")
    d["accretion"], d["accretion_flags"] = [], []
    for i in range(n):
        share = (fpb_s[i] or 0.0) / liab_s[i] if liab_s[i] else 0.0
        if acc_src[i] is not None:
            d["accretion"].append(acc_src[i])
            d["accretion_flags"].append(None)
        elif share >= 0.20:
            d["accretion"].append(None)
            d["accretion_flags"].append("accretion_missing_life_like")  # future policy benefits are material: the adjustment cannot be skipped
        else:
            d["accretion"].append(0.0)
            d["accretion_flags"].append("no_ldti_rollforward_tagged_future_policy_benefits_immaterial")
    d["underwriting_result"] = [None if (u is None or a is None) else u + a for u, a in zip(uw_r1, d["accretion"])]
    d["underwriting_margin"] = [safe_div(a, b) for a, b in zip(d["underwriting_result"], d["insurance_revenue"])]
    d["recurring_investment_income"] = [None if (nn is None or a is None) else nn - (c or 0.0) - a for nn, c, a in zip(g("nii"), ic, d["accretion"])]
    # adjusted equity (AOCI rate-driven components removed; FX and pension kept)
    eq, pf = g("equity"), g("preferred")
    afs, drr, cr = g("aoci_afs"), g("aoci_drr"), g("aoci_credit")
    d["adjusted_equity"], d["adj_equity_flags"] = [], []
    for i in range(n):
        if eq[i] is None or pf[i] is None:
            d["adjusted_equity"].append(None)
            d["adj_equity_flags"].append(["equity_or_preferred_missing"])
            continue
        fl = []
        if afs[i] is None:
            fl.append("aoci_afs_not_itemized")
        if drr[i] is None:
            fl.append("aoci_discount_rate_not_itemized")
        d["adjusted_equity"].append(eq[i] - pf[i] - (afs[i] or 0.0) - (drr[i] or 0.0) - (cr[i] or 0.0))
        d["adj_equity_flags"].append(fl)
    d["adjusted_tangible_equity"] = [None if (a is None or w is None or t is None) else a - w - t
                                     for a, w, t in zip(d["adjusted_equity"], g("goodwill"), g("intangibles"))]
    d["tbvps_adj"] = [safe_div(a, s) for a, s in zip(d["adjusted_tangible_equity"], g("shares_out"))]
    # operating ROE (average adjusted equity; <= 0 -> 0, flagged) and reported ROE (diagnostic)
    d["operating_roe"], d["roe_flags"], d["reported_roe"] = [None] * n, [None] * n, [None] * n
    ae, ni = d["adjusted_equity"], g("net_income")
    for i in range(1, n):
        if None not in (ae[i], ae[i - 1], d["nop_after_tax"][i]):
            avg = (ae[i] + ae[i - 1]) / 2
            if avg <= 0:
                d["operating_roe"][i], d["roe_flags"][i] = None, "average_adjusted_equity_nonpositive_Q8e_roe_undefined"
            else:
                d["operating_roe"][i] = d["nop_after_tax"][i] / avg
        if None not in (eq[i], eq[i - 1], ni[i]) and (eq[i] + eq[i - 1]) > 0:
            d["reported_roe"][i] = ni[i] / ((eq[i] + eq[i - 1]) / 2)
    # float: insurance liabilities net of reinsurance assets, with and without the discount-rate remeasurement in OCI (I16)
    cn, cg, ru = g("claims_net"), g("claims_gross"), g("reins_unpaid")
    fpb, pab, une, pre_r = g("fpb"), g("pab"), g("unearned"), g("reins_prepaid")
    d["float_reported"], d["float_flags"], d["float_sig"], d["float_parts"] = [], [], [], []
    for i in range(n):
        fl = []
        if cn[i] is not None:
            claims = cn[i]
        elif cg[i] is not None and ru[i] is not None:
            claims = cg[i] - ru[i]
        elif cg[i] is not None:
            claims, _ = cg[i], fl.append("claims_gross_no_reinsurance_recoverable")
        else:
            claims = None
        d["float_sig"].append((claims is not None, fpb[i] is not None, pab[i] is not None, une[i] is not None))
        d["float_parts"].append((claims, fpb[i], pab[i], une[i]))
        if claims is None and fpb[i] is None and pab[i] is None and une[i] is None:
            d["float_reported"].append(None)
            d["float_flags"].append(["no_insurance_liability_tags"])
            continue
        liab_i = g("liabilities")[i]
        life_like_i = bool(liab_i) and ((fpb[i] or 0.0) / liab_i) >= 0.20
        if claims is None and not life_like_i:  # a P&C-like float without the claims liability would be a partial number: missing instead
            d["float_reported"].append(None)
            d["float_flags"].append(["claims_liability_not_tagged_float_missing"])
            continue
        if fpb[i] is None:
            fl.append("future_policy_benefits_not_tagged")
        if pab[i] is None:
            fl.append("policyholder_account_balances_not_tagged")
        if une[i] is None:
            fl.append("unearned_premiums_not_tagged")
        if claims is None:
            fl.append("claims_liability_not_tagged")
        if fpb[i] or pab[i]:
            fl.append("reinsurance_assets_on_policy_liabilities_not_tagged")
        d["float_reported"].append((claims or 0.0) + (fpb[i] or 0.0) + (pab[i] or 0.0) + ((une[i] or 0.0) - (pre_r[i] or 0.0)))
        d["float_flags"].append(fl)
    d["float_ex_drr"] = []
    for i in range(n):
        fr = d["float_reported"][i]
        if fr is None:
            d["float_ex_drr"].append(None)
        elif drr[i] is None:
            d["float_ex_drr"].append(fr)  # remeasurement not reported: liabilities as reported, flagged by the caller
        else:
            d["float_ex_drr"].append(fr + drr[i])  # after-tax AOCI figure added back (pretax amount not extracted)
    d["float_cagr"] = _float_cagr(ii, d)
    _cost_of_float(ii, d)
    # adverse prior-period liability experience (section 3): (a) incurred-claims prior-year development, (b) LDTI remeasurement
    d["adverse_a"], d["adverse_b"], d["adverse_src"] = [None] * n, [None] * n, [None] * n
    pyd, ldti = g("prior_year_dev"), g("ldti_remeasurement")
    for i, lab in enumerate(ii.fy):
        src = []
        r = ii.reg.get(f"adverse_prior_year_dev:{lab}")
        if pyd[i] is not None:
            d["adverse_a"][i] = pyd[i]
            src.append("a: XBRL " + str((ii.tag_log.get("prior_year_dev", {}).get(lab) or {}).get("tag")))
        elif r and isinstance(r["value"], (int, float)):
            d["adverse_a"][i] = _usd(ii.reg, f"adverse_prior_year_dev:{lab}")
            src.append("a: extraction")
        r = ii.reg.get(f"adverse_ldti_remeasurement:{lab}")
        if ldti[i] is not None:
            d["adverse_b"][i] = -ldti[i]  # tag value: positive = gain
            src.append("b: XBRL LiabilityForFuturePolicyBenefitRemeasurementGainLoss (sign reversed: tag positive = gain)")
        elif r and isinstance(r["value"], (int, float)):
            d["adverse_b"][i] = _usd(ii.reg, f"adverse_ldti_remeasurement:{lab}")
            src.append("b: extraction")
        d["adverse_src"][i] = src
    d["relevant_liabilities_bop"] = [None] * n
    for i in range(1, n):
        lic = cg[i - 1] if cg[i - 1] is not None else cn[i - 1]
        if lic is None:  # incurred-claims liability at the start of the year is required (never a partial denominator)
            continue
        d["relevant_liabilities_bop"][i] = lic + (fpb[i - 1] or 0.0)
    d["fpb_share"] = [None if (f_ is None or fl_ in (None, 0)) else f_ / fl_ for f_, fl_ in zip(fpb, g("liabilities"))]
    d["reserve_deviation"], d["reserve_flags"] = [None] * n, [None] * n
    for i in range(1, n):
        life_like = (d["fpb_share"][i - 1] or 0.0) >= 0.20
        a, b, den = d["adverse_a"][i], d["adverse_b"][i], d["relevant_liabilities_bop"][i]
        if den is None or den <= 0:
            continue
        if life_like and b is None:
            d["reserve_flags"][i] = "ldti_component_missing_life_like"  # (b) is required when future policy benefits are material
            continue
        if a is None and b is None:
            continue
        d["reserve_deviation"][i] = ((a or 0.0) + (b or 0.0)) / den
    # financial debt (all debt incl. hybrid / subordinated); latest year may come from extraction
    debt_total, debt_lt, debt_st, jr = g("debt_total"), g("debt_lt"), g("debt_st"), g("debt_junior_sub")
    d["financial_debt"] = []
    for i in range(n):
        if debt_total[i] is not None:
            d["financial_debt"].append(debt_total[i])
        elif debt_lt[i] is not None or jr[i] is not None:
            d["financial_debt"].append((debt_lt[i] or 0.0) + (debt_st[i] or 0.0) + (jr[i] or 0.0))
        else:
            d["financial_debt"].append(None)
    ov = _usd(ii.reg, "debt_total")
    d["debt_override"] = ov
    if ov is not None:
        d["financial_debt"][-1] = ov
    d["financial_leverage"] = [None if (dd is None or a is None or dd + a <= 0) else dd / (dd + a)
                               for dd, a in zip(d["financial_debt"], d["adjusted_equity"])]
    # P/E for the buyback test
    d["pe"] = [None if (p is None or e is None or e <= 0) else p / e for p, e in zip(ii.price_avg or [None] * n, g("eps"))]
    dps = list(g("dps"))
    for i in range(n):
        if dps[i] is None and g("dividends")[i] is not None and g("shares_basic")[i]:
            dps[i] = g("dividends")[i] / g("shares_basic")[i]
    d["dps"] = dps
    d["latest"] = resolve_latest(ii, d)
    return d


FLOAT_PARTS = ("claims_liability", "future_policy_benefits", "policyholder_account_balances", "unearned_premiums")
MATERIAL_SHARE = 0.05  # Q10: a component is material at >= 5% of float (float components) or of total insurance expenses (underwriting components)


def float_break(d, i) -> tuple:
    """Q10 (Q8a, float components): between year i-1 and i a float component is tagged on one side only. Returns (material, notes): material when the tagged side
    is >= 5% of that year's float; otherwise the absent side counts as 0 and the year stays valid (flagged)."""
    mat, notes = False, []
    for k, nm in enumerate(FLOAT_PARTS):
        a, b = d["float_parts"][i - 1][k], d["float_parts"][i][k]
        if (a is None) == (b is None):
            continue
        j, v = (i - 1, a) if a is not None else (i, b)
        fl = d["float_reported"][j]
        if fl and abs(v) >= MATERIAL_SHARE * abs(fl):
            mat = True
            notes.append(f"{nm} material ({abs(v) / abs(fl):.0%} of float) and absent in the adjacent year")
        else:
            notes.append(f"{nm} absent in one year, immaterial: counted as 0")
    return mat, notes


def _year_of(label: str):
    import re
    m = re.search(r"\d{4}", str(label))
    return int(m.group()) if m else None


def _cost_of_float(ii, d) -> None:
    """Q6: cost of float = -underwriting result / average float (beginning and end of year; float ex discount-rate remeasurement); government yield =
    annual-average 10-year yield in the float's currency; cost gap = cost - yield. A year is missing when the underwriting result, either float, or the
    yield is missing, or when the tagged float components differ between the two year-ends (not comparable)."""
    n = ii.n
    fl, sig, uw = d["float_ex_drr"], d["float_sig"], d["underwriting_result"]
    # Q7: a year flagged under Q4 as a change in group structure (extracted event, or acquisition / divestiture / deconsolidation indicators above 10% of float)
    # is excluded from the cost-of-float series as well; float-component data breaks are handled separately below
    structural, structural_all = {}, set()
    for r in d["float_cagr"]["transitions"]:
        if r["source"] and r["fy"] in ii.fy:
            structural_all.add(ii.fy.index(r["fy"]))
    for r in d["float_cagr"]["transitions"]:
        if r["source"] in ("extraction (quote in the CSV)", "XBRL indicator tags") and r["fy"] in ii.fy:
            structural[ii.fy.index(r["fy"])] = r["reason"]
    # Q9: the income statement of year i excludes an operation presented as discontinued (income from discontinued operations reported) while that operation's
    # liabilities are still in the float (they leave it only in a later structural float decrease, Q4) -> basis mismatch, year excluded
    mismatch = {}
    dis = ii.series("disc_ops")
    drops = [ii.fy.index(r["fy"]) for r in d["float_cagr"]["transitions"]
             if r["source"] in ("extraction (quote in the CSV)", "XBRL indicator tags") and r["fy"] in ii.fy and r["float"] is not None and r["float_prev"] is not None
             and r["float"] < r["float_prev"]]
    drop_size = {ii.fy.index(r["fy"]): r["float_prev"] - r["float"] for r in d["float_cagr"]["transitions"]
                 if r["source"] in ("extraction (quote in the CSV)", "XBRL indicator tags") and r["fy"] in ii.fy and r["float"] is not None and r["float_prev"] is not None
                 and r["float"] < r["float_prev"]}
    for i in range(n):
        later = [j for j in drops if j > i]
        if dis[i] in (None, 0.0) or not later or not fl[i]:
            continue
        j = min(later)
        # the operation is presented as discontinued in every year from i up to the year its liabilities leave the float, and those liabilities are >= 10% of float
        if all(dis[k] not in (None, 0.0) for k in range(i, j)) and drop_size[j] >= 0.10 * fl[i]:
            mismatch[i] = (f"income statement excludes discontinued operations ({dis[i] / 1e9:+.2f}bn) whose liabilities stay in the float until FY{ii.fy[j][2:]} "
                           f"({drop_size[j] / fl[i]:.0%} of float, >= 10%)")
    d["basis_mismatch"] = {ii.fy[i]: m for i, m in mismatch.items()}
    # Q8a / Q10 (underwriting components: policy fees, interest credited; interest expense on debt is not one): absent in a year = 0, flagged, unless it was material
    # (>= 5% of total insurance expenses) in an adjacent year on the same group basis (no Q4 structural change in between) -> the year is missing
    te_, ucomp = ii.series("total_expenses"), {"policy_fees": ii.series("policy_fees"), "interest_credited": ii.series("interest_credited")}
    uw_missing, d["uw_flags"] = {}, [None] * n
    for i in range(n):
        for nm, sr in ucomp.items():
            if sr[i] is not None or not any(x is not None for x in sr):
                continue
            mat = None
            for k in (i - 1, i + 1):
                if not 0 <= k < n or sr[k] is None or not te_[k]:
                    continue
                if (max(i, k) in structural) or (max(i, k) in structural_all):
                    continue  # across a Q4 structural-change year the years are not compared
                if abs(sr[k]) >= MATERIAL_SHARE * abs(te_[k]):
                    mat = f"{nm} absent; {abs(sr[k]) / abs(te_[k]):.0%} of total insurance expenses in {ii.fy[k]}"
            if mat:
                uw_missing[i] = (uw_missing[i] + "; " + mat) if i in uw_missing else mat
            else:
                d["uw_flags"][i] = ((d["uw_flags"][i] + "; ") if d["uw_flags"][i] else "") + f"{nm}_absent_counted_as_0_Q10"
    d["avg_float"], d["cost_of_float"], d["gov_yield_yr"], d["cost_gap"], d["cost_ratio"], d["cost_flags"] = [None] * n, [None] * n, [None] * n, [None] * n, [None] * n, [None] * n
    for i in range(1, n):
        y = ii.gov_yield.get(_year_of(ii.fy[i]))
        d["gov_yield_yr"][i] = y
        if uw[i] is None:
            d["cost_flags"][i] = "underwriting_result_missing"
        elif fl[i] is None or fl[i - 1] is None or fl[i] <= 0 or fl[i - 1] <= 0:
            d["cost_flags"][i] = "float_missing"
        elif i in structural:
            d["cost_flags"][i] = "structural_change_Q4_year_excluded: " + structural[i]
        elif i in mismatch:
            d["cost_flags"][i] = "basis_mismatch_Q9_year_excluded: " + mismatch[i]
        elif sig[i] != sig[i - 1] and float_break(d, i)[0]:
            d["cost_flags"][i] = "float_components_changed_not_comparable_Q10: " + "; ".join(float_break(d, i)[1])
        elif i in uw_missing:
            d["cost_flags"][i] = "underwriting_component_missing_Q10: " + uw_missing[i]
        else:
            avg = (fl[i] + fl[i - 1]) / 2
            d["avg_float"][i] = avg
            d["cost_of_float"][i] = -uw[i] / avg
        c = d["cost_of_float"][i]
        if c is None:
            continue
        if y is None:
            d["cost_flags"][i] = "government_yield_missing"
            continue
        d["cost_gap"][i] = c - y
        # ratio of cost to yield (Buffett 3.5.1 scale): non-positive cost = 0 (best); with a non-positive yield any positive cost is >= the yield
        if c <= 0:
            d["cost_ratio"][i] = 0.0 if y > 0 else (0.0)
        elif y > 0:
            d["cost_ratio"][i] = c / y
        else:
            d["cost_ratio"][i] = 2.0
            d["cost_flags"][i] = "yield_nonpositive_positive_cost_counted_as_above_yield"


def _float_cagr(ii, d) -> dict:
    """Q4 (as BANK D7): CAGR of float (ex discount-rate remeasurement) over the valid transitions of the last 4; a transition with a change in
    group structure is excluded; fewer than 2 valid transitions = missing. Structural change = (a) an event extracted from the filing, or (b)
    an acquisition / divestiture / deconsolidation indicator tag in the year together with a float change above 10% (proxy for a transaction
    above 10% of float). Currency effects are flagged when more than 25% of pretax income is foreign."""
    n, fx = ii.n, d["float_ex_drr"]
    acq, gwa, dvp, dec, gws = (ii.series(k) for k in ("acquisitions", "goodwill_acquired", "divestiture_proceeds", "deconsolidation_cash", "goodwill_written_off_sale"))
    rows = []
    for i in range(max(1, n - 4), n):
        lab = ii.fy[i]
        a, b = fx[i - 1], fx[i]
        row = {"fy": lab, "float_prev": a, "float": b, "growth": None, "valid": False, "reason": None, "source": None}
        ev = ii.reg.get(f"structural_event:{lab}")
        if a is None or b is None or a <= 0 or b <= 0:
            row["reason"] = "float missing for the year or the year before"
        else:
            row["growth"] = b / a - 1
            ind = [(name, abs(v)) for name, v in (("acquisitions", acq[i]), ("goodwill_acquired", gwa[i]), ("divestiture_proceeds", dvp[i]),
                                                  ("deconsolidation_cash", dec[i]), ("goodwill_written_off_sale", gws[i])) if v not in (None, 0, 0.0)]
            size = sum(v for _, v in ind)
            sig_changed = i < len(d["float_sig"]) and d["float_sig"][i] != d["float_sig"][i - 1] and float_break(d, i)[0]
            if ev:
                row["reason"], row["source"] = "structural change: " + str(ev["note"]), "extraction (quote in the CSV)"
            elif ind and size > 0.10 * a:
                row["reason"] = (f"structural change proxy: acquisition / divestiture / deconsolidation indicator(s) "
                                 f"{', '.join(f'{k} {v / 1e9:.2f}bn' for k, v in ind)} = {size / a:.0%} of the prior-year float")
                row["source"] = "XBRL indicator tags"
            elif sig_changed:
                row["reason"] = "float components changed between the two years (tag availability: " \
                                f"{d['float_sig'][i - 1]} -> {d['float_sig'][i]}); not comparable"
                row["source"] = "data break"
            else:
                row["valid"] = True
        rows.append(row)
    valid = [r for r in rows if r["valid"]]
    out = {"transitions": rows, "n_valid": len(valid), "cagr": None}
    if len(valid) >= 2:
        prod = 1.0
        for r in valid:
            prod *= 1 + r["growth"]
        out["cagr"] = prod ** (1 / len(valid)) - 1
    pf, pt = [x for x in ii.series("pretax_foreign")[-5:] if x is not None], [x for x in ii.series("pretax")[-5:] if x is not None]
    share = (sum(pf) / sum(pt)) if (pf and pt and sum(pt) > 0) else None
    out["foreign_pretax_share"] = share
    out["fx_flag"] = bool(share is not None and share > 0.25)
    return out


def resolve_latest(ii, d) -> dict:
    """Regulatory capital multiple and portfolio composition for the latest year (extracted inputs)."""
    reg, out = ii.reg, {"flags": []}
    r = reg.get("reg_capital_ratio")
    out["reg_ratio"] = r["value"] if r and isinstance(r["value"], (int, float)) else None
    out["reg_note"] = r["note"] if r else None
    out["reg_period"] = r["period"] if r else None
    nt = (r["note"] or "") if r else ""
    out["reg_flags"] = ([f"prior_year_value_{r['period']}"] if r and r.get("period") and r["period"] != ii.fy[-1] else []) +         (["value_is_a_floor_in_excess_of"] if "FLOOR" in nt else []) + (["ratio_derived_from_reported_amounts"] if "DERIVED" in nt else []) +         (["lead_subsidiary_not_group"] if ("lead" in nt and "not group" in nt) or "lead subsidiary" in nt or "lead insurance subsidiary" in nt else []) +         (["regime_not_named_in_spec_SMR"] if "basis=SMR" in nt else [])
    basis = None
    if r:
        for tag in ("basis=ACL", "basis=CAL", "basis=SCR", "basis=SMR", "basis=OTHER"):
            if tag in (r["note"] or ""):
                basis = tag.split("=")[1]
    out["reg_basis"] = basis
    if out["reg_ratio"] is None or basis in (None, "OTHER"):
        out["reg_multiple"] = None
    elif basis in ("ACL", "SMR"):  # RBC ratio as % of Authorized Control Level (Company Action Level = 200% of ACL); Japanese SMR (intervention 200%)
        out["reg_multiple"] = out["reg_ratio"] / 200.0
    else:  # CAL: ratio already % of Company Action Level; SCR: % of SCR (first intervention level = 100%)
        out["reg_multiple"] = out["reg_ratio"] / 100.0
    cash = _usd(reg, "bs_cash")
    if cash is None:
        cash = ii.series("cash")[-1]
    out["cash"] = cash
    cats = {k: _usd(reg, f"bs_{k}") for k in ("short_term", "fixed_maturities", "equity", "illiquid_loans", "real_estate", "other_invested", "total_investments")}
    tot = cats["total_investments"]
    incl_cash = bool(tot is not None and "INCLUDES_CASH" in ((reg.get("bs_total_investments") or {}).get("note") or ""))
    out["bs_categories"] = {**cats, "cash": cash, "total_includes_cash": incl_cash}
    den = None if (tot is None or cash is None) else (tot if incl_cash else tot + cash)
    out["total_investments_and_cash"] = den
    need = ("fixed_maturities", "total_investments")
    if den is None or any(cats[k] is None for k in need) or cash is None:
        out["liquid_assets"], out["liquidity"] = None, None
        out["liquid_parts"] = {"cash": cash, **{k: cats[k] for k in ("short_term", "fixed_maturities", "equity")}}
    else:
        parts = {"cash": cash, "short_term_investments": cats["short_term"] or 0.0, "fixed_maturities": cats["fixed_maturities"], "equity_securities": cats["equity"] or 0.0}
        out["liquid_parts"] = parts
        out["liquid_assets"] = sum(parts.values())
        out["liquidity"] = out["liquid_assets"] / den
        listed = sum(v or 0.0 for k, v in cats.items() if k not in ("total_investments",)) + (0.0 if incl_cash else 0.0)
        resid = tot - sum(v or 0.0 for k, v in cats.items() if k != "total_investments") - (cash if incl_cash else 0.0)
        out["bs_residual"] = resid
        out["bs_residual_share"] = resid / tot if tot else None
        if out["bs_residual_share"] is not None and abs(out["bs_residual_share"]) > 0.01:
            out["flags"].append(f"balance_sheet_categories_residual_{out['bs_residual_share']:.1%}_of_total_investments")
    out["pledged_flag"] = "not assessed (flag only, Q2): pledged / restricted assets are not deducted"
    ig, fi = _usd(reg, "ig_fixed_income"), _usd(reg, "total_fixed_income")
    pct = reg.get("ig_share_pct")
    if ig is not None and fi:
        out["ig_share"] = ig / fi
    elif pct and isinstance(pct["value"], (int, float)):
        out["ig_share"] = pct["value"] / 100.0
    else:
        out["ig_share"] = None
    fm = cats["fixed_maturities"]
    below = None
    if ig is not None and fi:
        below, below_src = max(0.0, fi - ig), "total fixed income - investment-grade fixed income (credit-quality table)"
    elif out["ig_share"] is not None and fm:
        below, below_src = (1 - out["ig_share"]) * fm, "(1 - stated investment-grade share) x fixed maturities"
    else:
        below_src = "omitted: no credit-quality table / investment-grade share extracted"
    cparts = {"equity_securities": cats["equity"] or 0.0, "real_estate": cats["real_estate"] or 0.0,
              "other_invested_assets_limited_partnerships": cats["other_invested"] or 0.0, "below_ig_fixed_maturities": below}
    out["complex_parts"] = cparts
    out["below_ig_source"] = below_src
    if below is None:
        out["flags"].append("complex_assets_exclude_below_investment_grade_fixed_maturities_no_credit_quality_table")
    out["complex_assets"] = None if (den is None or cats["fixed_maturities"] is None or below is None) else sum(cparts.values())  # Q8b: no partial numerator
    out["complex_share"] = None if (out["complex_assets"] is None or not den) else out["complex_assets"] / den
    out["alm_disclosed"] = (reg.get("alm_disclosed") or {}).get("value")
    cat = _usd(reg, "cat_loss_latest")
    prem = ii.series("premiums")[-1]
    out["cat_loss"] = cat
    out["cat_share"] = None if (cat is None or not prem) else cat / prem
    out["cat_flag"] = None if out["cat_share"] is None else out["cat_share"] > CAT_MATERIAL_SHARE
    return out


# ---------------------------------------------------------------- adapter for the kept criteria
class _View:
    """Exposes insurance series under the general model's field names (revenue = operating revenue)."""

    def __init__(self, ii, d):
        self._ii, self._d = ii, d
        self.n, self.fy, self.end = ii.n, ii.fy, ii.end
        self.price_avg, self.price_current = ii.price_avg, ii.price_current
        self.first_annual_report, self.as_of, self.profile = ii.first_annual_report, ii.as_of, PROFILE
        self.ai_answers = getattr(ii, "ai_answers", {})

    def series(self, name):
        if name == "revenue":
            return self._d["operating_revenue"]
        if name == "shares":
            return self._ii.series("shares_dil")
        if name == "dps":
            return self._d["dps"]
        return self._ii.series(name)


class _GateView:
    """P5: growth-eligibility gate for INSURANCE reads insurance revenue (premiums earned + policy fees) and operating EPS; thresholds are the general ones."""

    def __init__(self, ii, d):
        self._ii, self._d = ii, d
        self._eps = operating_eps_series(ii, d)[0]

    def series(self, name):
        if name == "revenue":
            return self._d["insurance_revenue"]
        if name == "eps":
            return self._eps
        return self._ii.series(name)


# ================================================================ BUFFETT QUALITY
def b31(ii, d):
    return B.c31(ii, d)


def b32(ii, d):
    items = [not_applicable("1a", "Gross margin level", 1.0, note="insurance: gross margin not applicable (matrix)"),
             not_applicable("1b", "Gross margin stability", 1.5, note="insurance: gross margin not applicable (matrix)")]
    om = L(d["total_operating_margin"])
    ov = clean(om)
    a2a, a2b = [(0.04, 1.5), (0.12, 0)], [(-0.05, 0), (-0.01, 1.0)]
    if len(ov) < 3:
        items.append(miss("2a", "Total operating margin stability", 1.5, "fewer than 3 years of total operating margin", a2a))
        items.append(miss("2b", "No total operating margin erosion", 1.0, "fewer than 3 years of total operating margin", a2b))
    else:
        items.append(thresholded("2a", "Total operating margin stability", 1.5, max(ov) - min(ov), a2a, "", "total operating margin range (5y)",
                                 {"total_operating_margin": om}))
        if om[-1] is None:
            items.append(miss("2b", "No total operating margin erosion", 1.0, "latest total operating margin missing", a2b))
        else:
            items.append(thresholded("2b", "No total operating margin erosion", 1.0, om[-1] - median(ov), a2b, "",
                                     "latest minus 5y median total operating margin", {"total_operating_margin": om}))
    ro = L(d["operating_roe"])
    cnt, nv, part = count_scaled([None if x is None else x >= 0.10 for x in ro], 5)
    a3 = [(1, 0), (2, 0.5), (3, 1), (4, 1.5), (5, 2)]
    items.append(miss("3", "Persistent operating ROE", 2.0, "fewer than 3 years of operating ROE", a3, inputs={"operating_roe": ro}) if cnt is None else
                 thresholded("3", "Persistent operating ROE", 2.0, cnt, a3, "", "years with operating ROE >= 10% (of 5)", {"operating_roe": ro},
                             ["partial_window"] if part else []))
    items.append(ai_item(ii, "B3.2-Q4", "4", "Stable competitive position", 2.0, note="AI question"))
    items.append(ai_item(ii, "B3.2-Q5", "5", "Clear moat", 1.0, note="AI question x0.5"))
    return items


def b33(ii, d):
    return B.c33(_View(ii, d), d)


def b34(ii, d):
    ro = L(d["operating_roe"])
    v = clean(ro)
    a1, a2 = [(0.05, 0), (0.10, 4), (0.15, 7), (0.20, 10)], [(0.0, 0), (0.08, 5)]
    items = [miss("1", "Operating ROE (5y median)", 10, "fewer than 3 years of operating ROE", a1, inputs={"operating_roe": ro}) if len(v) < 3 else
             thresholded("1", "Operating ROE (5y median)", 10, median(v), a1, "", "5y median operating ROE", {"operating_roe": ro},
                         ["partial_window"] if len(v) < 5 else [])]
    bad = [f for f in tail(d["roe_flags"], 5) if f]
    if bad:  # Q8e: any window year with non-positive average adjusted equity -> worst year = 0 points
        items.append(zero("2", "Worst year", 5, None, a2, "", "lowest operating ROE of the window", {"operating_roe": ro}, ["average_adjusted_equity_nonpositive_Q8e"],
                          "a window year has non-positive average adjusted equity -> 0 points"))
        return items
    items.append(miss("2", "Worst year", 5, "fewer than 3 years of operating ROE", a2, inputs={"operating_roe": ro}) if len(v) < 3 else
                 thresholded("2", "Worst year", 5, min(v), a2, "", "lowest operating ROE of the window", {"operating_roe": ro},
                             ["partial_window"] if len(v) < 5 else []))
    return items


def b35(ii, d):
    items = []
    cr, cost, yl = L(d["cost_ratio"]), L(d["cost_of_float"]), L(d["gov_yield_yr"])
    gap = L(d["cost_gap"])
    flags_c = sorted({f for f in tail(d["cost_flags"], 5) if f})
    ins_c = {"cost_of_float": cost, "government_yield": yl, "cost_gap": gap, "currency": ii.yield_currency, "yield_source": ii.yield_source}
    a1 = [(0.0, 6), (0.5, 3), (1.0, 0)]
    v = clean(cr)
    items.append(miss("1", "Cost of float", 6, "cost of float available for fewer than 3 of the last 5 years (" + (", ".join(flags_c) or "inputs missing") + ")", a1,
                      inputs=ins_c, flags=flags_c) if len(v) < 3 else
                 thresholded("1", "Cost of float", 6, median(v), a1, "", "5y median of cost of float / government yield", ins_c,
                             flags_c + (["partial_window"] if len(v) < 5 else [])))
    a2 = [(1, 0), (2, 0.75), (3, 1.5), (4, 2.25), (5, 3)]
    below = [None if (c is None or y is None) else c < y for c, y in zip(cost, yl)]
    cnt, nv, part = count_scaled(below, 5)
    items.append(miss("2", "Cost-of-float consistency", 3, "cost of float available for fewer than 3 of the last 5 years", a2, inputs=ins_c, flags=flags_c) if cnt is None else
                 thresholded("2", "Cost-of-float consistency", 3, cnt, a2, "", "years with cost of float below the government yield (of 5)", ins_c,
                             flags_c + (["partial_window"] if part else [])))
    a3 = [(0.0, 0), (0.05, 2), (0.10, 4)]
    tm = L(d["total_operating_margin"])
    v = clean(tm)
    items.append(miss("3", "Total operating margin", 4, "fewer than 3 years of total operating margin", a3, inputs={"total_operating_margin": tm}) if len(v) < 3 else
                 thresholded("3", "Total operating margin", 4, median(v), a3, "", "5y median total operating margin", {"total_operating_margin": tm},
                             ["partial_window"] if len(v) < 5 else []))
    # 4 growing cheap float: cumulative cost below cumulative yield AND >= 3 of 5 years below the yield
    a4 = [(0.0, 0), (0.05, 2)]
    pairs = [(c, y) for c, y in zip(cost, yl) if c is not None and y is not None]
    drr_missing = all(x is None for x in tail(ii.series("aoci_drr"), 5))
    flags4 = (["float_includes_discount_rate_remeasurement_not_reported"] if drr_missing else []) + flags_c
    if len(pairs) < 3 or ii.n < 5:
        items.append(miss("4", "Growing cheap float", 2, "cost of float available for fewer than 3 of the last 5 years", a4, inputs=ins_c, flags=flags4))
    else:
        sc, sy = sum(c for c, _ in pairs), sum(y for _, y in pairs)
        nb = sum(1 for c, y in pairs if c < y)
        cond = sc < sy and nb >= 3
        ins = {**ins_c, "cumulative_cost": sc, "cumulative_yield": sy, "years_below_yield": nb, "years_known": len(pairs), "cheap_float_condition": cond}
        if not cond:
            items.append(zero("4", "Growing cheap float", 2, None, a4, "", "float CAGR (condition failed)", ins, ["cheap_float_condition_failed"] + flags4,
                              "cumulative cost of float >= cumulative government yield or fewer than 3 of 5 years below the yield -> 0"))
        else:
            fc = d["float_cagr"]
            tr = [{"fy": r["fy"], "growth": r["growth"], "valid": r["valid"], "reason": r["reason"]} for r in fc["transitions"]]
            fl4 = flags4 + (["fx_effects_not_removed_foreign_pretax_%.0f%%" % (100 * fc["foreign_pretax_share"])] if fc["fx_flag"] else []) + \
                [f"excluded_{r['fy']}" for r in fc["transitions"] if not r["valid"] and r["growth"] is not None]
            if fc["cagr"] is None:
                items.append(miss("4", "Growing cheap float", 2, f"fewer than 2 valid float transitions ({fc['n_valid']} of {len(fc['transitions'])}); see the reasons", a4,
                                  inputs={**ins, "transitions": tr}, flags=fl4))
            else:
                items.append(thresholded("4", "Growing cheap float", 2, fc["cagr"], a4, "", f"float CAGR over {fc['n_valid']} valid transitions (ex discount-rate remeasurement)",
                                         {**ins, "transitions": tr}, fl4 + d["float_flags"][-1]))
    return items


def _reg_multiple_item(id_, name, mx, a, lt):
    if lt["reg_multiple"] is None:
        reason = ("regulatory capital ratio not found in the filing (AI extraction found no numeric group ratio)" if lt["reg_ratio"] is None
                  else "regulatory basis not usable for a multiple")
        return miss(id_, name, mx, reason, a, flags=["exceeds_requirements_without_a_number_is_missing"] if lt["reg_ratio"] is None else [])
    return thresholded(id_, name, mx, lt["reg_multiple"], a, "x", "reported ratio / first intervention level",
                       {"ratio": lt["reg_ratio"], "basis": lt["reg_basis"], "period": lt["reg_period"], "note": lt["reg_note"]}, lt["reg_flags"])


def _reserve_item(id_, name, mx, d, ii, graham=False):
    dev = L(d["reserve_deviation"])
    v = clean(dev)
    a = [(0.0, 9), (0.01, 6.75), (0.02, 4.5), (0.03, 2.25), (0.04, 0)] if graham else [(0.0, 4), (0.04, 0)]
    flags = sorted({x for x in tail(d["reserve_flags"], 5) if x})
    if len(v) < 3:
        return miss(id_, name, mx, "reserve deviation available for fewer than 3 of the last 5 years (inputs missing: " +
                    (", ".join(flags) or "prior-year development not tagged / not extracted") + ")", a, inputs={"reserve_deviation": dev}, flags=flags)
    med = median(v)
    pts_flags = ["partial_window"] if len(v) < 5 else []
    if not graham:
        return thresholded(id_, name, mx, med, a, "", "5y median reserve deviation", {"reserve_deviation": dev}, pts_flags + flags)
    base = interpolate(med, a)
    n_over = sum(1 for x in v if x > 0.01)
    pen = 0.0 if n_over < 2 else (0.5 if n_over == 2 else (1.0 if n_over == 3 else 2.0))
    return scored(id_, name, mx, max(0.0, base - pen), metric=med, metric_label="5y median reserve deviation", thresholds=describe(a),
                  inputs={"reserve_deviation": dev, "years_over_1pct": n_over, "penalty": pen}, flags=pts_flags + flags,
                  note=f"base {base:.2f} - consistency penalty {pen}")


def b36(ii, d):
    lt = d["latest"]
    items = [_reg_multiple_item("1", "Regulatory capital", 4, [(1.0, 0), (1.5, 2), (2.0, 4)], lt),
             _reserve_item("2", "Reserve development", 4, d, ii)]
    a3 = [(0.20, 2), (0.40, 0)]
    lv = d["financial_leverage"][-1]
    items.append(miss("3", "Financial leverage", 2, "financial debt or adjusted equity missing", a3) if lv is None else
                 thresholded("3", "Financial leverage", 2, lv, a3, "", "financial debt / (debt + adjusted equity)",
                             {"financial_debt": d["financial_debt"][-1], "adjusted_equity": d["adjusted_equity"][-1]},
                             ["debt_from_extraction"] if d["debt_override"] is not None else []))
    return items


def b37(ii, d):
    return BK.b37(ii, d)


def b38(ii, d):
    items = []
    rev = L(d["operating_revenue"])
    a1 = [(1, 0), (2, 1), (3, 2), (4, 3)]
    cnt, nv, part = count_scaled([rose(a, b) for a, b in zip(rev[:-1], rev[1:])], 4)
    items.append(miss("1", "Consistency of revenue growth", 3, "fewer than 3 transitions", a1) if cnt is None else
                 thresholded("1", "Consistency of revenue growth", 3, cnt, a1, "", "operating revenue rises (of 4)", {"operating_revenue": rev},
                             ["partial_window"] if part else []))
    items.append(growth_item("2", "EPS growth", 3, smoothed_growth(L(ii.series("eps"))), [(0, 0), (0.10, 3)], "smoothed EPS growth"))
    tb = L(d["tbvps_adj"])  # adjusted book value per share growth, smoothed (R14); adjusted equity per share incl. intangibles per spec 3.8.3
    bv = L([None if (a is None or s is None or not s) else a / s for a, s in zip(d["adjusted_equity"], ii.series("shares_out"))])
    items.append(growth_item("3", "Adjusted book value per share growth", 3, smoothed_growth(bv), [(0, 0), (0.10, 3)], "smoothed adjusted BVPS growth"))
    items.append(not_applicable("4", "Growth without excessive debt", 2, note="leverage is measured in Buffett 3.6 (matrix)"))
    a5 = [(0.01, 2), (0.05, 0)]
    nm = L(d["net_margin"])
    if any(x is None for x in (nm[0], nm[1], nm[3], nm[4])):
        items.append(miss("5", "Margins maintained", 2, "net margin missing in first/last two years", a5))
    else:
        items.append(thresholded("5", "Margins maintained", 2, (nm[0] + nm[1]) / 2 - (nm[3] + nm[4]) / 2, a5, "", "decline in net margin, avg first 2 -> last 2",
                                 {"net_margin": nm}))
    items.append(ai_item(ii, "B3.8-Q6", "6", "Growth is sustainable", 2, note="AI question"))
    return items


B_CRITERIA = [
    ("3.1", "Simple, understandable business", b31), ("3.2", "Moat", b32), ("3.3", "Consistent profitability", b33),
    ("3.4", "Return on capital", b34), ("3.5", "Earning power and cost of float", b35),
    ("3.6", "Capital, reserves and leverage", b36), ("3.7", "Management and capital allocation", b37),
    ("3.8", "Quality, sustainable growth", b38),
]


def insurance_buffett_quality(ii, d) -> ModelResult:
    return evaluate_model("buffett_quality_insurance", [evaluate_criterion(i, n, fn(ii, d)) for i, n, fn in B_CRITERIA])


# ================================================================ GRAHAM QUALITY
def g31(ii, d):
    return G.c31(_View(ii, d), d)


def g32(ii, d):
    lt = d["latest"]
    items = [_reg_multiple_item("1", "Regulatory capital", 10, [(1.0, 0), (1.5, 5), (2.0, 10)], lt)]
    a2 = [(0.40, 0), (0.60, 3), (0.80, 5)]
    fl = ["alm_risk_flag_only_in_v1:" + str(lt["alm_disclosed"])]
    fl += lt["flags"]
    if lt["liquidity"] is None:
        items.append(miss("2", "Portfolio liquidity", 5, "balance-sheet categories (fixed maturities, total investments, cash) not extracted", a2,
                          inputs=lt["bs_categories"], flags=fl))
    else:
        items.append(thresholded("2", "Portfolio liquidity", 5, lt["liquidity"], a2, "", "liquid assets / (total investments + cash)",
                                 {**lt["liquid_parts"], "total_investments_and_cash": lt["total_investments_and_cash"], "pledged": lt["pledged_flag"]}, fl))
    return items


def g33(ii, d):
    items = [_reserve_item("1", "Reserve development", 9, d, ii, graham=True)]
    a2 = [(0.20, 6), (0.30, 4.5), (0.40, 3), (0.50, 1.5), (0.60, 0)]
    lv = d["financial_leverage"][-1]
    items.append(miss("2", "Financial leverage", 6, "financial debt or adjusted equity missing", a2) if lv is None else
                 thresholded("2", "Financial leverage", 6, lv, a2, "", "financial debt / (debt + adjusted equity)",
                             {"financial_debt": d["financial_debt"][-1], "adjusted_equity": d["adjusted_equity"][-1]},
                             ["debt_from_extraction"] if d["debt_override"] is not None else []))
    return items


def g34(ii, d):
    return G.c34(_View(ii, d), d)


def g35(ii, d):
    items = BK._g35(_View(ii, d), d)
    for it in items:
        if it.id == "4" and it.state == "not_applicable":
            it.note = "insurance: cash-flow coverage not applicable (matrix)"
    return items


def g36(ii, d):
    return G.c36(_View(ii, d), d)


def g37(ii, d):
    lt = d["latest"]
    items = []
    a1 = [(-0.05, 0), (0.0, 2), (0.05, 4)]
    tb = d["tbvps_adj"]
    first, last = (tb[-5] if ii.n >= 5 else None), tb[-1]
    ins = {"tbvps_adj_t_minus_4": first, "tbvps_adj_latest": last}
    if first is None or last is None:
        items.append(miss("1", "Adjusted TBVPS preservation", 4, "adjusted TBVPS missing for t or t-4", a1, inputs=ins))
    elif last <= 0:
        items.append(zero("1", "Adjusted TBVPS preservation", 4, None, a1, "", "adjusted TBVPS CAGR", ins, ["tbvps_adj_nonpositive_latest"]))
    elif first <= 0:
        items.append(scored("1", "Adjusted TBVPS preservation", 4, 2.0, metric=None, metric_label="adjusted TBVPS CAGR", thresholds=describe(a1), inputs=ins,
                            flags=["negative_start_positive_end_D5"], note="negative start and positive end = 2"))
    else:
        items.append(thresholded("1", "Adjusted TBVPS preservation", 4, (last / first) ** 0.25 - 1, a1, "", "adjusted TBVPS CAGR (t-4 to t)", ins))
    a2 = [(0.75, 0), (0.95, 3)]
    items.append(miss("2", "Fixed-income credit quality", 3, "investment-grade / total fixed income not extracted", a2) if lt["ig_share"] is None else
                 thresholded("2", "Fixed-income credit quality", 3, lt["ig_share"], a2, "", "investment-grade fixed income / total fixed income",
                             {"ig": _usd(ii.reg, "ig_fixed_income"), "total": _usd(ii.reg, "total_fixed_income"),
                                  "ig_share_pct": (ii.reg.get("ig_share_pct") or {}).get("value")}))
    a3 = [(0.05, 3), (0.25, 0)]
    fl3 = [f for f in lt["flags"] if "complex" in f or "residual" in f]
    if lt["complex_share"] is None:
        items.append(miss("3", "Complex / volatile assets", 3, "balance-sheet categories or the credit-quality table not extracted (Q8b: no partial numerator)", a3,
                          inputs=lt["bs_categories"], flags=fl3))
    else:
        items.append(thresholded("3", "Complex / volatile assets", 3, lt["complex_share"], a3, "", "complex assets / (total investments + cash)",
                                 {**lt["complex_parts"], "below_ig_source": lt["below_ig_source"], "total_investments_and_cash": lt["total_investments_and_cash"]}, fl3))
    return items


def g38(ii, d):
    items = []
    a1 = [(0.10, 5), (0.40, 0)]
    gains, rate, ni = d["non_recurring_gains"], d["tax_rate"], ii.series("net_income")
    rows = [(max(0.0, x * (1 - r)), n_) for x, r, n_ in zip(tail(gains, 5), tail(rate, 5), tail(ni, 5)) if x is not None and n_ is not None]
    if len(rows) < 3:
        items.append(miss("1", "Reliance on non-recurring investment gains", 5, "gains or net income missing in more than 2 of the last 5 years", a1))
    else:
        sg, sn = sum(r[0] for r in rows), sum(r[1] for r in rows)
        if sn <= 0:
            items.append(zero("1", "Reliance on non-recurring investment gains", 5, None, a1, "", "sum max(0, after-tax gains) / sum net income",
                              {"sum_gains_after_tax": sg, "sum_net_income": sn}, ["total_net_income_nonpositive"], "sum of net income <= 0 -> 0"))
        else:
            items.append(thresholded("1", "Reliance on non-recurring investment gains", 5, sg / sn, a1, "", "sum max(0, after-tax gains) / sum net income (5y)",
                                     {"sum_gains_after_tax": sg, "sum_net_income": sn}, ["partial_window"] if len(rows) < 5 else []))
    a2 = [(0, 0), (1, 0.75), (2, 1.5), (3, 2.25), (4, 3)]
    tm = L(d["total_operating_margin"])
    fl = [None if (a is None or b is None) else (b - a) >= -0.02 for a, b in zip(tm[:-1], tm[1:])]
    cnt, nv, part = count_scaled(fl, 4)
    items.append(miss("2", "Operating margin stability", 3, "fewer than 3 transitions", a2, inputs={"total_operating_margin": tm}) if cnt is None else
                 thresholded("2", "Operating margin stability", 3, cnt, a2, "", "transitions (of 4) with total operating margin falling by no more than 2pp",
                             {"total_operating_margin": tm}, ["partial_window"] if part else []))
    items.append(BK._dil_item("3", "Dilution", 2, ii))
    return items


G_CRITERIA = [
    ("3.1", "Company size and business stability", g31), ("3.2", "Capital and liquidity", g32), ("3.3", "Reserves and leverage", g33),
    ("3.4", "Earnings stability", g34), ("3.5", "Dividend history", g35), ("3.6", "Moderate earnings growth", g36),
    ("3.7", "Quality of equity and assets", g37), ("3.8", "Earnings quality and dilution", g38),
]


def insurance_graham_quality(ii, d) -> ModelResult:
    return evaluate_model("graham_quality_insurance", [evaluate_criterion(i, n, fn(ii, d)) for i, n, fn in G_CRITERIA])


# ================================================================ PRICING (spec 2026-10-13_12-40, P1-P4)
ROE_CAP = BK.ROTCE_CAP
R_DISC, G_TERM = BK.R_DISC, BK.G_TERM


def insurance_buffett_price(ii, d, quality: ModelResult) -> dict:
    """P1-P2: two-stage excess returns on adjusted equity (BANK V1-V3, V6-V8 engine; base = adjusted equity, ROE = operating ROE)."""
    out = {"model": "buffett_price_insurance", "method": "two_stage_excess_returns_on_adjusted_equity", "flags": []}
    ro = clean(L(d["operating_roe"]))
    e0 = d["adjusted_equity"][-1]
    shares = ii.series("shares_out")[-1]
    out.update({"e0": e0, "shares": shares, "price_current": ii.price_current})
    na = {"state": "not_applicable", "points": None}
    if len(ro) < 3 or e0 is None or shares is None:
        return {**out, "state": "cannot_be_valued", "reason": "operating ROE (3y+), adjusted equity or period-end shares missing", "fair_value": None, "price_score": na, "buy_price": None}
    if e0 <= 0:
        return {**out, "state": "cannot_be_valued", "reason": "adjusted equity <= 0", "fair_value": None, "price_score": na, "buy_price": None}
    med = median(ro)
    norm = min(med, ROE_CAP)
    if med > ROE_CAP:
        out["flags"].append(f"roe_capped_at_20pct (median {med:.1%})")
    out.update({"roe_median": med, "roe_norm": norm, "roe_years": len(ro)})
    if norm <= G_TERM:  # V6
        return {**out, "state": "cannot_be_valued", "reason": f"ROE_norm {norm:.1%} <= 2.5% (V6)", "fair_value": None, "price_score": na, "buy_price": None,
                "flags": out["flags"] + ["V6_roe_norm_at_or_below_2.5pct"]}
    payout = BK.payout_ratio(ii)
    if payout is None:
        return {**out, "state": "cannot_be_valued", "reason": "payout ratio not computable (fewer than 3 paired years)", "fair_value": None, "price_score": na, "buy_price": None}
    gate = B.growth_gate(_GateView(ii, d))
    gate_before = B.growth_gate(_View(ii, d))  # round-3 basis (total operating revenue, reported EPS), kept for the before / after comparison
    out["growth_gate_before_P5"] = gate_before
    g1 = BK._g1(norm, payout, gate["passed"])
    if not gate["passed"]:
        out["flags"].append("growth_gate_failed (" + "; ".join(gate["failing"]) + ")")
    base = BK.two_stage_value(e0, norm, g1)
    per_share = base["total"] / shares
    adj_bvps = e0 / shares
    out.update({"payout": payout, "g1": g1, "growth_gate": gate, "state": "valued", "total_value": base["total"], "fair_value": per_share,
                "adjusted_bvps": adj_bvps, "value_to_adjusted_book": base["total"] / e0, "pv_residual_income": base["pv_ri"],
                "pv_terminal_value": base["pv_terminal_value"], "e10": base["tce10"], "schedule": base["years"]})
    out["justified_pb_single_stage"] = (norm - G_TERM) / (R_DISC - G_TERM)  # sanity check (display): single-stage justified P/B
    sens = {"base": per_share}
    if norm > R_DISC:  # V7
        sens["erosion"] = BK.two_stage_value(e0, norm, g1, erosion=True)["total"] / shares
    else:
        sens["erosion"] = per_share
        out["flags"].append("V7_erosion_equals_base_roe_norm_at_or_below_10pct")
    for sign, key in ((1, "roe_plus_1pp"), (-1, "roe_minus_1pp")):
        rr = norm + sign * 0.01
        if rr <= G_TERM:
            sens[key] = None
            continue
        v = BK.two_stage_value(e0, rr, BK._g1(rr, payout, gate["passed"]))["total"] / shares
        sens[key] = v if v > 0 else None
    out["sensitivity"] = sens
    vals = [v for v in sens.values() if v is not None]
    out["sensitivity_range"] = (min(vals), max(vals))
    if per_share <= 0:  # Rulebook C15 / P2, CL14 (H-07): value <= 0 -> price score 0, no buy price
        return {**out, "state": "cannot_be_valued", "reason": "model value <= 0 (V6)", "fair_value": None, "sensitivity": None, "sensitivity_range": None,
                "price_score": {"state": "score", "points": 0.0, "reason": "C15: value <= 0 -> price score 0"}, "buy_price": None,
                "flags": out["flags"] + ["C15_value_nonpositive_cannot_be_valued"]}
    price = ii.price_current
    if price is None:
        out["price_score"] = {"state": "missing", "points": None, "reason": "no current price"}
    else:
        disc = (per_share - price) / per_share
        out["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, B.PRICE_ANCHORS), "anchors": describe(B.PRICE_ANCHORS)}
        out["price_to_adjusted_book"] = price / adj_bvps if adj_bvps else None
        f_r = lambda r_: BK.two_stage_value(e0, norm, g1, r=r_)["total"] / shares - price  # noqa: E731
        ir = BK._solve(f_r, G_TERM + 1e-4, 0.40, decreasing=True)
        out["implied_return"] = BK.BELOW_2_5 if (ir == BK.NO_SOLUTION and f_r(G_TERM + 1e-4) < 0) else ir
        out["implied_roe"] = BK._solve(lambda x: BK.two_stage_value(e0, x, BK._g1(x, payout, gate["passed"]))["total"] / shares - price, -0.20, 0.40, decreasing=False)
    out["buy_price"] = B._buy_price(per_share, quality, B.MARGIN_ANCHORS)
    ratio = out["value_to_adjusted_book"]
    if ratio > 3.0:
        out["flags"].append(f"sanity_value_above_3x_adjusted_book ({ratio:.2f}x)")
    elif ratio < 0.5:
        out["flags"].append(f"sanity_value_below_0.5x_adjusted_book ({ratio:.2f}x)")
    return out


def operating_eps_series(ii, d) -> tuple:
    """Operating EPS per year = normalized operating profit after tax / diluted shares (non-recurring investment gains excluded).
    Share-count scale errors are handled at the source (ETL `guard_share_scale`), not here. Returns (series, flags); flags is kept empty."""
    return [None if (a is None or not s_) else a / s_ for a, s_ in zip(d["nop_after_tax"], ii.series("shares_dil"))], []


def insurance_graham_price(ii, d, quality: ModelResult) -> dict:
    """P3-P4: Graham Number = sqrt(22.5 x 10-year average operating EPS x adjusted TBVPS); loss years stay in the average; reported-EPS version for display."""
    out = {"model": "graham_price_insurance", "method": "graham_number_operating_eps_adjusted_tbvps", "flags": []}
    series, eps_flags = operating_eps_series(ii, d)
    series = tail(series, 10)
    out["flags"] += [f for f in eps_flags if f[:6] in {x for x in tail(ii.fy, 10)}]
    fys = tail(ii.fy, 10)
    vals = [(fy, v) for fy, v in zip(fys, series) if v is not None]
    tb = d["tbvps_adj"][-1]
    out.update({"operating_eps_series": dict(zip(fys, series)), "years_available": len(vals), "tbvps_adj": tb, "price_current": ii.price_current,
                "loss_years": [fy for fy, v in vals if v < 0]})
    rep_eps = clean(tail(ii.series("eps"), 10))
    out["reported_eps_comparison"] = None
    if len(rep_eps) >= 7 and tb is not None and tb > 0 and sum(rep_eps) > 0:
        out["reported_eps_comparison"] = {"average_eps": sum(rep_eps) / len(rep_eps), "years": len(rep_eps),
                                          "graham_number": math.sqrt(22.5 * (sum(rep_eps) / len(rep_eps)) * tb)}
    na = {"state": "not_applicable", "points": None}
    if len(vals) < 7:
        return {**out, "state": "cannot_be_valued", "reason": f"only {len(vals)} years of operating EPS (need 7+)", "value": None, "price_score": na, "buy_price": None}
    if len(vals) < 10:
        out["flags"].append(f"operating_eps_average_of_{len(vals)}_available_years")
    ne = sum(v for _, v in vals) / len(vals)
    out["normalized_eps"] = ne
    if ne <= 0 or tb is None or tb <= 0:
        return {**out, "state": "cannot_be_valued", "reason": "10-year average operating EPS <= 0 or adjusted TBVPS <= 0", "value": None, "price_score": na, "buy_price": None}
    val = math.sqrt(22.5 * ne * tb)
    out.update({"state": "valued", "value": val})
    if out["loss_years"]:
        out["flags"].append("loss_years_included_in_the_average: " + ", ".join(out["loss_years"]))
    if ii.price_current is None:
        out["price_score"] = {"state": "missing", "points": None}
    else:
        disc = (val - ii.price_current) / val
        out["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, G.CLASSIC_PRICE), "anchors": describe(G.CLASSIC_PRICE)}
        if quality.score is None or quality.score < 55:  # Rulebook A.5 / X1 / P3 (H-01): shown, labelled; buy price "not suitable" (_buy_price)
            out["price_score"]["label"] = ("Graham quality below 55" if quality.score is not None else "no Graham quality score")
            out["flags"].append("X1_price_score_shown_graham_quality_below_55")
    out["buy_price"] = B._buy_price(val, quality, G.CLASSIC_MARGIN)
    return out


def score_insurance_priced(ii: InsuranceInputs) -> dict:
    base = score_insurance(ii)
    d = base["derived"]
    base["buffett_price"] = insurance_buffett_price(ii, d, base["buffett_quality"])
    base["graham_price"] = insurance_graham_price(ii, d, base["graham_quality"])
    from .c16 import apply_c16
    return apply_c16(base, getattr(ii, "price_entity_issue", None))


def score_insurance(ii: InsuranceInputs) -> dict:
    d = derive_insurance(ii)
    return {"state": "scored", "derived": d, "buffett_quality": insurance_buffett_quality(ii, d), "graham_quality": insurance_graham_quality(ii, d)}

"""BANK profile scoring (docs/scoring/ValueCompass_Bank_Rules_2026-10-12_13-10_EN.md), pure functions.

Replaced criteria (Buffett 3.4/3.5/3.6, Graham 3.2/3.3/3.7/3.8), matrix adjustments for the kept criteria, and bank
pricing (justified P/TBV and Graham Number on tangible book). Missing-data policy M1-M9 comes from ``coverage``.
"""
from __future__ import annotations

import math
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from . import buffett as B
from . import graham as G
from .common import L, growth_item, miss, tail, thresholded, zero
from .coverage import (ModelResult, ai_pending, evaluate_criterion, evaluate_model, not_applicable, scored)
from .interpolate import describe, interpolate
from .metrics import clean, count_scaled, fell_more_than, median, mean, rose, safe_div, smoothed_growth, INF

CATEGORIES = ("residential_mortgage", "commercial_real_estate", "commercial_industrial", "consumer", "other")
R_, CRE, CI, CONS, OTH = CATEGORIES

# mapping of each extracted loan line (bank's own classification) to the 5 uniform categories (D3/B4)
LOAN_MAP = {
    "JPM": {"Residential real estate": R_, "Auto and other": CONS, "Credit card": CONS,
            "Wholesale - secured by real estate": CRE, "Wholesale - commercial and industrial": CI, "Wholesale - other": OTH},
    "BAC": {"Residential mortgage": R_, "Home equity": R_, "Credit card": CONS, "Direct/Indirect consumer": CONS,
            "Other consumer": CONS, "U.S. commercial": CI, "Non-U.S. commercial": CI, "Commercial real estate": CRE,
            "Commercial lease financing": CI, "U.S. small business commercial": CI},
    "C": {"Wealth - mortgages": R_, "Wealth - margin lending": CONS, "Wealth - personal, small business and other": CONS,
          "Wealth - cards": CONS, "USPB - Branded Cards": CONS, "USPB - Retail Services": CONS,
          "USPB - Retail Banking mortgages": R_, "USPB - Retail Banking personal, small business and other": CONS,
          "Mexico Consumer": CONS, "Asia Consumer": CONS, "Legacy Holdings Assets (consumer)": CONS,
          "Corporate N.A. - commercial and industrial": CI, "Corporate N.A. - financial institutions": OTH,
          "Corporate N.A. - mortgage and real estate": CRE, "Corporate N.A. - installment and other": OTH,
          "Corporate N.A. - lease financing": CI, "Corporate intl - commercial and industrial": CI,
          "Corporate intl - financial institutions": OTH, "Corporate intl - mortgage and real estate": CRE,
          "Corporate intl - installment and other": OTH, "Corporate intl - lease financing": CI,
          "Corporate - governments and official institutions": OTH},
    "WFC": {"Commercial and industrial": CI, "Commercial real estate": CRE, "Lease financing": CI,
            "Residential mortgage": R_, "Credit card": CONS, "Auto": CONS, "Other consumer": CONS},
    "USB": {"Commercial": CI, "Lease financing": CI, "Total commercial real estate": CRE,
            "Total residential mortgages": R_, "Credit Card": CONS, "Total other retail": CONS},
    "PNC": {"Commercial and industrial": CI, "Commercial real estate": CRE, "Equipment lease financing": CI,
            "Residential real estate": R_, "Home equity": R_, "Automobile": CONS, "Credit card": CONS,
            "Education": CONS, "Other consumer": CONS},
    "TFC": {"Commercial and industrial": CI, "CRE": CRE, "Commercial construction": CRE, "Residential mortgage": R_,
            "Home equity": R_, "Indirect auto": CONS, "Other consumer": CONS, "Credit card": CONS},
    "MTB": {"Commercial and industrial": CI, "Real estate - commercial": CRE, "Real estate - residential": R_,
            "Home equity lines and loans": R_, "Recreational finance": CONS, "Automobile": CONS,
            "Other secured": CONS, "Other unsecured": CONS},
    "FITB": {"Commercial and industrial loans": CI, "Commercial mortgage loans": CRE, "Commercial construction loans": CRE,
             "Commercial leases": CI, "Residential mortgage loans": R_, "Home equity": R_,
             "Indirect secured consumer loans": CONS, "Credit card": CONS, "Solar energy installation loans": CONS,
             "Other consumer loans": CONS},
    "KEY": {"Commercial and industrial": CI, "Commercial mortgage": CRE, "Real estate - construction": CRE,
            "Commercial lease financing": CI, "Real estate - residential mortgage": R_, "Home equity loans": R_,
            "Other consumer loans": CONS, "Credit Cards": CONS},
    "FLG": {"Multi-family": CRE, "Commercial real estate": CRE, "One-to-four family first mortgage": R_,
            "Commercial and industrial": CI, "Other loans": OTH},
    "GS": {"Corporate": CI, "Commercial real estate": CRE, "Residential real estate": R_, "Securities-based": OTH,
           "Other collateralized": OTH, "Credit cards": CONS, "Other": OTH},
}

# ---------------------------------------------------------------- profile path
log = logging.getLogger(__name__)
from .router import bank_path, bank_sic_set, default_tables  # noqa: E402,F401  (rows 1a / 1b live in the profile router, H-09)

BANK_SIC = tuple(sorted(str(x) for x in bank_sic_set(default_tables())))


# ---------------------------------------------------------------- inputs
@dataclass
class BankInputs:
    ticker: str
    name: str
    path: str  # "1" or "1b"
    fy: list
    end: list
    f: dict
    reg: dict  # extracted FY2025 items (scripts/bank_regulatory.csv)
    required_cet1: float  # percentage points
    price_current: Optional[float] = None
    price_entity_issue: Optional[str] = None  # C16
    price_avg: list = field(default_factory=list)
    first_annual_report: Optional[date] = None
    as_of: Optional[date] = None
    flags: list = field(default_factory=list)
    data_problems: list = field(default_factory=list)
    tag_log: dict = field(default_factory=dict)
    profile: str = "BANK"

    @property
    def n(self) -> int:
        return len(self.fy)

    def series(self, name: str) -> list:
        return self.f.get(name) or [None] * self.n


# ---------------------------------------------------------------- latest-year resolution (XBRL + extraction)
# Production thresholds (section 6c, K1: all four parallel-run candidates were rejected on 2026-10-13).
TH = {
    "graham_buffer": [(0.0, 0), (3.0, 8)],
    "nonaccrual_buffett": [(0.005, 1), (0.03, 0)],
    "nonaccrual_graham": [(0.005, 3), (0.03, 0)],
    "acl_buffett": [(0.75, 0), (1.50, 1)],
    "acl_graham": [(0.75, 0), (2.0, 4)],
    "deposit_funding": [(0.50, 0), (0.80, 2)],
}


def _num(reg, item):
    """Extracted value; USD-million rows are returned in USD (XBRL units), percent rows unchanged."""
    r = reg.get(item)
    if not r or not isinstance(r["value"], (int, float)):
        return None
    return r["value"] * 1e6 if r["unit"] == "USD mm" else r["value"]


def resolve_latest(bi: BankInputs) -> dict:
    """Combine regulatory ratios, credit quality, funding and loan categories for the latest year."""
    reg = bi.reg
    out: dict = {"flags": []}
    # --- D10: capital buffer = min over approaches of (CET1 ratio - the requirement reported for the same approach)
    ratios = {"standardized": _num(reg, "cet1_ratio_standardized"), "advanced": _num(reg, "cet1_ratio_advanced")}
    reqs = {a: _num(reg, f"cet1_required_{a}") for a in ratios}
    # V9: banks that report only the SCB: required CET1 = 4.5% + SCB + G-SIB surcharge (if any) + CCyB (0% in the US).
    # A requirement stated in the filing wins on mismatch (and the mismatch is logged).
    scb = _num(reg, "scb")
    v9 = {"scb": scb, "gsib_surcharge": _num(reg, "gsib_surcharge") or 0.0, "ccyb": 0.0, "computed": None,
          "stated": reqs["standardized"], "used": None, "match": None}
    if scb is not None:
        v9["computed"] = 4.5 + scb + v9["gsib_surcharge"] + v9["ccyb"]
        if reqs["standardized"] is None:
            reqs["standardized"] = v9["computed"]
            out["flags"].append("requirement_computed_V9_4.5_plus_SCB")
        else:
            v9["match"] = abs(reqs["standardized"] - v9["computed"]) < 0.05
            if not v9["match"]:
                out["flags"].append("V9_mismatch_stated_requirement_used")
                log.warning("%s: V9 computed CET1 requirement %.2f != stated %.2f; stated used", bi.ticker, v9["computed"],
                            reqs["standardized"])
    v9["used"] = reqs["standardized"]
    out["v9"] = v9
    buffers = {}
    for a, v in ratios.items():
        if v is None:
            continue
        if reqs[a] is None:
            out["flags"].append(f"requirement_missing_{a}_approach_excluded")
            continue
        buffers[a] = v - reqs[a]
    out.update({"cet1_std": ratios["standardized"], "cet1_adv": ratios["advanced"], "required_std": reqs["standardized"],
                "required_adv": reqs["advanced"], "buffer_by_approach": buffers})
    if buffers:
        approach = min(buffers, key=buffers.get)
        out.update({"approach": approach, "capital_buffer": buffers[approach], "cet1_ratio": ratios[approach],
                    "required_cet1": reqs[approach]})
    else:
        out.update({"approach": None, "capital_buffer": None, "cet1_ratio": None, "required_cet1": None, "rwa": None,
                    "total_capital": None})
    # first-round comparison: lower ratio vs the single supplied requirement
    avail = {a: v for a, v in ratios.items() if v is not None}
    out["buffer_round1"] = None if not avail else min(avail.values()) - bi.required_cet1
    if approach_key := out["approach"]:
        out["rwa"] = _num(reg, f"rwa_{approach_key}")
        out["total_capital"] = _num(reg, f"total_capital_{approach_key}")
        if out["total_capital"] is None and _num(reg, "total_capital_ratio") and out["rwa"]:
            out["total_capital"] = _num(reg, "total_capital_ratio") / 100 * out["rwa"]
            out["flags"].append("total_capital_derived_from_ratio")
    # --- D12: LCR. number | "NA" (exempt, evidenced in the 10-K) | "MISSING" (subject or unknown, no numeric value found)
    lcr = reg.get("lcr_q4_average")
    out["lcr"] = "MISSING" if lcr is None else lcr["value"]
    out["lcr_source"] = None if lcr is None else lcr["section"]
    out["lcr_note"] = None if lcr is None else lcr["note"]
    # V10: measurement type and date (Q4 average preferred; quarter-end accepted with a flag)
    if lcr is None or lcr["value"] in ("NA", "MISSING"):
        out["lcr_measure"] = None
    else:
        out["lcr_measure"] = "quarter_end" if "QUARTER-END" in str(lcr["note"]) else "q4_average"
    out["lcr_date"] = str(bi.end[-1]) if getattr(bi, "end", None) else None
    # --- loans and categories
    loans = bi.series("loans")
    loans_latest = loans[-1] if loans and loans[-1] is not None else _num(reg, "loans_2025")
    cat_amt = {c: 0.0 for c in CATEGORIES}
    mapped = 0.0
    lmap = LOAN_MAP.get(bi.ticker, {})
    unmapped = []
    for item, row in reg.items():
        if item.startswith("loan:"):
            label = item[5:]
            cat = lmap.get(label)
            if cat is None:
                unmapped.append(label)
                continue
            cat_amt[cat] += row["value"] * 1e6
            mapped += row["value"] * 1e6
    out["loan_categories"] = cat_amt
    out["loans_mapped_total"] = mapped
    out["unmapped_loan_lines"] = unmapped
    if not loans_latest and mapped:
        loans_latest = mapped
        out["flags"].append("loans_total_from_category_sum")
    out["loans_latest"] = loans_latest
    out["loans_mapped_share"] = safe_div(mapped, loans_latest) if mapped else None
    # --- D11: nonaccrual loans only; 90+ days past due and still accruing is kept for display
    na = _num(reg, "nonaccrual_loans")
    out["nonaccrual_source"] = "extraction"
    if na is None:
        na = bi.series("nonaccrual")[-1]
        out["nonaccrual_source"] = "xbrl"
    pd90 = [row["value"] * 1e6 for item, row in reg.items() if item.startswith("past_due_90_accruing:")]
    pd90v = sum(pd90) if pd90 else bi.series("past_due_90")[-1]
    out["nonaccrual"] = na
    out["past_due_90_display_only"] = pd90v
    out["nonaccrual_rate"] = None if (na is None or not loans_latest) else na / loans_latest
    out["acl"] = bi.series("acl")[-1] if bi.series("acl")[-1] is not None else _num(reg, "acl_loans_2025")
    out["acl_to_nonaccrual"] = None if (na is None or out["acl"] is None) else (None if na <= 0 else out["acl"] / na)
    # --- D15: deposit funding with repo / securities-lending liabilities counted once (extracted balance-sheet lines)
    roles: dict = {}
    lines = []
    for item, row in reg.items():
        if item.startswith("funding:"):
            _, role, label = item.split(":", 2)
            roles[role] = roles.get(role, 0.0) + row["value"] * 1e6
            lines.append({"role": role, "line": label, "value_usd": row["value"] * 1e6, "note": row["note"]})
    out["funding_lines"] = lines
    if roles.get("deposits"):
        den = sum(roles.values())
        out["deposit_funding"] = roles["deposits"] / den
        out["deposit_funding_v1"] = None  # filled from XBRL in derive_bank for the round-1 comparison
        out["funding_source"] = "extracted balance-sheet lines"
        out["funding_roles"] = roles
    else:
        out["deposit_funding"] = None
        out["funding_source"] = None
    # uninsured deposits (display only)
    out["uninsured_deposits"] = _num(reg, "uninsured_deposits")
    return out


# ---------------------------------------------------------------- derived per-year series
def derive_bank(bi: BankInputs) -> dict:
    n = bi.n
    g = bi.series
    nii, nonint = g("nii"), g("nonint")
    d: dict = {}
    d["revenue"] = [None if (a is None or b is None) else a + b for a, b in zip(nii, nonint)]
    # preferred stock: PNC's XBRL value is 0 while it pays preferred dividends -> flagged, latest year overridden
    pref = list(g("preferred"))
    ov = _num(bi.reg, "preferred_stock_2025")
    if ov is not None and pref and (pref[-1] in (None, 0.0)):
        pref[-1] = ov
        bi.flags.append("preferred_stock_latest_year_from_extraction")
    d["preferred"] = pref
    eq, gw, intg = g("equity"), g("goodwill"), g("intangibles")
    d["tce"] = [None if (e is None or g_ is None or i_ is None or p is None) else e - p - g_ - i_
                for e, p, g_, i_ in zip(eq, pref, gw, intg)]
    ta = g("assets")
    tce = d["tce"]
    ni, pdv = g("net_income"), g("pref_div")
    d["rotce"] = [None] * n
    d["roa"] = [None] * n
    d["ppnr"] = [None if (p is None or v is None) else p + v for p, v in zip(g("pretax"), g("provision"))]
    d["ppnr_to_assets"] = [None] * n
    for i in range(1, n):
        if None not in (ni[i], pdv[i], tce[i], tce[i - 1]) and (tce[i] + tce[i - 1]) != 0:
            d["rotce"][i] = (ni[i] - pdv[i]) / ((tce[i] + tce[i - 1]) / 2)
        if None not in (ni[i], ta[i], ta[i - 1]):
            d["roa"][i] = ni[i] / ((ta[i] + ta[i - 1]) / 2)
        if None not in (d["ppnr"][i], ta[i], ta[i - 1]):
            d["ppnr_to_assets"][i] = d["ppnr"][i] / ((ta[i] + ta[i - 1]) / 2)
    d["tbvps"] = [safe_div(t, s) for t, s in zip(tce, g("shares_out"))]
    d["pretax_margin"] = [safe_div(a, b) for a, b in zip(g("pretax"), d["revenue"])]
    d["net_margin"] = [safe_div(a, b) for a, b in zip(ni, d["revenue"])]
    d["pe"] = [None if (p is None or e is None or e <= 0) else p / e for p, e in zip(bi.price_avg or [None] * n, g("eps"))]
    # loans / NCO / rates (latest year may be overridden with extracted values)
    loans = list(g("loans"))
    ov_l = _num(bi.reg, "loans_2025")
    if loans[-1] is None and ov_l is not None:
        loans[-1] = ov_l
        bi.flags.append("loans_latest_from_extraction")
    d["loans"] = loans
    nco = list(g("nco"))
    ov_n = _num(bi.reg, "nco_2025")
    if nco[-1] is None and ov_n is not None:
        nco[-1] = ov_n
        bi.flags.append("nco_latest_from_extraction")
    d["nco"] = nco
    avg_l = [None] * n
    for i in range(n):
        if loans[i] is None:
            continue
        avg_l[i] = (loans[i] + loans[i - 1]) / 2 if (i and loans[i - 1] is not None) else loans[i]
    ov_a = _num(bi.reg, "avg_loans_2025")
    if ov_a is not None:
        avg_l[-1] = ov_a
    d["avg_loans"] = avg_l
    d["nco_rate"] = [safe_div(a, b) for a, b in zip(nco, avg_l)]
    d["deposit_growth"] = [None] + [safe_div(b, a) - 1 if (a and b is not None) else None
                                    for a, b in zip(g("deposits")[:-1], g("deposits")[1:])]
    dep, stb, ltd, fhlb = g("deposits"), g("st_borrow"), g("lt_debt"), g("fhlb")
    d["deposit_funding"] = [None if None in (a, b, c, e) else a / (a + b + c + e) for a, b, c, e in zip(dep, stb, ltd, fhlb)]
    # dividends per share: reported or dividends paid / basic shares
    dps = list(g("dps"))
    for i in range(n):
        if dps[i] is None and g("dividends")[i] is not None and g("shares_basic")[i]:
            dps[i] = g("dividends")[i] / g("shares_basic")[i]
            bi.flags.append("dps_derived")
    d["dps"] = dps
    d["latest"] = resolve_latest(bi)
    return d


class _View:
    """Adapter exposing bank series under the general model's field names (revenue = bank revenue)."""

    def __init__(self, bi, d):
        self._bi, self._d = bi, d
        self.n, self.fy, self.end = bi.n, bi.fy, bi.end
        self.price_avg, self.price_current = bi.price_avg, bi.price_current
        self.first_annual_report, self.as_of, self.profile = bi.first_annual_report, bi.as_of, "BANK"

    def series(self, name):
        if name == "revenue":
            return self._d["revenue"]
        if name == "shares":
            return self._bi.series("shares_dil")
        if name == "dps":
            return self._d["dps"]
        return self._bi.series(name)


def _dilution(bi) -> dict:
    s = bi.series("shares_out")
    if bi.n < 5 or s[-1] is None or s[-5] is None:
        return {"value": None, "reason": "period-end shares missing for latest year or t-4"}
    return {"value": s[-1] / s[-5] - 1, "latest": s[-1], "base": s[-5]}


def _dil_item(id_, name, mx, bi):
    a = [(0.0, mx), (0.10, 0)]
    dl = _dilution(bi)
    if dl["value"] is None:
        return miss(id_, name, mx, dl["reason"], a)
    return thresholded(id_, name, mx, dl["value"], a, "", "period-end share count change vs t-4",
                       {"latest": dl["latest"], "t_minus_4": dl["base"]})


# ================================================================ BUFFETT QUALITY
def _lcr_item(id_, name, mx, lt, anchors):
    """D9/D12: exempt (evidenced) = not applicable; subject or unknown without a numeric value = missing."""
    lcr = lt["lcr"]
    if lcr == "NA":
        return not_applicable(id_, name, mx, note="bank not subject to the LCR by regulatory category (D9/V11)",
                              flags=["lcr_not_applicable_V11"])
    if lcr == "MISSING":
        return miss(id_, name, mx, "no numeric LCR found in the 10-K or the bank's public disclosures (D12)", anchors,
                    flags=["lcr_missing_D12"])
    flags = ["lcr_from_public_disclosure"] if "Public" in str(lt.get("lcr_source")) else []
    if lt.get("lcr_measure") == "quarter_end":
        flags.append("lcr_quarter_end_not_q4_average")
    label = "LCR (quarter-end)" if lt.get("lcr_measure") == "quarter_end" else "LCR (Q4 average)"
    return thresholded(id_, name, mx, lcr, anchors, "%", label,
                       {"source": lt.get("lcr_source"), "measurement": lt.get("lcr_measure"), "as_of": lt.get("lcr_date")}, flags)


def b31(bi, d):
    return B.c31(bi, d)


def b32(bi, d):
    items = [not_applicable("1a", "Gross margin level", 1.0, note="bank: gross margin not applicable (matrix)"),
             not_applicable("1b", "Gross margin stability", 1.5, note="bank: gross margin not applicable (matrix)")]
    pm = L(d["pretax_margin"])
    pv = clean(pm)
    a2a, a2b = [(0.04, 1.5), (0.12, 0)], [(-0.05, 0), (-0.01, 1.0)]
    if len(pv) < 3:
        items.append(miss("2a", "Pretax margin stability", 1.5, "fewer than 3 years", a2a))
        items.append(miss("2b", "No pretax margin erosion", 1.0, "fewer than 3 years", a2b))
    else:
        items.append(thresholded("2a", "Pretax margin stability", 1.5, max(pv) - min(pv), a2a, "",
                                 "pretax margin range (pretax income / bank revenue)", {"pretax_margin": pm}, ["D8"]))
        if pm[-1] is None:
            items.append(miss("2b", "No pretax margin erosion", 1.0, "latest pretax margin missing", a2b))
        else:
            items.append(thresholded("2b", "No pretax margin erosion", 1.0, pm[-1] - median(pv), a2b, "",
                                     "latest minus 5y median pretax margin", {"pretax_margin": pm}, ["D8"]))
    ro = L(d["rotce"])
    cnt, nv, part = count_scaled([None if x is None else x >= 0.12 for x in ro], 5)
    a3 = [(1, 0), (2, 0.5), (3, 1), (4, 1.5), (5, 2)]
    items.append(miss("3", "Persistent ROTCE", 2.0, "fewer than 3 years of ROTCE", a3, inputs={"rotce": ro}) if cnt is None else
                 thresholded("3", "Persistent ROTCE", 2.0, cnt, a3, "", "years with ROTCE>=12% (of 5)", {"rotce": ro},
                             ["partial_window"] if part else []))
    items.append(ai_pending("4", "Stable competitive position", 2.0, note="AI question"))
    items.append(ai_pending("5", "Clear moat", 1.0, note="AI question x0.5"))
    return items


def b33(bi, d):
    return B.c33(_View(bi, d), d)


def b34(bi, d):
    a1, a2 = [(0.06, 0), (0.12, 6), (0.18, 10)], [(0.005, 0), (0.0125, 5)]
    ro, roa = L(d["rotce"]), L(d["roa"])
    items = []
    v = clean(ro)
    items.append(miss("1", "ROTCE (5y median)", 10, "fewer than 3 years of ROTCE", a1, inputs={"rotce": ro}) if len(v) < 3 else
                 thresholded("1", "ROTCE (5y median)", 10, median(v), a1, "", "5y median ROTCE", {"rotce": ro}))
    v = clean(roa)
    items.append(miss("2", "ROA (5y median)", 5, "fewer than 3 years of ROA", a2, inputs={"roa": roa}) if len(v) < 3 else
                 thresholded("2", "ROA (5y median)", 5, median(v), a2, "", "5y median ROA", {"roa": roa}))
    return items


def b35(bi, d):
    items = []
    a1 = [(0.01, 0), (0.02, 4)]
    pa = L(d["ppnr_to_assets"])
    v = clean(pa)
    items.append(miss("1", "Earning power (PPNR / avg assets)", 4, "fewer than 3 years", a1, inputs={"ppnr_to_assets": pa}) if len(v) < 3 else
                 thresholded("1", "Earning power (PPNR / avg assets)", 4, median(v), a1, "", "5y median PPNR / average assets",
                             {"ppnr_to_assets": pa}, ["ppnr_as_reported_one_offs_not_adjusted"]))
    a2 = [(0.5, 0), (1.0, 4)]
    ppnr = L(d["ppnr"])
    loans = d["loans"][-1]
    pv = clean(ppnr)
    if len(pv) < 3 or loans is None:
        items.append(miss("2", "Stress coverage", 4, "PPNR (3y+) or latest loans missing", a2))
    else:
        items.append(thresholded("2", "Stress coverage", 4, median(pv) / (0.03 * loans), a2, "",
                                 "median PPNR / (3% x latest loans)", {"ppnr": ppnr, "loans_latest": loans},
                                 ["pretax_earning_power_test_D1"]))
    a3 = [(0.0, 0), (0.12, 7)]
    tb, dps, so = d["tbvps"], d["dps"], bi.series("shares_out")
    vals, flags = [], []
    for i in range(bi.n - 4, bi.n):
        if i < 1 or tb[i] is None or tb[i - 1] is None or tb[i - 1] <= 0 or dps[i] is None:
            vals.append(None)
            continue
        vals.append((tb[i] - tb[i - 1] + dps[i]) / tb[i - 1])
        if so[i] and so[i - 1] and abs(so[i] / so[i - 1] - 1) > 0.10:
            flags.append(f"share_count_change_gt10pct_{bi.fy[i]}")
    v = clean(vals)
    items.append(miss("3", "Tangible value creation", 7, "fewer than 3 annual values", a3, inputs={"annual": vals}) if len(v) < 3 else
                 thresholded("3", "Tangible value creation", 7, median(v), a3, "",
                             "median of annual (dTBVPS + DPS) / prior TBVPS", {"annual": vals}, flags + ["D2"]))
    return items


def b36(bi, d):
    lt = d["latest"]
    items = []
    a1 = [(0.0, 0), (2.5, 4)]
    if lt["capital_buffer"] is None:
        items.append(miss("1", "Capital buffer", 4, "CET1 ratio not extracted", a1))
    else:
        ins = {"binding_approach": lt["approach"], "cet1": lt["cet1_ratio"], "required": lt["required_cet1"],
               "buffer_by_approach": lt["buffer_by_approach"], "cet1_std": lt["cet1_std"], "cet1_adv": lt["cet1_adv"],
               "required_std": lt["required_std"], "required_adv": lt["required_adv"]}
        items.append(thresholded("1", "Capital buffer", 4, lt["capital_buffer"], a1, " pp",
                                 "min over approaches of (CET1 - reported requirement) (pp)", ins, lt["flags"]))
    a2 = [(0.003, 2), (0.015, 0)]
    rates = L(d["nco_rate"])
    v = clean(rates)
    items.append(miss("2", "Typical charge-offs", 2, "NCO rate available for fewer than 3 of the last 5 years", a2,
                      inputs={"nco_rate": rates}) if len(v) < 3 else
                 thresholded("2", "Typical charge-offs", 2, median(v), a2, "", "5y median NCO rate", {"nco_rate": rates},
                             ["partial_window"] if len(v) < 5 else []))
    a3 = TH["nonaccrual_buffett"]
    na, loans = lt["nonaccrual"], lt["loans_latest"]
    if na is None or not loans:
        items.append(miss("3", "Nonaccrual loans", 1, "nonaccrual loans or total loans missing", a3))
    else:
        items.append(thresholded("3", "Nonaccrual loans", 1, na / loans, a3, "", "nonaccrual loans / gross loans (D11)",
                                 {"nonaccrual": na, "loans": loans, "source": lt["nonaccrual_source"],
                                  "past_due_90_display_only": lt["past_due_90_display_only"]},
                                 ["thresholds_to_recalibrate_D11"]))
    a4 = TH["acl_buffett"]
    if na is None or lt["acl"] is None:
        items.append(miss("4", "Reserve coverage (ACL / nonaccrual)", 1, "nonaccrual loans or ACL missing", a4))
    elif na <= 0:
        items.append(scored("4", "Reserve coverage (ACL / nonaccrual)", 1, 1, metric=None, metric_label="ACL / nonaccrual",
                            thresholds=describe(a4), note="no nonaccrual loans = 1"))
    else:
        items.append(thresholded("4", "Reserve coverage (ACL / nonaccrual)", 1, lt["acl"] / na, a4, "", "ACL / nonaccrual loans (D11)",
                                 {"acl": lt["acl"], "nonaccrual": na}, ["temporary_thresholds_D11"]))
    items.append(_lcr_item("5", "Liquidity (LCR)", 2, lt, [(100, 0), (110, 2)]))
    return items


def b37(bi, d):
    items = []
    # 1 relative buyback valuation (P/E)
    a1 = [(0.9, 2), (1.0, 1.5), (1.2, 0)]
    pe, bb = L(d["pe"]), L(bi.series("buybacks"))
    if all(p is None for p in L(bi.price_avg or [None] * bi.n)):
        items.append(miss("1", "Relative buyback valuation", 2, "no annual average prices", a1))
    else:
        bby = [(p, b) for p, b in zip(pe, bb) if b is not None and b > 0]
        valid = [(p, b) for p, b in bby if p is not None]
        med = median(pe)
        if not bby:
            items.append(not_applicable("1", "Relative buyback valuation", 2, note="no buybacks in the 5 years"))
        elif not valid:
            items.append(not_applicable("1", "Relative buyback valuation", 2, note="no valid buyback year (EPS<=0)"))
        elif len(clean(pe)) < 3 or med is None:
            items.append(miss("1", "Relative buyback valuation", 2, "fewer than 3 valid P/E years", a1))
        else:
            wavg = sum(p * b for p, b in valid) / sum(b for _, b in valid)
            items.append(thresholded("1", "Relative buyback valuation", 2, wavg / med, a1, "",
                                     "buyback-weighted P/E / median P/E", {"pe": pe, "buybacks": bb}))
    items.append(_dil_item("2", "No meaningful dilution", 2, bi))
    # 3 M&A gate: acquisitions / net income over 5 years
    acq = [(a if a is not None else 0.0) for a in L(bi.series("acquisitions"))]
    ni = L(bi.series("net_income"))
    pairs = [(a, n_) for a, n_ in zip(acq, ni) if n_ is not None]
    flags3 = []
    tags_acq = {str(v.get("tag")) for v in bi.tag_log.get("acquisitions", {}).values()}
    if "assumed_zero" in tags_acq:
        flags3.append("assumed_zero (acquisitions)")
    if any(t.startswith("PROXY") for t in tags_acq):
        flags3.append("acquisitions_proxy_goodwill")
    if len(pairs) < 3:
        items.append(miss("3", "M&A created value", 2, "fewer than 3 years"))
    else:
        sa, sn = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
        if sa <= 0:
            items.append(scored("3", "M&A created value", 2, 2, metric=0.0, metric_label="acquisitions / net income",
                                thresholds="<10% = 2, above: AI", inputs={"sum_acquisitions": sa, "sum_net_income": sn}, flags=flags3,
                                note="no acquisitions"))
        elif sn <= 0 or sa / sn > 0.10:
            items.append(ai_pending("3", "M&A created value", 2, metric=None if sn <= 0 else sa / sn,
                                    metric_label="acquisitions / net income", inputs={"sum_acquisitions": sa, "sum_net_income": sn},
                                    flags=flags3, note="acquisitions >= 10% of net income: AI question required"))
        else:
            items.append(scored("3", "M&A created value", 2, 2, metric=sa / sn, metric_label="acquisitions / net income",
                                thresholds="<10% = 2, above: AI", inputs={"sum_acquisitions": sa, "sum_net_income": sn}, flags=flags3))
    # 4 distributions / net income
    a4 = [(1.0, 2), (1.5, 0)]
    dist = [None if (x is None or y is None) else x + y for x, y in zip(L(bi.series("dividends")), L(bi.series("buybacks")))]
    pr = [(x, n_) for x, n_ in zip(dist, ni) if x is not None and n_ is not None]
    if len(pr) < 3:
        items.append(miss("4", "Distributions supported by earnings", 2, "fewer than 3 years", a4))
    else:
        sd, sn = sum(p[0] for p in pr), sum(p[1] for p in pr)
        if sd <= 0:
            items.append(scored("4", "Distributions supported by earnings", 2, 2, metric=0.0, metric_label="(div+buybacks)/NI",
                                thresholds=describe(a4), note="no distributions = 2"))
        elif sn <= 0:
            items.append(zero("4", "Distributions supported by earnings", 2, None, a4, "", "(div+buybacks)/NI",
                              {"sum_distributions": sd, "sum_net_income": sn}, ["total_net_income_nonpositive"]))
        else:
            items.append(thresholded("4", "Distributions supported by earnings", 2, sd / sn, a4, "",
                                     "(dividends + buybacks) / net income (5y)", {"sum_distributions": sd, "sum_net_income": sn}))
    items.append(ai_pending("5", "Transparent, conservative, consistent management", 2, note="AI question"))
    return items


def b38(bi, d):
    items = []
    rev = L(d["revenue"])
    a1 = [(1, 0), (2, 1), (3, 2), (4, 3)]
    cnt, nv, part = count_scaled([rose(a, b) for a, b in zip(rev[:-1], rev[1:])], 4)
    items.append(miss("1", "Consistency of revenue growth", 3, "fewer than 3 transitions", a1) if cnt is None else
                 thresholded("1", "Consistency of revenue growth", 3, cnt, a1, "", "bank revenue rises (of 4)", {"revenue": rev},
                             ["partial_window"] if part else []))
    items.append(growth_item("2", "EPS growth", 3, smoothed_growth(L(bi.series("eps"))), [(0, 0), (0.10, 3)], "smoothed EPS growth"))
    a3 = [(0, 3), (1, 2), (2, 1), (3, 0)]
    tb = L(d["tbvps"])
    fl = [None if (a is None or b is None) else b < a for a, b in zip(tb[:-1], tb[1:])]
    cnt, nv, part = count_scaled(fl, 4)
    items.append(miss("3", "TBVPS consistency", 3, "fewer than 3 transitions", a3, inputs={"tbvps": tb}) if cnt is None else
                 thresholded("3", "TBVPS consistency", 3, cnt, a3, "", "TBVPS declines (of 4 transitions)", {"tbvps": tb},
                             ["partial_window"] if part else []))
    # 4 loan growth over valid (non-acquisition) years
    a4 = [(0.10, 2), (0.20, 0)]
    loans, eq, gwa = d["loans"], bi.series("equity"), bi.series("goodwill_acquired")
    growth, skipped = [], []
    for i in range(bi.n - 4, bi.n):
        if i < 1 or loans[i] is None or loans[i - 1] in (None, 0):
            continue
        acq_year = gwa[i] is not None and eq[i] and gwa[i] > 0.01 * eq[i]
        if acq_year:
            skipped.append(bi.fy[i])
            continue
        growth.append(loans[i] / loans[i - 1] - 1)
    if len(growth) < 2:
        items.append(miss("4", "Loan growth (risk indicator)", 2, "fewer than 2 valid (non-acquisition) years", a4,
                          inputs={"valid_growth": growth, "acquisition_years_skipped": skipped}, flags=["D7"]))
    else:
        prod = 1.0
        for x in growth:
            prod *= 1 + x
        cg = prod ** (1 / len(growth)) - 1
        items.append(thresholded("4", "Loan growth (risk indicator)", 2, cg, a4, "", "CAGR over valid years",
                                 {"valid_growth": growth, "acquisition_years_skipped": skipped}, ["D7"]))
    a5 = [(0.01, 2), (0.05, 0)]
    nm = L(d["net_margin"])
    if any(x is None for x in (nm[0], nm[1], nm[3], nm[4])):
        items.append(miss("5", "Margins maintained", 2, "net margin missing in first/last two years", a5))
    else:
        items.append(thresholded("5", "Margins maintained", 2, (nm[0] + nm[1]) / 2 - (nm[3] + nm[4]) / 2, a5, "",
                                 "decline in net margin, avg first 2 -> last 2", {"net_margin": nm}))
    items.append(ai_pending("6", "Growth is sustainable", 2, note="AI question"))
    return items


B_CRITERIA = [
    ("3.1", "Simple, understandable business", b31), ("3.2", "Moat", b32), ("3.3", "Consistent profitability", b33),
    ("3.4", "Return on capital", b34), ("3.5", "Earning power and value creation", b35),
    ("3.6", "Capital, credit and liquidity", b36), ("3.7", "Management and capital allocation", b37),
    ("3.8", "Quality, sustainable growth", b38),
]


def bank_buffett_quality(bi, d) -> ModelResult:
    return evaluate_model("buffett_quality_bank",
                          [evaluate_criterion(i, n, fn(bi, d)) for i, n, fn in B_CRITERIA])


# ================================================================ GRAHAM QUALITY
def g31(bi, d):
    return G.c31(_View(bi, d), d)


def g32(bi, d):
    lt = d["latest"]
    items = []
    a1 = TH["graham_buffer"]
    if lt["capital_buffer"] is None:
        items.append(miss("1", "Capital buffer", 8, "CET1 ratio not extracted", a1))
    else:
        items.append(thresholded("1", "Capital buffer", 8, lt["capital_buffer"], a1, " pp",
                                 "min over approaches of (CET1 - reported requirement) (pp)",
                                 {"binding_approach": lt["approach"], "buffer_by_approach": lt["buffer_by_approach"],
                                  "required": lt["required_cet1"]}, lt["flags"]))
    items.append(_lcr_item("2", "Liquidity (LCR)", 4, lt, [(100, 0), (120, 4)]))
    if bi.path == "1b":
        items.append(not_applicable("3", "Deposit funding", 2, note="path 1b"))
        items.append(not_applicable("4", "Deposit stability", 1, note="path 1b"))
    else:
        a3 = TH["deposit_funding"]
        df = lt["deposit_funding"]
        fl = ["repo_included_D15"] + (["xbrl_funding_chain"] if lt.get("funding_source") is None else [])
        if df is None:
            df = d["deposit_funding"][-1]
            fl = ["funding_from_xbrl_without_repo_D15"]
        items.append(miss("3", "Deposit funding", 2, "borrowings/deposits missing", a3) if df is None else
                     thresholded("3", "Deposit funding", 2, df, a3, "", "deposits / (deposits + short-term + long-term + FHLB + repo) (D15)",
                                 {"funding_lines": lt.get("funding_lines")}, fl))
        a4 = [(-0.10, 0), (0.0, 1)]
        gr = [x for x in L(d["deposit_growth"])[1:] if x is not None]
        items.append(miss("4", "Deposit stability", 1, "fewer than 3 deposit growth transitions", a4) if len(gr) < 3 else
                     thresholded("4", "Deposit stability", 1, min(gr), a4, "", "worst annual deposit growth (4 transitions)",
                                 {"growth": gr}))
    return items


def _no_crisis(bi) -> bool:
    """Display note (6c): the fiscal-year window does not reach 2008-2010, the industry's NCO peak."""
    yrs = [int(m.group()) for y in bi.fy for m in [re.search(r"\d{4}", str(y))] if m]
    return bool(yrs) and min(yrs) > 2010


def g33(bi, d):
    lt = d["latest"]
    items = []
    # 1 worst credit-loss year over up to 10 years
    a1 = [(0.005, 5), (0.03, 0)]
    rates = [x for x in d["nco_rate"] if x is not None]
    if len(rates) < 6:
        items.append(miss("1", "Worst observed credit-loss year", 5, f"only {len(rates)} years of NCO rate (need 6+)", a1,
                          inputs={"nco_rate": d["nco_rate"]}))
    else:
        w = max(rates)
        pts = interpolate(w, a1)
        capped = len(rates) < 10
        if capped:
            pts = min(pts, 3.0)
        items.append(scored("1", "Worst observed credit-loss year", 5, pts, metric=w,
                            metric_label=f"highest NCO rate over {len(rates)} years", thresholds=describe(a1),
                            inputs={"nco_rate": d["nco_rate"], "years": len(rates)},
                            flags=(["max_3_points_with_6_to_9_years"] if capped else []) +
                                  (["window contains no credit crisis"] if _no_crisis(bi) else []),
                            note="window contains no credit crisis (display note; thresholds unchanged)" if _no_crisis(bi) else None))
    a2 = TH["nonaccrual_graham"]
    na, loans = lt["nonaccrual"], lt["loans_latest"]
    if na is None or not loans:
        items.append(miss("2", "Nonaccrual loans", 3, "nonaccrual loans or total loans missing", a2))
    else:
        items.append(thresholded("2", "Nonaccrual loans", 3, na / loans, a2, "", "nonaccrual loans / gross loans (D11)",
                                 {"nonaccrual": na, "source": lt["nonaccrual_source"]}, ["thresholds_to_recalibrate_D11"]))
    a3 = TH["acl_graham"]
    if na is None or lt["acl"] is None:
        items.append(miss("3", "Loss absorption (ACL / nonaccrual)", 4, "nonaccrual loans or ACL missing", a3))
    elif na <= 0:
        items.append(scored("3", "Loss absorption (ACL / nonaccrual)", 4, 4, metric=None, metric_label="ACL / nonaccrual",
                            thresholds=describe(a3), note="no nonaccrual loans = 4"))
    else:
        items.append(thresholded("3", "Loss absorption (ACL / nonaccrual)", 4, lt["acl"] / na, a3, "", "ACL / nonaccrual loans (D11)",
                                 {"acl": lt["acl"], "nonaccrual": na}, ["temporary_thresholds_D11"]))
    # 4 concentration
    a4 = [(0.25, 3), (0.50, 0)]
    share = lt["loans_mapped_share"]
    if share is None or share < 0.80:
        items.append(ai_pending("4", "Concentration", 3, note="loan breakdown insufficient (<80% mapped): AI question (D4)",
                                inputs={"mapped_share": share}))
    else:
        cats = lt["loan_categories"]
        tot = sum(cats.values())
        hhi = sum((v / tot) ** 2 for v in cats.values())
        cre = cats[CRE]
        tc = lt.get("total_capital")
        ins = {"categories": cats, "mapped_share": share, "hhi": hhi, "cre": cre, "total_regulatory_capital": tc,
               "cre_to_total_capital": None if not tc else cre / tc}
        if tc and cre > 3.0 * tc:
            items.append(zero("4", "Concentration", 3, hhi, a4, "", "HHI over 5 categories", ins,
                              ["cre_gt_300pct_of_total_capital"], "CRE > 300% of total regulatory capital -> 0"))
        elif not tc:
            items.append(thresholded("4", "Concentration", 3, hhi, a4, "", "HHI over 5 categories", ins,
                                     ["cre_test_skipped_total_capital_missing"]))
        else:
            items.append(thresholded("4", "Concentration", 3, hhi, a4, "", "HHI over 5 categories", ins))
    return items


def g34(bi, d):
    return G.c34(_View(bi, d), d)


def _g35(inp, d):
    """Graham 3.5 for banks: identical to the general criterion except sub-item 4 (cash-flow coverage) is not applicable."""
    div, dps, ni = tail(inp.series("dividends")), tail(inp.series("dps")), tail(inp.series("net_income"))
    has = []
    for a, b in zip(div, dps):
        has.append(None if (a is None and b is None) else bool((a or 0) > 0 or (b or 0) > 0))
    names = [("1", "Continuity", 4), ("2", "No cuts", 2), ("3", "Earnings coverage", 2)]
    if has and has[-1] is False:
        out = [zero(i, n, m, None, None, "", "", {}, ["does not meet Graham's dividend requirement"],
                    "no dividend in latest year -> criterion = 0") for i, n, m in names]
        out.append(not_applicable("4", "Cash-flow coverage", 2, note="bank: not applicable (matrix)"))
        return out
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
    vv = [x for x in fl if x is not None]
    items.append(miss("2", "No cuts", 2, "dividend per share missing for most years", a2) if len(vv) < 3 else
                 thresholded("2", "No cuts", 2, sum(1 for x in vv if x), a2, "", "DPS cuts >10%", {"dps": dps},
                             ["partial_history"] if len(vv) < 9 else []))
    a3 = [(0.6, 2), (0.8, 1), (1.0, 0)]
    pr = [(a, b) for a, b in zip(L(inp.series("dividends")), L(inp.series("net_income"))) if a is not None and b is not None]
    if len(pr) < 3:
        items.append(miss("3", "Earnings coverage", 2, "fewer than 3 paired years", a3))
    else:
        sd, sn = sum(p[0] for p in pr), sum(p[1] for p in pr)
        if sn <= 0:
            items.append(zero("3", "Earnings coverage", 2, None, a3, "", "dividends / NI", {}, ["total_net_income_nonpositive"]))
        else:
            items.append(thresholded("3", "Earnings coverage", 2, sd / sn, a3, "", "sum dividends / sum NI (5y)",
                                     {"sum_dividends": sd, "sum_ni": sn}))
    items.append(not_applicable("4", "Cash-flow coverage", 2, note="bank: not applicable (matrix)"))
    return items


def g36(bi, d):
    return G.c36(_View(bi, d), d)


def g37(bi, d):
    items = []
    lt = d["latest"]
    tce, ta, gw, intg = d["tce"], bi.series("assets"), bi.series("goodwill"), bi.series("intangibles")
    a1 = [(0.04, 0), (0.07, 5)]
    if None in (tce[-1], ta[-1], gw[-1], intg[-1]):
        items.append(miss("1", "Tangible equity to assets", 5, "TCE or assets missing", a1))
    else:
        den = ta[-1] - gw[-1] - intg[-1]
        items.append(thresholded("1", "Tangible equity to assets", 5, tce[-1] / den, a1, "", "TCE / (assets - goodwill - intangibles)",
                                 {"tce": tce[-1], "tangible_assets": den}))
    a2 = [(-0.05, 0), (0.0, 1.5), (0.05, 3)]
    tb = d["tbvps"]
    first, last = (tb[-5] if bi.n >= 5 else None), tb[-1]
    ins = {"tbvps_t_minus_4": first, "tbvps_latest": last}
    if first is None or last is None:
        items.append(miss("2", "TBVPS preservation", 3, "TBVPS missing", a2, inputs=ins))
    elif last <= 0:
        items.append(zero("2", "TBVPS preservation", 3, None, a2, "", "TBVPS CAGR", ins, ["tbvps_nonpositive_latest"]))
    elif first <= 0:
        items.append(scored("2", "TBVPS preservation", 3, 1.5, metric=None, metric_label="TBVPS CAGR", thresholds=describe(a2),
                            inputs=ins, flags=["negative_start_positive_end_D5"], note="negative start and positive end = 1.5"))
    else:
        items.append(thresholded("2", "TBVPS preservation", 3, (last / first) ** 0.25 - 1, a2, "", "TBVPS CAGR (t-4 to t)", ins))
    a3 = [(0.50, 2), (1.00, 0)]
    if lt["rwa"] is None or not ta[-1]:
        items.append(miss("3", "Risk intensity (RWA / assets)", 2, "RWA not extracted", a3))
    else:
        items.append(thresholded("3", "Risk intensity (RWA / assets)", 2, lt["rwa"] / ta[-1], a3, "",
                                 "binding RWA / total assets", {"rwa": lt["rwa"], "approach": lt["approach"]}))
    return items


def g38(bi, d):
    items = []
    eps = L(bi.series("eps"))
    a1 = [(0, 5), (1, 3.5), (2, 2), (3, 0)]
    if clean(eps) and any(x is not None and x <= 0 for x in eps):
        items.append(zero("1", "EPS stability", 5, None, a1, "", "EPS declines >10% (of 4)", {"eps": eps}, ["loss_year_in_window"],
                          "a loss year in the 5 = 0"))
    else:
        cnt, nv, part = count_scaled([fell_more_than(a, b, 0.10) for a, b in zip(eps[:-1], eps[1:])], 4)
        items.append(miss("1", "EPS stability", 5, "fewer than 3 EPS transitions", a1) if cnt is None else
                     thresholded("1", "EPS stability", 5, cnt, a1, "", "EPS declines >10% (of 4)", {"eps": eps},
                                 ["partial_window"] if part else []))
    a2 = [(0.05, 3), (0.20, 0)]
    nco, prov, pre = L(d["nco"]), L(bi.series("provision")), L(bi.series("pretax"))
    ratios, flags = [], []
    for i, (c, p, t) in enumerate(zip(nco, prov, pre)):
        if c is None or p is None or t is None:
            continue
        if p < 0:
            flags.append(f"negative_provision_{bi.fy[bi.n - 5 + i] if bi.n >= 5 else i}")
        if t <= 0:
            ratios.append(0.20 if c > p else 0.0)
        else:
            ratios.append(max(0.0, c - p) / t)
    items.append(miss("2", "Allowance erosion relative to earnings", 3, "NCO/provision/pretax available for fewer than 3 of 5 years",
                      a2) if len(ratios) < 3 else
                 thresholded("2", "Allowance erosion relative to earnings", 3, max(ratios), a2, "",
                             "worst year of max(0, NCO - provision) / pretax income", {"ratios": ratios, "nco": nco, "provision": prov, "pretax": pre},
                             flags + (["partial_window"] if len(ratios) < 5 else []) + ["D6"]))
    items.append(_dil_item("3", "Dilution", 2, bi))
    return items


G_CRITERIA = [
    ("3.1", "Company size and business stability", g31), ("3.2", "Capital, liquidity and funding", g32),
    ("3.3", "Credit quality and conservatism", g33), ("3.4", "Earnings stability", g34),
    ("3.5", "Dividend history", lambda bi, d: _g35(_View(bi, d), d)),
    ("3.6", "Moderate earnings growth", g36), ("3.7", "Quality of equity and assets", g37),
    ("3.8", "Earnings quality and dilution", g38),
]


def bank_graham_quality(bi, d) -> ModelResult:
    return evaluate_model("graham_quality_bank", [evaluate_criterion(i, n, fn(bi, d)) for i, n, fn in G_CRITERIA])


# ================================================================ PRICING
R_DISC, G_TERM = 0.10, 0.025
ROTCE_CAP = 0.20


def justified_ptbv(rotce_norm: float, tbvps: float, r: float = R_DISC, g: float = G_TERM) -> float:
    return tbvps * (rotce_norm - g) / (r - g)


def implied_return(rotce_norm: float, ptbv: float, g: float = G_TERM) -> float:
    """r = g + (ROTCE_norm - g) / (price / TBVPS)."""
    return g + (rotce_norm - g) / ptbv


def implied_rotce(ptbv: float, r: float = R_DISC, g: float = G_TERM) -> float:
    """ROTCE that justifies the current P/TBV: ROTCE = g + (P/TBV)(r - g)."""
    return g + ptbv * (r - g)


def bank_buffett_price_v1(bi, d, quality: ModelResult) -> dict:
    out = {"model": "buffett_price_bank", "method": "justified_p_tbv", "flags": []}
    ro = clean(L(d["rotce"]))
    tb = d["tbvps"][-1]
    if len(ro) < 3 or tb is None:
        return {**out, "state": "cannot_be_valued", "reason": "ROTCE (3y+) or TBVPS missing", "fair_value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    med = median(ro)
    norm = min(med, ROTCE_CAP)
    if med > ROTCE_CAP:
        out["flags"].append(f"rotce_capped_at_20pct (median {med:.1%})")
    out.update({"rotce_median": med, "rotce_norm": norm, "tbvps": tb, "r": R_DISC, "g": G_TERM})
    if norm <= G_TERM or tb <= 0:
        return {**out, "state": "cannot_be_valued", "reason": "ROTCE_norm <= g or TBVPS <= 0", "fair_value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    fv = justified_ptbv(norm, tb)
    out.update({"state": "valued", "fair_value": fv, "justified_ptbv": fv / tb})
    price = bi.price_current
    out["price_current"] = price
    if price is None:
        out["price_score"] = {"state": "missing", "points": None, "reason": "no current price"}
    else:
        disc = (fv - price) / fv
        out["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, B.PRICE_ANCHORS),
                              "anchors": describe(B.PRICE_ANCHORS)}
        ptbv = price / tb
        out["price_to_tbv"] = ptbv
        out["implied_return"] = implied_return(norm, ptbv)
        out["implied_rotce"] = implied_rotce(ptbv)
    out["buy_price"] = B._buy_price(fv, quality, B.MARGIN_ANCHORS)
    return out


def bank_graham_price_v1(bi, d, quality: ModelResult) -> dict:
    out = {"model": "graham_price_bank", "method": "graham_number_tangible_book", "flags": []}
    eps3 = L(bi.series("eps"), 3)
    tb = d["tbvps"][-1]
    if any(x is None for x in eps3) or tb is None:
        return {**out, "state": "cannot_be_valued", "reason": "EPS (3y) or TBVPS missing", "value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    ne = sum(eps3) / 3
    out.update({"normalized_eps": ne, "tbvps": tb})
    if ne <= 0 or tb <= 0:
        return {**out, "state": "cannot_be_valued", "reason": "normalized EPS <= 0 or TBVPS <= 0", "value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    val = math.sqrt(22.5 * ne * tb)
    out.update({"state": "valued", "value": val, "price_current": bi.price_current})
    if bi.price_current is None:
        out["price_score"] = {"state": "missing", "points": None}
    else:
        disc = (val - bi.price_current) / val
        out["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, G.CLASSIC_PRICE),
                              "anchors": describe(G.CLASSIC_PRICE)}
    out["buy_price"] = B._buy_price(val, quality, G.CLASSIC_MARGIN)
    return out


# ================================================================ PRICING v2 (spec section 6)
def _stage_growth(g1: float, t: int) -> float:
    """TCE growth in year t: g1 in years 1-5, linear fade to the terminal 2.5% over years 6-10."""
    return g1 if t <= 5 else g1 + (G_TERM - g1) * (t - 5) / 5


def two_stage_value(tce0: float, rotce: float, g1: float, r: float = R_DISC, erosion: bool = False) -> dict:
    """Total value of common tangible equity: TCE0 + PV(residual income, years 1-10) + PV(terminal value).

    Base case: ROTCE constant, RI_t = (ROTCE - r) x TCE_{t-1}, TV = RI_11 / (r - g_terminal) with RI_11 = (ROTCE - r) x TCE_10.
    Erosion case (V3a): ROTCE fades linearly from ROTCE_norm to the cost of equity over years 1-10 and the terminal RI is 0.
    """
    tce, pv_ri, rows = tce0, 0.0, []
    for t in range(1, 11):
        g = _stage_growth(g1, t)
        roe = rotce + (r - rotce) * t / 10 if erosion else rotce
        ri = (roe - r) * tce  # TCE_{t-1}
        pv_ri += ri / (1 + r) ** t
        rows.append({"year": t, "growth": g, "rotce": roe, "tce_start": tce, "residual_income": ri})
        tce *= 1 + g
    tv = 0.0 if erosion else (rotce - r) * tce / (r - G_TERM)
    pv_tv = tv / (1 + r) ** 10
    return {"total": tce0 + pv_ri + pv_tv, "tce0": tce0, "pv_ri": pv_ri, "terminal_value": tv, "pv_terminal_value": pv_tv,
            "tce10": tce, "years": rows}


def payout_ratio(bi: BankInputs) -> Optional[float]:
    """(Dividends + buybacks) / net income, 5-year sums, clipped to 0%-100% (V1)."""
    div, bb, ni = L(bi.series("dividends")), L(bi.series("buybacks")), L(bi.series("net_income"))
    pr = [(d_ + b_, n_) for d_, b_, n_ in zip(div, bb, ni) if None not in (d_, b_, n_)]
    if len(pr) < 3:
        return None
    sd, sn = sum(p[0] for p in pr), sum(p[1] for p in pr)
    if sn <= 0:
        return 1.0
    return max(0.0, min(1.0, sd / sn))


def _g1(rotce: float, payout: float, gate_ok: bool) -> float:
    if not gate_ok:
        return G_TERM
    return max(0.0, min(0.12, rotce * (1 - payout)))


def bank_buffett_price(bi, d, quality: ModelResult) -> dict:
    """Two-stage excess-returns model on total TCE (V1-V3). The single-stage v1 value is kept as a comparison."""
    out = {"model": "buffett_price_bank_v2", "method": "two_stage_excess_returns", "flags": []}
    v1 = bank_buffett_price_v1(bi, d, quality)
    out["v1_single_stage"] = {k: v1.get(k) for k in ("state", "fair_value", "justified_ptbv", "implied_return", "implied_rotce",
                                                      "rotce_median", "rotce_norm", "tbvps", "price_score", "reason")}
    ro = clean(L(d["rotce"]))
    tce0 = d["tce"][-1]
    shares = bi.series("shares_out")[-1]
    out.update({"tce0": tce0, "shares": shares, "price_current": bi.price_current})
    if len(ro) < 3 or tce0 is None or shares is None:
        return {**out, "state": "cannot_be_valued", "reason": "ROTCE (3y+), TCE or period-end shares missing", "fair_value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    if tce0 <= 0:
        return {**out, "state": "cannot_be_valued", "reason": "TCE0 <= 0", "fair_value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    med = median(ro)
    norm = min(med, ROTCE_CAP)
    if med > ROTCE_CAP:
        out["flags"].append(f"rotce_capped_at_20pct (median {med:.1%})")
    out.update({"rotce_median": med, "rotce_norm": norm})
    if norm <= G_TERM:  # V6: no valid value under the model (not an economic value of zero)
        return {**out, "state": "cannot_be_valued", "reason": f"ROTCE_norm {norm:.1%} <= 2.5% (V6)", "fair_value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None,
                "flags": out["flags"] + ["V6_rotce_norm_at_or_below_2.5pct"]}
    payout = payout_ratio(bi)
    if payout is None:
        return {**out, "state": "cannot_be_valued", "reason": "payout ratio not computable (fewer than 3 paired years)",
                "fair_value": None, "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    gate = B.growth_gate(_View(bi, d))
    g1 = _g1(norm, payout, gate["passed"])
    if not gate["passed"]:
        out["flags"].append("growth_gate_failed (" + "; ".join(gate["failing"]) + ")")
    base = two_stage_value(tce0, norm, g1)
    per_share = base["total"] / shares
    out.update({"rotce_median": med, "rotce_norm": norm, "payout": payout, "g1": g1, "growth_gate": gate, "state": "valued",
                "total_value": base["total"], "fair_value": per_share, "justified_ptbv": per_share / d["tbvps"][-1] if d["tbvps"][-1] else None,
                "pv_residual_income": base["pv_ri"], "pv_terminal_value": base["pv_terminal_value"], "tce10": base["tce10"],
                "schedule": base["years"]})
    # V3 sensitivity (display only)
    sens = {"base": per_share}
    # V7: erosion only when ROTCE_norm > 10% (otherwise erosion = base case); base growth path kept; +/-1pp recompute growth
    if norm > R_DISC:
        sens["erosion"] = two_stage_value(tce0, norm, g1, erosion=True)["total"] / shares
    else:
        sens["erosion"] = per_share
        out["flags"].append("V7_erosion_equals_base_rotce_norm_at_or_below_10pct")
    for sign, key in ((1, "rotce_plus_1pp"), (-1, "rotce_minus_1pp")):
        rr = norm + sign * 0.01
        if rr <= G_TERM:  # V6 applies to the scenario too: no negative value is shown
            sens[key] = None
            continue
        v = two_stage_value(tce0, rr, _g1(rr, payout, gate["passed"]))["total"] / shares
        sens[key] = v if v > 0 else None
    out["sensitivity"] = sens
    vals = [v for v in sens.values() if v is not None]
    out["sensitivity_range"] = (min(vals), max(vals))
    out["single_stage_sanity"] = (norm - G_TERM) / (R_DISC - G_TERM)  # justified P/TBV, single stage
    price = bi.price_current
    if per_share <= 0:  # never output a negative value
        # Rulebook C15 / V6, CL14 (H-07): value <= 0 -> price score 0, no buy price (as the general model)
        return {**out, "state": "cannot_be_valued", "reason": "model value <= 0 (V6)", "fair_value": None, "sensitivity": None,
                "sensitivity_range": None, "price_score": {"state": "score", "points": 0.0, "reason": "C15: value <= 0 -> price score 0"},
                "buy_price": None, "flags": out["flags"] + ["C15_value_nonpositive_cannot_be_valued"]}
    if price is None:
        out["price_score"] = {"state": "missing", "points": None, "reason": "no current price"}
    else:
        disc = (per_share - price) / per_share
        out["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, B.PRICE_ANCHORS),
                              "anchors": describe(B.PRICE_ANCHORS)}
        out["price_to_tbv"] = price / d["tbvps"][-1] if d["tbvps"][-1] else None
        # implied return (display): cost of equity that equates the two-stage value with the price
        f_r = lambda r_: two_stage_value(tce0, norm, g1, r=r_)["total"] / shares - price  # noqa: E731
        ir = _solve(f_r, G_TERM + 1e-4, 0.40, decreasing=True)
        # the value falls as the rate rises: a price above the value at the lower bound implies a rate below 2.5%
        out["implied_return"] = BELOW_2_5 if (ir == NO_SOLUTION and f_r(G_TERM + 1e-4) < 0) else ir
        # implied ROTCE (display): constant ROTCE (growth recomputed) that equates the value with the price
        out["implied_rotce"] = _solve(lambda x: two_stage_value(tce0, x, _g1(x, payout, gate["passed"]))["total"] / shares - price,
                                      -0.20, 0.40, decreasing=False)
    out["buy_price"] = B._buy_price(per_share, quality, B.MARGIN_ANCHORS)
    return out


NO_SOLUTION = "no solution"
BELOW_2_5 = "below 2.5%"


def _solve(fn, lo, hi, decreasing, tol=0.01, iters=200, undefined_below=None):
    """V8: bisection for fn(x) = 0 on [lo, hi]; stops when |fn| <= tol ($0.01 per share). No root inside the bounds
    -> 'no solution'. ``undefined_below``: the model has no value at or below this x (terminal value needs r > g), so the
    search starts just above it; a root requiring x below it is a 'no solution'."""
    if undefined_below is not None and lo <= undefined_below:
        lo = undefined_below + 1e-6
    flo, fhi = fn(lo), fn(hi)
    if abs(flo) <= tol:
        return lo
    if abs(fhi) <= tol:
        return hi
    if (flo > 0) == (fhi > 0):
        return NO_SOLUTION
    a, b = lo, hi
    mid = (a + b) / 2
    for _ in range(iters):
        mid = (a + b) / 2
        fm = fn(mid)
        if abs(fm) <= tol:
            return mid
        if (fm > 0) == decreasing:
            a = mid
        else:
            b = mid
    return mid


def _tag(bi, field, fy):
    return ((bi.tag_log or {}).get(field) or {}).get(fy, {}).get("tag")


def classify_loss_year(fy, eps, ppnr, provision, pretax, goodwill_impairment, securities_gain_loss, gw_tag=None, sec_tag=None) -> dict:
    """V5. Adjusted PPNR = PPNR + goodwill impairment + net realized securities loss (a gain is not deducted).
    operating: provision > adjusted PPNR (or the inputs are missing); otherwise one-off with a deterministic cause."""
    gw = max(0.0, goodwill_impairment or 0.0)
    sec = max(0.0, -(securities_gain_loss or 0.0))
    ly = {"year": fy, "eps": eps, "ppnr": ppnr, "provision": provision, "pretax": pretax, "goodwill_impairment": gw,
          "securities_loss": sec, "goodwill_tag": gw_tag, "securities_tag": sec_tag, "adjusted_ppnr": None, "kind": None, "cause": None}
    if ppnr is None or provision is None:
        return {**ly, "kind": "unclassified", "cause": "unidentified"}
    adj = ppnr + gw + sec
    ly["adjusted_ppnr"] = adj
    if provision > adj:
        return {**ly, "kind": "operating", "cause": "credit losses"}
    gap = provision - ppnr  # > 0: the adjustments are what bring PPNR up to the provision
    if gap > 0:
        if gw >= gap and sec >= gap:
            cause = "goodwill impairment" if gw >= sec else "securities losses"
        elif gw >= gap:
            cause = "goodwill impairment"
        elif sec >= gap:
            cause = "securities losses"
        else:
            cause = "goodwill impairment + securities losses"
    elif pretax is not None and pretax > 0:
        cause = "tax"
    else:
        cause = "unidentified"
    return {**ly, "kind": "one_off", "cause": cause}


def bank_graham_price(bi, d, quality: ModelResult) -> dict:
    """Graham Number on tangible book with 10-year average diluted EPS (V4). The 3-year v1 value is kept as a comparison."""
    out = {"model": "graham_price_bank_v2", "method": "graham_number_tangible_book_10y_eps", "flags": []}
    v1 = bank_graham_price_v1(bi, d, quality)
    out["v1_3y_eps"] = {k: v1.get(k) for k in ("state", "value", "normalized_eps", "price_score", "reason")}
    eps = clean(tail(bi.series("eps"), 10))
    tb = d["tbvps"][-1]
    out.update({"eps_years": len(eps), "tbvps": tb, "price_current": bi.price_current})
    if len(eps) < 7:
        return {**out, "state": "cannot_be_valued", "reason": f"only {len(eps)} years of EPS (need 7+)", "value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    if len(eps) < 10:
        out["flags"].append(f"eps_average_of_{len(eps)}_available_years")
    ne = sum(eps) / len(eps)
    out["normalized_eps"] = ne
    # V5 (2026-10-13): adjusted PPNR = PPNR + goodwill impairment + net realized securities loss (only when a loss).
    # Loss year (diluted EPS < 0): provision > adjusted PPNR -> operating (cannot be valued); otherwise one-off (valued, flagged).
    n_ = bi.n
    ser_eps, ppnr_s, prov_s, pre_s = (tail(bi.series("eps"), 10), tail(d["ppnr"], 10), tail(bi.series("provision"), 10),
                                      tail(bi.series("pretax"), 10))
    gwi_s = tail(bi.f.get("goodwill_impairment") or [None] * n_, 10)
    sec_s = tail(bi.f.get("securities_gain_loss") or [None] * n_, 10)
    fys = tail(bi.fy, 10)
    loss_years = []
    for e, p_, pv, pre, gw, sg, fy in zip(ser_eps, ppnr_s, prov_s, pre_s, gwi_s, sec_s, fys):
        if e is None or e >= 0:
            continue
        loss_years.append(classify_loss_year(fy, e, p_, pv, pre, gw, sg, _tag(bi, "goodwill_impairment", fy), _tag(bi, "securities_gain_loss", fy)))
    out["loss_years"] = loss_years

    def _bn(x):
        return "n/a" if x is None else f"{x / 1e9:.2f}bn"

    for ly in loss_years:
        if ly["kind"] == "one_off":
            out["flags"].append(f"V5_one_off_loss_year_{ly['year']} (cause: {ly['cause']}; provision {_bn(ly['provision'])} <= adjusted PPNR "
                                f"{_bn(ly['adjusted_ppnr'])})")
    bad = [ly for ly in loss_years if ly["kind"] != "one_off"]
    if bad:
        return {**out, "state": "cannot_be_valued", "value": None,
                "reason": "operating loss year(s) (V5): " + "; ".join(
                    f"{b['year']} ({b['kind']}: adjusted PPNR {_bn(b['adjusted_ppnr'])}, provision {_bn(b['provision'])})" for b in bad),
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    if ne <= 0 or tb is None or tb <= 0:
        return {**out, "state": "cannot_be_valued", "reason": "10-year average EPS <= 0 or TBVPS <= 0", "value": None,
                "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    val = math.sqrt(22.5 * ne * tb)
    out.update({"state": "valued", "value": val})
    if bi.price_current is None:
        out["price_score"] = {"state": "missing", "points": None}
    else:
        disc = (val - bi.price_current) / val
        out["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, G.CLASSIC_PRICE),
                              "anchors": describe(G.CLASSIC_PRICE)}
        if quality.score is None or quality.score < 55:  # Rulebook A.5 / X1 (H-01): the score stays shown, labelled; the buy price is "not suitable" (_buy_price)
            out["price_score"]["label"] = ("Graham quality below 55" if quality.score is not None else "no Graham quality score")
            out["flags"].append("X1_price_score_shown_graham_quality_below_55")
    out["buy_price"] = B._buy_price(val, quality, G.CLASSIC_MARGIN)
    return out


# ================================================================ entry point
STATE_UNSUPPORTED = "sector_not_supported_v1"


def score_bank(bi: BankInputs) -> dict:
    d = derive_bank(bi)
    bq = bank_buffett_quality(bi, d)
    bp = bank_buffett_price(bi, d, bq)
    gq = bank_graham_quality(bi, d)
    gp = bank_graham_price(bi, d, gq)
    from .c16 import apply_c16
    return apply_c16({"state": "scored", "derived": d, "buffett_quality": bq, "buffett_price": bp, "graham_quality": gq, "graham_price": gp}, getattr(bi, "price_entity_issue", None))

"""INCOME_REAL_ESTATE profile: derived metrics (spec 2026-10-14_10-05, section 3) and quality scoring (sections 4-5) and pricing RP1-RP3 (section 6, spec 2026-10-14_22-30).

Code computes every metric and score; items found only in text come from ``scripts/realestate_extracted.csv`` (exact quotes). A metric whose input is
missing is missing (M1-M9, D14), never estimated; the approved proxies (FFO_PROXY, NOI_PROXY) carry ``metric_basis``.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from . import buffett as B
from . import graham as G
from .common import L, miss, tail, thresholded, zero
from .coverage import ModelResult, ai_pending, evaluate_criterion, evaluate_model, not_applicable, scored
from .interpolate import describe, interpolate
from .metrics import INF, clean, clip, count_scaled, fell_more_than, median, safe_div, smoothed_growth

PROFILE = "INCOME_REAL_ESTATE"
R_EQUITY = 0.10          # cost of equity in the WACC proxy (general model discount rate)
KD_TAX_REIT = 0.0        # REITs: no tax shield
NTDC_MONTHS = 24
PROFILE_ASSET_SHARE = 0.50
PROFILE_RENTAL_SHARE = 0.50
NTDC_NO_MATURITY_FULL = True


@dataclass
class REInputs:
    ticker: str
    name: str
    fy: list
    end: list
    f: dict
    reg: dict  # extracted items: item -> {year label or "": {value, unit, quote, ...}}
    asset_type: str = ""
    utilization: str = "occupancy"
    noi_method: Optional[str] = None
    rental_proxy_note: str = ""
    price_current: Optional[float] = None
    price_entity_issue: Optional[str] = None  # C16: price of a successor entity vs financials of the predecessor -> cannot be priced
    price_date: Optional[str] = None
    price_avg: list = field(default_factory=list)
    first_annual_report: Optional[date] = None
    as_of: Optional[date] = None
    flags: list = field(default_factory=list)
    data_problems: list = field(default_factory=list)
    tag_log: dict = field(default_factory=dict)
    profile: str = PROFILE

    @property
    def n(self) -> int:
        return len(self.fy)

    def series(self, name: str) -> list:
        return self.f.get(name) or [None] * self.n


def ext_series(ri: REInputs, item: str) -> list:
    """Per fiscal year value of an extracted item (rows keyed by 'FY2025' / '2025'); a single row without a year applies to the latest year."""
    rows = ri.reg.get(item, {}) if ri.reg else {}
    out = [None] * ri.n
    for i, lab in enumerate(ri.fy):
        r = rows.get(lab) or rows.get(lab[2:])
        if r and isinstance(r["value"], (int, float)):
            out[i] = float(r["value"])
    if "" in rows and isinstance(rows[""]["value"], (int, float)) and out[-1] is None:
        out[-1] = float(rows[""]["value"])
    return out


def ext_sum(ri: REInputs, prefix: str) -> list:
    """Per fiscal year sum of the extracted component items ``<prefix>__*`` (e.g. debt maturing in the next 12 months, listed by instrument); None when no component exists for the year."""
    out = [None] * ri.n
    for item in (ri.reg or {}):
        if item.startswith(prefix + "__"):
            for i, v in enumerate(ext_series(ri, item)):
                if v is not None:
                    out[i] = (out[i] or 0.0) + v
    return out


def _ratio(a, b):
    return None if (a is None or b is None or b == 0) else a / b


def derive_re(ri: REInputs) -> dict:
    n, g = ri.n, ri.series
    d: dict = {"flags": []}
    tl = ri.tag_log
    tagof = lambda fld, i: (tl.get(fld, {}).get(ri.fy[i]) or {}).get("tag")  # noqa: E731
    rental, other, total_rev, opex, noi_rep = g("rental_revenue"), g("other_property_revenue"), g("total_revenue"), g("prop_opex"), g("noi_reported")
    # extracted income-statement lines stand in where no tag exists (PSA: self-storage revenue and cost of operations)
    rx, ox = ext_series(ri, "rental_revenue_extracted"), ext_series(ri, "property_opex_extracted")
    d["rental_revenue_source"] = ["tag" if r is not None else ("extracted" if x is not None else None) for r, x in zip(rental, rx)]
    rental = [r if r is not None else x for r, x in zip(rental, rx)]
    opex = [o if o is not None else x for o, x in zip(opex, ox)]
    d["property_revenue"] = [None if r is None else r + (o or 0.0) for r, o in zip(rental, other)]
    # ---- NOI (RE13): always computed by us = rental + other property revenue - property operating expenses; company-reported NOI is a reconciliation input only
    d["noi_basis"], d["noi"] = [None] * n, [None] * n
    comps = ["prop_opex"] if ri.noi_method == "rental_less_opex" else ri.noi_method
    for i in range(n):
        if comps == "revenue_less_cost":
            if total_rev[i] is not None and g("cost_of_revenue")[i] is not None:
                d["noi"][i] = total_rev[i] - g("cost_of_revenue")[i]
                d["noi_basis"][i] = "PROXY: total revenue - cost of revenue (data centers: no property-level revenue / expense data)"
            continue
        if d["property_revenue"][i] is None:
            continue
        parts, ok = [], True
        for c in (comps or []):
            v = opex[i] if c == "prop_opex" else g(c)[i]
            if v is None and c == "prop_opex":
                ok = False
                break
            parts.append((c, v or 0.0))
        if ok and parts:
            d["noi"][i] = d["property_revenue"][i] - sum(v for _, v in parts)
            d["noi_basis"][i] = "rental + other property revenue - " + " - ".join(c for c, _ in parts) + (" (extracted income-statement lines)" if d["rental_revenue_source"][i] == "extracted" else "")
    d["noi_reported"] = noi_rep
    d["noi_reconciliation_pct"] = [None if (a is None or b is None or b == 0) else (a - b) / abs(b) for a, b in zip(d["noi"], noi_rep)]
    denom = list(d["property_revenue"])
    d["noi_margin"] = [_ratio(a, b) for a, b in zip(d["noi"], denom)]
    # ---- FFO (uniform formula, US GAAP NAREIT form; JV adjustments and OP-unit attribution are not available -> flagged)
    ni, pref, gains, imp = g("net_income"), g("pref_div"), g("gains_sale"), g("impairment")
    redep, da = g("re_depr"), g("da_total")
    recon_ni = ext_series(ri, "recon_net_income")  # filers whose reconciliation starts from consolidated net income (AMT): the company's starting line replaces the attributable-income tag
    ni = [r if r is not None else x for r, x in zip(recon_ni, ni)]
    recon_da, recon_nci, recon_jv = ext_series(ri, "recon_re_da"), ext_series(ri, "recon_nci_adjust"), ext_series(ri, "recon_jv_other_adjust")
    recon_gi = ext_series(ri, "recon_gi_net")  # AMT: the company's line 'losses from sale or disposal of real estate and real estate related impairment charges' (incl. goodwill impairments), positive = add-back
    d["ffo"], d["ffo_flags"] = [None] * n, [[] for _ in range(n)]
    d["ffo_gi_adjustment"] = [None] * n  # sale results and impairments added back / removed in FFO (tags, or the company's reconciliation line)
    for i in range(n):
        fl = d["ffo_flags"][i]
        if ni[i] is None:
            continue
        # RE17 D&A priority: 1. the real-estate-related D&A of the company's FFO reconciliation (incl. the share of unconsolidated JVs), 2. the real-estate D&A tag
        # (Schedule III depreciation), 3. total D&A (flagged: may include non-real-estate amortization)
        if recon_da[i] is not None:
            dep = recon_da[i]
            fl.append("D&A_from_company_FFO_reconciliation (RE17)")
        elif redep[i] is not None:
            dep = redep[i]
            fl.append("D&A_from_real_estate_tag_Schedule_III (excludes lease-intangible amortization)")
        elif da[i] is not None:
            dep = da[i]
            fl.append("total_DA_used_may_include_non_real_estate_amortization")
        else:
            fl.append("real_estate_depreciation_missing")
            continue
        if gains[i] is None and recon_gi[i] is None:
            fl.append("gains_on_sale_AI_extraction_needed")
            continue
        gre = g("gains_re_entities")[i]  # RE12: gains on sales of investments in real-estate entities are excluded like gains on sales of real estate
        if gre:
            fl.append(f"RE12_gain_on_sale_of_investment_in_real_estate_entity_excluded ({gre / 1e6:,.0f}m)")
        impv = imp[i] or 0.0
        gtag = tagof("gains_sale", i) or ""
        if gtag.endswith("GainLossOnSaleOfOtherAssets"):
            fl.append("gain_line_is_other_assets_not_property_specific")
        if "ImpairmentNet" in gtag or "AndImpairment" in gtag:
            impv = 0.0
            fl.append("impairment_netted_inside_the_gain_line")
        if tagof("impairment", i) in ("AssetImpairmentCharges", "ImpairmentOfLongLivedAssetsHeldForUse"):
            fl.append("impairment_tag_is_generic_not_depreciable_real_estate_only")
        prefv = 0.0 if tagof("net_income", i) == "NetIncomeLossAvailableToCommonStockholdersBasic" else (pref[i] or 0.0)
        nci = recon_nci[i] or 0.0
        if recon_ni[i] is not None:
            fl.append("net_income_start_from_company_reconciliation (consolidated, RE17)")
            prefv = 0.0
        jvo = recon_jv[i] or 0.0
        if recon_gi[i] is not None:
            adj_gi = recon_gi[i]
            fl.append("gains_and_impairments_from_company_FFO_reconciliation_line (RE29 / RE17)")
        else:
            adj_gi = -gains[i] - (gre or 0.0) + impv
        d["ffo_gi_adjustment"][i] = adj_gi
        d["ffo"][i] = ni[i] + dep + adj_gi - prefv + nci + jvo
        if recon_jv[i] is not None:
            fl.append("JV_impairments_and_gains_within_unconsolidated_JVs_from_company_reconciliation")
        if recon_nci[i] is not None:
            fl.append("OP_unit_noncontrolling_adjustment_from_company_reconciliation (RE17)")
        if recon_da[i] is None:
            fl.append("JV_adjustments_not_available")
    # RE29: normalized FFO is without gains on sales of real estate left in FFO (development properties and land, as the company's Core FFO) and without impairments of non-real-estate assets
    # and investments that FFO does not already add back
    gains29 = [a if a is not None else b for a, b in zip(ext_sum(ri, "re29_re_sale_gains"), ext_series(ri, "dev_gains_reported"))]
    nonre29 = ext_sum(ri, "re29_nonre_impairments")
    # RE29a: no unrealized foreign-exchange remeasurement and no realized / unrealized results of non-real-estate investments in normalized FFO, in both directions (gain positive: deducted; loss: added back)
    fx_gross = list(g("fx_unrealized"))  # XBRL unrealized foreign-currency result (may exclude the hedging derivatives)
    fx_net_x = ext_series(ri, "re29b_fx_net")  # RE29b: the net result including the hedging derivatives (income-statement net line, or the company's own FFO / AFFO add-back)
    fx29a = [b if b is not None else a for a, b in zip(fx_gross, fx_net_x)]
    d["re29b_fx_gross"], d["re29b_fx_net_extracted"] = fx_gross, fx_net_x
    inv29a = ext_sum(ri, "re29a_nonre_inv")
    # RE30: normalized FFO = FFO - sum of the non-recurring P&L items, each signed as in net income (gain +, loss -; removing a loss adds it back), in the fixed order (1)-(5), each item once.
    # An amount already removed in the FFO source (RE12 gains and real-estate impairments through the tags or the company's reconciliation line) is not removed again: items (1)-(5) are only the
    # amounts that FFO still contains.
    one_off, re30_items = [], []
    for i in range(n):
        if d["ffo"][i] is None:
            one_off.append(None)
            re30_items.append(None)
            continue
        ext_gl, tc = g("debt_extinguishment")[i], g("transaction_costs")[i]
        items_i = [("(1) gains / losses on sales of real estate incl. development and land (RE29)", gains29[i] or 0.0),
                   ("(2) impairments of non-real-estate assets and investments (RE29)", -(nonre29[i] or 0.0)),
                   ("(3) realized and unrealized results of non-real-estate investments (RE29a)", inv29a[i] or 0.0),
                   ("(4) unrealized FX remeasurement net of hedges (RE29a / RE29b)", fx29a[i] or 0.0),
                   ("(5) gain / loss on debt extinguishment", ext_gl or 0.0), ("(5) transaction / merger costs", -(tc or 0.0))]
        re30_items.append(items_i)
        one_off.append(-sum(v for _, v in items_i))
    d["one_offs"] = one_off
    d["re30_items"] = re30_items
    d["re29_gains_deducted"], d["re29_nonre_added"] = gains29, nonre29
    d["re29a_fx_result"], d["re29a_investment_result"] = fx29a, inv29a  # signed results removed from normalized FFO (gain positive)
    d["impairment_tag_addback"] = list(imp)
    d["norm_ffo"] = [None if (a is None or b is None) else a + b for a, b in zip(d["ffo"], one_off)]
    sh = list(g("shares_dil"))
    sho = ext_series(ri, "shares_basis_override")  # RE28: SPG - weighted shares + limited partnership units (operating-partnership basis, FFO of the Operating Partnership)
    if any(x is not None for x in sho):
        sh = [x if x is not None else y for x, y in zip(sho, sh)]
        d["flags"].append("RE28_per_share_basis: shares + OP units (operating-partnership basis)")
    d["shares_eff"] = sh
    d["ffo_ps"] = [_ratio(a, s) for a, s in zip(d["ffo"], sh)]
    d["nffo_ps"] = [_ratio(a, s) for a, s in zip(d["norm_ffo"], sh)]
    d["nffo_margin"] = [_ratio(a, r) for a, r in zip(d["norm_ffo"], total_rev)]
    # ---- reported FFO reconciliation (AI-extracted reported NAREIT FFO, USD)
    rep = ext_series(ri, "reported_ffo")
    d["reported_ffo"] = rep
    d["ffo_reconciliation_pct"] = [None if (a is None or b is None or b == 0) else (a - b) / abs(b) for a, b in zip(d["ffo"], rep)]
    d["ffo_gap_flag_over_10pct"] = [None if x is None else abs(x) > 0.10 for x in d["ffo_reconciliation_pct"]]
    # ---- owner earnings
    sl, maint, tilc = list(g("straight_line")), g("maint_capex"), ext_series(ri, "ti_lc_income_preserving")
    slx = ext_series(ri, "straight_line_x")  # company AFFO reconciliation line (sign: positive = GAAP rent above cash rent)
    if any(x is not None for x in slx):
        sl = [x if x is not None else y for x, y in zip(sl, slx)]
        d["flags"].append("straight_line_from_company_AFFO_reconciliation_where_not_tagged")
    if ri.asset_type == "data centers" and all(x is None for x in sl):
        sl = [0.0] * n  # the company's AFFO reconciliation has no lessor straight-line revenue line (extraction: absence verified); interpretation, flagged
        d["flags"].append("straight_line_not_reported_set_to_0 (data centers: AFFO has no lessor straight-line line)")
    if ri.asset_type in ("residential", "self-storage") and all(x is None for x in sl):
        sl = [0.0] * n  # monthly leases: no straight-line rent adjustment (flagged)
        d["flags"].append("straight_line_not_applicable_set_to_0 (" + ri.asset_type + ")")
    maint_x = ext_series(ri, "maintenance_capex")
    maint = [m if m is not None else x for m, x in zip(maint, maint_x)]
    if ri.asset_type in ("residential", "self-storage", "data centers", "communication towers") and all(x is None for x in tilc):
        tilc = [0.0] * n  # no TI/LC concept for apartments / storage units / data centers (RE20, flagged); recurring maintenance capex (unit turnover) is still extracted
        d["flags"].append("TI_LC_not_applicable_set_to_0 (" + ri.asset_type + ("; towers: the AFFO capital-improvement deduction is the maintenance capex" if ri.asset_type == "communication towers" else "") + ")")
    incs = ext_series(ri, "inc_share_of_bplp")  # RE28: BXP - FFO is the BXP, Inc. share; the FAD deductions are the partnership's (BXP's share incl. OP units) -> scaled to the Inc. share
    d["inc_share_of_partnership"] = incs
    if any(x is not None for x in incs):
        slx_ = ext_series(ri, "straight_line_x")
        sl = [(a * s_) if (a is not None and s_) else (b * s_ if (b is not None and s_) else b) for a, b, s_ in zip(slx_, sl, incs)]
        maint = [m * s_ if (m is not None and s_) else m for m, s_ in zip(maint, incs)]
        tilc = [t_ * s_ if (t_ is not None and s_) else t_ for t_, s_ in zip(tilc, incs)]
        d["straight_line_adjustment"] = sl
        d["flags"].append("RE28_deductions_scaled_to_BXP_Inc_share_of_the_partnership (straight-line, maintenance capex, 2nd generation TI/LC)")
    d["maint_capex"], d["tilc_pres"] = maint, tilc
    d["oe"], d["oe_basis"], d["oe_ps"] = [None] * n, [None] * n, [None] * n
    for i in range(n):
        if d["norm_ffo"][i] is None:
            continue
        if sl[i] is not None and maint[i] is not None and tilc[i] is not None:
            d["oe"][i] = d["norm_ffo"][i] - sl[i] - maint[i] - tilc[i]
            d["oe_basis"][i] = "OE"
            d["oe_ps"][i] = _ratio(d["oe"][i], sh[i])
        else:
            d["oe_ps"][i] = d["nffo_ps"][i]  # FFO proxy (flagged): growth / stability sub-items only
            d["oe_basis"][i] = "FFO_PROXY"
    d["oe_ps_strict"] = [d["oe_ps"][i] if d["oe_basis"][i] == "OE" else None for i in range(n)]  # level basis for pricing (RP1): the FFO proxy is never a level
    # RE24: straight-line adjustment = GAAP rent - cash rent received, deducted from FFO; a negative adjustment (cash rent above GAAP rent) increases OE
    d["straight_line_adjustment"] = sl
    d["straight_line_increases_oe"] = [None if x is None else x < 0 for x in sl]
    # ---- EBITDAre, leverage, coverage
    interest, cap_int, tax = g("interest_expense"), g("interest_capitalized"), g("income_tax")
    d["ebitdare"] = [None if (ni[i] is None or interest[i] is None or da[i] is None or gains[i] is None)
                     else ni[i] + interest[i] + (tax[i] or 0.0) + da[i] - gains[i] - (g("gains_re_entities")[i] or 0.0) + (imp[i] or 0.0) for i in range(n)]
    debt, cash, sti = list(g("debt_total")), g("cash"), g("sti")
    dbs = ext_series(ri, "debt_total_bs")
    d["debt_from_extraction"] = [i for i in range(n) if debt[i] is None and dbs[i] is not None]
    debt = [x if x is not None else y for x, y in zip(debt, dbs)]
    d["net_debt"] = [None if (a is None or c is None) else a - c - (s or 0.0) for a, c, s in zip(debt, cash, sti)]
    d["nd_ebitdare"] = [None if (a is None or b is None or b <= 0) else a / b for a, b in zip(d["net_debt"], d["ebitdare"])]
    d["nd_ebitdare_state"] = []
    for nd_, eb in zip(d["net_debt"], d["ebitdare"]):
        if nd_ is None or eb is None:
            d["nd_ebitdare_state"].append(("missing", None))
        elif nd_ <= 0:
            d["nd_ebitdare_state"].append(("net_cash", nd_ / eb if eb > 0 else 0.0))
        elif eb <= 0:
            d["nd_ebitdare_state"].append(("ebitda_nonpositive", INF))
        else:
            d["nd_ebitdare_state"].append(("ratio", nd_ / eb))
    d["fixed_charges"] = [None if interest[i] is None else interest[i] + (cap_int[i] or 0.0) + (pref[i] or 0.0) for i in range(n)]
    d["fcc"] = [None if (a is None or b is None or b <= 0) else a / b for a, b in zip(d["ebitdare"], d["fixed_charges"])]
    # ---- near-term debt coverage (24 months)
    m1, m2, fac = list(g("mat_year1")), list(g("mat_year2")), ext_series(ri, "committed_undrawn_facilities")
    x1, x2 = ext_sum(ri, "mat_year1_x"), ext_sum(ri, "mat_year2_x")
    d["maturities_from_extraction"] = [i for i in range(n) if (m1[i] is None and x1[i] is not None) or (m2[i] is None and x2[i] is not None)]
    m1 = [a if a is not None else b for a, b in zip(m1, x1)]
    m2 = [a if a is not None else b for a, b in zip(m2, x2)]
    d["maturities_12m"] = m1
    d["maturities_24m"] = [None if (a is None or b is None) else a + b for a, b in zip(m1, m2)]
    d["facilities"] = fac
    d["ntdc"] = [None] * n
    for i in range(n):
        if d["maturities_24m"][i] is None or cash[i] is None or fac[i] is None:
            continue
        mat = d["maturities_24m"][i]
        d["ntdc"][i] = INF if mat <= 0 else (cash[i] + (sti[i] or 0.0) + fac[i]) / mat
    d["core_ffo_reported"], d["dev_gains_reported"] = ext_series(ri, "core_ffo_reported"), ext_series(ri, "dev_gains_reported")
    d["affo_reported"], d["sbc"] = ext_series(ri, "reported_affo"), g("sbc")
    d["core_ffo_ps_reported"] = ext_series(ri, "core_ffo_ps_reported")
    d["partnership_units_weighted"] = ext_series(ri, "partnership_units_weighted")
    # RP1a: near-term debt coverage on the debt maturing in the next 12 months (cash + short-term investments + undrawn committed facilities)
    d["ntdc12"] = [None] * n
    for i in range(n):
        if m1[i] is None or cash[i] is None or fac[i] is None:
            continue
        d["ntdc12"][i] = INF if m1[i] <= 0 else (cash[i] + (sti[i] or 0.0) + fac[i]) / m1[i]
    # Q2: company-reported EBITDAre (annual / trailing twelve months at the fiscal year end; extraction)
    d["ebitdare_reported"] = ext_series(ri, "ebitdare_reported")
    d["ebitdare_reconciliation_pct"] = [None if (a is None or b is None or b == 0) else (a - b) / abs(b) for a, b in zip(d["ebitdare"], d["ebitdare_reported"])]
    # ---- WACC proxy (latest year; market weights)
    d["wacc"] = {"value": None, "flags": []}
    mcap = None if (ri.price_current is None or g("shares_out")[-1] is None) else ri.price_current * g("shares_out")[-1]
    d["market_cap"] = mcap
    avg_debt = None if (debt[-1] is None or debt[-2] is None) else (debt[-1] + debt[-2]) / 2
    kd = _ratio(interest[-1], avg_debt)
    dnet = d["net_debt"][-1]
    if mcap is not None and kd is not None and dnet is not None:
        dd = max(dnet, 0.0)
        wd = dd / (dd + mcap)
        d["wacc"] = {"value": wd * kd * (1 - KD_TAX_REIT) + (1 - wd) * R_EQUITY, "kd": kd, "weight_debt": wd, "net_debt": dd, "market_cap": mcap,
                     "price": ri.price_current, "price_date": ri.price_date, "flags": []}
    # ---- incremental return: direct (extracted yields) else NOI proxy (needs same-property growth and growth capital)
    d["incremental"] = _incremental_return(ri, d)
    # ---- values (economic only with an economic basis; no proxy) and display-only reported leverage
    fv = ext_series(ri, "fair_value_real_estate")
    d["economic_value"] = fv
    d["economic_ltv"] = [None if (fv[i] is None or d["net_debt"][i] is None) else d["net_debt"][i] / fv[i] for i in range(n)]
    d["reported_leverage"] = [_ratio(a, b) for a, b in zip(debt, g("re_gross"))]
    d["stressed_ltv"] = _stressed_ltv(ri, d)
    # ---- operating data (extracted)
    d["occupancy"] = ext_series(ri, "occupancy")
    d["same_property_noi_growth"] = ext_series(ri, "same_property_noi_growth")
    d["largest_tenant"] = ext_series(ri, "largest_tenant_share")
    d["unencumbered_noi_share"] = ext_series(ri, "unencumbered_noi_share")
    d["unencumbered_assets_share"] = ext_series(ri, "unencumbered_assets_share")
    # ---- write-down flag
    imp5 = [x for x in tail(imp, 5) if x is not None]
    ren = g("re_net")[-1]
    d["writedowns_5y"] = sum(imp5) if imp5 else None
    d["writedowns_share_of_property"] = _ratio(d["writedowns_5y"], ren)
    # ---- profile check
    d["profile_check"] = _profile_check(ri, d)
    d["pe_nffo"] = [None if (p is None or e is None or e <= 0) else p / e for p, e in zip(ri.price_avg or [None] * n, d["nffo_ps"])]
    # dps: the tagged value is replaced by dividends paid / basic shares when it deviates by more than 3x (some filers tag a special or a per-class amount)
    dps, div, shb = g("dps"), g("dividends"), g("shares_basic")
    d["dps"], d["dps_flags"] = [], []
    for i in range(n):
        calc = _ratio(div[i], shb[i])
        if dps[i] is not None and calc and 1 / 3 <= dps[i] / calc <= 3:
            d["dps"].append(dps[i]); d["dps_flags"].append(None)
        elif calc:
            d["dps"].append(calc); d["dps_flags"].append("dps_derived_from_dividends_paid_tagged_dps_missing_or_inconsistent")
        else:
            d["dps"].append(dps[i]); d["dps_flags"].append(None)
    return d


INCREMENTAL_GROWTH = 0.025  # RE31: fixed long-term growth term (the RP1 terminal growth); the company's own same-property growth is not added (it is scored in Buffett 3.4.2)
DISPOSALS_LIMIT = 0.10      # NOI_PROXY: not computable when gross disposals over t-4 ... t exceed this share of the real estate at t-4


def noi_proxy_inputs(ri, d) -> dict:
    """The two NOI_PROXY validity inputs, reported for every company: net growth capital over t-4 ... t-1 (acquisitions + development - disposal proceeds) and the gross disposals over t-4 ... t as a share of the real estate at t-4."""
    n = ri.n
    g_ = ri.series
    if n < 5:
        return {"net_growth_capital": None, "gross_disposals": None, "re_t4": None, "disposals_share": None, "flags": ["fewer than 5 years"]}
    cap = []
    for i in range(n - 5, n - 1):
        acq = (g_("acq_real_estate")[i] or 0.0) + (g_("acq_business")[i] or 0.0)
        dev = g_("development")[i] or 0.0
        sale = g_("sale_proceeds")[i] or 0.0
        cap.append(acq + dev - sale)
    sales = [g_("sale_proceeds")[i] for i in range(n - 5, n)]
    disp = sum(x or 0.0 for x in sales)
    re4 = g_("re_gross")[n - 5] or g_("re_net")[n - 5]
    fl = (["disposal_proceeds_missing_in_some_years_counted_0"] if any(x is None for x in sales) else []) + ([] if re4 else ["real_estate_at_t-4_missing"])
    return {"net_growth_capital": sum(cap), "gross_disposals": disp, "re_t4": re4, "disposals_share": None if not re4 else disp / re4, "flags": fl}


def _incremental_return(ri, d) -> dict:
    """RE31: incremental return = weighted stabilized (initial) yield on acquisitions and developments (5 years, as disclosed) + 2.5% fixed growth; when no yield is disclosed the NOI_PROXY
    ((NOI_t - NOI_t-4 - organic NOI growth) / net growth capital + 2.5%) is computed. The proxy is valid only if net growth capital >= 5% of property value (RE22), and is not computable when net growth
    capital <= 0 or when gross disposals over t-4 ... t exceed 10% of the real estate at t-4."""
    import math
    n = ri.n
    sp = ext_series(ri, "same_property_noi_growth")
    spv = [x for x in sp[-5:] if x is not None]
    med_sp = median(spv) if len(spv) >= 3 else None
    pi = noi_proxy_inputs(ri, d)
    pairs = []
    for ykey, akey in (("acquisition_yield", "acquisition_invested"), ("development_yield", "development_invested")):
        ys, am = ext_series(ri, ykey), ext_series(ri, akey)
        for i in range(max(0, n - 5), n):
            if ys[i] is not None:
                pairs.append((ys[i], am[i]))
    if pairs:
        if all(a is not None and a > 0 for _, a in pairs):
            wy = sum(y * a for y, a in pairs) / sum(a for _, a in pairs)
            wnote = "weighted by invested amounts"
        else:
            wy = sum(y for y, _ in pairs) / len(pairs)
            wnote = "simple mean (invested amounts not all disclosed)"
        return {"basis": "direct", "value": wy + INCREMENTAL_GROWTH, "stabilized_yield": wy, "growth_term": INCREMENTAL_GROWTH, "same_property_median_not_used": med_sp, "n_yield_observations": len(pairs),
                "yield_weighting": wnote, "proxy_inputs": pi, "flags": []}
    noi = d["noi"]
    if n < 5 or noi[-1] is None or noi[-5] is None or len(spv) < 3:
        why = "no disclosed stabilized acquisition / development yield, and the NOI_PROXY needs NOI at t and t-4 plus at least 3 years of same-property NOI growth (organic growth)"
        return {"basis": None, "value": None, "reason": why, "proxy_inputs": pi, "flags": ["AI_extraction_needed"]}
    net_cap = pi["net_growth_capital"]
    fv = ext_series(ri, "fair_value_real_estate")[-1]
    g_ = ri.series
    # RE22: materiality base = economic property value when available, otherwise gross real estate at cost (never scored)
    prop, prop_basis = (fv, "economic value") if fv else (g_("re_gross")[-1] or g_("re_net")[-1], "gross real estate at cost (materiality test only, RE22)")
    common = {"net_growth_capital": net_cap, "property_base": prop, "property_base_kind": prop_basis, "proxy_inputs": pi}
    if net_cap <= 0:
        return {"basis": None, "value": None, "reason": f"NOI_PROXY not computable: net growth capital {net_cap / 1e9:,.2f}bn is not positive", **common, "flags": ["NOI_PROXY_net_capital_not_positive"]}
    if pi["disposals_share"] is not None and pi["disposals_share"] > DISPOSALS_LIMIT:
        return {"basis": None, "value": None, "reason": f"NOI_PROXY not computable: gross disposals over t-4 ... t are {pi['disposals_share']:.1%} of the real estate at t-4 (above 10%): the NOI change mixes sold assets", **common, "flags": ["NOI_PROXY_disposals_above_10pct"]}
    gl = [x if x is not None else med_sp for x in sp[-4:]]
    organic = noi[-5] * (math.prod(1 + x for x in gl) - 1)
    if prop is None or net_cap < 0.05 * prop:
        return {"basis": None, "value": None, "reason": f"NOI_PROXY not valid: net growth capital {net_cap / 1e9:,.2f}bn is below 5% of {prop_basis} ({'n/a' if prop is None else format(prop / 1e9, ',.1f') + 'bn'})",
                **common, "flags": ["NOI_PROXY_validity_test_failed"]}
    flags = ["NOI_PROXY"] + (["same_property_growth_gaps_filled_with_median"] if any(x is None for x in sp[-4:]) else [])
    return {"basis": "NOI_PROXY", "value": (noi[-1] - noi[-5] - organic) / net_cap + INCREMENTAL_GROWTH, "growth_term": INCREMENTAL_GROWTH, **common, "flags": flags}


def _stressed_ltv(ri, d) -> Optional[float]:
    snoi, sval = ext_series(ri, "stabilized_noi"), ext_series(ri, "stabilized_value")
    other = ext_series(ri, "other_property_value")  # carrying value of development, land and other non-stabilized property
    # RE26: numerator = total net debt (all debt, incl. debt on non-stabilized assets); denominator = stressed stabilized value + carrying value of the other property;
    # a missing carrying value of the other property makes the test missing (never assumed 0)
    if snoi[-1] is None or sval[-1] is None or d["net_debt"][-1] is None or sval[-1] <= 0 or other[-1] is None:
        return None
    cap = snoi[-1] / sval[-1]
    stressed = sval[-1] * cap / (cap + 0.01)
    return d["net_debt"][-1] / (stressed + other[-1])


def _last(ri, item):
    v = ext_series(ri, item)
    return v[-1]


def _profile_check(ri, d) -> dict:
    """S3 profile test (investment property / total assets >= 50% and rental revenue / total revenue >= 50%), RE10 (a company that fails is STANDARD) and RE11
    (when the lease-income or investment-property tag is missing the test runs on extracted data: revenue breakdown and real estate leased to tenants incl. PP&E)."""
    from .profile_flags import borderline_flag
    g = ri.series
    assets, ren = g("assets")[-1], g("re_net")[-1]
    rental, tot = g("rental_revenue")[-1], g("total_revenue")[-1]
    basis, notes = {"property": "XBRL tag", "rental": "XBRL tag"}, []
    x_assets, x_prop, x_rent, x_tot = _last(ri, "profile_total_assets"), _last(ri, "profile_property_value"), _last(ri, "profile_rental_revenue"), _last(ri, "profile_total_revenue")
    if ren is None or assets is None:
        if x_prop is not None and x_assets is not None:
            ren, assets, basis["property"] = x_prop, x_assets, "extracted (RE11: real estate leased to tenants carried in PP&E)"
        else:
            basis["property"] = "missing"
    if rental is None or tot is None:
        if x_rent is not None and x_tot is not None:
            rental, tot, basis["rental"] = x_rent, x_tot, "extracted (RE11: revenue breakdown from the 10-K)"
        else:
            basis["rental"] = "missing"
    a_share, r_share = _ratio(ren, assets), _ratio(rental, tot)
    intang = g("intangibles_net")[-1]
    if a_share is not None and a_share < PROFILE_ASSET_SHARE and intang and assets:
        # RE15: real estate includes acquired lease-related intangibles (in-place leases, tenant relationships tied to leased assets); the finite-lived acquired
        # intangibles (excluding goodwill) of tower / data-center companies are tenant-related and network-location intangibles
        a2 = (ren + intang) / assets
        notes.append(f"RE15: with acquired lease-related intangibles ({intang / 1e9:,.1f}bn) the share is {a2:.1%} (property alone {a_share:.1%})")
        basis["property"] += " + acquired lease-related intangibles (RE15)"
        a_share = a2
    asset_ok = None if a_share is None else a_share >= PROFILE_ASSET_SHARE
    rental_ok = None if r_share is None else r_share >= PROFILE_RENTAL_SHARE
    ok = None if (asset_ok is None or rental_ok is None) else (asset_ok and rental_ok)
    if ok is False:
        notes.append("fails the test -> STANDARD (RE10 / RE11)")
    return {"investment_property_share": a_share, "rental_revenue_share": r_share, "asset_ok": asset_ok, "rental_ok": rental_ok, "confirmed": ok, "basis": basis, "notes": notes,
            "assignment": "INCOME_REAL_ESTATE" if ok else ("STANDARD" if ok is False else "undetermined"),
            **borderline_flag({"investment_property_share": (a_share, PROFILE_ASSET_SHARE), "rental_revenue_share": (r_share, PROFILE_RENTAL_SHARE)})}


# ================================================================ adapters for the kept criteria
class _View:
    """Exposes real-estate series under the general model's names: net_income = normalized FFO, eps = normalized FFO per share, revenue = total revenue."""

    def __init__(self, ri, d):
        self._ri, self._d = ri, d
        self.n, self.fy, self.end = ri.n, ri.fy, ri.end
        self.price_avg, self.price_current = ri.price_avg, ri.price_current
        self.first_annual_report, self.as_of, self.profile = ri.first_annual_report, ri.as_of, PROFILE

    def series(self, name):
        m = {"net_income": self._d["norm_ffo"], "eps": self._d["nffo_ps"], "revenue": self._d["property_revenue_or_total"] if "property_revenue_or_total" in self._d else self._ri.series("total_revenue"),
             "shares": self._d.get("shares_eff") or self._ri.series("shares_dil"), "dps": self._d["dps"], "acquisitions": self._ri.series("acq_business")}
        return m[name] if name in m else self._ri.series(name)


def _gd(ri, d) -> dict:
    """The `d` dict the general criteria expect."""
    return {"fcf": d["oe"] if all(x is not None for x in tail(d["oe"], 5)) else d["norm_ffo"], "owner_earnings": d["oe"], "pe": d["pe_nffo"],
            "nd_ebitda": d["nd_ebitdare_state"], "net_margin": d["nffo_margin"]}


# ================================================================ BUFFETT QUALITY
def _median5(vals):
    v = clean(tail(vals, 5))
    return (median(v), len(v)) if len(v) >= 3 else (None, len(v))


def b31(ri, d):
    return [ai_pending(str(i), nm, 2.0, note="AI question") for i, nm in enumerate(
        ["Understandable business", "Predictable demand", "Simple economics", "Durable asset base", "Transparent reporting"], start=1)]


def b32(ri, d):
    items = [not_applicable("1a", "Gross margin level", 1.0, note="real estate: gross margin not applicable (matrix)"),
             not_applicable("1b", "Gross margin stability", 1.5, note="real estate: gross margin not applicable (matrix)")]
    om = tail(d["nffo_margin"], 5)
    ov = clean(om)
    a2a, a2b = [(0.04, 1.5), (0.12, 0)], [(-0.05, 0), (-0.01, 1.0)]
    if len(ov) < 3:
        items += [miss("2a", "Normalized FFO margin stability", 1.5, "fewer than 3 years of normalized FFO margin (FFO needs the gains-on-sale line)", a2a),
                  miss("2b", "No normalized FFO margin erosion", 1.0, "fewer than 3 years of normalized FFO margin", a2b)]
    else:
        items.append(thresholded("2a", "Normalized FFO margin stability", 1.5, max(ov) - min(ov), a2a, "", "normalized FFO margin range (5y)", {"nffo_margin": om}))
        if om[-1] is None:
            items.append(miss("2b", "No normalized FFO margin erosion", 1.0, "latest normalized FFO margin missing", a2b))
        else:
            items.append(thresholded("2b", "No normalized FFO margin erosion", 1.0, om[-1] - median(ov), a2b, "", "latest minus 5y median normalized FFO margin", {"nffo_margin": om}))
    items.append(not_applicable("3", "Persistent return", 2.0, note="real estate: measured in Buffett 3.4 (matrix)"))
    items.append(ai_pending("4", "Stable competitive position", 2.0, note="AI question"))
    items.append(ai_pending("5", "Clear moat", 1.0, note="AI question x0.5"))
    return items


def b33(ri, d):
    return B.c33(_View(ri, d), _gd(ri, d))


def b34(ri, d):
    items = []
    inc, wacc = d["incremental"], d["wacc"]
    a1 = [(0.0, 0), (0.01, 1), (0.02, 2), (0.03, 3), (0.04, 4)]  # RE23: weight 4
    if inc["value"] is None or wacc["value"] is None:
        why = inc.get("reason") if inc["value"] is None else "WACC proxy not computable (price, shares, debt or interest missing)"
        items.append(miss("1", "Incremental spread over WACC", 4, why, a1, inputs={"metric_basis": inc.get("basis"), "wacc": wacc}, flags=inc.get("flags", [])))
    else:
        items.append(thresholded("1", "Incremental spread over WACC", 4, inc["value"] - wacc["value"], a1, "", "incremental return - WACC proxy",
                                 {"metric_basis": inc["basis"], "incremental_return": inc["value"], "wacc": wacc}, inc.get("flags", []) + ([] if inc["basis"] == "direct" else ["proxy_confidence_lower"])))
    a2 = [(0.0, 0), (0.02, 3), (0.04, 6)]  # RE23: weight 6
    m, nv = _median5(d["same_property_noi_growth"])
    items.append(miss("2", "Same-property NOI growth", 6, "same-property NOI growth not extracted (AI extraction needed; fewer than 3 years)", a2,
                      inputs={"same_property_noi_growth": d["same_property_noi_growth"]}) if m is None else
                 thresholded("2", "Same-property NOI growth", 6, m, a2, "", "5y median same-property NOI growth", {"same_property_noi_growth": d["same_property_noi_growth"]}))
    a3 = [(0.03, 5), (0.10, 0)]  # RE19: NOI margin stability (5-year range, max - min); the level reflects the lease structure, not quality
    mv = clean(tail(d["noi_margin"], 5))
    items.append(miss("3", "NOI margin stability", 5, "NOI margin computable for fewer than 3 of the last 5 years", a3, inputs={"noi_margin": tail(d["noi_margin"], 5)}) if len(mv) < 3 else
                 thresholded("3", "NOI margin stability", 5, max(mv) - min(mv), a3, "", "5-year range (max - min) of the NOI margin", {"noi_margin": tail(d["noi_margin"], 5), "noi_basis": d["noi_basis"][-1]},
                             ["partial_window"] if len(mv) < 5 else []))
    return items


def _decline_count_item(id_, name, mx, series, thr, anchors, label, basis_list, flags):
    s = tail(series, 5)
    fl = [fell_more_than(a, b, thr) for a, b in zip(s[:-1], s[1:])]
    cnt, nv, part = count_scaled(fl, 4)
    inputs = {"series": s, "metric_basis": "FFO_PROXY" if "FFO_PROXY" in basis_list else "OE"}
    if cnt is None:
        return miss(id_, name, mx, "fewer than 3 valid transitions (normalized FFO / OE per share missing)", anchors, inputs=inputs, flags=flags)
    return thresholded(id_, name, mx, cnt, anchors, "", label, inputs, flags + (["partial_window"] if part else []) + (["FFO_PROXY"] if "FFO_PROXY" in basis_list else []))


def b35(ri, d):
    items = []
    s = tail(d["oe_ps"], 5)
    basis = [x for x in tail(d["oe_basis"], 5) if x]
    a1 = [(0.0, 0), (0.02, 2), (0.04, 4), (0.06, 6), (0.08, 8)]
    if s[0] is None or s[-1] is None or s[0] <= 0 or s[-1] <= 0:
        items.append(miss("1", "OE per share growth", 8, "OE per share (or the FFO proxy) missing or non-positive at the start / end of the window", a1,
                          inputs={"oe_ps": s, "metric_basis": "FFO_PROXY" if "FFO_PROXY" in basis else "OE"}))
    else:
        items.append(thresholded("1", "OE per share growth", 8, (s[-1] / s[0]) ** 0.25 - 1, a1, "", "5-year CAGR of OE per share",
                                 {"oe_ps": s, "metric_basis": "FFO_PROXY" if "FFO_PROXY" in basis else "OE"}, ["FFO_PROXY"] if "FFO_PROXY" in basis else []))
    a2 = [(0, 7), (1, 5.25), (2, 3.5), (3, 1.75), (4, 0)]
    items.append(_decline_count_item("2", "OE per share stability", 7, d["oe_ps"], 0.05, a2, "transitions (of 4) with OE per share down more than 5%", basis, []))
    return items


def b36(ri, d):
    items = []
    state, ratio = d["nd_ebitdare_state"][-1]
    a1 = [(5.0, 4), (9.0, 0)]
    ins = {"net_debt": d["net_debt"][-1], "ebitdare": d["ebitdare"][-1]}
    if state == "missing":
        items.append(miss("1", "Net debt / EBITDAre", 4, "net debt or EBITDAre missing (gains-on-sale line, interest, D&A or debt tag)", a1, inputs=ins))
    elif state == "net_cash":
        items.append(scored("1", "Net debt / EBITDAre", 4, 4.0, metric=ratio, metric_label="net debt / EBITDAre", thresholds=describe(a1), inputs=ins, note="net cash = full points"))
    elif state == "ebitda_nonpositive":
        items.append(zero("1", "Net debt / EBITDAre", 4, None, a1, "", "net debt / EBITDAre", ins, ["ebitdare_nonpositive_with_net_debt"]))
    else:
        items.append(thresholded("1", "Net debt / EBITDAre", 4, ratio, a1, "", "net debt / EBITDAre (latest)", ins, ["JV_debt_not_included"]))
    a2 = [(1.5, 0), (2.0, 1), (2.5, 2), (3.0, 2.67), (4.0, 3.33), (5.0, 4)]
    fcc = d["fcc"][-1]
    items.append(miss("2", "Fixed-charge coverage", 4, "EBITDAre or fixed charges missing", a2) if fcc is None else
                 thresholded("2", "Fixed-charge coverage", 4, fcc, a2, "", "EBITDAre / (interest + capitalized interest + preferred dividends)", {"fixed_charges": d["fixed_charges"][-1]}))
    a3 = [(0.30, 2), (0.60, 0)]
    ltv = d["economic_ltv"][-1]
    items.append(miss("3", "Economic LTV", 2, "no economic value basis (US GAAP without a disclosed fair value of real estate; no proxy)", a3,
                      inputs={"reported_basis_leverage_display_only": d["reported_leverage"][-1]}) if ltv is None else
                 thresholded("3", "Economic LTV", 2, ltv, a3, "", "net debt / economic property value", {"economic_value": d["economic_value"][-1]}))
    return items


def b37(ri, d):
    gd, v = _gd(ri, d), _View(ri, d)
    items = B.c37(v, gd)
    # 4 distributions: dividends / OE (FFO proxy flagged), <=100% = 2, >=150% = 0
    a4 = [(1.0, 2), (1.5, 0)]
    div = tail(ri.series("dividends"), 5)
    base = tail(d["oe"], 5) if all(x is not None for x in tail(d["oe"], 5)) else tail(d["norm_ffo"], 5)
    basis = "OE" if base is not None and all(x is not None for x in tail(d["oe"], 5)) else "FFO_PROXY"
    pairs = [(a, b) for a, b in zip(div, base) if a is not None and b is not None]
    new = (miss("4", "Distributions supported by owner earnings", 2, "fewer than 3 paired years of dividends and OE / normalized FFO", a4) if len(pairs) < 3 else
           (zero("4", "Distributions supported by owner earnings", 2, None, a4, "", "dividends / OE", {"metric_basis": basis}, ["total_base_nonpositive"]) if sum(b for _, b in pairs) <= 0 else
            thresholded("4", "Distributions supported by owner earnings", 2, sum(a for a, _ in pairs) / sum(b for _, b in pairs), a4, "", "dividends / OE (5y)",
                        {"metric_basis": basis}, ["FFO_PROXY"] if basis == "FFO_PROXY" else [])))
    items = [new if i.id == "4" else i for i in items]
    return items


def b38(ri, d):
    gd = _gd(ri, d)
    gd["fcf"] = d["oe_ps"]  # smoothed OE per share growth (R14); FFO proxy flagged through metric_basis
    items = B.c38(_View(ri, d), gd)
    basis = [x for x in tail(d["oe_basis"], 5) if x]
    out = []
    for i in items:
        if i.id == "3":
            i.inputs = {**(i.inputs or {}), "metric_basis": "FFO_PROXY" if "FFO_PROXY" in basis else "OE"}
            if "FFO_PROXY" in basis:
                i.flags = list(i.flags or []) + ["FFO_PROXY"]
        out.append(i)
    return out


B_CRITERIA = [("3.1", "Simple, understandable business", b31), ("3.2", "Moat", b32), ("3.3", "Consistent profitability", b33), ("3.4", "Return on capital", b34),
              ("3.5", "Owner earnings", b35), ("3.6", "Balance sheet and debt", b36), ("3.7", "Management and capital allocation", b37), ("3.8", "Quality, sustainable growth", b38)]


def realestate_buffett_quality(ri, d) -> ModelResult:
    return evaluate_model("buffett_quality_real_estate", [evaluate_criterion(i, n, fn(ri, d)) for i, n, fn in B_CRITERIA])


# ================================================================ GRAHAM QUALITY
def g31(ri, d):
    return G.c31(_View(ri, d), _gd(ri, d))


def g32(ri, d):
    a1 = [(1.5, 0), (2.0, 1.75), (2.5, 3.5), (3.0, 4.8), (4.0, 6.1), (5.0, 7)]
    fcc = d["fcc"][-1]
    items = [miss("1", "Fixed-charge coverage", 7, "EBITDAre or fixed charges missing", a1) if fcc is None else
             thresholded("1", "Fixed-charge coverage", 7, fcc, a1, "", "EBITDAre / fixed charges (latest)", {"fixed_charges": d["fixed_charges"][-1]})]
    a2 = [(0.5, 0), (0.75, 2), (1.0, 4), (1.25, 5.5), (1.5, 7), (2.0, 8)]
    nt = d["ntdc"][-1]
    if nt is None:
        why = ("debt maturities (XBRL) missing" if d["maturities_24m"][-1] is None else "committed undrawn facilities not extracted (AI extraction needed)")
        items.append(miss("2", "Near-term debt coverage (24 months)", 8, why, a2, inputs={"maturities_24m": d["maturities_24m"][-1], "facilities": d["facilities"][-1]}))
    elif nt == INF:
        items.append(scored("2", "Near-term debt coverage (24 months)", 8, 8.0, metric=None, metric_label="NTDC", thresholds=describe(a2), note="no maturities within 24 months = full score"))
    else:
        items.append(thresholded("2", "Near-term debt coverage (24 months)", 8, nt, a2, "", "(cash + short-term investments + committed facilities) / debt due in 24 months",
                                 {"maturities_24m": d["maturities_24m"][-1], "facilities": d["facilities"][-1]}))
    return items


def g33(ri, d):
    state, ratio = d["nd_ebitdare_state"][-1]
    a1 = [(3.0, 7), (4.0, 6.3), (5.0, 5.6), (6.0, 4.9), (8.0, 3.5), (10.0, 2.1), (12.0, 1.05), (15.0, 0)]
    ins = {"net_debt": d["net_debt"][-1], "ebitdare": d["ebitdare"][-1]}
    if state == "missing":
        items = [miss("1", "Net debt / EBITDAre", 7, "net debt or EBITDAre missing", a1, inputs=ins)]
    elif state == "net_cash":
        items = [scored("1", "Net debt / EBITDAre", 7, 7.0, metric=ratio, metric_label="net debt / EBITDAre", thresholds=describe(a1), inputs=ins, note="net cash = full points")]
    elif state == "ebitda_nonpositive":
        items = [zero("1", "Net debt / EBITDAre", 7, None, a1, "", "net debt / EBITDAre", ins, ["ebitdare_nonpositive_with_net_debt"])]
    else:
        items = [thresholded("1", "Net debt / EBITDAre", 7, ratio, a1, "", "net debt / EBITDAre (latest)", ins)]
    a2 = [(0.20, 0), (0.60, 4)]
    u, basis = d["unencumbered_noi_share"][-1], "unencumbered NOI share"
    if u is None:
        u, basis = d["unencumbered_assets_share"][-1], "unencumbered assets share (fallback, flagged)"
    items.append(miss("2", "Financial flexibility", 4, "unencumbered NOI (or assets) not extracted (AI extraction needed)", a2) if u is None else
                 thresholded("2", "Financial flexibility", 4, u, a2, "", basis, {"metric_basis": basis}, [] if "NOI" in basis and "fallback" not in basis else ["unencumbered_assets_fallback"]))
    a3 = [(0.35, 4), (0.45, 2), (0.60, 0)]
    sl = d["stressed_ltv"]
    items.append(miss("3", "Stressed economic LTV", 4, "not computable: needs a stabilized portfolio with economic value and matching NOI (extracted); no artificial test", a3) if sl is None else
                 thresholded("3", "Stressed economic LTV", 4, sl, a3, "", "net debt / stressed value (cap rate +1pp)", {}))
    return items


def g34(ri, d):
    return G.c34(_View(ri, d), _gd(ri, d))


def g35(ri, d):
    v, gd = _View(ri, d), _gd(ri, d)
    items = G.c35(v, gd)
    if len(items) < 4 or items[0].state == "true_zero":
        return items
    a4 = [(0.8, 2), (1.0, 1), (1.2, 0)]
    if all(x is not None for x in tail(d["oe"], 5)):
        s_div, s_oe, nn = _paired(ri.series("dividends"), d["oe"])
        new = (miss("4", "Cash-flow coverage (dividends / OE)", 2, "fewer than 3 paired years", a4) if s_div is None else
               (zero("4", "Cash-flow coverage (dividends / OE)", 2, None, a4, "", "dividends / OE", {}, ["total_oe_nonpositive"]) if s_oe <= 0 else
                thresholded("4", "Cash-flow coverage (dividends / OE)", 2, s_div / s_oe, a4, "", "dividends / OE (5y)", {"metric_basis": "OE"})))
    else:
        new = miss("4", "Cash-flow coverage (dividends / OE)", 2, "OE is a proxy (maintenance capex / TI-LC not extracted): level item missing by rule", a4, inputs={"metric_basis": "FFO_PROXY"})
    return [new if i.id == "4" else i for i in items]


def _paired(a, b):
    pairs = [(x, y) for x, y in zip(tail(a, 5), tail(b, 5)) if x is not None and y is not None]
    if len(pairs) < 3:
        return None, None, len(pairs)
    return sum(x for x, _ in pairs), sum(y for _, y in pairs), len(pairs)


def g36(ri, d):
    return G.c36(_View(ri, d), _gd(ri, d))


def g37(ri, d):
    items = []
    util = ri.utilization
    a1 = [(0.80, 0), (0.85, 1), (0.89, 2), (0.92, 3), (0.95, 4)]
    if util == "not_applicable":
        items.append(not_applicable("1", "Utilization", 4, note="communication towers: no occupancy metric (table A); resilience through organic revenue growth in 3.7.2"))
    else:
        m, nv = _median5(d["occupancy"])
        label = "occupancy" if util == "occupancy" else "leased capacity / available capacity"
        if m is None:
            items.append(miss("1", "Utilization (" + label + ")", 4, "occupancy / mapped metric not extracted (AI extraction needed; fewer than 3 years)", a1, inputs={"occupancy": d["occupancy"]}))
        else:
            it = thresholded("1", "Utilization (" + label + ")", 4, m, a1, "", "5y median " + label, {"occupancy": d["occupancy"]})
            lat = d["occupancy"][-1]
            if lat is not None and m - lat > 0.03 and it.points > 2:
                it = thresholded("1", "Utilization (" + label + ")", 4, m, a1, "", "5y median " + label + "; guardrail: latest below the median by >3pp", {"occupancy": d["occupancy"]},
                                 ["guardrail_latest_below_median_cap_2"])
                it.points = 2.0
            items.append(it)
    a2 = [(0, 4), (1, 3), (2, 2), (3, 1), (4, 0)]
    sp = tail(d["same_property_noi_growth"], 5)
    vals = [x for x in sp[1:] if x is not None]
    if len(vals) < 3:
        items.append(miss("2", "Property income resilience", 4, "same-property NOI growth not extracted (AI extraction needed)" if ri.ticker != "AMT" else "organic revenue growth not extracted (AI extraction needed)",
                          a2, inputs={"same_property_noi_growth": sp}))
    else:
        falls = sum(1 for x in vals if x < -0.03)
        scaled = falls * 4 / len(vals)
        items.append(thresholded("2", "Property income resilience", 4, scaled, a2, "", "transitions (of 4) with same-property NOI down more than 3%", {"same_property_noi_growth": sp},
                                 ["partial_window"] if len(vals) < 4 else []))
    a3 = [(0.05, 2), (0.10, 1.5), (0.15, 1), (0.20, 0.5), (0.25, 0)]
    lt = d["largest_tenant"][-1]
    if ri.asset_type in ("residential", "self-storage"):
        items.append(not_applicable("3", "Tenant concentration", 2, note=f"{ri.asset_type}: tenants are individuals, concentration is economically irrelevant (interpretation of 'not applicable only when economically irrelevant'; to be confirmed)"))
        return items
    items.append(miss("3", "Tenant concentration", 2, "largest tenant share not extracted (AI extraction needed)", a3) if lt is None else
                 thresholded("3", "Tenant concentration", 2, lt, a3, "", "largest independent tenant share of rent / NOI", {}))
    return items


def g38(ri, d):
    basis = [x for x in tail(d["oe_basis"], 5) if x]
    proxy = "FFO_PROXY" in basis
    a1 = [(0, 5), (1, 3.75), (2, 2.5), (3, 1.25), (4, 0)]
    items = [_decline_count_item("1", "OE stability", 5, d["oe_ps"], 0.05, a1, "transitions (of 4) with OE per share down more than 5%", basis, [])]
    a2 = [(0.01, 3), (0.02, 2.5), (0.03, 2), (0.04, 1), (0.05, 0)]
    oe5 = tail(d["oe"], 5)
    diag = {"oe_to_ffo_diagnostic": [None if (o is None or f_ is None or f_ <= 0) else o / f_ for o, f_ in zip(oe5, tail(d["norm_ffo"], 5))]}
    if proxy or len(basis) < 5:
        items.append(miss("2", "Reported vs economic earnings", 3, "OE is a proxy or missing: the gap is not computed (rule)", a2, inputs={"metric_basis": "FFO_PROXY" if proxy else None, **diag}))
    elif any(o is None or o <= 0 for o in oe5):  # RE27: requires positive OE (and full maintenance data, i.e. OE basis in all five years)
        items.append(miss("2", "Reported vs economic earnings", 3, "RE27: OE is not positive in all five years (the growth gap is not meaningful)", a2, inputs=diag))
    else:
        gaps = []
        for a, b, c, e in zip(tail(d["nffo_ps"], 5)[:-1], tail(d["nffo_ps"], 5)[1:], tail(d["oe_ps"], 5)[:-1], tail(d["oe_ps"], 5)[1:]):
            if None in (a, b, c, e) or a <= 0 or c <= 0:
                continue
            gaps.append(max(0.0, (b / a - 1) - (e / c - 1)))
        items.append(miss("2", "Reported vs economic earnings", 3, "fewer than 2 valid transitions (a transition whose base is <= 0 in either series is excluded)", a2) if len(gaps) < 2 else
                     thresholded("2", "Reported vs economic earnings", 3, median(gaps), a2, "", "median growth gap (normalized FFO per share - OE per share), penalized only when FFO grows faster", {"gaps": gaps, **diag}))
    sh = tail(ri.series("shares_out"), 5)
    oe = tail(d["oe_ps"], 5)
    if sh[0] is None or sh[-1] is None or sh[0] <= 0:
        items.append(miss("3", "Per-share capital discipline", 2, "share counts missing", None))
    else:
        sg = (sh[-1] / sh[0]) ** 0.25 - 1
        if sg <= 0.01:
            items.append(scored("3", "Per-share capital discipline", 2, 2.0, metric=sg, metric_label="share CAGR", thresholds="<=1% = 2", inputs={"share_cagr": sg}))
        elif oe[0] is None or oe[-1] is None or oe[0] <= 0 or oe[-1] <= 0:
            items.append(miss("3", "Per-share capital discipline", 2, "share CAGR above 1% and OE per share growth not computable", None, inputs={"share_cagr": sg}))
        else:
            gr = (oe[-1] / oe[0]) ** 0.25 - 1
            pts = 2.0 if gr >= 0.04 else 1.5 if gr >= 0.02 else 1.0 if gr >= 0.0 else 0.5 if gr > -0.02 else 0.0
            items.append(scored("3", "Per-share capital discipline", 2, pts, metric=gr, metric_label="OE per share CAGR (share CAGR > 1%)",
                                thresholds=">=4% = 2, 2-4% = 1.5, 0-2% = 1, -2-0% = 0.5, <=-2% = 0", inputs={"share_cagr": sg, "metric_basis": "FFO_PROXY" if proxy else "OE"},
                                flags=["FFO_PROXY"] if proxy else []))
    return items


G_CRITERIA = [("3.1", "Company size and business stability", g31), ("3.2", "Financial condition and liquidity", g32), ("3.3", "Debt and balance-sheet conservatism", g33),
              ("3.4", "Earnings stability", g34), ("3.5", "Dividend history", g35), ("3.6", "Moderate earnings growth", g36), ("3.7", "Quality of equity and assets", g37),
              ("3.8", "Earnings quality and dilution", g38)]


def realestate_graham_quality(ri, d) -> ModelResult:
    return evaluate_model("graham_quality_real_estate", [evaluate_criterion(i, n, fn(ri, d)) for i, n, fn in G_CRITERIA])


# ================================================================ PRICING (RP1-RP3; spec 2026-10-14_22-30, section 6)
REQUIRED_RETURN = 0.10        # RP1: conservative required return (model parameter, not a measured cost of equity)
LEVERAGE_BLOCK = 8.0          # RP1a: no Buffett price score above this net debt / EBITDAre
RP5_GAP = 0.03               # RP5: market-distress flag when the market-implied cap rate exceeds the conservative one by more than this
LIQUIDITY_BLOCK = 1.0         # RP1a: no Buffett price score below this 12-month liquidity coverage
LEVERAGE_BORDERLINE = (7.5, 8.5)  # RP1a: flagged borderline (display only)
CAP_SPREAD, CAP_FLOOR = 0.03, 0.06  # RP2: conservative cap rate = max(10-year government yield + 3 pp, 6%)
NON_NOI_MATERIAL = 0.10       # RP2: unidentified non-NOI assets above 10% of total assets -> no Graham price score
GOV_YIELDS_CSV = Path(__file__).resolve().parents[2] / "scripts" / "gov_yields.csv"


def gov_yield(currency: str = "USD", path: Path = GOV_YIELDS_CSV):
    """Latest monthly average of the 10-year government yield (fraction) and its period ('YYYY-MM'); when no monthly row exists the latest annual average and its year.
    Returns (yield, period, kind) with kind 'monthly' / 'annual', or (None, None, None)."""
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh) if r["currency"] == currency]
    except OSError:
        return None, None, None
    monthly = [r for r in rows if not str(r["year"]).isdigit()]
    if monthly:
        r = max(monthly, key=lambda x: x["year"])
        return float(r["yield_pct"]) / 100.0, r["year"], "monthly"
    annual = [r for r in rows if str(r["year"]).isdigit()]
    if not annual:
        return None, None, None
    r = max(annual, key=lambda x: int(x["year"]))
    return float(r["yield_pct"]) / 100.0, str(r["year"]), "annual"


def conservative_cap_rate(currency: str = "USD", path: Path = GOV_YIELDS_CSV) -> dict:
    """RP2: max(latest monthly average 10-year yield + 3 pp, 6%); falls back to the latest annual average (flagged) and then to the 6% floor (flagged)."""
    y, per, kind = gov_yield(currency, path)
    if y is None:
        return {"value": CAP_FLOOR, "gov_yield": None, "gov_year": None, "gov_period": None, "gov_kind": None, "currency": currency, "flags": ["gov_yield_missing_floor_used"]}
    fl = [] if kind == "monthly" else [f"gov_yield_is_annual_average_{per}_monthly_not_available"]
    return {"value": max(y + CAP_SPREAD, CAP_FLOOR), "gov_yield": y, "gov_year": per, "gov_period": per, "gov_kind": kind, "currency": currency, "flags": fl}


def _leverage_guard(d, quality) -> dict:
    """RP1a: hard guards (net debt / EBITDAre > 8x, EBITDAre <= 0, debt missing) and the quality checks that must be computed (coverage; near-term debt coverage on the debt maturing in the next
    12 months and the undrawn committed facilities). 7.5x-8.5x is flagged borderline (display; the block is unchanged)."""
    st, ratio = d["nd_ebitdare_state"][-1]
    eb, nd = d["ebitdare"][-1], d["net_debt"][-1]
    hard = []
    if nd is None:
        hard.append("debt data missing")
    if eb is None:
        hard.append("EBITDAre missing")
    elif eb <= 0:
        hard.append("EBITDAre <= 0")
    if st == "ratio" and ratio is not None and ratio > LEVERAGE_BLOCK:
        hard.append(f"net debt / EBITDAre {ratio:.2f}x > {LEVERAGE_BLOCK:g}x")
    ntdc12 = d["ntdc12"][-1]
    if ntdc12 is not None and ntdc12 < LIQUIDITY_BLOCK:  # RP1a: 12-month liquidity coverage below 1.0x (the company depends on new market funding within a year)
        hard.append(f"12-month liquidity coverage {ntdc12:.2f}x < {LIQUIDITY_BLOCK:g}x")
    checks = []
    if d["ntdc12"][-1] is None:
        checks.append("near-term debt coverage (12 months) not computed (maturities or facilities missing)")
    if quality is not None and quality.status != "full":
        checks.append(f"Buffett quality coverage {quality.coverage:.0%} (status {quality.status}): not full")
    borderline = st == "ratio" and ratio is not None and LEVERAGE_BORDERLINE[0] <= ratio <= LEVERAGE_BORDERLINE[1]
    return {"blocked": bool(hard or checks), "hard": hard, "quality_checks": checks, "reasons": hard + checks, "nd_ebitdare": ratio if st in ("ratio", "net_cash") else None,
            "borderline": borderline, "ntdc12": d["ntdc12"][-1]}


OCCUPANCY_DROP_PP = 0.02  # RP1b


def recent_trend(ri, d) -> dict:
    """RP1b: latest-year condition added to the growth gate. Same-property NOI fell in the latest year, or occupancy fell by more than 2 pp -> stage-1 growth = 0.
    Same-property NOI missing -> the latest-year revenue decline is tested instead; occupancy not applicable (table A) or not available for both years -> that part is not tested."""
    out: dict = {"tested": [], "not_tested": [], "failed": [], "inputs": {}}
    sp = d["same_property_noi_growth"][-1]
    rev = ri.series("total_revenue")
    if sp is not None:
        out["tested"].append("same-property NOI growth")
        out["inputs"]["same_property_noi_growth"] = sp
        if sp < 0:
            out["failed"].append(f"same-property NOI growth {sp:.1%} in the latest year")
    elif len(rev) >= 2 and rev[-1] is not None and rev[-2] not in (None, 0):
        out["tested"].append("latest-year revenue (same-property NOI missing)")
        out["inputs"]["revenue_change"] = rev[-1] / rev[-2] - 1
        if rev[-1] < rev[-2]:
            out["failed"].append(f"revenue {rev[-1] / rev[-2] - 1:.1%} in the latest year (same-property NOI missing)")
    else:
        out["not_tested"].append("same-property NOI and revenue missing")
    if ri.utilization in ("not applicable", "not_applicable", "none", None, "") or ri.asset_type == "communication towers":
        out["not_tested"].append("occupancy not applicable (table A)")
    else:
        o1, o0 = d["occupancy"][-1], d["occupancy"][-2] if len(d["occupancy"]) > 1 else None
        if o1 is None or o0 is None:
            out["not_tested"].append("occupancy missing for the latest or the previous year")
        else:
            out["tested"].append("occupancy")
            out["inputs"]["occupancy_change_pp"] = (o1 - o0) * 100
            if o0 - o1 > OCCUPANCY_DROP_PP + 1e-12:
                out["failed"].append(f"occupancy {(o1 - o0) * 100:+.1f} pp in the latest year")
    return out


def _buffett_base_growth(ri, d, series) -> dict:
    """Base and stage-1 growth exactly as the general model v1.2 (median of the last 5 years rolled forward under G1; median-vs-median or R14 growth clipped to 0-12%;
    growth gate on normalized FFO per share and revenue), on a per-share series."""
    out: dict = {"flags": []}
    last5 = tail(series, 5)
    if any(x is None for x in last5):
        return {**out, "ok": False, "reason": "per-share earnings are not available in all of the last 5 years (FFO_PROXY years are never a level for OE); the median base needs all 5"}
    med = median(last5)
    out["last5"], out["median"] = last5, med
    if med <= 0:
        return {**out, "ok": False, "reason": "per-share base <= 0"}
    prev5 = series[-10:-5] if len(series) >= 10 else []
    if len(prev5) == 5 and all(x is not None for x in prev5) and median(prev5) > 0:
        graw = (med / median(prev5)) ** (1 / 5) - 1
        g1 = clip(graw, *B.STAGE1_CAP)
        out["growth_method"] = "median(last 5) vs median(previous 5), annualized"
        if g1 != graw:
            out["flags"].append(f"growth_clipped ({graw:.1%} -> {g1:.1%})")
    else:
        g = smoothed_growth(last5)
        out["growth_method"] = "R14 smoothed growth (fewer than 10 years)"
        out["flags"].append("growth_fallback_r14")
        if g["kind"] == "insufficient":
            return {**out, "ok": False, "reason": "per-share earnings missing in the first / last two years of the window (growth not computable)"}
        if g["kind"] == "growth":
            g1 = clip(g["value"], *B.STAGE1_CAP)
            if g1 != g["value"]:
                out["flags"].append(f"growth_clipped ({g['value']:.1%} -> {g1:.1%})")
        else:
            g1 = 0.0
            out["flags"].append(f"growth_not_measurable ({g['kind']}): stage-1 growth set to 0% (assumption)")
    out["growth_before_gate"] = g1
    gate = B.growth_gate(_View(ri, d))  # revenue and normalized FFO per share
    out["growth_gate"] = gate
    if not gate["passed"]:
        out["flags"].append("growth_gate_failed (" + "; ".join(gate["failing"]) + ")")
        g1 = 0.0
    rt = recent_trend(ri, d)  # RP1b
    out["recent_trend"] = rt
    if rt["failed"]:
        out["flags"].append("growth_gate_recent_trend (" + "; ".join(rt["failed"]) + ")")
        g1 = 0.0
    base = med * (1 + g1) ** 2
    if last5[-1] < med:
        base = med
        out["flags"].append("G1_no_roll_latest_below_5y_median")
    return {**out, "ok": True, "g1": g1, "base": base}


def _dcf_ps(base, g1, r):
    return B.dcf_fair_value(base, g1, 0.0, 1.0, r=r)["fair_value_per_share"]  # flows are per share and after interest: no debt subtraction, no excess cash


def re_buffett_price(ri, d, quality, r: float = REQUIRED_RETURN) -> dict:
    """RP1 / RP1a / RP3 (Buffett)."""
    out: dict = {"model": "buffett_price_real_estate", "method": "dcf_oe_per_share_no_debt_subtraction", "discount_rate": r, "flags": []}
    out["guard"] = _leverage_guard(d, quality)
    price = ri.price_current
    out["price_current"] = price
    bg = _buffett_base_growth(ri, d, d["oe_ps_strict"])
    out["base_growth"] = bg
    out["flags"] += bg.get("flags", [])
    # analysis only: the same DCF on normalized FFO per share (before recurring capex; overstates OE; never a value or a buy price)
    pg = _buffett_base_growth(ri, d, d["nffo_ps"])
    out["indicative_ffo_dcf_per_share"] = _dcf_ps(pg["base"], pg["g1"], r) if pg["ok"] else None
    if not bg["ok"]:
        return {**out, "state": "cannot_be_valued", "reason": bg["reason"], "fair_value": None, "price_score": {"state": "not_applicable", "points": None}, "buy_price": None, "label": None}
    fv = _dcf_ps(bg["base"], bg["g1"], r)
    out["base"], out["stage1_growth"] = bg["base"], bg["g1"]
    if fv <= 0:  # C15
        return {**out, "state": "cannot_be_valued", "reason": "cannot be valued (modeled value <= 0)", "fair_value": None, "modeled_value_nonpositive": fv,
                "price_score": {"state": "score", "points": 0.0, "reason": "C15: value <= 0 -> price score 0"}, "buy_price": None, "label": None}
    out.update({"state": "valued", "fair_value": fv})
    out["sensitivities"] = {name: _dcf_ps(bg["base"], bg["g1"] + dg, r + dr)
                            for name, (dr, dg) in {"r-1pp": (-0.01, 0.0), "r+1pp": (0.01, 0.0), "g-1pp": (0.0, -0.01), "g+1pp": (0.0, 0.01)}.items()}
    if out["guard"]["blocked"]:
        out["label"] = "not a buy price"
        out["price_score"] = {"state": "blocked", "points": None, "reason": "; ".join(out["guard"]["reasons"])}
        out["buy_price"] = None
        return out
    out["label"] = None
    if price is None:
        out["price_score"] = {"state": "missing", "points": None, "reason": "no current price"}
    else:
        disc = (fv - price) / fv
        out["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, B.PRICE_ANCHORS), "anchors": describe(B.PRICE_ANCHORS)}
    out["buy_price"] = B._buy_price(fv, quality, B.MARGIN_ANCHORS)
    return out


def _bsa_classes(ri) -> tuple:
    """RP2a: sums per class of the extracted FY balance-sheet lines (bsa_<class>__<slug>) for the latest fiscal year; classes noi | carry | carryfin | inre | wc | excl | other."""
    cls: dict = {}
    lines: list = []
    for item in (ri.reg or {}):
        if item.startswith("bsa_") and "__" in item:
            c, slug = item[4:].split("__", 1)
            v = ext_series(ri, item)[-1]
            if v is not None:
                cls[c] = cls.get(c, 0.0) + v
                lines.append((c, slug, v))
    return cls, lines


def _share_basis(ri, d) -> dict:
    """RP2b: noncontrolling interests and the share count. OP units are never both in the shares and deducted as NCI."""
    g = ri.series
    sh = (d.get("shares_eff") or g("shares_dil"))[-1]
    nci_total, nci_op_x, nci_lp = g("nci_total")[-1], g("nci_op")[-1], g("nci_lp")[-1]
    redeem = g("nci_redeemable")[-1] or 0.0
    nci_all = (max(nci_total, 0.0) if nci_total is not None else ((nci_op_x or 0.0) + (nci_lp or 0.0))) + max(redeem, 0.0)
    units = ext_series(ri, "nci_op_units")[-1]
    op_book = sum(v for item in (ri.reg or {}) if item.startswith("nci_op_book__") for v in [ext_series(ri, item)[-1]] if v is not None)
    if not op_book:
        op_book = None
        if nci_op_x:
            op_book = nci_op_x  # XBRL OP-unit holders' interest (SPG, BXP)
    incl = ext_series(ri, "diluted_includes_op")[-1]
    if ext_series(ri, "shares_basis_override")[-1] is not None:
        incl = 1.0  # RE28: the share series already includes the OP units (SPG)
    out = {"nci_all": nci_all, "op_units": units, "op_book": op_book, "diluted_includes_op": incl, "flags": []}
    if units == 0:
        out.update({"basis": "no_op_units", "nci_deducted": nci_all, "shares": sh, "op_units_added": 0.0})
    elif units and op_book is not None:
        other = max(nci_all - op_book, 0.0)
        if incl == 1:
            out.update({"basis": "op_units_in_diluted_shares", "nci_deducted": other, "shares": sh, "op_units_added": 0.0})
        else:
            out.update({"basis": "op_units_added_to_shares", "nci_deducted": other, "shares": (sh or 0.0) + units, "op_units_added": units})
            if incl is None:
                out["flags"].append("RP2b: whether diluted shares include OP units not extracted: assumed excluded (units added)")
    else:
        out.update({"basis": "nci_not_split", "nci_deducted": nci_all, "shares": sh, "op_units_added": 0.0})
        out["flags"].append("RP2b: NCI cannot be split (OP-unit data not extracted): shares exclude OP units and the whole NCI is deducted")
    return out


def rp2c_basis(ri, d) -> dict:
    """RP2c: one basis for NOI, debt and JV interests. Default (a) consolidated: consolidated NOI (computed by us from the consolidated lines, RE13), consolidated debt, NCI deducted (RP2b), unconsolidated JV
    interests at carrying value (RP2a). Never the JV's NOI capitalized together with the JV interest added: the check fails when the NOI basis is proportionate while JV interests are also added."""
    nb = str(d["noi_basis"][-1] or "")
    proportionate = any(w in nb.lower() for w in ("proportionate", "pro rata", "our share", "incl. jv", "including joint venture"))
    cls, _ = _bsa_classes(ri)
    jv_added = bool(ri.series("equity_method_inv")[-1]) or any(k.startswith("bsa_carry__") and any(w in k for w in ("unconsol", "jv", "partnership", "klepierre", "joint"))
                                                                   for k in (ri.reg or {}))
    return {"noi_basis": "proportionate" if proportionate else "consolidated", "noi_line": nb, "debt_basis": "consolidated (balance-sheet debt)", "nci": "deducted (RP2b)",
            "jv_interests": "carrying value, equity method (RP2a)" if jv_added else "none identified", "jv_noi_capitalized_with_jv_interest": bool(proportionate and jv_added),
            "ok": not (proportionate and jv_added)}


def nav_components(ri, d, cap: Optional[float] = None) -> dict:
    """RP2 conservative NAV (equity, latest fiscal year, USD): stabilized NOI / cap + assets at carrying value (RP2a) - net debt - other claims (RP2b)."""
    g = ri.series
    cr = conservative_cap_rate()
    cap = cr["value"] if cap is None else cap
    noi = d["noi"][-1]
    c: dict = {"cap_rate": cap, "cap_detail": cr, "noi": noi, "noi_basis": d["noi_basis"][-1], "flags": list(cr["flags"]), "rp2c": rp2c_basis(ri, d)}
    if noi is None or noi <= 0:
        return {**c, "ok": False, "reason": "stabilized NOI missing or not positive"}
    if d["net_debt"][-1] is None:
        return {**c, "ok": False, "reason": "net debt missing"}
    sb = _share_basis(ri, d)
    c["share_basis"] = sb
    c["flags"] += sb["flags"]
    if not sb["shares"]:
        return {**c, "ok": False, "reason": "diluted shares missing"}
    if d["noi_basis"][-1] and str(d["noi_basis"][-1]).startswith("PROXY"):
        c["flags"].append("NOI_is_a_proxy (total revenue - cost of revenue)")
    c["flags"].append("stabilized_NOI = latest fiscal-year NOI of the whole portfolio (the non-stabilized share is not separable in the cached data)")
    assets = g("assets")[-1]
    cls, lines = _bsa_classes(ri)
    c["bsa_classes"], c["bsa_lines"] = cls, lines
    if cls and assets:
        # RP2a: (1) noi -> 0, (2) carry / inre / carryfin at carrying value, (3) wc excluded, (4) excl excluded, (5) unidentified = other lines + any residual to total assets
        classified = sum(cls.get(k, 0.0) for k in ("noi", "carry", "carryfin", "wc", "excl"))
        unident = (assets - classified)  # includes the explicit 'other' lines (they are not in the classified sum)
        c["unidentified_assets"], c["unidentified_share_of_assets"] = unident, unident / assets
        c["graham_block"] = unident / assets > NON_NOI_MATERIAL
        c["non_noi_counted"] = cls.get("carry", 0.0) + cls.get("carryfin", 0.0) + cls.get("inre", 0.0)
        c["non_noi_breakdown"] = {"carry": cls.get("carry", 0.0), "carryfin": cls.get("carryfin", 0.0), "inre": cls.get("inre", 0.0)}
        c["rp2a_basis"] = "extracted balance-sheet classification (RP2a)"
        if cls.get("carryfin"):
            c["flags"].append("carryfin_counted: financial investments (securities / preferred equity) at carrying value - not in the RP2a list (rule question)")
        if cls.get("inre"):
            c["flags"].append("inre: development / CIP / land held for development sit inside real estate and are counted at carrying value (not capitalized through the NOI)")
    else:
        cip, land, jv = g("cip")[-1], g("re_dev_land")[-1], g("equity_method_inv")[-1]
        c["non_noi_counted"] = (cip or 0.0) + (land or 0.0) + (jv or 0.0)
        c["non_noi_breakdown"] = {"cip": cip, "land": land, "jv": jv}
        ppe = g("re_net")[-1]
        ident = [ppe, g("intangibles_net")[-1], g("goodwill")[-1], g("cash")[-1], g("sti")[-1], jv]
        if assets and ppe is not None:
            resid = assets - sum(x or 0.0 for x in ident)
            c["unidentified_assets"], c["unidentified_share_of_assets"] = resid, resid / assets
            c["graham_block"] = resid / assets > NON_NOI_MATERIAL
        else:
            c["unidentified_assets"], c["unidentified_share_of_assets"], c["graham_block"] = None, None, True
        c["rp2a_basis"] = "XBRL tags only (round-1 residual method: RP2a classification not extracted)"
        c["flags"].append("RP2a_classification_not_extracted")
    if g("goodwill")[-1] or cls.get("excl"):
        c["flags"].append("goodwill_and_cash_excluded_from_NAV")
    pref, fl_ = g("pref_equity")[-1], g("finance_lease_liab")[-1]
    claims = {"preferred": pref or 0.0, "noncontrolling_interests_non_op": sb["nci_deducted"], "finance_lease_liabilities": fl_ or 0.0}
    if fl_:
        c["flags"].append("finance_lease_liability_added_as_a_claim (may already be inside the debt tag)")
    c["other_claims"] = claims
    dev_lines = [(k, sl_, v) for k, sl_, v in lines if (k == "inre") or (k == "carry" and any(w in sl_ for w in ("construction", "development")))] if cls else []
    c["development_and_land"] = sum(v for _, _, v in dev_lines) if cls else None
    c["op_value"] = noi / cap
    c["net_debt"] = d["net_debt"][-1]
    c["nav"] = c["op_value"] + c["non_noi_counted"] - c["net_debt"] - sum(claims.values())
    c["shares"] = sb["shares"]
    c["nav_per_share"] = c["nav"] / c["shares"]
    c["nav_without_development_per_share"] = None if c["development_and_land"] is None else (c["nav"] - c["development_and_land"]) / c["shares"]
    return {**c, "ok": True}


def re_graham_nav(ri, d, quality) -> dict:
    """RP2 / RP3 (Graham-style conservative NAV)."""
    out: dict = {"model": "graham_price_real_estate", "method": "conservative_nav", "flags": [],
                 "display_label": "conservative value under a uniform model assumption, not a market-value estimate"}
    c = nav_components(ri, d)
    out["components"] = c
    out["flags"] += c["flags"]
    price = ri.price_current
    out["price_current"] = price
    if not c["ok"]:
        return {**out, "state": "cannot_be_valued", "reason": c["reason"], "value": None, "price_score": {"state": "not_applicable", "points": None}, "buy_price": None}
    v = c["nav_per_share"]
    if v <= 0:
        return {**out, "state": "cannot_be_valued", "reason": "cannot be valued (net debt and other claims exceed the capitalized NOI)", "value": None, "modeled_value_nonpositive": v,
                "price_score": {"state": "score", "points": 0.0, "reason": "C15: value <= 0 -> price score 0"}, "buy_price": None}
    out.update({"state": "valued", "value": v})
    sens = {}
    for k, dx in (("cap-1pp", -0.01), ("cap+1pp", 0.01)):
        cc = nav_components(ri, d, cap=c["cap_rate"] + dx)
        sens[k] = cc["nav_per_share"] if cc["ok"] else None
    out["sensitivities"] = sens
    if price is not None and c["shares"]:  # market-implied cap rate (double-conservatism check)
        ev_noi = price * c["shares"] + c["net_debt"] + sum(c["other_claims"].values()) - c["non_noi_counted"]
        out["market_implied_cap_rate"] = c["noi"] / ev_noi if ev_noi > 0 else None
    out["nav_without_development_per_share"] = c.get("nav_without_development_per_share")
    mic = out.get("market_implied_cap_rate")
    out["distress"] = {"flag": bool(mic is not None and mic - c["cap_rate"] > RP5_GAP + 1e-12), "market_implied_cap_rate": mic, "conservative_cap_rate": c["cap_rate"],
                       "gap_pp": None if mic is None else (mic - c["cap_rate"]) * 100,
                       "text": "the market prices distress not visible in the annual data - check the latest results before buying"}
    out["value_full_nav"] = v
    if out["distress"]["flag"] and c.get("nav_without_development_per_share") is not None:  # RP5a: the price score and buy price use the NAV without development and land; the full NAV stays on display
        v = c["nav_without_development_per_share"]
        out["rp5a_applied"] = True
        out["value_for_score"] = v
        out["flags"].append("RP5a_price_score_on_NAV_without_development_and_land")
        if v <= 0:
            return {**out, "price_score": {"state": "score", "points": 0.0, "reason": "RP5a: NAV without development and land <= 0 -> price score 0"}, "buy_price": None}
    else:
        out["rp5a_applied"] = False
    if c["graham_block"]:
        why = (f"unidentified assets {c['unidentified_share_of_assets']:.0%} of total assets > 10%" if c.get("unidentified_share_of_assets") is not None else "real-estate carrying value missing")
        out["price_score"] = {"state": "blocked", "points": None, "reason": "RP2: non-NOI assets missing and material (" + why + ")"}
        out["buy_price"] = None
        out["label"] = "indicative NAV (non-NOI assets incomplete) - not a buy price"
        return out
    if price is None:
        out["price_score"] = {"state": "missing", "points": None, "reason": "no current price"}
    else:
        disc = (v - price) / v
        out["price_score"] = {"state": "score", "discount": disc, "points": interpolate(disc, G.CLASSIC_PRICE), "anchors": describe(G.CLASSIC_PRICE)}
    out["buy_price"] = B._buy_price(v, quality, G.CLASSIC_MARGIN)
    return out


def price_display(ri, d) -> dict:
    """Display only: Price / average normalized FFO per share (<= 15 is indicative only: FFO is before recurring capex)."""
    ffo5 = clean(tail(d["nffo_ps"], 5))
    avg = sum(ffo5) / len(ffo5) if len(ffo5) >= 3 else None
    pf = None if (avg is None or avg <= 0 or ri.price_current is None) else ri.price_current / avg
    return {"avg_normalized_ffo_per_share_5y": avg, "price_to_avg_ffo": pf, "within_15x": None if pf is None else pf <= 15.0, "note": "indicative only: FFO is before recurring capex"}


def re29b_gap_control(d, i, threshold: float = 0.05) -> Optional[dict]:
    """RE29b control: the Q1 gap (normalized FFO per share vs the company's Core / normalized / adjusted FFO per share) and the Q6 gap (OE per share vs reported AFFO less SBC per share) before and after
    the RE29a removal (foreign exchange net of hedges and the non-real-estate investment results). A gap whose absolute value widens by more than ``threshold`` (5 pp) flags the company for review."""
    sh, nf, oe = d["shares_eff"][i], d["norm_ffo"][i], d["oe"][i]
    if not sh or nf is None:
        return None
    adj = (d["re29a_fx_result"][i] or 0.0) + (d["re29a_investment_result"][i] or 0.0)
    ps, tot = d["core_ffo_ps_reported"][i], d["core_ffo_reported"][i]
    comp = ps if ps is not None else (None if tot is None else tot / sh)
    aff = d["affo_reported"][i]
    aps = None if aff is None else (aff - (d["sbc"][i] or 0.0)) / sh
    q1_after = None if not comp else nf / sh / comp - 1
    q1_before = None if not comp else (nf + adj) / sh / comp - 1
    ok6 = bool(aps) and oe is not None and d["oe_basis"][i] == "OE"
    q6_after = (oe / sh / aps - 1) if ok6 else None
    q6_before = ((oe + adj) / sh / aps - 1) if ok6 else None
    w1 = None if q1_after is None else (abs(q1_after) - abs(q1_before)) * 100
    w6 = None if q6_after is None else (abs(q6_after) - abs(q6_before)) * 100
    flag = (w1 is not None and w1 > threshold * 100 + 1e-9) or (w6 is not None and w6 > threshold * 100 + 1e-9)
    return {"adjustment": adj, "q1_before": q1_before, "q1_after": q1_after, "q1_widening_pp": w1, "q6_before": q6_before, "q6_after": q6_after, "q6_widening_pp": w6, "flag": bool(flag)}


def score_realestate_pricing(ri: REInputs, sc: dict) -> dict:
    """Pricing on top of a quality result (RP1-RP3 and the display items)."""
    from .c16 import apply_c16
    d = sc["derived"]
    res = {"buffett_price": re_buffett_price(ri, d, sc["buffett_quality"]), "graham_price": re_graham_nav(ri, d, sc["graham_quality"]), "display": price_display(ri, d)}
    return apply_c16(res, ri.price_entity_issue)


def score_realestate(ri: REInputs) -> dict:
    d = derive_re(ri)
    return {"state": "scored", "derived": d, "buffett_quality": realestate_buffett_quality(ri, d), "graham_quality": realestate_graham_quality(ri, d)}

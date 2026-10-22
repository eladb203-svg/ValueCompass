"""Engine side of the AI extraction (code stage K5b): the CSV item -> item_key / block map, the conversion of stored extraction items to the ``reg`` dicts the engines read,
and ``attach_ext`` (a no-op unless VC_AI_EXT_STORE names an items.jsonl file, so every normal / golden run is unchanged). Approved items enter as input; pending ones only when
VC_AI_EXT_UNAPPROVED=1 (development runs; the run is flagged ``extraction_unapproved``).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------- CSV item -> (item_key, block). Order matters: the first pattern that matches wins; None = no block covers it.
BANK_MAP = [
    (r"^cet1_ratio_(standardized|advanced)$", "cet1_ratio_\\1", "B1"), (r"^cet1_required_(standardized|advanced)$", "cet1_required_\\1", "B1"), (r"^cet1_capital$", "cet1_capital", "B1"),
    (r"^total_capital_(standardized|advanced)$", "total_capital_\\1", "B1"), (r"^rwa_(standardized|advanced)$", "rwa_\\1", "B1"), (r"^lcr_q4_average$", "lcr_q4_average", "B1"),
    (r"^scb$", "scb", "B1"), (r"^uninsured_deposits$", "uninsured_deposits", "B1"),
    (r"^loan:", "loan_line", "B2"), (r"^loans_20\d\d$", "total_loans", "B2"),
    (r"^funding:", None, None), (r"^acl_loans_20\d\d$", None, None), (r"^avg_loans_20\d\d$", None, None), (r"^nco_20\d\d$", None, None), (r"^nonaccrual_loans$", None, None),
    (r"^past_due_90_accruing:", None, None), (r"^preferred_stock_20\d\d$", None, None),
]
INS_MAP = [
    (r"^reg_capital_ratio$", "reg_capital_ratio", "B3"), (r"^adverse_prior_year_dev:", "prior_year_dev", "B3"), (r"^adverse_ldti_remeasurement:", "ldti_remeasurement", "B3"),
    (r"^bs_cash$", "inv_cash", "B4"), (r"^bs_short_term$", "inv_short_term", "B4"), (r"^bs_fixed_maturities$", "inv_fixed_maturities", "B4"), (r"^bs_equity$", "inv_equity", "B4"),
    (r"^bs_illiquid_loans$", "inv_illiquid_loans", "B4"), (r"^bs_real_estate$", "inv_real_estate", "B4"), (r"^bs_other_invested$", "inv_other", "B4"),
    (r"^bs_total_investments$", "inv_total", "B4"), (r"^ig_fixed_income$", "inv_ig_fixed", "B4"), (r"^ig_share_pct$", "inv_ig_share", "B4"),
    (r"^cat_loss_latest$", "cat_loss_latest", "B4"), (r"^alm_disclosed$", "alm_disclosed", "B4"),
    (r"^total_fixed_income$", None, None), (r"^debt_total$", None, None), (r"^structural_event:", None, None),
]
RE_MAP = [
    (r"^occupancy$", "occupancy", "B5"), (r"^largest_tenant_share$", "largest_tenant_share", "B5"), (r"^same_property_noi_growth$", "same_property_noi_growth", "B5"),
    (r"^(acquisition|development)_(yield|invested)$", "\\1_\\2", "B5"), (r"^same_store_revenue_growth$", None, None),
    (r"^maintenance_capex(_q)?$", "maint_capex", "B6"), (r"^ti_lc_income_preserving(_q)?$", "ti_lc", "B6"), (r"^straight_line_x(_q)?$", "straight_line_rent_affo", "B6"),
    (r"^fair_value_real_estate$", "fair_value_real_estate", "B7"), (r"^committed_undrawn_facilities$", "committed_undrawn_facilities", "B8"),
    (r"^mat_year1_x__", "debt_maturity_year1", "B8"), (r"^mat_year2_x__", "debt_maturity_year2", "B8"),
    (r"^unencumbered_noi_share$", "unencumbered_noi_share", "B9"), (r"^unencumbered_assets_share$", "unencumbered_assets_share", "B9"),
    (r"^bsa_(noi|carry|inre|carryfin|wc|excl|other)__", "bsa_\\1", "B10"),
    (r"^nci_op_units$", "op_units_count", "B11"), (r"^nci_op_book__", "op_units_book_value", "B11"), (r"^diluted_includes_op$", "diluted_includes_op", "B11"),
    (r"^partnership_units_weighted$", "partnership_units_weighted", "B11"), (r"^shares_basis_override$", "shares_basis_override", "B11"), (r"^inc_share_of_bplp$", "inc_share_of_bplp", "B11"),
    (r"^recon_net_income$", "recon_net_income", "B12"), (r"^recon_re_da$", "recon_re_da", "B12"), (r"^recon_(nci_adjust|jv_other_adjust)$", "recon_nci_jv", "B12"),
    (r"^recon_gi_net$", "recon_gi_net", "B12"), (r"^reported_ffo$", "reported_ffo", "B12"), (r"^core_ffo_reported$", "reported_core_ffo", "B12"), (r"^core_ffo_ps_reported$", "core_ffo_ps_reported", "B12"),
    (r"^reported_affo(_q)?$", "reported_affo", "B12"), (r"^ebitdare_reported$", "reported_ebitdare", "B12"), (r"^dev_gains_reported$", "re29_re_sale_gains", "B12"),
    (r"^re29_nonre_impairments__", "re29_nonre_impairments", "B12"), (r"^info_nonre_impairments_in_investment_income$", "re29_nonre_impairments", "B12"),
    (r"^re29a_nonre_inv__", "re29a_nonre_inv", "B12"), (r"^re29b_fx_net$", "re29b_fx_net", "B12"),
    (r"^profile_(total_assets|property_value|rental_revenue|total_revenue)$", "profile_\\1", "B13"),
    (r"^(rental_revenue_extracted|property_opex_extracted)$", None, None), (r"^affo_(br__|addback_)", None, None), (r"^bs_check__", None, None), (r"^debt_total_bs$", None, None),
    (r"^secured_debt$", None, None),
]
MAPS = {"bank": BANK_MAP, "insurance": INS_MAP, "realestate": RE_MAP}


def map_csv_item(kind: str, item: str) -> tuple:
    """-> (item_key, block) of the AI extraction that covers the CSV item, or (None, None) when no block covers it (a B14 candidate)."""
    for rx, key, blk in MAPS[kind]:
        m = re.search(rx, item)
        if m:
            return (m.expand(key) if key else None), blk
    return None, None


# ---------------------------------------------------------------- stored items -> reg dicts
def load_items(path, ticker: str, include_pending: bool = False) -> list:
    p = Path(path)
    if not p.exists():
        return []
    rows = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [r for r in rows if r["ticker"] == ticker and r["state"] == "value" and (r["approval_status"] == "approved" or (include_pending and r["approval_status"] == "pending"))]


def _label(year: int) -> str:
    return f"FY{year}"


def to_reg(kind: str, rows: list, fy_latest: int) -> dict:
    """Stored items -> the dict the engine reads (same shape as the CSV loaders): bank / insurance {item: {value, unit, ...}} (latest year; USD in millions), real estate {item: {year label: {...}}}."""
    reg: dict = {}
    for r in rows:
        key, y = r["item_key"], r["year"]
        v, unit = r["value_full"], r["unit"]
        row = {"quote": r["quote"], "section": r["section"], "verified": True, "note": (r.get("basis") or "") + " [AI extraction K5b]", "source": r["accession"]}
        if kind == "realestate":
            name = {"debt_maturity_year1": "mat_year1_x__total", "debt_maturity_year2": "mat_year2_x__total", "reported_core_ffo": "core_ffo_reported", "maint_capex": "maintenance_capex",
                    "ti_lc": "ti_lc_income_preserving", "straight_line_rent_affo": "straight_line_x", "reported_ebitdare": "ebitdare_reported", "op_units_count": "nci_op_units",
                    "op_units_book_value": "nci_op_book__total", "recon_nci_jv": "recon_nci_adjust", "re29_re_sale_gains": "re29_re_sale_gains__total",
                    "re29_nonre_impairments": "re29_nonre_impairments__total", "re29a_nonre_inv": "re29a_nonre_inv__total"}.get(key, key)
            if key.startswith("bsa_"):
                name = f"{key}__{re.sub(r'[^a-z0-9]+', '_', (r.get('basis') or 'line').lower()).strip('_')}"
            if unit == "percent":
                v, u = v / 100.0, "fraction"
            else:
                u = unit if unit != "USD" else "USD"
            reg.setdefault(name, {})[_label(y)] = {**row, "value": v, "unit": u}
            continue
        if y != fy_latest and not key.startswith("prior_year_dev"):
            continue
        u = "USD mm" if unit == "USD" else ("%" if unit == "percent" else unit)
        if unit == "USD":
            v = v / 1e6
        if kind == "bank":
            name = f"loan:{r.get('basis') or 'line'}" if key == "loan_line" else (f"loans_{fy_latest}" if key == "total_loans" else key)
        else:
            name = {"prior_year_dev": f"adverse_prior_year_dev:{_label(y)}", "inv_cash": "bs_cash", "inv_short_term": "bs_short_term", "inv_fixed_maturities": "bs_fixed_maturities",
                    "inv_equity": "bs_equity", "inv_illiquid_loans": "bs_illiquid_loans", "inv_real_estate": "bs_real_estate", "inv_other": "bs_other_invested",
                    "inv_total": "bs_total_investments", "inv_ig_fixed": "ig_fixed_income", "inv_ig_share": "ig_share_pct", "ldti_remeasurement": f"adverse_ldti_remeasurement:{_label(y)}"}.get(key, key)
        reg[name] = {**row, "value": v, "unit": u, "period": _label(y)}
    return reg


def merge_reg(base: dict, ai: dict, kind: str) -> dict:
    """The AI items replace the CSV rows of the same item (real estate: per year); everything else stays."""
    out = {k: (dict(v) if kind == "realestate" else v) for k, v in (base or {}).items()}
    for k, v in ai.items():
        if kind == "realestate":
            out.setdefault(k, {}).update(v)
        else:
            out[k] = v
    return out


def attach_ext(inp, ticker: str, kind: str):
    """Code stage K5b: replace extraction rows of an engine inputs object by the stored AI items. A no-op unless VC_AI_EXT_STORE names an items.jsonl file."""
    path = os.environ.get("VC_AI_EXT_STORE")
    if not path:
        return inp
    unapproved = os.environ.get("VC_AI_EXT_UNAPPROVED") == "1"
    rows = load_items(path, ticker, include_pending=unapproved)
    if rows:
        inp.reg = merge_reg(inp.reg, to_reg(kind, rows, int(inp.fy[-1][2:])), kind)
        if unapproved and any(r["approval_status"] == "pending" for r in rows):
            inp.flags = list(getattr(inp, "flags", None) or []) + ["extraction_unapproved"]
    return inp


# ---------------------------------------------------------------- engine-based controls (real estate): computed on the inputs with the AI items merged in
def re_controls(ri_base, rows_all: list) -> dict:
    """-> {control name: {result, detail, items}} for the controls that need the engine: Q6 (B6), coverage band (B8), E11 + RE29b (B12), value range (B7), router band (B13)."""
    from . import realestate as R
    from .router import property_test
    import copy
    out: dict = {}
    ri = copy.copy(ri_base)
    ri.reg = merge_reg(ri_base.reg, to_reg("realestate", [r for r in rows_all if r["state"] == "value"], int(ri_base.fy[-1][2:])), "realestate")
    try:
        d = R.derive_re(ri)
    except Exception as e:  # noqa: BLE001
        return {k: {"name": k, "result": "na", "detail": f"engine error: {type(e).__name__}"} for k in ("q6", "coverage_band", "e11_re29b", "value_basis_range", "router_band")}
    i = ri.n - 1
    q6 = [x for x in R.q6_gap_flags(ri, d) if x["year"] == ri.fy[-1]]
    out["q6"] = ({"name": "q6", "result": "na", "detail": "Q6 gap not computable (no reported AFFO or no OE)"} if not q6 or q6[0]["gap"] is None else
                 {"name": "q6", "result": "fail" if q6[0]["flag"] else "pass", "detail": f"OE per share vs (AFFO - SBC) per share gap {q6[0]['gap']:+.1%} (threshold 15%)"})
    cov = d.get("ntdc12", [None])[i]
    out["coverage_band"] = ({"name": "coverage_band", "result": "na", "detail": "12-month coverage not computable"} if cov is None else
                            {"name": "coverage_band", "result": "fail" if 0.8 <= cov <= 1.25 else "pass", "detail": f"RP1a 12-month coverage {cov if cov != float('inf') else 'inf'} (band 0.8-1.25)"})
    gap = (d.get("ffo_reconciliation_pct") or [None])[i]
    g29 = R.re29b_gap_control(d, i)
    bad = []
    if gap is not None and abs(gap) > 0.10:
        bad.append(f"E11 FFO gap {gap:+.1%} > 10%")
    if g29 and g29.get("flag"):
        bad.append("RE29b control flagged (gap widens > 5 pp)")
    out["e11_re29b"] = ({"name": "e11_re29b", "result": "na", "detail": "reported FFO or normalized FFO not available"} if gap is None and not g29 else
                        {"name": "e11_re29b", "result": "fail" if bad else "pass", "detail": "; ".join(bad) or f"E11 FFO gap {gap if gap is None else format(gap, '+.1%')}; RE29b ok"})
    fv = next((r for r in rows_all if r["item_key"] == "fair_value_real_estate" and r["state"] == "value" and r["year"] == int(ri.fy[-1][2:])), None)
    gross = ri.series("re_gross")[-1]
    if fv is None:
        out["value_basis_range"] = {"name": "value_basis_range", "result": "na", "detail": "no fair value extracted"}
    else:
        probs = []
        if not (fv.get("basis") or "").strip():
            probs.append("basis not stated")
        if gross:
            ratio = fv["value_full"] / gross
            if not (0.5 <= ratio <= 3.0):
                probs.append(f"fair value / gross real estate at cost = {ratio:.2f}x outside 0.5-3x")
        out["value_basis_range"] = {"name": "value_basis_range", "result": "fail" if probs else "pass", "detail": "; ".join(probs) or "basis stated and ratio within 0.5-3x"}
    gv = ri.series
    px = {k: next((r["value_full"] for r in rows_all if r["item_key"] == k and r["state"] == "value" and r["year"] == int(ri.fy[-1][2:])), None)
          for k in ("profile_total_assets", "profile_property_value", "profile_rental_revenue", "profile_total_revenue")}
    pt = property_test(gv("assets")[-1], gv("re_net")[-1], gv("rental_revenue")[-1], gv("total_revenue")[-1], gv("intangibles_net")[-1], px["profile_total_assets"], px["profile_property_value"],
                       px["profile_rental_revenue"], px["profile_total_revenue"])
    shares = [x for x in (pt["investment_property_share"], pt["rental_revenue_share"]) if x is not None]
    if not shares:
        out["router_band"] = {"name": "router_band", "result": "na", "detail": "router test not computable"}
    else:
        dist = min(abs(x - 0.5) for x in shares) * 100
        out["router_band"] = {"name": "router_band", "result": "fail" if dist <= 5.0 else "pass", "detail": f"S3a: nearest test share {dist:.1f} pp from the 50% threshold (band 5 pp); assignment {pt['assignment']}"}
    return out

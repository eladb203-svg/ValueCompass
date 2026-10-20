"""Profile router (Rulebook Part B and B.1, code stage K4b; H-09).

Pure: no I/O, no company lists. Everything company-specific arrives as data:
  * ``RouterData``  - SIC, provider industry and per-year values (built from a FactSet by ``router_data_from_factset``);
  * ``Tables``      - SIC -> industry rules and provider industry -> industry map (CSV files in ``router_data/``, loaded by ``load_tables``);
  * ``Override``    - manual correction (P1) with a mandatory reason;
  * ``AIAnswer``    - tier-3 classification (interface only; the AI call is code stage K5).

Order of operations (Part B): (1) classify the industry (B.1: SIC -> provider industry -> AI); (2) test the rows 1a..6 for that industry, first match wins;
(3) one result per fiscal year of the window, then the two-year stability rule gives the effective profile. An undetermined year is neither a failure nor a break.
The tests ``bank_path``, ``property_test`` and ``insurance_liability_test`` are the single implementation used by the engines and the runners.
"""
from __future__ import annotations

import csv
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .profile_flags import borderline_flag

# ---------------------------------------------------------------- constants (Part B thresholds, one place)
BANK_DEPOSIT_SHARE, BANK_LOAN_SHARE = 0.50, 0.30
INSURANCE_SHARE = 0.50
PROPERTY_ASSET_SHARE, PROPERTY_RENTAL_SHARE = 0.50, 0.50
MORTGAGE_PROPERTY_SHARE, MORTGAGE_INTEREST_SHARE, MORTGAGE_ASSET_SHARE = 0.50, 0.50, 0.50
BDC_INVESTMENT_SHARE = 0.50
CREDIT_LOAN_SHARE = 0.50
TECH_RD_SHARE, TECH_GROSS_MARGIN = 0.10, 0.50
WINDOW_YEARS = 5
STABILITY_YEARS = 2

OTHER = "Other"
INDUSTRIES = ("Banks", "Investment banks and brokers", "Consumer and commercial credit", "Insurance carriers", "Managed health insurance",
              "Insurance brokers and services", "Property REITs and income real estate", "Mortgage REITs", "BDCs and credit funds",
              "SPACs and asset-backed issuers", "Software", "IT services", "Internet platforms and advertising", "Hardware", "Semiconductors",
              "Semiconductor equipment", "Communications equipment", "Electronic components", "Asset managers", "Exchanges and data", "Payments",
              "Homebuilders and developers", OTHER)
PROFILES = ("STANDARD", "TECH_ASSET_LIGHT", "BANK", "INSURANCE", "INCOME_REAL_ESTATE", "UNSUPPORTED")
DATA_DIR = Path(__file__).with_name("router_data")

BANK_I, BROKER_I, CREDIT_I = "Banks", "Investment banks and brokers", "Consumer and commercial credit"
INS_I = ("Insurance carriers", "Managed health insurance", "Insurance brokers and services")
PROP_I, MORT_I, BDC_I, SPAC_I = "Property REITs and income real estate", "Mortgage REITs", "BDCs and credit funds", "SPACs and asset-backed issuers"
TECH5A = ("Software", "IT services", "Internet platforms and advertising")
TECH5B = ("Hardware", "Semiconductors", "Semiconductor equipment", "Communications equipment", "Electronic components")


# ---------------------------------------------------------------- Part B rows as data
@dataclass(frozen=True)
class Row:
    order: str
    profile: str
    industries: tuple          # candidate industries ("*" = all)
    test: Optional[str]        # name in TESTS, None = industry suffices
    on_fail: dict = field(default_factory=dict)   # industry (or "*") -> profile | "next"


ROWS = (
    Row("1a", "BANK", (BANK_I,), "bank_1a", {"*": "next"}),
    Row("1b", "BANK", (BANK_I, BROKER_I, CREDIT_I), "bank_1b", {BROKER_I: "STANDARD", CREDIT_I: "UNSUPPORTED", BANK_I: "UNSUPPORTED"}),
    Row("2", "INSURANCE", INS_I, "insurance_liabilities", {"*": "STANDARD"}),
    Row("3", "INCOME_REAL_ESTATE", (PROP_I,), "property", {"*": "STANDARD"}),
    Row("4", "UNSUPPORTED", (MORT_I, BDC_I, SPAC_I), None, {}),
    Row("5a", "TECH_ASSET_LIGHT", TECH5A, None, {}),
    Row("5b", "TECH_ASSET_LIGHT", TECH5B, "tech_5b", {"*": "STANDARD"}),
    Row("6", "STANDARD", ("*",), None, {}),
)


# ---------------------------------------------------------------- tables (data)
@dataclass(frozen=True)
class SicRule:
    lo: int
    hi: int
    industry: str
    kind: str                  # auto | multi | split_6798 | credit_6199
    default: str = ""
    allowed: tuple = ()


@dataclass(frozen=True)
class Tables:
    sic_rules: tuple
    provider: dict             # provider industry -> (industry, decision) ; decision 'map' | 'tier3'


def load_tables(directory: Path = DATA_DIR) -> Tables:
    with (directory / "sic_industry.csv").open(encoding="utf-8", newline="") as fh:
        rules = tuple(SicRule(int(r["sic_from"]), int(r["sic_to"]), r["industry"], r["kind"], r["default"],
                              tuple(x for x in r["allowed"].split("|") if x)) for r in csv.DictReader(fh))
    with (directory / "provider_industry.csv").open(encoding="utf-8", newline="") as fh:
        prov = {r["provider_industry"]: (r["industry"], r["decision"]) for r in csv.DictReader(fh)}
    return Tables(rules, prov)


def bank_sic_set(tables: Tables) -> set:
    return {s for r in tables.sic_rules if r.industry == BANK_I for s in range(r.lo, r.hi + 1)}


def sic_set(tables: Tables, industries) -> set:
    return {s for r in tables.sic_rules if r.industry in industries for s in range(r.lo, r.hi + 1)}


_DEFAULT_TABLES: Optional[Tables] = None


def default_tables() -> Tables:
    global _DEFAULT_TABLES
    if _DEFAULT_TABLES is None:
        _DEFAULT_TABLES = load_tables()
    return _DEFAULT_TABLES


# ---------------------------------------------------------------- inputs / outputs
@dataclass
class RouterData:
    ticker: str
    years: list                              # fiscal-year labels, ascending
    values: dict                             # label -> {name: value}
    sic: Optional[str] = None
    sic_description: Optional[str] = None
    provider_industry: Optional[str] = None
    flags: list = field(default_factory=list)


@dataclass(frozen=True)
class Override:
    reason: str
    set_by: str = ""
    set_at: str = ""
    profile: Optional[str] = None
    industry: Optional[str] = None
    valid_from_fy: Optional[int] = None

    def __post_init__(self):
        if not (self.reason or "").strip():
            raise ValueError("a manual override needs a stored reason (P1)")
        if self.profile is None and self.industry is None:
            raise ValueError("an override must set a profile or an industry")
        if self.profile is not None and self.profile not in PROFILES:
            raise ValueError(f"unknown profile {self.profile!r}")
        if self.industry is not None and self.industry not in INDUSTRIES:
            raise ValueError(f"unknown industry {self.industry!r}")


@dataclass(frozen=True)
class AIAnswer:
    """Tier 3 (interface only; K5 runs the AI question). ``approved`` = an admin approved a disagreement with tier 2."""
    industry: str
    quote: str = ""
    approved: bool = False


@dataclass
class Classification:
    industry: str
    tier: str                                # 'sic' | 'provider' | 'ai' | 'numeric' | 'override' | 'default' | 'none'
    status: str                              # 'decided' | 'classification_pending'
    reasons: list = field(default_factory=list)


@dataclass
class TestOut:
    result: str                              # pass | fail | undetermined
    tests: dict = field(default_factory=dict)  # name -> (value, threshold)
    notes: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)


@dataclass
class YearResult:
    fiscal_year: str
    row: Optional[str]
    profile: Optional[str]                   # None = undetermined
    tests: dict = field(default_factory=dict)
    borderline: bool = False
    borderline_tests: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


@dataclass
class RouterResult:
    ticker: str
    profile: str                             # effective (after stability and override)
    computed_profile: str                    # effective by the stability rule, before any override
    industry: str
    classification: Classification
    reason: list
    borderline: bool
    borderline_tests: dict
    per_year: dict
    since: Optional[str]
    pending_change: Optional[str]            # a different result in the latest determined year, waiting for the second year
    override_applied: Optional[dict]
    missing_inputs: list
    flags: list

    def to_jsonable(self) -> dict:
        return asdict(self)


def _div(a, b):
    return None if a is None or b is None or b == 0 else a / b


# ---------------------------------------------------------------- tests (pure; single implementation)
def bank_path(sic, deposits, total_liabilities, loans, assets, reports_cet1, reports_lcr, regulated_bhc=True, tables: Optional[Tables] = None) -> dict:
    """Rows 1a / 1b. path 1 = industry 'Banks' + deposits / liabilities >= 50% + loans / assets >= 30%;
    path 1b = a supervised bank holding company that reports CET1 and LCR. (Used by bank.py and the bank runner.)"""
    dep_ratio, loan_ratio = _div(deposits, total_liabilities), _div(loans, assets)
    industry_ok = str(sic) in {str(s) for s in bank_sic_set(tables or default_tables())}
    p1 = bool(industry_ok and dep_ratio is not None and loan_ratio is not None and dep_ratio >= BANK_DEPOSIT_SHARE and loan_ratio >= BANK_LOAN_SHARE)
    detail = {"deposits_to_liabilities": dep_ratio, "loans_to_assets": loan_ratio, "sic": str(sic), "industry_is_banks": industry_ok,
              **borderline_flag({"deposits_to_liabilities": (dep_ratio, BANK_DEPOSIT_SHARE), "loans_to_assets": (loan_ratio, BANK_LOAN_SHARE)})}
    if p1:
        return {"path": "1", **detail}
    if regulated_bhc and reports_cet1 and reports_lcr:
        return {"path": "1b", **detail}
    return {"path": None, **detail}


def insurance_liabilities_ratio(components: dict, total_liabilities) -> tuple:
    """-> (sum of the available components, ratio to total liabilities, names of the missing components)."""
    tot = sum(v for v in components.values() if v is not None)
    return tot, _div(tot, total_liabilities), [k for k, v in components.items() if v is None]


def insurance_liability_test(components: dict, total_liabilities, main_component: str = "claims") -> TestOut:
    """Row 2 test: insurance liabilities / total liabilities >= 50%. Components only add, so a missing component can lower the ratio but never raise it:
    pass when the ratio reaches 50%; a ratio below 50% is a failure only when the main (claims) component is present, otherwise undetermined (CL15)."""
    tot, ratio, missing = insurance_liabilities_ratio(components, total_liabilities)
    out = TestOut("undetermined", {"insurance_liabilities_share": (ratio, INSURANCE_SHARE)}, detail={"insurance_liabilities": tot, "missing_components": missing})
    if ratio is None:
        out.notes.append("total liabilities or all components missing")
    elif ratio >= INSURANCE_SHARE:
        out.result = "pass"
    elif components.get(main_component) is not None:
        out.result = "fail"
    else:
        out.notes.append(f"ratio {ratio:.1%} below 50% but the claims component is missing: undetermined, not a failure")
    return out


def property_test(assets, re_net, rental, total_revenue, intangibles, x_assets=None, x_prop=None, x_rent=None, x_total=None) -> dict:
    """Row 3 (S3, RE10, RE11, RE15): investment property / total assets >= 50% and rental revenue / total revenue >= 50%; extracted data when a tag is missing."""
    basis, notes = {"property": "XBRL tag", "rental": "XBRL tag"}, []
    ren = re_net
    if ren is None or assets is None:
        if x_prop is not None and x_assets is not None:
            ren, assets, basis["property"] = x_prop, x_assets, "extracted (RE11: real estate leased to tenants carried in PP&E)"
        else:
            basis["property"] = "missing"
    rental_v, tot = rental, total_revenue
    if rental_v is None or tot is None:
        if x_rent is not None and x_total is not None:
            rental_v, tot, basis["rental"] = x_rent, x_total, "extracted (RE11: revenue breakdown from the 10-K)"
        else:
            basis["rental"] = "missing"
    a_share, r_share = _div(ren, assets), _div(rental_v, tot)
    if a_share is not None and a_share < PROPERTY_ASSET_SHARE and intangibles and assets:
        a2 = (ren + intangibles) / assets
        notes.append(f"RE15: with acquired lease-related intangibles ({intangibles / 1e9:,.1f}bn) the share is {a2:.1%} (property alone {a_share:.1%})")
        basis["property"] += " + acquired lease-related intangibles (RE15)"
        a_share = a2
    asset_ok = None if a_share is None else a_share >= PROPERTY_ASSET_SHARE
    rental_ok = None if r_share is None else r_share >= PROPERTY_RENTAL_SHARE
    ok = None if (asset_ok is None or rental_ok is None) else (asset_ok and rental_ok)
    if ok is False:
        notes.append("fails the test -> STANDARD (RE10 / RE11)")
    return {"investment_property_share": a_share, "rental_revenue_share": r_share, "asset_ok": asset_ok, "rental_ok": rental_ok, "confirmed": ok, "basis": basis, "notes": notes,
            "assignment": "INCOME_REAL_ESTATE" if ok else ("STANDARD" if ok is False else "undetermined"),
            **borderline_flag({"investment_property_share": (a_share, PROPERTY_ASSET_SHARE), "rental_revenue_share": (r_share, PROPERTY_RENTAL_SHARE)})}


def mortgage_reit_test(assets, invest_property, interest_income, total_revenue, mortgage_assets) -> TestOut:
    """B.1 (SIC 6798, latest year): mortgage REIT when investment property / assets < 50% and (interest income / total revenue >= 50% or (mortgage loans + MBS) / assets >= 50%).
    Result 'pass' = mortgage REIT. An absent investment-property line in a retrieved balance sheet counts as 0 (C5), flagged by the caller."""
    prop = _div(invest_property if invest_property is not None else (0.0 if assets else None), assets)
    int_share, mort_share = _div(interest_income, total_revenue), _div(mortgage_assets, assets)
    out = TestOut("undetermined", {"investment_property_share": (prop, MORTGAGE_PROPERTY_SHARE), "interest_income_share": (int_share, MORTGAGE_INTEREST_SHARE),
                                   "mortgage_assets_share": (mort_share, MORTGAGE_ASSET_SHARE)})
    if prop is None:
        out.notes.append("total assets missing")
        return out
    if prop >= MORTGAGE_PROPERTY_SHARE:
        out.result = "fail"
        return out
    if (int_share is not None and int_share >= MORTGAGE_INTEREST_SHARE) or (mort_share is not None and mort_share >= MORTGAGE_ASSET_SHARE):
        out.result = "pass"
    elif int_share is None or mort_share is None:
        out.notes.append("the interest-income share or the mortgage-asset share cannot be computed and the other is below 50%: undetermined, not a failure (CL15)")
    else:
        out.result = "fail"
    return out


def bdc_test(sic, nav_per_share, investments_fv, assets) -> TestOut:
    """B.1 BDC identification: SIC 6726 / 6799, or NAV per share reported and investments at fair value >= 50% of total assets."""
    share = _div(investments_fv, assets)
    out = TestOut("fail", {"investments_fair_value_share": (share, BDC_INVESTMENT_SHARE)})
    if str(sic) in ("6726", "6799"):
        out.result = "pass"
        out.notes.append(f"SIC {sic}")
    elif nav_per_share is not None and share is not None and share >= BDC_INVESTMENT_SHARE:
        out.result = "pass"
    return out


def _median(vals):
    v = [x for x in vals if x is not None]
    return statistics.median(v) if len(v) >= 3 else None


def tech_5b_test(rd, revenue, gross_profit, cost_of_revenue) -> TestOut:
    """Row 5b: R&D / revenue >= 10% and gross margin >= 50% (5-year medians; gross profit may be derived as revenue - cost of revenue per C4, flagged).
    The arguments are the yearly series of the window (oldest first)."""
    rdr = [_div(a, b) for a, b in zip(rd, revenue)]
    derived = False
    gm = []
    for g, c, r in zip(gross_profit, cost_of_revenue, revenue):
        if g is not None:
            gm.append(_div(g, r))
        elif c is not None and r:
            gm.append((r - c) / r)
            derived = True
        else:
            gm.append(None)
    m_rd, m_gm = _median(rdr), _median(gm)
    out = TestOut("undetermined", {"rd_to_revenue_median": (m_rd, TECH_RD_SHARE), "gross_margin_median": (m_gm, TECH_GROSS_MARGIN)})
    if derived:
        out.notes.append("gross profit derived as revenue - cost of revenue (C4)")
    if m_rd is None or m_gm is None:
        out.notes.append("fewer than 3 years of R&D / revenue or of gross margin")
    else:
        out.result = "pass" if (m_rd >= TECH_RD_SHARE and m_gm >= TECH_GROSS_MARGIN) else "fail"
    return out


# ---------------------------------------------------------------- row tests over the per-year values
def _t_bank_1a(v, w, ctx) -> TestOut:
    liab = v.get("liabilities")
    note = []
    if liab is None and v.get("assets") is not None and v.get("equity") is not None:
        liab, note = v["assets"] - v["equity"], ["total liabilities taken as assets - equity"]
    loans = v.get("loans") if v.get("loans") is not None else v.get("loans_extracted")
    dep, lo = _div(v.get("deposits"), liab), _div(loans, v.get("assets"))
    out = TestOut("undetermined", {"deposits_to_liabilities": (dep, BANK_DEPOSIT_SHARE), "loans_to_assets": (lo, BANK_LOAN_SHARE)}, note)
    if dep is None or lo is None:
        out.notes.append("deposits, loans, liabilities or assets missing")
    else:
        out.result = "pass" if (dep >= BANK_DEPOSIT_SHARE and lo >= BANK_LOAN_SHARE) else "fail"
    return out


def _t_bank_1b(v, w, ctx) -> TestOut:
    c, l_ = ctx.get("reports_cet1"), ctx.get("reports_lcr")
    out = TestOut("pass" if (c and l_) else "fail", {}, [])
    if c and l_:
        out.notes.append("CET1 and LCR reported (supervised bank holding company assumed from the regulatory disclosure; regulatory status is not historical)")
    return out


def _t_insurance(v, w, ctx) -> TestOut:
    comps = {"claims": v["claims_gross"] if v.get("claims_gross") is not None else v.get("claims_net"), "future_policy_benefits": v.get("fpb"),
             "policyholder_account_balances": v.get("pab"), "unearned_premiums": v.get("unearned"), "separate_accounts": v.get("separate_accounts"),
             "market_risk_benefit": v.get("mrb_liability")}
    return insurance_liability_test(comps, v.get("liabilities"))


def _t_property(v, w, ctx) -> TestOut:
    r = property_test(v.get("assets"), v.get("re_net"), v.get("rental_revenue"), v.get("revenue"), v.get("intangibles_net"),
                      v.get("x_assets"), v.get("x_prop"), v.get("x_rent"), v.get("x_total"))
    res = {True: "pass", False: "fail", None: "undetermined"}[r["confirmed"]]
    return TestOut(res, {"investment_property_share": (r["investment_property_share"], PROPERTY_ASSET_SHARE),
                         "rental_revenue_share": (r["rental_revenue_share"], PROPERTY_RENTAL_SHARE)}, list(r["notes"]), {"basis": r["basis"]})


def _t_tech5b(v, w, ctx) -> TestOut:
    return tech_5b_test(w["rd"], w["revenue"], w["gross_profit"], w["cost_of_revenue"])


TESTS = {"bank_1a": _t_bank_1a, "bank_1b": _t_bank_1b, "insurance_liabilities": _t_insurance, "property": _t_property, "tech_5b": _t_tech5b}


def evaluate_year(industry: str, fy: str, v: dict, w: dict, ctx: dict, rows=ROWS) -> YearResult:
    """First matching row for the industry. A failing test moves to ``on_fail`` ('next' = the next row)."""
    tests: dict = {}
    notes: list = []
    nxt = False
    for row in rows:
        if "*" not in row.industries and industry not in row.industries:
            continue
        if row.test is None:
            return _finish(YearResult(fy, row.order, row.profile, tests, notes=notes))
        out = TESTS[row.test](v, w, ctx)
        tests.update(out.tests)
        notes += out.notes
        if out.result == "undetermined":
            return _finish(YearResult(fy, row.order, None, tests, notes=notes))
        if out.result == "pass":
            return _finish(YearResult(fy, row.order, row.profile, tests, notes=notes))
        target = row.on_fail.get(industry, row.on_fail.get("*"))
        if target is None or target == "next":
            continue
        return _finish(YearResult(fy, row.order, target, tests, notes=notes + [f"row {row.order} failed -> {target}"]))
    return _finish(YearResult(fy, None, "STANDARD", tests, notes=notes + ["no row matched: STANDARD"]))


def _finish(yr: YearResult) -> YearResult:
    thr = {k: tv for k, tv in yr.tests.items() if tv[0] is not None}
    flag = borderline_flag(thr)
    yr.borderline, yr.borderline_tests = flag["borderline_assignment"], flag["borderline_tests"]
    return yr


# ---------------------------------------------------------------- classification (B.1)
def _sic_rule(sic, tables: Tables) -> Optional[SicRule]:
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return None
    for r in tables.sic_rules:
        if r.lo <= s <= r.hi:
            return r
    return None


def classify(data: RouterData, tables: Tables, ai: Optional[AIAnswer] = None, override: Optional[Override] = None) -> Classification:
    last = data.values.get(data.years[-1], {}) if data.years else {}
    if override is not None and override.industry:
        return Classification(override.industry, "override", "decided", [f"manual override: {override.reason}"])
    prov_raw = data.provider_industry
    prov = tables.provider.get(prov_raw) if prov_raw else None          # (industry, decision) | None
    prov_ind = prov[0] if prov and prov[1] == "map" else None
    reasons: list = []
    bdc = bdc_test(data.sic, last.get("nav_per_share"), last.get("investments_fair_value"), last.get("assets"))
    if bdc.result == "pass":
        return Classification(BDC_I, "numeric", "decided", ["BDC identification (B.1): " + ("; ".join(bdc.notes) or "NAV per share reported and investments at fair value >= 50% of assets")])
    rule = _sic_rule(data.sic, tables)

    def tier23(allowed=None, default=None, why="") -> Classification:
        if prov_ind and (allowed is None or "*" in allowed or prov_ind in allowed):
            if ai and ai.industry != prov_ind and not ai.approved:
                return Classification(default or OTHER, "provider", "classification_pending", reasons + [f"provider industry {prov_raw!r} -> {prov_ind}, AI says {ai.industry}: admin approval needed"])
            return Classification(prov_ind, "provider", "decided", reasons + [f"{why}provider industry {prov_raw!r} -> {prov_ind}"])
        if ai and (ai.approved or (prov_ind and ai.industry == prov_ind) or (not prov_ind and prov is None)):
            return Classification(ai.industry, "ai", "decided", reasons + ["AI classification (tier 3): " + ai.industry])
        if default:
            return Classification(default, "sic", "decided", reasons + [f"{why}default industry for SIC {data.sic}"])
        pend = prov is None or (prov and prov[1] == "tier3") or (data.sic is None and not prov_ind)
        if pend and not (prov and prov[1] == "map"):
            return Classification(OTHER, "none", "classification_pending", reasons + [f"{why}no deciding classification (provider industry {prov_raw!r}); tier 3 (AI) needed: STANDARD until decided"])
        if prov and prov[1] == "map":   # provider industry maps, but outside the allowed set
            return Classification(OTHER, "provider", "decided", reasons + [f"{why}provider industry {prov_raw!r} -> {prov[0]} is not a candidate for SIC {data.sic}: Other"])
        return Classification(OTHER, "sic", "decided", reasons + [f"{why}no candidate industry"])

    if data.sic is None or str(data.sic).strip() == "":
        reasons.append("no SIC code")
        return tier23(why="")
    if rule is None:                                           # SIC maps to Other; tiers 2-3 run only for candidate provider industries
        reasons.append(f"SIC {data.sic} maps to Other")
        if prov_ind and prov_ind != OTHER:
            return Classification(prov_ind, "provider", "decided", reasons + [f"provider industry {prov_raw!r} -> {prov_ind}"])
        if prov and prov[1] == "tier3":
            return Classification(OTHER, "none", "classification_pending", reasons + [f"provider industry {prov_raw!r} may be a candidate: tier 3 (AI) needed"])
        return Classification(OTHER, "sic", "decided", reasons)
    if rule.kind == "auto":
        c = Classification(rule.industry, "sic", "decided", [f"SIC {data.sic} -> {rule.industry}"])
        if prov_ind and prov_ind != rule.industry:
            c.reasons.append(f"cross-check: provider industry {prov_raw!r} -> {prov_ind} differs (SIC decides)")
        return c
    if rule.kind == "split_6798":
        mt = mortgage_reit_test(last.get("assets"), last.get("re_net"), last.get("interest_income"), last.get("revenue"), last.get("mortgage_assets"))
        if mt.result == "pass":
            return Classification(MORT_I, "numeric", "decided", ["SIC 6798: mortgage REIT test passed (B.1)"])
        if mt.result == "fail":
            c = Classification(PROP_I, "numeric", "decided", ["SIC 6798: mortgage REIT test not met -> Property REITs (row 3 decides)"])
            if prov_ind == MORT_I:
                c.reasons.append("cross-check: provider industry says Mortgage REITs (numeric test decides)")
            return c
        reasons.append("SIC 6798: mortgage REIT test undetermined")
        if prov_ind in (MORT_I, PROP_I):
            return Classification(prov_ind, "provider", "decided", reasons + [f"provider industry {prov_raw!r} -> {prov_ind}"])
        return Classification(PROP_I, "sic", "decided", reasons + ["default Property REITs"])
    if rule.kind == "credit_6199":
        share = _div(last.get("loans"), last.get("assets"))
        if share is not None and share >= CREDIT_LOAN_SHARE:
            return Classification(CREDIT_I, "numeric", "decided", [f"SIC 6199: loans and receivables / assets {share:.0%} >= 50% -> credit"])
        reasons.append("SIC 6199 is multi; credit only when loans / assets >= 50%")
        return tier23(why="")
    # multi
    reasons.append(f"SIC {data.sic} is multi")
    return tier23(allowed=rule.allowed or None, default=rule.default, why="")


# ---------------------------------------------------------------- stability (two consecutive years)
def stability(results: list, previous_profile: Optional[str] = None, years: int = STABILITY_YEARS) -> tuple:
    """results: [(fiscal_year, profile | None)] ascending. -> (effective profile, since, pending_change).
    The profile changes only after ``years`` consecutive determined years with the same different result; undetermined years are skipped (they do not break the sequence)."""
    eff, since = previous_profile, None
    run_profile, run_start, run_len = None, None, 0
    for fy, prof in results:
        if prof is None:
            continue
        if eff is None:
            eff, since = prof, fy
            continue
        if prof == eff:
            run_profile, run_len = None, 0
            continue
        if prof == run_profile:
            run_len += 1
        else:
            run_profile, run_start, run_len = prof, fy, 1
        if run_len >= years:
            eff, since = prof, run_start
            run_profile, run_len = None, 0
    pending = run_profile if run_len and run_profile != eff else None
    return eff, since, pending


# ---------------------------------------------------------------- route
def _windows(data: RouterData, k: int) -> dict:
    lo = max(0, k - WINDOW_YEARS + 1)
    labs = data.years[lo:k + 1]
    return {n: [data.values.get(l, {}).get(n) for l in labs] for n in ("rd", "revenue", "gross_profit", "cost_of_revenue")}


def route(data: RouterData, tables: Optional[Tables] = None, override: Optional[Override] = None, previous_profile: Optional[str] = None,
          ai: Optional[AIAnswer] = None, window: int = WINDOW_YEARS) -> RouterResult:
    tables = tables or default_tables()
    cls = classify(data, tables, ai, override)
    ctx = {"reports_cet1": data.values.get(data.years[-1], {}).get("reports_cet1") if data.years else None,
           "reports_lcr": data.values.get(data.years[-1], {}).get("reports_lcr") if data.years else None}
    per_year: dict = {}
    n = len(data.years)
    for k in range(max(0, n - window), n):
        fy = data.years[k]
        per_year[fy] = evaluate_year(cls.industry, fy, data.values.get(fy, {}), _windows(data, k), ctx)
    results = [(fy, yr.profile) for fy, yr in per_year.items()]
    eff, since, pending = stability(results, previous_profile)
    reasons = list(cls.reasons)
    missing = sorted({x for yr in per_year.values() for x in yr.notes if "missing" in x or "undetermined" in x})
    flags = list(data.flags)
    if cls.status == "classification_pending":
        flags.append("classification_pending")
    if eff is None:
        eff = "STANDARD"
        flags.append("profile_undetermined_standard_default")
        reasons.append("no determined year in the window: STANDARD by default")
    latest = per_year[data.years[-1]] if data.years else None
    if latest is not None:
        reasons.append(f"row {latest.row} -> {latest.profile or 'undetermined'} ({data.years[-1]})")
    applied = None
    final = eff
    if override is not None and override.profile:
        final = override.profile
        applied = {"profile": override.profile, "reason": override.reason, "set_by": override.set_by, "set_at": override.set_at, "valid_from_fy": override.valid_from_fy}
        reasons.append(f"manual override to {final}: {override.reason} (computed: {eff})")
    elif override is not None and override.industry:
        applied = {"industry": override.industry, "reason": override.reason, "set_by": override.set_by, "set_at": override.set_at}
    if cls.status == "classification_pending" and final == "STANDARD":
        reasons.append("classification pending: STANDARD until decided")
    bl = latest.borderline if latest else False
    return RouterResult(data.ticker, final, eff, cls.industry, cls, reasons, bl, latest.borderline_tests if latest else {}, {fy: asdict(y) for fy, y in per_year.items()},
                        since, pending, applied, missing, flags)


# ---------------------------------------------------------------- FactSet adapter (K2 structure)
ROUTER_ITEMS = {  # RouterData value name -> item_key in the facts layer (engine "router", etl.field_map.ROUTER)
    "assets": "total_assets", "liabilities": "total_liabilities", "equity": "equity", "deposits": "deposits", "loans": "loans",
    "revenue": "revenue", "gross_profit": "gross_profit", "cost_of_revenue": "cost_of_revenue", "rd": "rd_expense",
    "re_net": "re_net", "rental_revenue": "rental_revenue", "intangibles_net": "intangibles",
    "interest_income": "interest_income_operating", "mortgage_assets": "mortgage_loans_mbs", "nav_per_share": "nav_per_share",
    "investments_fair_value": "investments_fair_value",
    "claims_gross": "claims_gross", "claims_net": "claims_net", "fpb": "fpb", "pab": "pab", "unearned": "unearned",
    "separate_accounts": "separate_accounts", "mrb_liability": "mrb_liability",
}
# extraction rows read by the router: item_key -> value name (per fiscal-year label; a row without a period applies to the latest year)
ROUTER_EXTRACTION = {"loans_2025": "loans_extracted", "profile_total_assets": "x_assets", "profile_property_value": "x_prop",
                     "profile_rental_revenue": "x_rent", "profile_total_revenue": "x_total", "cet1_ratio_standardized": "reports_cet1",
                     "cet1_ratio_advanced": "reports_cet1", "lcr_q4_average": "reports_lcr"}


def router_data_from_factset(fs) -> RouterData:
    """FactSet (engine 'router', one company, window of fiscal years) -> RouterData. Text rows: sic_code (FIN-188), sic_description, provider_industry (FIN-189)."""
    years = [p[1] for p in fs.periods]
    by = fs.by_key()
    values: dict = {lab: {} for lab in years}
    for name, key in ROUTER_ITEMS.items():
        rows = by.get(key, {})
        for fy_i, lab, _ in fs.periods:
            if fy_i in rows:
                values[lab][name] = rows[fy_i].value
    text: dict = {}
    for r in fs.extraction:
        if r.item_key in ("sic_code", "sic_description", "provider_industry"):
            text[r.item_key] = None if r.value in (None, "") else str(r.value)
            continue
        name = ROUTER_EXTRACTION.get(r.item_key)
        if name is None or r.value_state != "value" or r.approval_status != "approved":
            continue
        labs = [r.period] if r.period else [years[-1]]
        for lab in labs:
            if lab in values:
                values[lab][name] = True if name.startswith("reports_") else float(r.value) * (1e6 if r.unit == "USD mm" else 1.0)
    # regulatory status is not historical: the latest year's disclosure is carried to the window
    for nm in ("reports_cet1", "reports_lcr"):
        if values[years[-1]].get(nm):
            for lab in years[:-1]:
                values[lab].setdefault(nm, True)
    return RouterData(fs.ticker, years, values, text.get("sic_code"), text.get("sic_description"), text.get("provider_industry"), list(fs.context.get("flags", [])))

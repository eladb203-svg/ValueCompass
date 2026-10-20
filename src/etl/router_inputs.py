"""Router inputs as a FactSet (code stage K4b): engine "router" = the data the profile router (src/scoring/router.py) tests.

Numeric facts (financial_facts shape): the series the engines already built (``f``, when given) win; everything else comes from the SEC companyfacts tag chains below
(cache only). New dictionary items: FIN-187 ``rd_expense``, FIN-190 ``interest_income_operating``, FIN-191 ``mortgage_loans_mbs``, FIN-192 ``nav_per_share`` and
``investments_fair_value``. Text rows (extraction_items shape): FIN-188 ``sic_code`` (+ ``sic_description``) from the SEC submissions and FIN-189 ``provider_industry``.
(The dictionary additions in the database are code stage K6.)
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from ..providers.bank_facts import BANK_FIELDS
from ..providers.insurance_facts import INS_FIELDS
from ..providers.realestate_facts import RE_FIELDS
from ..providers.sec_companyfacts import FIELD_MAP, _match, annual_series, fy_label
from .extraction_store import rows_from_reg
from .facts import ExtractionRow, Fact, FactSet, label_to_year, parse_date

_REV = list(dict.fromkeys(FIELD_MAP["revenue"][2] + RE_FIELDS["total_revenue"][2]))
# name -> (kind, unit, tags)
ROUTER_TAGS = {
    "assets": ("instant", "USD", ["Assets"]),
    "liabilities": ("instant", "USD", ["Liabilities"]),
    "equity": ("instant", "USD", ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "deposits": BANK_FIELDS["deposits"],
    "loans": BANK_FIELDS["loans"],
    "revenue": ("flow", "USD", _REV),
    "gross_profit": FIELD_MAP["gross_profit"],
    "cost_of_revenue": FIELD_MAP["cost_of_revenue"],
    "rd": ("flow", "USD", ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"]),   # FIN-187
    "re_net": RE_FIELDS["re_net"],
    "rental_revenue": RE_FIELDS["rental_revenue"],
    "intangibles_net": RE_FIELDS["intangibles_net"],
    "interest_income": ("flow", "USD", ["InterestAndDividendIncomeOperating", "InterestIncomeOperating"]),                    # FIN-190
    "nav_per_share": ("instant", "USD/shares", ["NetAssetValuePerShare"]),                                                    # FIN-192
    "investments_fair_value": ("instant", "USD", ["InvestmentOwnedAtFairValue"]),                                              # FIN-192
    **{k: INS_FIELDS[k] for k in ("claims_gross", "claims_net", "fpb", "pab", "unearned", "separate_accounts", "mrb_liability")},
}
# managed-care organizations report the claims liability under other tags than the insurers' chain (run_managed_care INS_COMPONENTS)
ROUTER_TAGS["claims_gross"] = ("instant", "USD", list(dict.fromkeys(ROUTER_TAGS["claims_gross"][2] + [
    "LiabilityForClaimsAndClaimsAdjustmentExpense", "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseNet",
    "ShortdurationInsuranceContractsLiabilityForUnpaidClaimsAndAllocatedClaimAdjustmentExpenseNet"])))
MORTGAGE_LOAN_TAGS = ["MortgageLoansOnRealEstate"]                                                                              # FIN-191
MBS_TAGS = ["MortgageBackedSecuritiesAvailableForSaleFairValueDisclosure", "FinancialInstrumentsOwnedMortgagesMortgageBackedAndAssetBackedSecuritiesAtFairValue"]
F_ALIASES = {"total_revenue": "revenue", "revenue_total": "revenue"}   # engine series name -> router name
ENGINE_ONLY = ("re_net", "rental_revenue", "intangibles_net")           # prefer the engine's series (company extension elements, RE11 fallbacks)


def _value_at(facts: dict, spec, end: date):
    kind, unit, tags = spec
    for tag in tags:
        m = _match(annual_series(facts, tag, unit, kind), end)
        if m is not None:
            return m.val, tag
    return None, None


def _periods(facts: dict, labels, ends, n_years: int):
    if labels and ends:
        return [(label_to_year(l), l, parse_date(e)) for l, e in zip(labels, ends)]
    ends_ = sorted(annual_series(facts, "Assets", "USD", "instant"))
    dedup: list = []
    for e in ends_:
        if dedup and (e - dedup[-1]).days <= 10:
            dedup[-1] = e
        else:
            dedup.append(e)
    return [(label_to_year(fy_label(e)), fy_label(e), e) for e in dedup[-n_years:]]


def router_factset(ticker: str, name: str, facts: dict, submissions: dict, provider_industry: Optional[str], f: Optional[dict] = None, labels=None, ends=None,
                   reg: Optional[dict] = None, reg_engine: Optional[str] = None, n_years: int = 9) -> FactSet:
    """``f`` = the engine's series (aligned with ``labels``); ``reg`` = the engine's extraction dictionary (bank / realestate)."""
    periods = _periods(facts, labels, ends, n_years)
    fs = FactSet(ticker=ticker, name=name, engine="router", periods=periods)
    eng = {}
    for k, vals in (f or {}).items():
        eng[F_ALIASES.get(k, k)] = vals
    for nm, spec in ROUTER_TAGS.items():
        for i, (year, lab, end) in enumerate(periods):
            v, tag = None, None
            if nm in eng:
                x = eng[nm][i] if i < len(eng[nm]) else None
                if x is not None:
                    v, tag = x, "engine series"
                elif nm not in ENGINE_ONLY:
                    v, tag = _value_at(facts, spec, end)
            else:
                v, tag = _value_at(facts, spec, end)
            if v is not None:
                fs.facts.append(Fact(ticker, year, _key(nm), float(v), "found", "xbrl" if tag != "engine series" else "derived", tag=tag))
    for year, lab, end in periods:
        loans, _ = _value_at(facts, ("instant", "USD", MORTGAGE_LOAN_TAGS), end)
        mbs, tag = _value_at(facts, ("instant", "USD", MBS_TAGS), end)
        if loans is not None or mbs is not None:
            fs.facts.append(Fact(ticker, year, _key("mortgage_assets"), float((loans or 0.0) + (mbs or 0.0)), "found", "derived",
                                 tag="SUM: MortgageLoansOnRealEstate + " + str(tag)))
    # text rows (extraction shape): SIC (FIN-188) and provider industry (FIN-189)
    sic, sicd = submissions.get("sic"), submissions.get("sicDescription")
    fs.extraction.append(ExtractionRow(ticker, "sic_code", "", sic or "", "value" if sic else "MISSING", "", "sec_submissions"))
    fs.extraction.append(ExtractionRow(ticker, "sic_description", "", sicd or "", "value" if sicd else "MISSING", "", "sec_submissions"))
    fs.extraction.append(ExtractionRow(ticker, "provider_industry", "", provider_industry or "", "value" if provider_industry else "MISSING", "", "provider"))
    if reg and reg_engine:
        fs.extraction += rows_from_reg(reg_engine, ticker, reg)
        fs.has_reg = True
    return fs


def _key(nm: str) -> str:
    from .field_map import FIELDS
    return FIELDS["router"][nm]

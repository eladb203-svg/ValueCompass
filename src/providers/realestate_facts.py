"""INCOME_REAL_ESTATE data builder (spec 2026-10-14_10-05, sections 2-3): SEC XBRL (standard tags via companyfacts, company-extension elements via the
inline-XBRL fallback) for 10 fiscal years, plus the extracted-items CSV.

Every field is a priority chain; the tag used is logged per company-year. A field with no tag in a year is None and reported as "AI-extraction needed".
Items found only in text (same-property NOI, occupancy, largest tenant, maintenance capex / income-preserving TI-LC where untagged, committed facilities,
unencumbered NOI, secured debt, acquisition / development yields, disclosed fair value of real estate, JV share, reported NAREIT FFO) are loaded from
``scripts/realestate_extracted.csv`` with ``load_realestate_extracted`` (exact quote, source, admin-verified flag), as for BANK and INSURANCE.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from . import sec_ixbrl as ix
from .sec_companyfacts import ROOT, SecClient, _match, annual_series, fy_label

EXTRACTED_CSV = ROOT / "scripts" / "realestate_extracted.csv"
CIK_OVERRIDE = {"EQR": ("0000906107", "EQUITY RESIDENTIAL"), "AVB": ("0000915912", "AVALONBAY COMMUNITIES")}  # absent from SEC company_tickers.json

# field -> (kind, unit, [standard us-gaap tags in priority order])
RE_FIELDS: dict = {
    "total_revenue": ("flow", "USD", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax"]),
    "rental_revenue": ("flow", "USD", ["OperatingLeaseLeaseIncome", "LeaseIncome"]),
    "other_property_revenue": ("flow", "USD", []),
    "prop_opex": ("flow", "USD", ["DirectCostsOfLeasedAndRentedPropertyOrEquipment", "CostOfOtherPropertyOperatingExpense"]),
    "re_tax": ("flow", "USD", ["RealEstateTaxExpense", "RealEstateTaxesAndInsurance"]),
    "repairs": ("flow", "USD", ["CostOfPropertyRepairsAndMaintenance"]),
    "gains_re_entities": ("flow", "USD", ["EquityMethodInvestmentRealizedGainLossOnDisposal"]),
    "cost_of_revenue": ("flow", "USD", ["CostOfRevenue"]),
    "noi_reported": ("flow", "USD", []),
    "net_income": ("flow", "USD", ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"]),
    "pref_div": ("flow", "USD", ["PreferredStockDividendsIncomeStatementImpact", "DividendsPreferredStock", "DividendsPreferredStockCash",
                                 "PreferredStockDividendsAndOtherAdjustments"]),
    "interest_expense": ("flow", "USD", ["InterestExpense", "InterestExpenseDebt", "InterestExpenseNonoperating", "InterestExpenseOperating", "InterestExpenseBorrowings"]),
    "interest_capitalized": ("flow", "USD", ["InterestCostsCapitalized", "InterestPaidCapitalized", "InterestCostsCapitalizedAdjustment"]),
    "income_tax": ("flow", "USD", ["IncomeTaxExpenseBenefit"]),
    "da_total": ("flow", "USD", ["DepreciationAndAmortization", "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "Depreciation",
                                 "OtherDepreciationAndAmortization"]),
    "re_depr": ("flow", "USD", ["SECScheduleIIIRealEstateAccumulatedDepreciationDepreciationExpense"]),
    "gains_sale": ("flow", "USD", ["GainLossOnSaleOfProperties", "GainsLossesOnSalesOfInvestmentRealEstate", "GainLossOnSaleOfPropertyPlantEquipment",
                                   "GainLossOnDispositionOfAssets", "GainLossOnDispositionOfAssets1", "GainLossOnSaleOfOtherAssets"]),
    "impairment": ("flow", "USD", ["ImpairmentOfRealEstate", "AssetImpairmentCharges", "ImpairmentOfLongLivedAssetsHeldForUse"]),
    "debt_extinguishment": ("flow", "USD", ["GainsLossesOnExtinguishmentOfDebt"]),
    "transaction_costs": ("flow", "USD", ["BusinessCombinationAcquisitionRelatedCosts"]),
    "sbc": ("flow", "USD", ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]),
    "fx_unrealized": ("flow", "USD", ["ForeignCurrencyTransactionGainLossUnrealized", "ForeignCurrencyTransactionGainLossBeforeTax", "ForeignCurrencyTransactionGainLossUnrealizedAfterTax"]),
    "straight_line": ("flow", "USD", ["StraightLineRent", "StraightLineRentAdjustments"]),
    "maint_capex": ("flow", "USD", []),
    "equity_method_income": ("flow", "USD", ["IncomeLossFromEquityMethodInvestments"]),
    "eps": ("flow", "USD/shares", ["EarningsPerShareDiluted"]),
    "dps": ("flow", "USD/shares", ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"]),
    "shares_dil": ("flow", "shares", ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
    "shares_basic": ("flow", "shares", ["WeightedAverageNumberOfSharesOutstandingBasic"]),
    "shares_out": ("instant", "shares", ["CommonStockSharesOutstanding"]),
    "dividends": ("flow", "USD", ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsOfOrdinaryDividends", "DividendsCommonStock"]),
    "buybacks": ("flow", "USD", ["PaymentsForRepurchaseOfCommonStock"]),
    "acq_real_estate": ("flow", "USD", ["PaymentsToAcquireRealEstate", "PaymentsToAcquireCommercialRealEstate", "PaymentsToAcquireOtherRealEstate"]),
    "acq_business": ("flow", "USD", ["PaymentsToAcquireBusinessesNetOfCashAcquired"]),
    "development": ("flow", "USD", ["PaymentsToDevelopRealEstateAssets"]),
    "capital_improvements": ("flow", "USD", ["PaymentsForCapitalImprovements"]),
    "ti_lc_total": ("flow", "USD", ["PaymentsForTenantImprovements", "PaymentsForLeasingCostsCommissionsAndTenantImprovements"]),
    "sale_proceeds": ("flow", "USD", ["ProceedsFromSaleOfRealEstateHeldforinvestment", "ProceedsFromSaleOfProductiveAssets"]),
    "assets": ("instant", "USD", ["Assets"]),
    "intangibles_net": ("instant", "USD", ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"]),
    "re_net": ("instant", "USD", ["RealEstateInvestmentPropertyNet", "PropertyPlantAndEquipmentNet"]),
    "re_gross": ("instant", "USD", ["RealEstateGrossAtCarryingValue", "RealEstateInvestmentPropertyAtCost"]),
    "debt_total": ("instant", "USD", ["LongTermDebt", "DebtInstrumentCarryingAmount"]),
    "cash": ("instant", "USD", ["CashAndCashEquivalentsAtCarryingValue"]),
    "sti": ("instant", "USD", ["ShortTermInvestments"]),
    "mat_year1": ("instant", "USD", ["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"]),
    "mat_year2": ("instant", "USD", ["LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo"]),
    "secured_debt_tag": ("instant", "USD", ["SecuredDebt"]),
    # pricing round (RP2 conservative NAV): non-NOI assets and other claims at carrying value
    "equity_method_inv": ("instant", "USD", ["EquityMethodInvestments"]),
    "cip": ("instant", "USD", ["ConstructionInProgressGross", "RealEstateInvestmentPropertyConstructionInProgress"]),
    "re_dev_land": ("instant", "USD", ["RealEstateHeldForDevelopmentAndSale", "LandAndLandImprovements"]),
    "nci_total": ("instant", "USD", ["MinorityInterest"]),
    "pref_equity": ("instant", "USD", ["PreferredStockValue", "PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount", "PreferredStockValueOutstanding"]),
    "finance_lease_liab": ("instant", "USD", ["FinanceLeaseLiability", "FinanceLeaseLiabilityNoncurrent"]),
    "goodwill": ("instant", "USD", ["Goodwill"]),
    "nci_op": ("instant", "USD", ["MinorityInterestInOperatingPartnerships"]),
    "nci_lp": ("instant", "USD", ["MinorityInterestInLimitedPartnerships"]),
    "nci_redeemable": ("instant", "USD", ["RedeemableNoncontrollingInterestEquityCarryingAmount", "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests",
                                          "RedeemableNoncontrollingInterestEquityRedemptionValue"]),
}
PER_SHARE = ("eps", "dps")
SHARE_COUNTS = ("shares_dil", "shares_basic", "shares_out")
ZERO_IF_ABSENT_FLOW = ("pref_div", "impairment", "debt_extinguishment", "transaction_costs", "buybacks", "acq_real_estate", "acq_business", "development",
                       "capital_improvements")
# company-extension elements (inline XBRL of the 10-K): ticker -> field -> (local names, kind)
RE_EXT: dict = {
    "PLD": {"rental_revenue": (["RentalRevenue"], "flow"), "other_property_revenue": (["OtherRealEstateRevenue"], "flow"),
            "straight_line": (["StraightLineRentsAndAmortizationOfAboveAndBelowMarketLeases"], "flow"),
            "gains_sale": (["GainsOnOtherDispositionsOfInvestmentsInRealEstateNet"], "flow")},
    "BXP": {"rental_revenue": (["RentalRevenueTotal"], "flow"), "prop_opex": (["RentalExpensesOperatingExpensesTotal"], "flow")},
    "SPG": {"noi_reported": (["NetOperatingIncome"], "flow"), "dividends": (["PaymentsOfOrdinaryDividendsCommonStockAndPreferredStock"], "flow"),
            "gains_sale": (["AcquisitionOfControllingInterestSaleOrDisposalOfOrRecoveryOnAssetsAndInterestsInUnconsolidatedEntitiesGainOrLossAndImpairmentNet",
                            "AcquisitionOfControllingInterestSaleOrDisposalOfAssetsAndInterestsInUnconsolidatedEntitiesGainOrLossAndImpairmentNet"], "flow")},
    "FRT": {"noi_reported": (["PropertyOperatingIncome"], "flow"), "dividends": (["DividendsPaidToCommonAndPreferredShareholders"], "flow"), "gains_sale": (["GainOnSaleOfRealEstate"], "flow")},
    "WELL": {"noi_reported": (["NetOperatingIncome"], "flow"), "gains_sale": (["GainLossOnDispositionOfRealEstateAndAssetAcquisitionsNet"], "flow")},
    "EQR": {"noi_reported": (["NetOperatingIncomeLossFromRentalRealEstate"], "flow")},
    "PSA": {"dividends": (["DividendsAndDistributionsCommonStockAndShareBasedPaymentArrangementCash"], "flow"),
            "maint_capex": (["RealEstateInvestmentPropertyAtCostCapitalExpendituresToMaintainRealEstateFacilities"], "flow")},
}
# total financial debt when no single total is tagged: sum of standard tags (+ company-extension elements) -> (std tags, ext local names)
DEBT_PARTS: dict = {
    "O": (["NotesPayable", "SecuredDebt"], ["RevolvingCreditFacilityAndCommercialPaper"]),
    "BXP": (["SeniorNotes", "SecuredDebt", "ConvertibleDebt", "OtherBorrowings", "LineOfCredit"], []),
    "AMT": (["LongTermDebtAndCapitalLeaseObligations", "LongTermDebtCurrent"], []),
}
# NOI is always computed by us (RE13): property revenue (rental + other) - property operating expenses; the expense components differ by filer.
# components: fields subtracted from property revenue. "revenue_less_cost" = total revenue - cost of revenue (data centers: no property-level data, proxy, flagged).
# Company-reported NOI (SPG, FRT, EQR, WELL, ...) is only a reconciliation input (noi_reported).
NOI_COMPONENTS: dict = {
    "O": ["prop_opex"], "PLD": ["prop_opex"], "SPG": ["prop_opex", "re_tax", "repairs"], "FRT": ["prop_opex", "re_tax"], "BXP": ["prop_opex"], "ARE": ["prop_opex"],
    "EQR": ["repairs", "re_tax"], "AVB": ["prop_opex"], "EQIX": "revenue_less_cost", "AMT": ["prop_opex"], "PSA": ["prop_opex"], "WELL": ["prop_opex"],
}
NOI_METHOD: dict = NOI_COMPONENTS  # backwards-compatible name
ASSET_TYPE: dict = {
    "O": "net lease", "PLD": "industrial", "SPG": "retail (malls)", "FRT": "retail (shopping centers)", "BXP": "office", "ARE": "office (life science)",
    "EQR": "residential", "AVB": "residential", "EQIX": "data centers", "AMT": "communication towers", "PSA": "self-storage", "WELL": "healthcare",
}
# Table A utilization metric: occupancy unless economically irrelevant (towers) -> "not_applicable"
UTILIZATION: dict = {t: "occupancy" for t in ASSET_TYPE}
UTILIZATION["AMT"] = "not_applicable"
UTILIZATION["EQIX"] = "leased_capacity"
# revenue is rental only by construction: no separate lease-income tag (profile test uses total revenue, flagged)
RENTAL_PROXY = {"PSA": "all revenue is self-storage rental income (no lease-income tag)"}


def load_realestate_extracted(path: Path = EXTRACTED_CSV) -> dict:
    """ticker -> item -> {year(str or ''): {value, unit, quote, source, verified, note}}."""
    out: dict = defaultdict(lambda: defaultdict(dict))
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if not r.get("ticker") or r["ticker"].startswith("#"):
                continue
            try:
                v = float(r["value"])
            except (TypeError, ValueError):
                v = r["value"]
            out[r["ticker"]][r["item"]][r.get("year", "")] = {"value": v, "unit": r.get("unit", ""), "quote": r.get("quote", ""), "source": r.get("source", ""),
                                                              "verified": str(r.get("verified", "")).lower() in ("1", "true", "yes", "y"), "note": r.get("note", "")}
    _sum_quarters(out)
    return out


_QUARTER_ITEMS = {"maintenance_capex_q": "maintenance_capex", "ti_lc_income_preserving_q": "ti_lc_income_preserving", "straight_line_x_q": "straight_line_x", "reported_affo_q": "reported_affo"}


def _sum_quarters(out: dict) -> None:
    """Quarter rows ('FY2024Q3') of ``*_q`` items are summed to the fiscal year when all four quarters are present (provenance of every quarter is kept in the combined quote)."""
    for tk, items in out.items():
        for qitem, item in _QUARTER_ITEMS.items():
            rows = items.get(qitem)
            if not rows:
                continue
            years = {k[:-2] for k in rows if k[-2:-1] == "Q" and k[-1] in "1234"}
            for y in sorted(years):
                qs = [rows.get(f"{y}Q{i}") for i in (1, 2, 3, 4)]
                if any(q is None or not isinstance(q["value"], (int, float)) for q in qs):
                    continue
                items.setdefault(item, {})[y] = {"value": sum(q["value"] for q in qs), "unit": qs[0]["unit"], "verified": all(q["verified"] for q in qs),
                                  "quote": " || ".join(f"{i + 1}Q: {q['quote']}" for i, q in enumerate(qs)), "source": " || ".join(sorted({q["source"] for q in qs})),
                                  "note": "sum of the four quarters (" + qs[0]["note"] + ")"}


def build_realestate_series(sec: SecClient, ticker: str, splits: list, n_years: int = 10) -> dict:
    cik, title = CIK_OVERRIDE.get(ticker) or sec.cik_for(ticker)
    facts = sec.companyfacts(cik)
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    first_report = sec.first_annual_report(cik)
    all_tags = {name: list(tags) for name, (_, _, tags) in RE_FIELDS.items()}
    for std, _ in DEBT_PARTS.values():
        all_tags.setdefault("_debt_parts", [])
        all_tags["_debt_parts"] = sorted(set(all_tags["_debt_parts"]) | set(std))
    series = {name: {tag: annual_series(facts, tag, RE_FIELDS[name][1], RE_FIELDS[name][0]) for tag in tags} for name, tags in all_tags.items() if name in RE_FIELDS}
    parts_series = {tag: annual_series(facts, tag, "USD", "instant") for tag in all_tags.get("_debt_parts", [])}
    anchor: set = set()
    for tag in RE_FIELDS["net_income"][2]:
        anchor |= set(series["net_income"][tag])
    ends = sorted(anchor)
    dedup: list = []
    for e in ends:
        if dedup and (e - dedup[-1]).days <= 10:
            dedup[-1] = e
        else:
            dedup.append(e)
    ends = dedup[-n_years:]
    labels = [fy_label(e) for e in ends]
    n = len(ends)
    problems: list = []
    flags: list = []

    def split_factor(filed: date) -> float:
        fac = 1.0
        for d_, ratio in splits:
            if d_ > filed:
                fac *= ratio
        return fac

    f: dict = {}
    log: dict = {}
    for name, (kind, unit, tags) in RE_FIELDS.items():
        vals, lg = [], {}
        for end, lab in zip(ends, labels):
            fact = None
            for tag in tags:
                fact = _match(series[name][tag], end)
                if fact is not None:
                    break
            if fact is None:
                vals.append(None)
                lg[lab] = {"tag": None}
                continue
            v, fac = fact.val, 1.0
            if name in PER_SHARE or name in SHARE_COUNTS:
                fac = split_factor(fact.filed)
                v = v / fac if name in PER_SHARE else v * fac
            vals.append(v)
            lg[lab] = {"tag": fact.tag, "value": v, "filed": str(fact.filed), **({"split_adjust_factor": fac} if fac != 1.0 else {})}
        f[name], log[name] = vals, lg
    from .sec_companyfacts import guard_share_scale
    if guard_share_scale(f, labels, log, problems, SHARE_COUNTS):
        flags.append("share_scale_guard")
    # company-extension fallback (inline XBRL of the 10-K) for fields whose standard chain left years missing
    for name, (local_names, kind) in RE_EXT.get(ticker, {}).items():
        miss_ends = [e for e, v in zip(ends, f[name]) if v is None]
        if not miss_ends:
            continue
        try:
            got = ix.extension_series(sec, cik, local_names, kind, miss_ends)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name}: inline-XBRL extension fallback failed ({type(exc).__name__}: {exc})")
            continue
        for i, (end, lab) in enumerate(zip(ends, labels)):
            fact = got.get(end)
            if fact is not None and f[name][i] is None:
                f[name][i] = fact.val
                log[name][lab] = {"tag": fact.tag, "value": fact.val, "filed": str(fact.filed)}
    # total revenue: when no revenue tag exists, lease income stands in (flagged)
    miss_rev = [lab for i, lab in enumerate(labels) if f["total_revenue"][i] is None and f["rental_revenue"][i] is not None]
    for i, lab in enumerate(labels):
        if f["total_revenue"][i] is None and f["rental_revenue"][i] is not None:
            f["total_revenue"][i] = f["rental_revenue"][i]
            log["total_revenue"][lab] = {"tag": "lease income used (no total-revenue tag): " + str((log["rental_revenue"].get(lab) or {}).get("tag")), "value": f["total_revenue"][i]}
    if miss_rev:
        problems.append("total_revenue: no revenue tag, lease income used in " + ", ".join(miss_rev))
    # total debt: a single tagged total, else the sum of components (flagged)
    if ticker in DEBT_PARTS:
        std_tags, ext_names = DEBT_PARTS[ticker]
        ext_got = {}
        if ext_names:
            miss_ends = [e for e, v in zip(ends, f["debt_total"]) if v is None]
            try:
                ext_got = ix.extension_series(sec, cik, ext_names, "instant", miss_ends)
            except Exception as exc:  # noqa: BLE001
                problems.append(f"debt components: inline-XBRL extension fallback failed ({type(exc).__name__}: {exc})")
        for i, (end, lab) in enumerate(zip(ends, labels)):
            if f["debt_total"][i] is not None:
                continue
            parts = []
            for tag in std_tags:
                fa = _match(parts_series.get(tag, {}), end)
                if fa is not None:
                    parts.append((tag, fa.val))
            fa = ext_got.get(end)
            if fa is not None:
                parts.append((fa.tag, fa.val))
            if parts and (len(parts) >= 2 or ticker == "AMT"):
                f["debt_total"][i] = sum(v for _, v in parts)
                log["debt_total"][lab] = {"tag": "SUM: " + " + ".join(t for t, _ in parts), "value": f["debt_total"][i]}
    # plausibility of the total debt: a year whose tagged total implies an interest rate above 9% is a component, not the total -> missing (flagged)
    bad = []
    for i, lab in enumerate(labels):
        dv, ie = f["debt_total"][i], f["interest_expense"][i]
        if dv and ie and dv > 0 and ie / dv > 0.09:
            bad.append(lab)
            log["debt_total"][lab] = {"tag": "set missing: tagged total implies interest / debt above 9% (" + str(log["debt_total"].get(lab, {}).get("tag")) + ")", "value": dv}
            f["debt_total"][i] = None
    if bad:
        problems.append("debt_total: implausible (interest / debt above 9%, probably a component tag), set missing in " + ", ".join(bad))
    # zero-if-absent (flagged, as T10 in the general model); gains on sale are NOT assumed zero (they decide FFO)
    assumed: dict = {}
    for name in ZERO_IF_ABSENT_FLOW:
        labs = []
        for i, lab in enumerate(labels):
            if f[name][i] is None and f["net_income"][i] is not None:
                f[name][i] = 0.0
                log[name][lab] = {"tag": "assumed_zero", "value": 0.0}
                labs.append(lab)
        if labs:
            assumed[name] = labs
            problems.append(f"{name}: assumed_zero in {', '.join(labs)}")
    # shares_out cover-page fallback
    dei = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    from .sec_companyfacts import _d
    cover = []
    for i, (end, lab) in enumerate(zip(ends, labels)):
        if f["shares_out"][i] is None:
            c = [e for e in dei if e.get("form") in ("10-K", "10-K/A") and 0 < (_d(e["filed"]) - end).days <= 150]
            if c:
                e = min(c, key=lambda x: x["filed"])
                f["shares_out"][i] = float(e["val"]) * split_factor(_d(e["filed"]))
                log["shares_out"][lab] = {"tag": "dei:EntityCommonStockSharesOutstanding (cover page)", "value": f["shares_out"][i]}
                cover.append(lab)
    if cover:
        flags.append("shares_out_cover_page")
        problems.append("shares_out: balance-sheet tag missing, cover-page count used in " + ", ".join(cover))
    return {"cik": cik, "name": title, "sic": sub.get("sic"), "sic_description": sub.get("sicDescription"), "ends": ends, "labels": labels, "f": f,
            "tag_log": log, "first_annual_report": first_report, "flags": flags, "problems": problems, "assumed": assumed}

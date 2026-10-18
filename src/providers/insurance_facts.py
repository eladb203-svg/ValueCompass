"""INSURANCE profile data builder: XBRL (SEC companyfacts, 10 fiscal years) + inline-XBRL equity components + the extracted CSV.

Every field is a priority chain (the first tag with a value for the fiscal year wins) and the tag used is logged per company-year.
A field with no tag in a year is None ("AI-extraction needed" in the report). No uniform tag is assumed for reserve development
(I20): the chains differ by item and the log shows which one each company used.

Items found only in text (regulatory capital ratio, pledged assets, credit-quality table, portfolio composition, reserve / LDTI
movement tables where untagged, catastrophe losses, ALM disclosures) are loaded from ``scripts/insurance_regulatory.csv`` with
``load_insurance_regulatory``.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from . import sec_ixbrl as ix
from .sec_companyfacts import ROOT, SecClient, _match, annual_series, fy_label
from .sec_filings import _get_raw

REG_CSV = ROOT / "scripts" / "insurance_regulatory.csv"

# field -> (kind, unit, [tags in priority order])
INS_FIELDS: dict = {
    # --- income statement
    "revenue_total": ("flow", "USD", ["Revenues"]),
    "premiums": ("flow", "USD", ["PremiumsEarnedNet", "PremiumsEarnedNetPropertyAndCasualty"]),
    "policy_fees": ("flow", "USD", ["InsuranceCommissionsAndFees"]),
    "nii": ("flow", "USD", ["NetInvestmentIncome", "InvestmentIncomeNet"]),
    "gains_realized": ("flow", "USD", ["RealizedInvestmentGainsLosses", "GainLossOnInvestments", "DebtAndEquitySecuritiesGainLoss"]),
    "mrb_change": ("flow", "USD", ["MarketRiskBenefitChangeInFairValueGainLoss"]),
    "benefits": ("flow", "USD", ["PolicyholderBenefitsAndClaimsIncurredNet"]),
    "total_expenses": ("flow", "USD", ["BenefitsLossesAndExpenses"]),
    "interest_credited": ("flow", "USD", ["InterestCreditedToPolicyholdersAccountBalances", "InterestCreditedToPolicyOwnerAccount"]),
    "interest_expense": ("flow", "USD", ["InterestExpense", "InterestExpenseDebt", "InterestExpenseOperating", "InterestExpenseNonoperating",
                                         "InterestExpenseLongTermDebt", "InterestExpenseSubordinatedNotesAndDebentures"]),
    "goodwill_impairment": ("flow", "USD", ["GoodwillImpairmentLoss", "GoodwillAndIntangibleAssetImpairment"]),
    "pretax": ("flow", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                               "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]),
    "tax": ("flow", "USD", ["IncomeTaxExpenseBenefit"]),
    "net_income": ("flow", "USD", ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]),
    "disc_ops": ("flow", "USD", ["IncomeLossFromDiscontinuedOperationsNetOfTax", "IncomeLossFromDiscontinuedOperationsNetOfTaxAttributableToReportingEntity",
                                 "IncomeLossFromDiscontinuedOperationsNetOfTaxIncludingPortionAttributableToNoncontrollingInterest"]),
    "eps": ("flow", "USD/shares", ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"]),
    "shares_dil": ("flow", "shares", ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
    "shares_basic": ("flow", "shares", ["WeightedAverageNumberOfSharesOutstandingBasic"]),
    "dividends": ("flow", "USD", ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsOfOrdinaryDividends"]),
    "dps": ("flow", "USD/shares", ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"]),
    "buybacks": ("flow", "USD", ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"]),
    "acquisitions": ("flow", "USD", ["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross"]),
    # structural-change indicators for the float CAGR (Q4); absent = no tag (treated as no event, flagged by the report)
    "goodwill_acquired": ("flow", "USD", ["GoodwillAcquiredDuringPeriod"]),
    "divestiture_proceeds": ("flow", "USD", ["ProceedsFromDivestitureOfBusinessesNetOfCashDivested"]),
    "deconsolidation_cash": ("flow", "USD", ["CashDivestedFromDeconsolidation"]),
    "goodwill_written_off_sale": ("flow", "USD", ["GoodwillWrittenOffRelatedToSaleOfBusinessUnit"]),
    "pretax_foreign": ("flow", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign"]),
    # --- reserve development (I20: no uniform tag; chain order = most specific first)
    "prior_year_dev": ("flow", "USD", ["LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseIncurredClaimsPriorYears",
                                       "SupplementalInformationForPropertyCasualtyInsuranceUnderwritersPriorYearClaimsAndClaimsAdjustmentExpense",
                                       "SecSchedule1218SupplementalInformationPropertyCasualtyInsuranceUnderwritersPriorYearClaimAndClaimAdjustmentExpense"]),
    "ldti_remeasurement": ("flow", "USD", ["LiabilityForFuturePolicyBenefitRemeasurementGainLoss"]),
    "fpb_adverse_development": ("flow", "USD", ["LiabilityForFuturePolicyBenefitAdverseDevelopmentExpense"]),
    # --- balance sheet
    "assets": ("instant", "USD", ["Assets"]),
    "liabilities": ("instant", "USD", ["Liabilities"]),
    "equity": ("instant", "USD", ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "preferred": ("instant", "USD", ["PreferredStockValue", "PreferredStockValueOutstanding"]),
    "goodwill": ("instant", "USD", ["Goodwill"]),
    "intangibles": ("instant", "USD", ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"]),
    "claims_gross": ("instant", "USD", ["LiabilityForClaimsAndClaimsAdjustmentExpense"]),
    "claims_net": ("instant", "USD", ["LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseNet"]),
    "fpb": ("instant", "USD", ["LiabilityForFuturePolicyBenefits", "LiabilityForFuturePolicyBenefitAfterReinsurance"]),
    "pab": ("instant", "USD", ["PolicyholderContractDeposits", "PolicyholderFunds"]),
    "unearned": ("instant", "USD", ["UnearnedPremiums"]),
    "reins_unpaid": ("instant", "USD", ["ReinsuranceRecoverablesOnPaidAndUnpaidLosses", "ReinsuranceRecoverableForUnpaidClaimsAndClaimsAdjustments",
                                        "ReinsuranceRecoverables"]),
    "reins_prepaid": ("instant", "USD", ["PrepaidReinsurancePremiums"]),
    "separate_accounts": ("instant", "USD", ["SeparateAccountsLiability"]),
    "mrb_liability": ("instant", "USD", ["MarketRiskBenefitLiabilityAmount"]),
    "cash": ("instant", "USD", ["CashAndCashEquivalentsAtCarryingValue", "Cash", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
    "investments": ("instant", "USD", ["Investments"]),
    "debt_total": ("instant", "USD", ["DebtLongtermAndShorttermCombinedAmount"]),
    "debt_lt": ("instant", "USD", ["LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "NotesPayable"]),
    "debt_st": ("instant", "USD", ["ShortTermBorrowings", "DebtCurrent"]),
    "debt_junior_sub": ("instant", "USD", ["JuniorSubordinatedNotes", "SubordinatedDebt"]),
    "shares_out": ("instant", "shares", ["CommonStockSharesOutstanding"]),
    "aoci_total": ("instant", "USD", ["AccumulatedOtherComprehensiveIncomeLossNetOfTax"]),
    "aoci_afs_tag": ("instant", "USD", ["AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesAdjustmentNetOfTax"]),
    "_profit_loss": ("flow", "USD", ["ProfitLoss"]),
    "_pretax_dom": ("flow", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"]),
    "_pretax_for": ("flow", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign"]),
}
PER_SHARE = ("eps", "dps")
SHARE_COUNTS = ("shares_dil", "shares_basic", "shares_out")
ZERO_IF_ABSENT_FLOW = ("buybacks", "dividends", "acquisitions", "goodwill_impairment")
ZERO_IF_ABSENT_BS = ("goodwill", "intangibles", "preferred", "reins_prepaid")
# filings whose financial statements sit in a second document (suffix replaces ".htm" of the primary document)
EXTRA_DOC_SUFFIX = {"PGR": "_d2.htm"}

# AOCI equity-statement members -> rate-driven component (spec section 3, I13). FX translation, pension and cash-flow hedge are kept.
_AFS = re.compile(r"(NetUnrealizedInvestmentGainLoss(?!PreTax)|NetInvestmentGainLoss|DebtSecuritiesAvailableForSale|AvailableForSale|"
                  r"UnrealizedGainLossOnLifePolicyReserves)", re.I)
_DRR = re.compile(r"(LiabilityForFuturePolicyBenefit|FuturePolicyBenefit|DiscountRate)", re.I)
_CREDIT = re.compile(r"(InstrumentSpecificCreditRisk|OwnCredit)", re.I)


def classify_aoci_member(member: str) -> Optional[str]:
    """'afs' | 'drr' | 'credit' for the rate-driven AOCI components, None for components that are kept (FX, pension, hedges, total)."""
    m = member.split(":")[-1]
    if "PreTax" in m or "BeforeTax" in m:
        return None
    if _CREDIT.search(m):
        return "credit"
    if _DRR.search(m):
        return "drr"
    if _AFS.search(m):
        return "afs"
    return None


YIELDS_CSV = ROOT / "scripts" / "gov_yields.csv"


def load_gov_yields(path: Path = YIELDS_CSV) -> dict:
    """currency -> {'yields': {year: fraction}, 'source', 'series', 'retrieved', 'version'} from the versioned government-yield table."""
    out: dict = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if not str(r["year"]).isdigit():  # monthly rows (year = YYYY-MM, e.g. FRED GS10 for the real-estate cap rate) are not annual averages
                continue
            c = out.setdefault(r["currency"], {"yields": {}, "source": f"{r['series']} - {r['source']}", "series": r["series"],
                                               "retrieved": r["retrieved"], "version": r["version"]})
            c["yields"][int(r["year"])] = float(r["yield_pct"]) / 100.0
    return out


def load_insurance_regulatory(path: Path = REG_CSV) -> dict:
    """ticker -> item -> {value, unit, period, section, quote, verified, note}."""
    out: dict = defaultdict(dict)
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            v = r["value"]
            try:
                v = float(v)
            except ValueError:
                pass
            out[r["ticker"]][r["item"]] = {"value": v, "unit": r["unit"], "period": r.get("period", ""), "section": r["10-K section"],
                                          "quote": r["exact quote"], "verified": r["verified"] == "YES", "note": r["note"]}
    return out


def _filing_raw(sec: SecClient, cik: str, k: dict, ticker: str) -> list:
    acc = k["accession"].replace("-", "")
    docs = [k["primary"]]
    suf = EXTRA_DOC_SUFFIX.get(ticker)
    if suf:
        docs.append(k["primary"].replace(".htm", suf))
    return [_get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{d}", f"{acc}_{d}") for d in docs]


def aoci_components(sec: SecClient, cik: str, ticker: str, ends: list, max_filings: int = 4) -> dict:
    """{end: {'afs','drr','credit' (USD, net of tax), 'members': {component: [member names]}}} from the equity statement of the 10-K inline XBRL.

    Reads 10-Ks newest first until every fiscal-year end in ``ends`` plus the year before the first is covered. Only members that sit alone
    on the StatementEquityComponentsAxis are used (undimensioned total excluded). Companies whose statements do not itemize the rate-driven
    components return nothing for them ("AI-extraction needed" or the balance-sheet AFS tag).
    """
    need = set(ends)
    out: dict = {}
    used = 0
    for k in ix.tenk_filings(sec, cik):
        if used >= max_filings or not need:
            break
        if all(abs((k["report_date"] - e).days) > 1500 for e in need):
            continue
        used += 1
        for raw in _filing_raw(sec, cik, k, ticker):
            ctx = ix.parse_contexts(raw)
            found: dict = {}
            for attrs, text in ix._NF.findall(raw):
                full = ix._attr(attrs, "name") or ""
                if full.split(":")[-1] not in ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"):
                    continue
                c = ctx.get(ix._attr(attrs, "contextRef") or "")
                if not c or not c["instant"] or len(c["dims"]) != 1 or "StatementEquityComponentsAxis" not in c["dims"][0][0]:
                    continue
                comp = classify_aoci_member(c["dims"][0][1])
                if comp is None:
                    continue
                v = ix.parse_numeric(attrs, text)
                if v is None:
                    continue
                found.setdefault(c["end"], {}).setdefault(comp, {})[c["dims"][0][1].split(":")[-1]] = v
            for end, comps in found.items():
                m = next((e for e in need if abs((e - end).days) <= 10), None)
                if m is None or m in out:
                    continue
                out[m] = {"members": {c: sorted(v) for c, v in comps.items()}, "accession": k["accession"],
                          **{c: sum(v.values()) for c, v in comps.items()}}
        need -= set(out)
    return out


_ACC_BENEFIT = "LiabilityForFuturePolicyBenefitExpectedFuturePolicyBenefitInterestExpense"
_ACC_PREMIUM = "LiabilityForFuturePolicyBenefitExpectedNetPremiumInterestIncome"


def _aggregate_rollforward(contexts_values: list) -> tuple:
    """contexts_values: [(dims [(axis, member)], value)] of one roll-forward element for one year.

    Contexts carrying a deferred-profit-liability member are separate liabilities and are excluded. If a context whose member starts with
    'Total' exists it is the aggregate. Otherwise, when a context with fewer dimensions equals the sum of the contexts with the most dimensions
    (within 0.5%) it is the aggregate (Chubb: segment total = sum of products); otherwise the leaf contexts are summed.
    Returns (value, rule, n_contexts).
    """
    cv = [(d, v) for d, v in contexts_values if not any("DeferredProfit" in m for _, m in d)]
    if not cv:
        return None, "none", 0
    tot = [(d, v) for d, v in cv if any(m.split(":")[-1].startswith("Total") for _, m in d)]
    if tot:
        return tot[0][1], "company-reported total member", len(tot)
    maxd = max(len(d) for d, _ in cv)
    leaves = [v for d, v in cv if len(d) == maxd]
    lo = [v for d, v in cv if len(d) < maxd]
    sl = sum(leaves)
    for v in lo:
        if sl and abs(v - sl) / abs(sl) < 0.005:
            return v, "aggregate context equal to the sum of the product contexts", len(cv)
    return sl, "sum of product / segment contexts", len(leaves)


def ldti_accretion(sec: SecClient, cik: str, ticker: str, ends: list, max_filings: int = 4) -> dict:
    """{end: {'benefit_interest','premium_interest','net','rule_b','rule_p','accession'}} from the LDTI roll-forward elements in the 10-K inline XBRL
    (interest accretion on the present value of expected future policy benefits and on expected net premiums; net = benefits - premiums)."""
    need = set(ends)
    out: dict = {}
    used = 0
    for k in ix.tenk_filings(sec, cik):
        if used >= max_filings or not need:
            break
        if all(abs((k["report_date"] - e).days) > 1500 for e in need):
            continue
        used += 1
        for raw in _filing_raw(sec, cik, k, ticker):
            ctx = ix.parse_contexts(raw)
            vals: dict = {}
            for attrs, text in ix._NF.findall(raw):
                loc = (ix._attr(attrs, "name") or "").split(":")[-1]
                if loc not in (_ACC_BENEFIT, _ACC_PREMIUM):
                    continue
                c = ctx.get(ix._attr(attrs, "contextRef") or "")
                if not c or c["instant"] or not 340 <= (c["end"] - c["start"]).days <= 380:
                    continue
                v = ix.parse_numeric(attrs, text)
                if v is None:
                    continue
                vals.setdefault((c["end"], loc), {})[tuple(c["dims"])] = v
            years = {e for e, _ in vals}
            for end in years:
                m = next((e for e in need if abs((e - end).days) <= 10), None)
                if m is None or m in out:
                    continue
                b, rb, nb = _aggregate_rollforward([(list(dm), v) for dm, v in vals.get((end, _ACC_BENEFIT), {}).items()])
                p, rp, np_ = _aggregate_rollforward([(list(dm), v) for dm, v in vals.get((end, _ACC_PREMIUM), {}).items()])
                if b is None:
                    continue
                out[m] = {"benefit_interest": b, "premium_interest": p or 0.0, "net": b - (p or 0.0), "rule_benefit": rb, "rule_premium": rp,
                          "n_benefit_contexts": nb, "n_premium_contexts": np_, "accession": k["accession"]}
        need -= set(out)
    return out


def build_insurance_series(sec: SecClient, ticker: str, splits: list, n_years: int = 10, with_aoci: bool = True) -> dict:
    cik, title = sec.cik_for(ticker)
    facts = sec.companyfacts(cik)
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    first_report = sec.first_annual_report(cik)
    series = {name: {tag: annual_series(facts, tag, unit, kind) for tag in tags} for name, (kind, unit, tags) in INS_FIELDS.items()}
    anchor = set()
    for s in list(series["net_income"].values()) + list(series["_profit_loss"].values()):
        anchor |= set(s)
    ends = sorted(anchor)
    dedup: list = []
    for e in ends:
        if dedup and (e - dedup[-1]).days <= 10:
            dedup[-1] = e
        else:
            dedup.append(e)
    ends = dedup[-n_years:]
    labels = [fy_label(e) for e in ends]
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
    for name, (kind, unit, tags) in INS_FIELDS.items():
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
    n = len(ends)
    for fld in SHARE_COUNTS:
        sc = [lab for lab, v in zip(labels, f[fld]) if v is not None and v < 1e5]
        if sc:
            f[fld] = [v * 1e6 if (v is not None and v < 1e5) else v for v in f[fld]]
            problems.append(f"{fld}: reported in millions in {', '.join(sc)} -> rescaled x1e6")
    # shares_out cover-page fallback
    dei = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    cover = []
    from .sec_companyfacts import _d
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
    from .sec_companyfacts import guard_share_scale
    if guard_share_scale(f, labels, log, problems, SHARE_COUNTS):
        flags.append("share_scale_guard")
    # net income fallback and pretax fallbacks
    for i, lab in enumerate(labels):
        if f["net_income"][i] is None and f["_profit_loss"][i] is not None:
            f["net_income"][i] = f["_profit_loss"][i]
            log["net_income"][lab] = {"tag": "ProfitLoss (includes noncontrolling interest)", "value": f["net_income"][i]}
        if f["pretax"][i] is None and f["_pretax_dom"][i] is not None and f["_pretax_for"][i] is not None:
            f["pretax"][i] = f["_pretax_dom"][i] + f["_pretax_for"][i]
            log["pretax"][lab] = {"tag": "DERIVED: pretax domestic + foreign", "value": f["pretax"][i]}
        if f["pretax"][i] is None and f["revenue_total"][i] is not None and f["total_expenses"][i] is not None:
            f["pretax"][i] = f["revenue_total"][i] - f["total_expenses"][i]
            log["pretax"][lab] = {"tag": "DERIVED: Revenues - BenefitsLossesAndExpenses", "value": f["pretax"][i]}
    # total expenses: when BenefitsLossesAndExpenses is not tagged, revenues - pretax income is the same quantity (identity)
    for i, lab in enumerate(labels):
        if f["total_expenses"][i] is None and f["revenue_total"][i] is not None and f["pretax"][i] is not None:
            f["total_expenses"][i] = f["revenue_total"][i] - f["pretax"][i]
            log["total_expenses"][lab] = {"tag": "DERIVED: Revenues - pretax income (BenefitsLossesAndExpenses not tagged)", "value": f["total_expenses"][i]}
    # zero-if-absent (flagged)
    assumed: dict = {}
    for name in ZERO_IF_ABSENT_FLOW + ZERO_IF_ABSENT_BS:
        labs = []
        anchor_field = "net_income" if name in ZERO_IF_ABSENT_FLOW else "assets"
        for i, lab in enumerate(labels):
            if f[name][i] is None and f[anchor_field][i] is not None:
                f[name][i] = 0.0
                log[name][lab] = {"tag": "assumed_zero", "value": 0.0}
                labs.append(lab)
        if labs:
            assumed[name] = labs
            problems.append(f"{name}: assumed_zero in {', '.join(labs)}")
    # AOCI components (inline XBRL equity statement)
    aoci_log: dict = {}
    f["aoci_afs"], f["aoci_drr"], f["aoci_credit"] = [None] * n, [None] * n, [None] * n
    if with_aoci:
        comp = aoci_components(sec, cik, ticker, ends)
        for i, (end, lab) in enumerate(zip(ends, labels)):
            c = comp.get(end)
            tag_afs = f["aoci_afs_tag"][i]
            if c and "afs" in c:
                f["aoci_afs"][i] = c["afs"]
                aoci_log[lab] = {"source": "inline XBRL equity statement", "members": c["members"]}
            elif tag_afs is not None:
                f["aoci_afs"][i] = tag_afs
                aoci_log[lab] = {"source": "balance-sheet tag AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesAdjustmentNetOfTax"}
            for key in ("drr", "credit"):
                if c and key in c:
                    f[f"aoci_{key}"][i] = c[key]
    log["aoci"] = aoci_log
    f["ldti_accretion_net"] = [None] * n
    acc_log: dict = {}
    if with_aoci:
        acc = ldti_accretion(sec, cik, ticker, ends)
        for i, (end, lab) in enumerate(zip(ends, labels)):
            a = acc.get(end)
            if a:
                f["ldti_accretion_net"][i] = a["net"]
                acc_log[lab] = a
    log["ldti_accretion"] = acc_log
    for k in [k for k in f if k.startswith("_")]:
        f.pop(k)
        log.pop(k, None)
    return {"cik": cik, "name": title, "sic": sub.get("sic"), "sic_description": sub.get("sicDescription"), "ends": ends, "labels": labels,
            "f": f, "tag_log": log, "first_annual_report": first_report, "flags": flags, "problems": problems, "assumed": assumed}

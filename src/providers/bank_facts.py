"""BANK profile data builder: XBRL (SEC companyfacts, 10 fiscal years) + the extracted regulatory CSV.

Bank statements use many tag variants, so each field is a priority chain (first available per fiscal year, logged).
Extracted FY2025 items (scripts/bank_regulatory.csv) are loaded separately by ``load_regulatory``.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from .sec_companyfacts import ROOT, SecClient, _d, _match, annual_series, fy_label

REG_CSV = ROOT / "scripts" / "bank_regulatory.csv"

# field -> (kind, unit, [tags in priority order])
BANK_FIELDS: dict = {
    "net_income": ("flow", "USD", ["NetIncomeLoss"]),
    "_profit_loss": ("flow", "USD", ["ProfitLoss"]),
    "_nci": ("flow", "USD", ["NetIncomeLossAttributableToNoncontrollingInterest"]),
    "ni_common": ("flow", "USD", ["NetIncomeLossAvailableToCommonStockholdersBasic"]),
    "pref_div": ("flow", "USD", ["PreferredStockDividendsIncomeStatementImpact", "DividendsPreferredStock",
                                 "PreferredStockDividendsAndOtherAdjustments", "DividendsPreferredStockCash",
                                 "PaymentsOfDividendsPreferredStockAndPreferenceStock"]),
    "pretax": ("flow", "USD", [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]),
    "_pretax_dom": ("flow", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"]),
    "_pretax_for": ("flow", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign"]),
    "eps": ("flow", "USD/shares", ["EarningsPerShareDiluted"]),
    "shares_dil": ("flow", "shares", ["WeightedAverageNumberOfDilutedSharesOutstanding"]),
    "shares_basic": ("flow", "shares", ["WeightedAverageNumberOfSharesOutstandingBasic"]),
    "provision": ("flow", "USD", ["ProvisionForLoanLeaseAndOtherLosses", "ProvisionForLoanLossesExpensed",
                                  "ProvisionForLoanAndLeaseLosses"]),
    "_nii_after_prov": ("flow", "USD", ["InterestIncomeExpenseAfterProvisionForLoanLoss"]),
    "_prov_loans": ("flow", "USD", ["FinancingReceivableExcludingAccruedInterestCreditLossExpenseReversal"]),
    "_prov_offbs": ("flow", "USD", ["OffBalanceSheetCreditLossLiabilityCreditLossExpenseReversal"]),
    "nii": ("flow", "USD", ["InterestIncomeExpenseNet"]),
    "nonint": ("flow", "USD", ["NoninterestIncome"]),
    "goodwill_acquired": ("flow", "USD", ["GoodwillAcquiredDuringPeriod"]),
    # V5 adjusted PPNR add-backs (standard tags; absent = tag not found, reported per bank-year)
    "_sec_real_gain": ("flow", "USD", ["DebtSecuritiesAvailableForSaleRealizedGain"]),
    "_sec_real_loss": ("flow", "USD", ["DebtSecuritiesAvailableForSaleRealizedLoss"]),
    "goodwill_impairment": ("flow", "USD", ["GoodwillImpairmentLoss", "GoodwillAndIntangibleAssetImpairment", "GoodwillImpairmentLossNetOfTax"]),
    "securities_gain_loss": ("flow", "USD", ["DebtSecuritiesRealizedGainLoss", "DebtSecuritiesAvailableForSaleRealizedGainLoss",
                                             "AvailableForSaleSecuritiesGainLossIncludingOtherThanTemporaryImpairment",
                                             "MarketableSecuritiesRealizedGainLoss", "GainLossOnSaleOfSecuritiesNet",
                                             "DebtAndEquitySecuritiesGainLoss",
                                             "GainLossOnSaleOfAvailableForSaleSecuritiesNet", "GainLossOnInvestments"]),
    "acquisitions": ("flow", "USD", ["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross"]),
    "buybacks": ("flow", "USD", ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"]),
    "dividends": ("flow", "USD", ["PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends", "PaymentsOfDividends"]),
    "dps": ("flow", "USD/shares", ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"]),
    "_nco_net": ("flow", "USD", [
        "FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossWriteoffAfterRecovery",
        "FinancingReceivableAllowanceForCreditLossWriteoffAfterRecovery",
        "AllowanceForLoanAndLeaseLossesWriteoffsNet"]),
    "_wo_gross": ("flow", "USD", ["FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossWriteoff",
                                  "FinancingReceivableAllowanceForCreditLossesWriteOffs",
                                  "AllowanceForLoanAndLeaseLossesWriteOffs"]),
    "_recoveries": ("flow", "USD", ["FinancingReceivableExcludingAccruedInterestAllowanceForCreditLossRecovery",
                                    "FinancingReceivableAllowanceForCreditLossesRecovery"]),
    "assets": ("instant", "USD", ["Assets"]),
    "equity": ("instant", "USD", ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "preferred": ("instant", "USD", ["PreferredStockValue", "PreferredStockValueOutstanding",
                                     "PreferredStockIncludingAdditionalPaidInCapitalNetOfDiscount",
                                     "PreferredStockIncludingAdditionalPaidInCapital"]),
    "goodwill": ("instant", "USD", ["Goodwill"]),
    "intangibles": ("instant", "USD", ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"]),
    "loans": ("instant", "USD", ["FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss",
                                 "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLossFeeAndLoanInProcess",
                                 "NotesReceivableGross", "LoansAndLeasesReceivableNetOfDeferredIncome",
                                 "LoansAndLeasesReceivableGrossCarryingAmount"]),
    "deposits": ("instant", "USD", ["Deposits"]),
    "st_borrow": ("instant", "USD", ["ShortTermBorrowings", "OtherShortTermBorrowings"]),
    "lt_debt": ("instant", "USD", ["LongTermDebt", "LongTermDebtNoncurrent",
                                   "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
                                   "LongTermDebtAndCapitalLeaseObligations"]),
    "fhlb": ("instant", "USD", ["AdvancesFromFederalHomeLoanBanks"]),
    "shares_out": ("instant", "shares", ["CommonStockSharesOutstanding"]),
    "acl": ("instant", "USD", ["FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest",
                               "FinancingReceivableAllowanceForCreditLosses", "LoansAndLeasesReceivableAllowance"]),
    "nonaccrual": ("instant", "USD", ["FinancingReceivableExcludingAccruedInterestNonaccrual",
                                      "FinancingReceivableRecordedInvestmentNonaccrualStatus"]),
    "past_due_90": ("instant", "USD", ["FinancingReceivableExcludingAccruedInterest90DaysOrMorePastDueStillAccruing"]),
}
PER_SHARE = ("eps", "dps")
SHARE_COUNTS = ("shares_dil", "shares_basic", "shares_out")
ZERO_IF_ABSENT_FLOW = ("buybacks", "dividends", "acquisitions", "goodwill_acquired", "pref_div")  # pref_div: Rulebook C5 / CL12, after the net income - net income to common derivation
ZERO_IF_ABSENT_BS = ("goodwill", "intangibles", "preferred", "st_borrow", "lt_debt", "fhlb")


def load_regulatory(path: Path = REG_CSV) -> dict:
    """ticker -> item -> {value, unit, section, quote, verified, note}; multi-row items (loan:*, past_due_90_*) are keyed by item."""
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
            out[r["ticker"]][r["item"]] = {"value": v, "unit": r["unit"], "section": r["10-K section"],
                                          "quote": r["exact quote"], "verified": r["verified"] == "YES", "note": r["note"]}
    return out


def build_bank_series(sec: SecClient, ticker: str, splits: list, n_years: int = 10) -> dict:
    cik, title = sec.cik_for(ticker)
    facts = sec.companyfacts(cik)
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    first_report = sec.first_annual_report(cik)
    series = {name: {tag: annual_series(facts, tag, unit, kind) for tag in tags}
              for name, (kind, unit, tags) in BANK_FIELDS.items()}
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
    for name, (kind, unit, tags) in BANK_FIELDS.items():
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
            lg[lab] = {"tag": fact.tag, "value": v, "filed": str(fact.filed),
                       **({"split_adjust_factor": fac} if fac != 1.0 else {})}
        f[name], log[name] = vals, lg
    n = len(ends)

    # shares reported in millions -> rescale
    for fld in SHARE_COUNTS:
        sc = [lab for lab, v in zip(labels, f[fld]) if v is not None and v < 1e5]
        if sc:
            f[fld] = [v * 1e6 if (v is not None and v < 1e5) else v for v in f[fld]]
            problems.append(f"{fld}: reported in millions in {', '.join(sc)} -> rescaled x1e6")
    # period-end shares: cover-page fallback
    dei = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
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
    from .sec_companyfacts import guard_share_scale
    if guard_share_scale(f, labels, log, problems, SHARE_COUNTS):
        flags.append("share_scale_guard")

    # net income attributable to the parent: ProfitLoss - noncontrolling interest when NetIncomeLoss is not tagged
    for i, lab in enumerate(labels):
        if f["net_income"][i] is None and f["_profit_loss"][i] is not None:
            f["net_income"][i] = f["_profit_loss"][i] - (f["_nci"][i] or 0.0)
            log["net_income"][lab] = {"tag": "DERIVED: ProfitLoss - NetIncomeLossAttributableToNoncontrollingInterest",
                                      "value": f["net_income"][i]}
    # pretax fallback
    for i, lab in enumerate(labels):
        if f["pretax"][i] is None and f["_pretax_dom"][i] is not None and f["_pretax_for"][i] is not None:
            f["pretax"][i] = f["_pretax_dom"][i] + f["_pretax_for"][i]
            log["pretax"][lab] = {"tag": "DERIVED: domestic + foreign", "value": f["pretax"][i]}
    # preferred dividends fallback: net income - net income to common
    for i, lab in enumerate(labels):
        if f["pref_div"][i] is None and f["net_income"][i] is not None and f["ni_common"][i] is not None:
            f["pref_div"][i] = f["net_income"][i] - f["ni_common"][i]
            log["pref_div"][lab] = {"tag": "DERIVED: net income - net income to common", "value": f["pref_div"][i]}
    # realized securities gain/loss fallback: gross realized gains - gross realized losses
    for i, lab in enumerate(labels):
        if f["securities_gain_loss"][i] is None and f["_sec_real_gain"][i] is not None and f["_sec_real_loss"][i] is not None:
            f["securities_gain_loss"][i] = f["_sec_real_gain"][i] - f["_sec_real_loss"][i]
            log["securities_gain_loss"][lab] = {"tag": "DERIVED: DebtSecuritiesAvailableForSaleRealizedGain - ...RealizedLoss",
                                                "value": f["securities_gain_loss"][i]}
    # provision fallbacks
    for i, lab in enumerate(labels):
        if f["provision"][i] is None:
            if f["nii"][i] is not None and f["_nii_after_prov"][i] is not None:
                f["provision"][i] = f["nii"][i] - f["_nii_after_prov"][i]
                log["provision"][lab] = {"tag": "DERIVED: NII - NII after provision", "value": f["provision"][i]}
            elif f["_prov_loans"][i] is not None:
                f["provision"][i] = f["_prov_loans"][i] + (f["_prov_offbs"][i] or 0.0)
                log["provision"][lab] = {"tag": "DERIVED: loans credit-loss expense + off-balance-sheet", "value": f["provision"][i]}
    # net charge-offs: net tag, else gross write-offs - recoveries
    f["nco"], log["nco"] = [], {}
    for i, lab in enumerate(labels):
        if f["_nco_net"][i] is not None:
            f["nco"].append(f["_nco_net"][i])
            log["nco"][lab] = {"tag": log["_nco_net"][lab]["tag"], "value": f["_nco_net"][i]}
        elif f["_wo_gross"][i] is not None and f["_recoveries"][i] is not None:
            f["nco"].append(f["_wo_gross"][i] - f["_recoveries"][i])
            log["nco"][lab] = {"tag": "DERIVED: write-offs - recoveries", "value": f["nco"][-1]}
        else:
            f["nco"].append(None)
            log["nco"][lab] = {"tag": None}
    # acquisitions: goodwill acquired in the year as a lower-bound proxy when the cash tag is absent (C6)
    assumed: dict = {}
    for i, lab in enumerate(labels):
        if f["acquisitions"][i] is None and f["goodwill_acquired"][i] is not None and f["net_income"][i] is not None:
            f["acquisitions"][i] = f["goodwill_acquired"][i]
            log["acquisitions"][lab] = {"tag": "PROXY: GoodwillAcquiredDuringPeriod (lower bound)", "value": f["acquisitions"][i]}
            assumed.setdefault("acquisitions_proxy_goodwill", []).append(lab)
    # absent line items -> 0 when the parent statement exists (flagged)
    for name in ZERO_IF_ABSENT_FLOW:
        for i, lab in enumerate(labels):
            if f[name][i] is None and f["net_income"][i] is not None:
                f[name][i] = 0.0
                log[name][lab] = {"tag": "assumed_zero", "value": 0.0}
                assumed.setdefault(name, []).append(lab)
    for name in ZERO_IF_ABSENT_BS:
        for i, lab in enumerate(labels):
            if f[name][i] is None and f["assets"][i] is not None:
                f[name][i] = 0.0
                log[name][lab] = {"tag": "assumed_zero", "value": 0.0}
                assumed.setdefault(name, []).append(lab)
    for name, labs in assumed.items():
        if name == "acquisitions_proxy_goodwill":
            problems.append(f"acquisitions: cash tag absent, GoodwillAcquiredDuringPeriod used as lower-bound proxy (C6) in {', '.join(labs)}")
        elif len(labs) == n:
            problems.append(f"{name}: no XBRL tag in any year -> assumed_zero")
        else:
            problems.append(f"{name}: assumed_zero in {', '.join(labs)}")
    for name in ("net_income", "pretax", "eps", "provision", "nii", "nonint", "assets", "equity", "loans", "deposits",
                 "shares_out", "dps", "nco", "acl"):  # dps: derived from dividends / basic shares later when missing
        miss = [l for l, v in zip(labels, f[name]) if v is None]
        if miss:
            problems.append(f"{name}: missing in {', '.join(miss)}" if len(miss) < n else f"{name}: no data in any year")
    # tag-chain switches
    for name in ("loans", "nco", "acl", "provision", "pref_div", "preferred"):
        tags = {v.get("tag") for v in log[name].values() if v.get("tag")}
        if len(tags) > 1:
            problems.append(f"{name}: tag changes across years -> {sorted(tags)}")
    for k in [k for k in f if k.startswith("_")]:
        f.pop(k)
        log.pop(k, None)
    return {"cik": cik, "name": title, "sic": sub.get("sic"), "sic_description": sub.get("sicDescription"),
            "ends": ends, "labels": labels, "f": f, "tag_log": log, "first_annual_report": first_report,
            "flags": flags, "problems": problems, "assumed": assumed}

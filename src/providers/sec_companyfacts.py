"""SEC EDGAR provider: companyfacts XBRL -> annual (10-K, fp=FY) fiscal-year series.

Respects the SEC fair-access limits (<= 10 requests/s, identifying User-Agent). Raw JSON is cached
under scripts/cache/sec so reruns do not hit the SEC again. No Supabase, no secrets printed.
"""
from __future__ import annotations

import statistics

import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

from src.net import retry_network

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "scripts" / "cache" / "sec"
MIN_INTERVAL = 0.15  # seconds between requests (< 10 req/s)
ANNUAL_FORMS = ("10-K", "10-K/A", "10-KT", "10-K405")
FIRST_REPORT_FORMS = ("10-K", "10-K405", "10-KT")

# field -> (kind, unit, [us-gaap tags in priority order])
FIELD_MAP: dict = {
    "revenue": ("flow", "USD", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                                "SalesRevenueGoodsNet", "SalesRevenueServicesNet"]),
    "gross_profit": ("flow", "USD", ["GrossProfit"]),
    "cost_of_revenue": ("flow", "USD", ["CostOfRevenue", "CostOfGoodsAndServicesSold"]),
    "_cogs_goods": ("flow", "USD", ["CostOfGoodsSold"]),
    "_cogs_services": ("flow", "USD", ["CostOfServices"]),
    "_cogs_amort1": ("flow", "USD", ["CostOfGoodsAndServicesSoldAmortization"]),
    "_cogs_amort2": ("flow", "USD", ["CostOfServicesAmortization"]),
    "deferred_rev_current": ("instant", "USD", ["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"]),
    "_funds_held": ("instant", "USD", ["FundsHeldForClients"]),
    "_restricted_cash": ("instant", "USD", ["RestrictedCashAndCashEquivalents", "RestrictedCashCurrent"]),
    "impairments": ("flow", "USD", ["GoodwillImpairmentLoss", "AssetImpairmentCharges",
                                    "GoodwillAndIntangibleAssetImpairment"]),
    "ebit": ("flow", "USD", ["OperatingIncomeLoss"]),
    "pretax": ("flow", "USD", [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]),
    "_pretax_dom": ("flow", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic"]),
    "_pretax_for": ("flow", "USD", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign"]),
    "tax": ("flow", "USD", ["IncomeTaxExpenseBenefit"]),
    "net_income": ("flow", "USD", ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic",
                                   "ProfitLoss"]),
    "interest_expense": ("flow", "USD", ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt",
                                         "InterestExpenseLongTermDebt", "InterestAndDebtExpense"]),
    "eps": ("flow", "USD/shares", ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"]),
    "shares": ("flow", "shares", ["WeightedAverageNumberOfDilutedSharesOutstanding",
                                  "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted"]),
    "shares_basic": ("flow", "shares", ["WeightedAverageNumberOfSharesOutstandingBasic"]),
    "shares_out": ("instant", "shares", ["CommonStockSharesOutstanding"]),
    "da": ("flow", "USD", ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                           "DepreciationAndAmortization", "DepreciationAmortizationAndOther"]),
    "_dep": ("flow", "USD", ["Depreciation"]),
    "_fin_lease_amort": ("flow", "USD", ["FinanceLeaseRightOfUseAssetAmortization"]),
    "goodwill_acquired": ("flow", "USD", ["GoodwillAcquiredDuringPeriod"]),
    "acq_amort": ("flow", "USD", ["AmortizationOfIntangibleAssets", "FiniteLivedIntangibleAssetsAmortizationExpense"]),
    "cfo": ("flow", "USD", ["NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),
    "capex": ("flow", "USD", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
                              "PaymentsForCapitalImprovements", "PaymentsToAcquireOtherPropertyPlantAndEquipment"]),
    "sbc": ("flow", "USD", ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]),
    "acquisitions": ("flow", "USD", ["PaymentsToAcquireBusinessesNetOfCashAcquired",
                                     "PaymentsToAcquireBusinessesGross",
                                     "PaymentsToAcquireBusinessesAndInterestInAffiliates"]),
    "buybacks": ("flow", "USD", ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"]),
    "dividends": ("flow", "USD", ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends",
                                  "PaymentsOfOrdinaryDividends"]),
    "dps": ("flow", "USD/shares", ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"]),
    "assets": ("instant", "USD", ["Assets"]),
    "cur_assets": ("instant", "USD", ["AssetsCurrent"]),
    "cur_liab": ("instant", "USD", ["LiabilitiesCurrent"]),
    "liabilities": ("instant", "USD", ["Liabilities"]),
    "cash": ("instant", "USD", ["CashAndCashEquivalentsAtCarryingValue",
                                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
    "sti": ("instant", "USD", ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                               "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "OtherShortTermInvestments"]),
    "equity": ("instant", "USD", ["StockholdersEquity",
                                  "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]),
    "goodwill": ("instant", "USD", ["Goodwill"]),
    "intangibles": ("instant", "USD", ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"]),
    "receivables": ("instant", "USD", ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
                                       "AccountsAndOtherReceivablesNetCurrent",
                                       # managed care / insurers (ETL fix 2026-10-13): premium receivables
                                       "PremiumsReceivableAtCarryingValue", "PremiumsAndOtherReceivablesNet"]),
    # insurers / managed care (display and v1.1 candidates; not used by default scoring)
    "claims_liability": ("instant", "USD", ["LiabilityForClaimsAndClaimsAdjustmentExpense",
                                            "LiabilityForUnpaidClaimsAndClaimsAdjustmentExpenseNet"]),
    "claims_expense": ("flow", "USD", ["PolicyholderBenefitsAndClaimsIncurredNet"]),
    "lt_mdebt_explicit": ("instant", "USD", ["AvailableForSaleSecuritiesDebtSecuritiesNoncurrent", "MarketableSecuritiesNoncurrent"]),
    "_afs_total": ("instant", "USD", ["AvailableForSaleSecuritiesDebtSecurities", "DebtSecuritiesAvailableForSaleExcludingAccruedInterest"]),
    # debt building blocks (combined into debt_current / debt_lt by the builder)
    "_debt_current_total": ("instant", "USD", ["DebtCurrent"]),
    "_ltd_current": ("instant", "USD", ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"]),
    "_st_borrowings": ("instant", "USD", ["ShortTermBorrowings", "CommercialPaper", "NotesPayableCurrent"]),
    "_ltd_noncurrent": ("instant", "USD", ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"]),
    "_ltd_total": ("instant", "USD", ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"]),
    "_ltd_notes": ("instant", "USD", ["LongTermNotesPayable", "NotesPayableNoncurrent"]),
}

# Extension-namespace elements (not in companyfacts) read from the 10-K inline XBRL when the standard chain leaves years missing.
# field -> (element local names, kind, only_if_insurer). Cigna reports the claims liability only per business segment
# (CignaHealthcare + AllSegmentsExcludingCignaHealthcare), so the segment members are summed when exhaustive.
EXT_FALLBACK = {
    "capex": (["PaymentsForProceedsFromPropertyPlantAndEquipment"], "flow", False),
    "claims_liability": (["LiabilityForClaimsAndClaimsAdjustmentExpenseCurrent"], "instant", True),
}
EXT_SEGMENT_SUM = ("claims_liability",)
INSURER_MARKERS = ("PremiumsEarnedNet", "PolicyholderBenefitsAndClaimsIncurredNet")

SBC_TAGS = ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]
PER_SHARE_FIELDS = ("eps", "dps")
SHARE_COUNT_FIELDS = ("shares", "shares_out", "shares_basic")


SCALE_RATIO = (700.0, 1500.0)   # "about 1,000x" window
SCALE_AGREE = (0.2, 5.0)        # share counts of one year agree when within this ratio of each other


def guard_share_scale(f: dict, labels: list, log: dict, problems: list, fields: tuple) -> list:
    """Share-count scale guard (spec 2026-10-13_13-00 / ETL, all profiles, all uses of share counts).

    A value that is about 1,000x smaller or larger than its reference is rescaled by 1,000 and the year flagged; any other mismatch (outside
    0.2x-5x of every reference) makes the value missing. References: the period-end count `shares_out` is checked against its own nearest
    neighbours in the series (median of up to 4); the weighted-average counts are checked against the (corrected) period-end count of the same year,
    else against the other counts of that year, else against their own neighbours. Mutates `f`, `log` and `problems`; returns the events
    [{field, label, action, original, new, reference}].
    """
    events: list = []
    order = sorted(fields, key=lambda x: 0 if x == "shares_out" else 1)
    for fld in order:
        if fld not in f:
            continue
        vals_before = list(f[fld])
        for i, lab in enumerate(labels):
            v = vals_before[i]
            if not v:
                continue
            near = [vals_before[j] for j in sorted(range(len(labels)), key=lambda j: abs(j - i)) if j != i and vals_before[j]][:4]
            if fld == "shares_out":
                refs = [statistics.median(near)] if near else []
            else:
                refs = [f["shares_out"][i]] if "shares_out" in f and f["shares_out"][i] else [f[o][i] for o in fields if o != fld and o in f and f[o][i]]
                if not refs and near:
                    refs = [statistics.median(near)]
            if not refs:
                continue
            lo, hi = SCALE_AGREE
            if any(lo <= v / r <= hi for r in refs):
                continue
            action, new = None, None
            for k, name in ((1000.0, "rescaled x1000"), (1 / 1000.0, "rescaled /1000")):
                if any(lo <= v * k / r <= hi for r in refs) and any(SCALE_RATIO[0] <= (r / v if k > 1 else v / r) <= SCALE_RATIO[1] for r in refs):
                    action, new = name, v * k
                    break
            if action is None:
                action, new = "set missing (mismatch larger than the scale error)", None
            f[fld][i] = new
            entry = log.get(fld, {}).get(lab)
            if isinstance(entry, dict):
                entry["share_scale_guard"] = action
                entry["value_before_guard"] = v
            events.append({"field": fld, "label": lab, "action": action, "original": v, "new": new, "reference": refs[0]})
    if events:
        problems.append("share_scale_guard: " + "; ".join(f"{e['field']} {e['label']} {e['action']} ({e['original']:,.0f} vs {e['reference']:,.0f})" for e in events))
    return events
ZERO_IF_ABSENT_CF = ("acquisitions", "buybacks", "dividends", "impairments")  # anchored on cfo being retrieved
ZERO_IF_ABSENT_BS = ("sti", "goodwill", "intangibles")  # anchored on total assets being retrieved


@dataclass
class Fact:
    val: float
    end: date
    filed: date
    form: str
    accn: str
    tag: str


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


class SecClient:
    def __init__(self, user_agent: Optional[str] = None):
        ua = user_agent or _read_user_agent()
        if not ua:
            raise RuntimeError("SEC_USER_AGENT is not set (add it to .env, e.g. 'Name email@example.com')")
        self._headers = {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
        self._last = 0.0
        CACHE.mkdir(parents=True, exist_ok=True)
        self.requests_made = 0

    def get_json(self, url: str, cache_name: str, refresh: bool = False):
        path = CACHE / cache_name
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        wait = MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        r = retry_network(lambda: requests.get(url, headers=self._headers, timeout=60))          # a network error waits 30, 60, 120, 120 s between five attempts
        self._last = time.monotonic()
        self.requests_made += 1
        r.raise_for_status()
        path.write_text(r.text, encoding="utf-8")
        return r.json()

    def cik_for(self, ticker: str) -> tuple:
        data = self.get_json("https://www.sec.gov/files/company_tickers.json", "company_tickers.json")
        for row in data.values():
            if row["ticker"].upper() == ticker.upper():
                return str(row["cik_str"]).zfill(10), row["title"]
        raise KeyError(f"ticker {ticker} not found in SEC company_tickers.json")

    def companyfacts(self, cik: str) -> dict:
        return self.get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", f"facts_{cik}.json")

    def first_annual_report(self, cik: str) -> Optional[date]:
        sub = self.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
        dates: list = []

        def collect(block):
            for form, filed in zip(block.get("form", []), block.get("filingDate", [])):
                if form in FIRST_REPORT_FORMS:
                    dates.append(_d(filed))
        collect(sub.get("filings", {}).get("recent", {}))
        for f in sub.get("filings", {}).get("files", []):
            collect(self.get_json(f"https://data.sec.gov/submissions/{f['name']}", f"sub_{cik}_{f['name']}"))
        return min(dates) if dates else None


def _read_user_agent() -> Optional[str]:
    """Read only SEC_USER_AGENT (from the environment, else .env). Nothing else is loaded."""
    v = os.environ.get("SEC_USER_AGENT")
    if v:
        return v
    env = ROOT / ".env"
    if env.exists():
        try:
            from dotenv import dotenv_values
            return dotenv_values(env).get("SEC_USER_AGENT")
        except Exception:
            return None
    return None


# ------------------------------------------------------------------ extraction
def annual_series(facts: dict, tag: str, unit: str, kind: str) -> dict:
    """end-date -> Fact for annual values of one us-gaap tag (latest filing wins per end date)."""
    node = facts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not node:
        return {}
    best: dict = {}
    for e in node.get("units", {}).get(unit, []):
        if e.get("form") not in ANNUAL_FORMS or e.get("fp") != "FY":
            continue
        end = _d(e["end"])
        if kind == "flow":
            if "start" not in e:
                continue
            days = (end - _d(e["start"])).days
            if not 340 <= days <= 380:
                continue
        elif "start" in e:
            continue
        f = Fact(float(e["val"]), end, _d(e["filed"]), e["form"], e.get("accn", ""), tag)
        cur = best.get(end)
        if cur is None or (f.filed, f.accn) > (cur.filed, cur.accn):
            best[end] = f
    return best


def fy_label(end: date) -> str:
    """Fiscal-year label by end date; year ends in Jan/Feb belong to the prior calendar year."""
    return f"FY{end.year - 1 if end.month <= 2 else end.year}"


def _match(series: dict, end: date, tol_days: int = 10) -> Optional[Fact]:
    if end in series:
        return series[end]
    near = [(abs((e - end).days), f) for e, f in series.items() if abs((e - end).days) <= tol_days]
    return min(near, key=lambda t: t[0])[1] if near else None


def build_inputs(sec: SecClient, ticker: str, profile: str, splits: list, n_years: int = 10):
    """Return a dict with the raw annual table and logs; the caller adds prices and builds CompanyInputs.

    splits: list of (date, ratio) stock splits (ratio 2.0 for 2-for-1) used to restate per-share data.
    """
    cik, title = sec.cik_for(ticker)
    facts = sec.companyfacts(cik)
    first_report = sec.first_annual_report(cik)
    series = {name: {} for name in FIELD_MAP}
    for name, (kind, unit, tags) in FIELD_MAP.items():
        per_tag = {tag: annual_series(facts, tag, unit, kind) for tag in tags}
        series[name] = per_tag  # tag -> {end: Fact}

    # fiscal-year ends anchored on annual net income (fallback revenue)
    anchor_ends: set = set()
    for name in ("net_income", "revenue"):
        for s in series[name].values():
            anchor_ends |= set(s)
        if anchor_ends:
            break
    ends = sorted(anchor_ends)
    # collapse ends that fall within 10 days of each other (52/53-week noise): keep the later one
    dedup: list = []
    for e in ends:
        if dedup and (e - dedup[-1]).days <= 10:
            dedup[-1] = e
        else:
            dedup.append(e)
    ends = dedup[-n_years:]

    f: dict = {}
    tag_log: dict = {}
    problems: list = []
    flags: list = []

    def pick(name, end):
        for tag in FIELD_MAP[name][2]:
            fact = _match(series[name][tag], end)
            if fact is not None:
                return fact
        return None

    def split_factor(filed: date) -> float:
        fac = 1.0
        for d_, ratio in splits:
            if d_ > filed:
                fac *= ratio
        return fac

    labels = [fy_label(e) for e in ends]
    for name in FIELD_MAP:
        if name == "da":
            continue
        vals, log = [], {}
        for end, lab in zip(ends, labels):
            fact = pick(name, end)
            if fact is None:
                vals.append(None)
                log[lab] = {"tag": None}
                continue
            v = fact.val
            fac = 1.0
            if name in PER_SHARE_FIELDS or name in SHARE_COUNT_FIELDS:
                fac = split_factor(fact.filed)
                v = v / fac if name in PER_SHARE_FIELDS else v * fac
            vals.append(v)
            log[lab] = {"tag": fact.tag, "value": v, "filed": str(fact.filed), "form": fact.form,
                        **({"split_adjust_factor": fac} if fac != 1.0 else {})}
        f[name] = vals
        tag_log[name] = log

    # extension-element fallback (inline XBRL of the 10-K) for fields whose standard chain left fiscal years missing
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for name, (local_names, kind, insurer_only) in EXT_FALLBACK.items():
        miss_ends = [e for e, v in zip(ends, f[name]) if v is None]
        if not miss_ends or (insurer_only and not any(m in gaap for m in INSURER_MARKERS)):
            continue
        if name == "capex" and all(v is None for v in f["cfo"]):
            continue
        try:
            from .sec_ixbrl import extension_series
            got = extension_series(sec, cik, local_names, kind, miss_ends, segment_sum=name in EXT_SEGMENT_SUM)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name}: inline-XBRL extension fallback failed ({type(exc).__name__}: {exc})")
            continue
        filled = []
        for i, (end, lab) in enumerate(zip(ends, labels)):
            fact = got.get(end)
            if fact is not None and f[name][i] is None:
                f[name][i] = fact.val
                tag_log[name][lab] = {"tag": fact.tag, "value": fact.val, "filed": str(fact.filed), "form": fact.form}
                filled.append(lab)
        if filled:
            problems.append(f"{name}: extension element read from the 10-K inline XBRL in {', '.join(filled)} "
                            f"({sorted({tag_log[name][l]['tag'] for l in filled})})")
            if any("[sum of segment members]" in str(tag_log[name][l]["tag"]) for l in filled):
                flags.append(f"{name}_segment_sum (exhaustive segment members summed; approved convention)")

    n = len(ends)
    # shares reported in millions (e.g. MCD): rescale values below 100k
    assumed_extra: dict = {}
    dei = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding", {}).get("units", {}).get("shares", [])
    for i, (end, lab) in enumerate(zip(ends, labels)):
        if f["shares_out"][i] is None:
            cands = [e for e in dei if e.get("form") in ("10-K", "10-K/A") and 0 < (_d(e["filed"]) - end).days <= 150]
            if cands:
                e = min(cands, key=lambda x: x["filed"])
                fac = split_factor(_d(e["filed"]))
                f["shares_out"][i] = float(e["val"]) * fac
                tag_log["shares_out"][lab] = {"tag": "dei:EntityCommonStockSharesOutstanding (cover page, "
                                              "date after fiscal year end)", "value": f["shares_out"][i],
                                              "filed": e["filed"]}
                assumed_extra.setdefault("shares_out_cover_page", []).append(lab)
    for fld in ("shares", "shares_out", "shares_basic"):
        scaled = [lab for lab, v in zip(labels, f[fld]) if v is not None and v < 1e5]
        if scaled:
            f[fld] = [v * 1e6 if (v is not None and v < 1e5) else v for v in f[fld]]
            for lab in scaled:
                tag_log[fld][lab]["scaled_x1e6"] = True
            problems.append(f"{fld}: values reported in millions in {', '.join(scaled)} -> rescaled x1e6")
    guard_events = guard_share_scale(f, labels, tag_log, problems, SHARE_COUNT_FIELDS)
    if guard_events:
        flags.append("share_scale_guard")
    if assumed_extra.get("shares_out_cover_page"):
        problems.append("shares_out: balance-sheet tag missing, cover-page count used in "
                        + ", ".join(assumed_extra["shares_out_cover_page"]))
    # cash: exclude restricted / customer funds when the cash figure comes from the restricted-cash-inclusive tag
    cust_years = []
    for i, lab in enumerate(labels):
        t = str((tag_log["cash"].get(lab) or {}).get("tag") or "")
        if f["cash"][i] is not None and t.startswith("CashCashEquivalentsRestrictedCash"):
            excl = f["_restricted_cash"][i] if f["_restricted_cash"][i] is not None else f["_funds_held"][i]
            if excl is not None:
                f["cash"][i] -= excl
                tag_log["cash"][lab] = {"tag": t + " minus customer/restricted funds", "value": f["cash"][i],
                                        "customer_funds_excluded": excl}
                cust_years.append(lab)
    if cust_years:
        assumed_extra.setdefault("customer_funds_excluded", []).extend(cust_years)
        problems.append("cash: restricted/customer funds excluded (customer_funds_excluded) in " + ", ".join(cust_years))
    # customer funds: remove customer-funds assets and the matching liabilities from current assets and current
    # liabilities. Only for companies that report FundsHeldForClients (a customer-funds business). Where that tag
    # is absent in a year (INTU after FY2021, extension tags), restricted cash is used as a lower-bound proxy.
    if "FundsHeldForClients" in facts.get("facts", {}).get("us-gaap", {}):
        proxy_years, cf_years = [], []
        for i, lab in enumerate(labels):
            x, src = f["_funds_held"][i], "FundsHeldForClients"
            if x is None:
                x, src = f["_restricted_cash"][i], "proxy: RestrictedCashAndCashEquivalents"
            if x is not None and x > 0 and f["cur_assets"][i] is not None and f["cur_liab"][i] is not None:
                f["cur_assets"][i] -= x
                f["cur_liab"][i] -= x  # matching liability assumed equal to the funds held
                tag_log["cur_assets"][lab] = {**(tag_log["cur_assets"].get(lab) or {}), "value": f["cur_assets"][i],
                                              "customer_funds_excluded": x, "customer_funds_source": src}
                tag_log["cur_liab"][lab] = {**(tag_log["cur_liab"].get(lab) or {}), "value": f["cur_liab"][i],
                                            "customer_funds_excluded": x, "customer_funds_source": src}
                cf_years.append(lab)
                if src.startswith("proxy"):
                    proxy_years.append(lab)
        if cf_years:
            assumed_extra.setdefault("customer_funds_excluded", []).extend(cf_years)
            problems.append("current assets and current liabilities: customer funds excluded "
                            "(customer_funds_excluded) in " + ", ".join(cf_years)
                            + ("; restricted cash used as proxy (lower bound) in " + ", ".join(proxy_years)
                               if proxy_years else ""))
    # D&A: prefer the cash-flow total tags (largest available); the derived Depreciation +
    # AmortizationOfIntangibleAssets is used only when no total tag exists, or when the best total tag is
    # below 50% of the derived sum (then it is a component, e.g. a segment note).
    f["da"], tag_log["da"] = [], {}
    for end, lab, dep, am, fla in zip(ends, labels, f["_dep"], f["acq_amort"], f["_fin_lease_amort"]):
        totals = []
        for tag in FIELD_MAP["da"][2]:
            fact = _match(series["da"][tag], end)
            if fact is not None:
                totals.append((tag, fact.val))
        derived = None
        if dep is not None:
            derived = ("DERIVED: Depreciation + AmortizationOfIntangibleAssets" +
                       (" + FinanceLeaseRightOfUseAssetAmortization" if fla is not None else "") +
                       ("" if am is not None else " (amortization tag missing this year: Depreciation only)"),
                       dep + (am or 0.0) + (fla or 0.0))
        choice = None
        if totals:
            choice = max(totals, key=lambda t: t[1])
            if derived and choice[1] < 0.5 * derived[1]:
                choice = (derived[0] + " [total tag " + choice[0] + " rejected as a component]", derived[1])
        elif derived:
            choice = derived
        if choice:
            f["da"].append(choice[1])
            tag_log["da"][lab] = {"tag": choice[0], "value": choice[1]}
        else:
            f["da"].append(None)
            tag_log["da"][lab] = {"tag": None}
    nder = [l for l, v in tag_log["da"].items() if str(v.get("tag") or "").startswith("DERIVED")]
    if nder:
        problems.append(f"da: derived as Depreciation + AmortizationOfIntangibleAssets in {len(nder)} of {n} years "
                        "(no usable cash-flow total D&A tag in companyfacts; may miss other amortization, e.g. "
                        "finance-lease ROU amortization, or double count)")
    # pretax fallback: domestic + foreign components (a single component alone is NOT used)
    for i, lab in enumerate(labels):
        if f["pretax"][i] is None and f["_pretax_dom"][i] is not None and f["_pretax_for"][i] is not None:
            f["pretax"][i] = f["_pretax_dom"][i] + f["_pretax_for"][i]
            tag_log["pretax"][lab] = {"tag": "DERIVED: pretax domestic + foreign", "value": f["pretax"][i]}
    # derived EBIT fallback: pretax + interest expense
    for i, lab in enumerate(labels):
        if f["ebit"][i] is None and f["pretax"][i] is not None and f["interest_expense"][i] is not None:
            f["ebit"][i] = f["pretax"][i] + f["interest_expense"][i]
            tag_log["ebit"][lab] = {"tag": "DERIVED: pretax + interest_expense", "value": f["ebit"][i]}
            problems.append(f"{lab}: EBIT derived as pretax + interest expense (no OperatingIncomeLoss)")
    # cost of revenue: components when no total tag exists (needs BOTH a goods and a services line; otherwise a
    # lone goods line is the total, and anything else stays missing - e.g. INTU after FY2017 uses extension tags)
    for i, lab in enumerate(labels):
        if f["cost_of_revenue"][i] is None:
            gds, svc = f["_cogs_goods"][i], f["_cogs_services"][i]
            if gds is not None and svc is not None:
                parts = [("CostOfGoodsSold", gds), ("CostOfServices", svc),
                         ("CostOfGoodsAndServicesSoldAmortization", f["_cogs_amort1"][i]),
                         ("CostOfServicesAmortization", f["_cogs_amort2"][i])]
                used = [(t, v) for t, v in parts if v is not None]
                f["cost_of_revenue"][i] = sum(v for _, v in used)
                tag_log["cost_of_revenue"][lab] = {
                    "tag": "cost_of_revenue_derived: " + " + ".join(t for t, _ in used), "value": f["cost_of_revenue"][i]}
            elif gds is not None:
                f["cost_of_revenue"][i] = gds
                tag_log["cost_of_revenue"][lab] = {"tag": "CostOfGoodsSold (goods-only company)", "value": gds}
    nder_c = [l for l, v in tag_log["cost_of_revenue"].items() if str(v.get("tag") or "").startswith("cost_of_revenue_derived")]
    if nder_c:
        problems.append("cost_of_revenue_derived from components in " + ", ".join(nder_c))
    # gross profit fallback: Revenues - CostOfRevenue (logged)
    for i, lab in enumerate(labels):
        if f["gross_profit"][i] is None and f["revenue"][i] is not None and f["cost_of_revenue"][i] is not None:
            f["gross_profit"][i] = f["revenue"][i] - f["cost_of_revenue"][i]
            tag_log["gross_profit"][lab] = {"tag": "DERIVED: Revenues - CostOfRevenue (" +
                                            str(tag_log["cost_of_revenue"][lab]["tag"]) + ")",
                                            "value": f["gross_profit"][i]}
    n_der = sum(1 for v in tag_log["gross_profit"].values() if str(v.get("tag", "")).startswith("DERIVED"))
    if n_der:
        problems.append(f"gross_profit: derived as Revenues - CostOfRevenue in {n_der} of {len(labels)} years "
                        "(no GrossProfit tag)")
    # financial debt composition
    f["debt_current"], f["debt_lt"] = [None] * n, [None] * n
    tag_log["debt_current"], tag_log["debt_lt"] = {}, {}
    for i, lab in enumerate(labels):
        tot = f["_debt_current_total"][i]
        if tot is not None:
            f["debt_current"][i] = tot
            tag_log["debt_current"][lab] = {"tag": "DebtCurrent", "value": tot}
        else:
            parts = [x for x in (f["_ltd_current"][i], f["_st_borrowings"][i]) if x is not None]
            if parts:
                f["debt_current"][i] = sum(parts)
                tag_log["debt_current"][lab] = {"tag": "LongTermDebtCurrent + short-term borrowings/CP/notes",
                                                "value": sum(parts)}
        lt = f["_ltd_noncurrent"][i]
        src = "LongTermDebtNoncurrent"
        if lt is None and f["_ltd_total"][i] is not None:
            lt = f["_ltd_total"][i] - (f["_ltd_current"][i] or 0.0)
            src = "LongTermDebt - LongTermDebtCurrent"
        if lt is None and f["_ltd_notes"][i] is not None:
            lt, src = f["_ltd_notes"][i], "LongTermNotesPayable/NotesPayableNoncurrent"
        if lt is not None:
            f["debt_lt"][i] = lt
            tag_log["debt_lt"][lab] = {"tag": src, "value": lt}
    for i, lab in enumerate(labels):
        have_bs = f["assets"][i] is not None
        if have_bs and f["debt_current"][i] is None:
            f["debt_current"][i] = 0.0
            tag_log["debt_current"][lab] = {"tag": "ASSUMED_ZERO (no current-debt tag)", "value": 0.0}
        if have_bs and f["debt_lt"][i] is None:
            f["debt_lt"][i] = 0.0
            tag_log["debt_lt"][lab] = {"tag": "ASSUMED_ZERO (no long-term-debt tag)", "value": 0.0}
    lease_years = [lab for lab in labels for k in ("_ltd_noncurrent", "_ltd_current", "_ltd_total")
                   if "CapitalLease" in str(tag_log.get(k, {}).get(lab, {}).get("tag", ""))]
    if lease_years:
        problems.append("financial debt uses LongTermDebtAndCapitalLease* tags (may include finance leases; "
                        f"spec excludes leases) in {len(set(lease_years))} of {n} years")
    # long-term marketable debt securities, derived tier (v1.1 candidate C12): AFS debt total less current investments
    f["lt_mdebt_derived"], tag_log["lt_mdebt_derived"] = [], {}
    for i, lab in enumerate(labels):
        tot, cur = f["_afs_total"][i], f["sti"][i]
        if tot is not None and cur is not None:
            f["lt_mdebt_derived"].append(max(0.0, tot - cur))
            tag_log["lt_mdebt_derived"][lab] = {"tag": "DERIVED: " + str((tag_log["_afs_total"].get(lab) or {}).get("tag")) + " - short-term investments",
                                                "value": f["lt_mdebt_derived"][-1]}
        else:
            f["lt_mdebt_derived"].append(None)
            tag_log["lt_mdebt_derived"][lab] = {"tag": None}
    for k in [k for k in f if k.startswith("_")]:
        del f[k]
        tag_log.pop(k, None)
    # acquisitions: goodwill acquired during the period as a lower-bound proxy when the cash tag is absent
    assumed: dict = dict(assumed_extra)
    for i, lab in enumerate(labels):
        if f["acquisitions"][i] is None and f["goodwill_acquired"][i] is not None and f["cfo"][i] is not None:
            f["acquisitions"][i] = f["goodwill_acquired"][i]
            tag_log["acquisitions"][lab] = {"tag": "PROXY: GoodwillAcquiredDuringPeriod (lower bound)",
                                            "value": f["acquisitions"][i]}
            assumed.setdefault("acquisitions_proxy_goodwill", []).append(lab)
    if assumed.get("acquisitions_proxy_goodwill"):
        problems.append("acquisitions: cash tag absent, GoodwillAcquiredDuringPeriod used as lower-bound proxy "
                        "(acquisitions_proxy_goodwill) in " + ", ".join(assumed["acquisitions_proxy_goodwill"]))
    # absent line item -> 0 when the parent statement was retrieved
    for name, anchor in [(x, "cfo") for x in ZERO_IF_ABSENT_CF] + [(x, "assets") for x in ZERO_IF_ABSENT_BS]:
        for i, lab in enumerate(labels):
            if f[name][i] is None and f[anchor][i] is not None:
                f[name][i] = 0.0
                tag_log[name][lab] = {"tag": "assumed_zero (line item absent while statement retrieved)", "value": 0.0}
                assumed.setdefault(name, []).append(lab)
    # dividends per share: dividends paid / weighted-average basic shares when the DPS tag is missing
    for i, lab in enumerate(labels):
        if f["dps"][i] is None and f["dividends"][i] is not None and f["shares_basic"][i]:
            f["dps"][i] = f["dividends"][i] / f["shares_basic"][i]
            tag_log["dps"][lab] = {"tag": "DERIVED: dividends paid / weighted basic shares", "value": f["dps"][i]}
            assumed.setdefault("dps_derived", []).append(lab)
    if assumed.get("dps_derived"):
        problems.append("dps: tag missing, derived as dividends paid / weighted basic shares (dps_derived) in "
                        + ", ".join(assumed["dps_derived"]))
    for name, labs in assumed.items():
        if name not in ZERO_IF_ABSENT_CF and name not in ZERO_IF_ABSENT_BS:
            continue
        problems.append(f"{name}: no XBRL line item in {len(labs)} of {n} years -> assumed_zero "
                        f"({', '.join(labs)})")

    # SBC three states
    any_sbc_tag = any(tag in facts.get("facts", {}).get("us-gaap", {}) for tag in SBC_TAGS)
    sbc_state = []
    for i, lab in enumerate(labels):
        if f["sbc"][i] is not None:
            sbc_state.append("found")
        elif not any_sbc_tag and f["cfo"][i] is not None:
            sbc_state.append("reported_none")
            f["sbc"][i] = 0.0
            tag_log["sbc"][lab] = {"tag": "ASSUMED reported_none (cash-flow retrieved, no SBC tag in any year)",
                                   "value": 0.0}
        else:
            sbc_state.append("not_found")
    if "reported_none" in sbc_state:
        flags.append("SBC: assumed reported_none - needs verification")
    if "not_found" in sbc_state:
        problems.append(f"SBC not found in {sbc_state.count('not_found')} of {n} years "
                        f"({', '.join(l for l, s in zip(labels, sbc_state) if s == 'not_found')})")

    # data-quality checks
    for name in ("revenue", "net_income", "eps", "shares", "cfo", "capex", "assets", "equity", "da", "ebit",
                 "gross_profit", "interest_expense", "dps"):
        miss = [l for l, v in zip(labels, f[name]) if v is None]
        if miss and len(miss) < n:
            problems.append(f"{name}: missing in {', '.join(miss)}")
        elif miss:
            problems.append(f"{name}: no data in any year (no usable tag)")
    used_tags: dict = {}
    for name in FIELD_MAP:
        if name.startswith("_"):
            continue
        tags = {v["tag"] for v in tag_log.get(name, {}).values() if v.get("tag")}
        if len(tags) > 1 and name not in ("claims_liability", "claims_expense", "lt_mdebt_explicit", "lt_mdebt_derived"):
            problems.append(f"{name}: tag changes across years -> {sorted(tags)}")
        used_tags[name] = sorted(tags)
    sh = [(l, x) for l, x in zip(labels, f["shares"]) if x is not None]
    for (_, a), (lab, b) in zip(sh[:-1], sh[1:]):
        if a and (b / a > 1.4 or b / a < 0.7):
            problems.append(f"shares jump {b / a - 1:+.0%} into {lab}: possible unadjusted split / major event")
    if any(v.get("split_adjust_factor") for v in tag_log["eps"].values()):
        flags.append("per-share data restated for stock splits using yfinance split history")

    return {"cik": cik, "name": title, "ends": ends, "labels": labels, "f": f, "tag_log": tag_log,
            "assumed_zero": assumed, "sbc_state": sbc_state, "first_annual_report": first_report, "problems": problems, "flags": flags,
            "used_tags": used_tags}

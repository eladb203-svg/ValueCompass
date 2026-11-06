"""Material-change exception of the 10-year growth window (owner decision 2026-11-05, parameter ``growth_window_10y``).
A fiscal year is a BREAK when the acquisitions of the year - cash paid for businesses (PaymentsToAcquireBusinesses...) plus shares issued for acquisitions (StockIssuedDuringPeriodValueAcquisitions...) -
are at least ``growth_break_equity_pct`` (40%) of the stockholders' equity at the END of the previous fiscal year. After a break the growth is measured over the years AFTER the break year
(at least 5; with fewer the ordinary 5-year window applies). ``years_after`` = latest fiscal year - break year.
Pure functions over the SEC company-facts JSON (10-K values); ``scoring_window`` sets the cut for the growth functions while an engine runs."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Optional

ACQ = ("PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross", "PaymentsToAcquireBusinessesAndInterestInAffiliates",
       "PaymentsToAcquireBusinessesNetOfCashAcquiredIncludingInterestInAffiliates")
STK = ("StockIssuedDuringPeriodValueAcquisitions", "StockIssuedDuringPeriodValueBusinessAcquisitionNet")
EQ = ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
NI = ("NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic")
_YEARS_AFTER: Optional[int] = None                       # read by metrics.growth10


def years_after() -> Optional[int]:
    return _YEARS_AFTER


@contextmanager
def scoring_window(n: Optional[int]):
    global _YEARS_AFTER
    old, _YEARS_AFTER = _YEARS_AFTER, n
    try:
        yield
    finally:
        _YEARS_AFTER = old


def _annual(facts: dict, tags, instant: bool) -> dict:
    out: dict = {}
    for tag in tags:
        node = (facts.get("facts") or {}).get("us-gaap", {}).get(tag)
        if not node:
            continue
        for unit, rows in node["units"].items():
            if unit != "USD":
                continue
            best: dict = {}
            for r in rows:
                if not str(r.get("form", "")).startswith("10-K"):
                    continue
                if not instant:
                    if not r.get("start"):
                        continue
                    if not 340 <= (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days <= 380:
                        continue
                if r["end"] not in best or r["filed"] >= best[r["end"]]["filed"]:
                    best[r["end"]] = r
            for e, r in best.items():
                out.setdefault(e, r["val"])
        if out:
            break
    return out


def fy_of(end: str) -> int:
    y, m = int(end[:4]), int(end[5:7])
    return y - 1 if m <= 2 else y


def acquisition_break(facts: dict, threshold: float = 0.40, since: int = 2016) -> Optional[tuple]:
    """-> (latest break fiscal year, latest fiscal year, ratio) or None."""
    acq, stk, eq, ni = _annual(facts, ACQ, False), _annual(facts, STK, False), _annual(facts, EQ, True), _annual(facts, NI, False)
    if not ni:
        return None
    latest = max(fy_of(e) for e in ni)
    ends, found = sorted(eq), None
    for e in sorted(set(acq) | set(stk)):
        fy = fy_of(e)
        if fy < since:
            continue
        prev = [x for x in ends if x < e and (date.fromisoformat(e) - date.fromisoformat(x)).days < 400]
        if not prev or not eq[prev[-1]] or eq[prev[-1]] <= 0:
            continue
        ratio = ((acq.get(e) or 0) + (stk.get(e) or 0)) / eq[prev[-1]]
        if ratio >= threshold:
            found = (fy, latest, ratio)
    return found


def years_after_break(ticker: str, threshold: float = 0.40) -> Optional[int]:
    """Latest fiscal year - break year for the company, from the (cached) SEC company facts; None when there is no break or the facts are not available."""
    try:
        from src.providers.sec_companyfacts import SecClient
        sec = SecClient()
        cik, _ = sec.cik_for(ticker)
        b = acquisition_break(sec.companyfacts(cik), threshold)
    except Exception:  # noqa: BLE001 - no facts, no exception: the ordinary window applies
        return None
    return None if b is None else b[1] - b[0]

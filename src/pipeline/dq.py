"""DATA-QUALITY CHECKS (K6 spec 2.5), run on a company's facts before they are written.

Each check ends in one of three outcomes, recorded as a ``DqResult`` and in the ``flags`` of the affected fact rows:
  rescaled   the value is corrected by a power of ten and flagged          (share-count scale, C14 / E3)
  flagged    the value stays, the row (or the year) carries a flag
  held       the value is not written: it is missing (R17), never 0
Reconciliations (E11: FFO, Q6, RE29b) need the engine's output: only ``reconciliation_inputs`` prepares them here.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Optional

from src.etl.facts import Fact

SHARE_KEYS = ("shares_diluted_weighted", "shares_basic_weighted", "shares_period_end")
BALANCE_TOLERANCE = 0.01
PRICE_STALE_DAYS = 3                    # trading days (E1)
POWERS = (1e3, 1e6, 1e-3, 1e-6)
COVERAGE_KEYS = {"general": ("revenue", "net_income", "cfo", "equity", "total_assets"), "bank": ("net_income", "equity", "total_assets", "loans", "deposits"),
                 "insurance": ("revenue", "net_income", "equity", "total_assets"), "realestate": ("net_income", "equity", "total_assets")}
NON_NEGATIVE = ("revenue", "total_assets")
MONETARY_EXEMPT = SHARE_KEYS + ("eps_diluted", "dps")


@dataclass(frozen=True)
class DqResult:
    check: str
    outcome: str                 # rescaled | flagged | held
    fiscal_year: Optional[int]
    item_key: Optional[str]
    detail: str


def _with_flag(f: Fact, flag: str, value=None) -> Fact:
    flags = tuple(dict.fromkeys(f.flags + (flag,)))
    return replace(f, flags=flags) if value is None else replace(f, flags=flags, value=value)


def _power_of_ten(ratio: float) -> Optional[float]:
    for p in POWERS:
        if abs(ratio / p - 1) < 0.05:
            return p
    return None


def check_share_scale(facts: list, results: list) -> list:
    """C14 / E3. A share count that differs from the company's own median by a factor of 1,000 or 1,000,000 is rescaled and flagged; a larger unexplained mismatch (x100 or more) is held.
    (The provider's own guard, ``guard_share_scale``, runs first; this is the second look on the whole series.)"""
    out = list(facts)
    for key in SHARE_KEYS:
        rows = [(i, f) for i, f in enumerate(out) if f is not None and f.item_key == key and f.value]
        if len(rows) < 3:
            continue
        ref = statistics.median(g.value for _j, g in rows)          # the series' own median: robust while fewer than half of the years are off
        for i, f in rows:
            ratio = f.value / ref
            p = _power_of_ten(ratio)
            if p is not None:
                out[i] = _with_flag(f, "share_scale_rescaled", f.value / p)
                results.append(DqResult("share_scale", "rescaled", f.fiscal_year, key, f"{f.value:,.0f} is {ratio:,.4g}x the median {ref:,.0f}; divided by {p:g}"))
            elif ratio >= 100 or ratio <= 0.01:
                out[i] = None
                results.append(DqResult("share_scale", "held", f.fiscal_year, key, f"{f.value:,.0f} is {ratio:,.4g}x the median {ref:,.0f}: no power-of-ten explanation, value held"))
    return [f for f in out if f is not None]


def check_currency(facts: list, currency: Optional[str], results: list) -> list:
    """Values are in the reporting currency; a non-USD filer is not converted here (conversion belongs to R15, Israel stage): the monetary values are held."""
    if currency in (None, "USD"):
        return facts
    out = []
    for f in facts:
        if f.item_key in MONETARY_EXEMPT:
            out.append(f)
        else:
            results.append(DqResult("currency", "held", f.fiscal_year, f.item_key, f"reporting currency {currency}, not USD: no conversion in this stage"))
    return out


def noncontrolling_by_year(facts_json: dict, periods: list) -> dict:
    """Noncontrolling interests per fiscal year, for the balance identity only (the equity fact and the cards keep the parent's equity): the ``MinorityInterest`` tag, else equity including
    the noncontrolling portion minus the parent's equity. -> {fiscal_year: value}; a year without either tag is absent (no noncontrolling interest to add)."""
    from src.providers.sec_companyfacts import _match, annual_series
    minority = annual_series(facts_json, "MinorityInterest", "USD", "instant")
    total = annual_series(facts_json, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "USD", "instant")
    parent = annual_series(facts_json, "StockholdersEquity", "USD", "instant")
    out = {}
    for year, _label, end in periods:
        m = _match(minority, end) if end else None
        if m is not None:
            out[year] = m.val
            continue
        t, p = (_match(total, end), _match(parent, end)) if end else (None, None)
        if t is not None and p is not None and t.val != p.val:
            out[year] = t.val - p.val
    return out


def check_balance_identity(facts: list, results: list, nci: Optional[dict] = None) -> list:
    """Total assets = total liabilities + equity (including noncontrolling interests), within 1%: the year is flagged on the three items. ``nci``: noncontrolling interests per year, added to
    the parent's equity for this check only."""
    nci = nci or {}
    by = {}
    for f in facts:
        by.setdefault(f.fiscal_year, {})[f.item_key] = f
    bad = {}
    for y, d in by.items():
        a, l, e = (d.get(k) for k in ("total_assets", "total_liabilities", "equity"))
        if not (a and l and e and a.value):
            continue
        rhs = l.value + e.value + nci.get(y, 0.0)
        gap = abs(a.value - rhs) / abs(a.value)
        if gap > BALANCE_TOLERANCE:
            bad[y] = gap
            results.append(DqResult("balance_identity", "flagged", y, None, f"assets {a.value:,.0f} vs liabilities + equity (+ noncontrolling interests {nci.get(y, 0.0):,.0f}) {rhs:,.0f} ({gap:.1%} apart)"))
    return [(_with_flag(f, "balance_identity") if f.fiscal_year in bad and f.item_key in ("total_assets", "total_liabilities", "equity") else f) for f in facts]


def check_signs(facts: list, results: list) -> list:
    out = []
    for f in facts:
        if f.item_key in NON_NEGATIVE and f.value is not None and f.value < 0:
            results.append(DqResult("sign", "flagged", f.fiscal_year, f.item_key, f"{f.item_key} is negative ({f.value:,.0f})"))
            f = _with_flag(f, "negative_value")
        out.append(f)
    return out


def check_restatement(facts: list, previous: dict, results: list) -> list:
    """A value that differs from the one stored from an earlier filing: the latest filing wins, the row is flagged ``restated``.
    ``previous``: (fiscal_year, item_key) -> {"value", "flags"} from the DB. An unchanged value keeps the flag it already carries (so a second run writes nothing)."""
    out = []
    for f in facts:
        old = previous.get((f.fiscal_year, f.item_key))
        if old is not None and old["value"] is not None and f.value is not None:
            if abs(float(old["value"]) - f.value) > 1e-9 * max(1.0, abs(f.value)):
                results.append(DqResult("restatement", "flagged", f.fiscal_year, f.item_key, f"stored {float(old['value']):,.6g}, now {f.value:,.6g}"))
                f = _with_flag(f, "restated")
            elif "restated" in (old.get("flags") or ()):
                f = _with_flag(f, "restated")
        out.append(f)
    return out


def check_year_coverage(facts: list, results: list, engine: str = "general") -> None:
    """Fewer than 3 years for a 5-year criterion, or fewer than 5 for a 10-year one: noted for the log (the engine marks the criterion missing, R5)."""
    for key in COVERAGE_KEYS.get(engine, COVERAGE_KEYS["general"]):
        n = len({f.fiscal_year for f in facts if f.item_key == key})
        if n < 3:
            results.append(DqResult("year_coverage", "flagged", None, key, f"{n} year(s): fewer than 3 for a 5-year criterion"))
        elif n < 5:
            results.append(DqResult("year_coverage", "flagged", None, key, f"{n} years: fewer than 5 for a 10-year criterion"))


def price_freshness(last_price_at: Optional[datetime], now: Optional[datetime] = None, max_days: Optional[int] = None) -> tuple:
    """E1 (decided 2026-10-28): a price is stale when its date is before the last trading day, i.e. the most recent day whose session has closed (the NYSE calendar, New York time). A price
    of the day that is still trading is fresh, and so is the last close until the next session has closed. -> (is_stale, detail). The same rule runs in the database
    (migration 22, ``flag_stale_prices``). ``max_days`` is kept for old callers and ignored."""
    from src.sched.nyse import NY, Calendar
    now = now or datetime.now(timezone.utc)
    if last_price_at is None:
        return True, "no price time"
    if last_price_at.tzinfo is None:
        last_price_at = last_price_at.replace(tzinfo=timezone.utc)
    cal = Calendar()
    day = last_price_at.astimezone(NY).date()
    last = cal.last_close_at_or_before(now)
    last_day = last.date() if last else None
    return (last_day is not None and day < last_day), f"price date {day.isoformat()}, last trading day {last_day.isoformat() if last_day else '?'}"


def reconciliation_inputs(facts: list) -> dict:
    """Preparation for E11 (FFO, Q6, RE29b): the items each reconciliation needs, by year. Not evaluated here - it runs after the engine."""
    need = {"FFO": ("net_income", "da"), "Q6": ("cfo", "capex"), "RE29b": ("total_assets", "total_liabilities")}
    by = {}
    for f in facts:
        by.setdefault(f.fiscal_year, {})[f.item_key] = f.value
    return {name: {y: {k: d.get(k) for k in keys} for y, d in sorted(by.items())} for name, keys in need.items()}


def run_checks(facts: list, previous: Optional[dict] = None, currency: Optional[str] = None, engine: str = "general", nci: Optional[dict] = None) -> tuple:
    """All checks in order. -> (facts after the checks, [DqResult])."""
    results: list = []
    out = check_currency(list(facts), currency, results)
    out = check_share_scale(out, results)
    out = check_signs(out, results)
    out = check_balance_identity(out, results, nci)
    out = check_restatement(out, previous or {}, results)
    check_year_coverage(out, results, engine)
    return out, results

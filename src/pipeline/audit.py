"""AUDIT (K6 spec 2.2): the annual reports filed (10-K, 10-K/A, 10-KT in the submissions list) against ``filing_periods`` in the DB.

Result: a plan per fiscal year of the 10-year window (t-9 ... t):
  present        the DB holds the year with the accession of the effective filing
  missing        the year is filed but not in the DB
  superseded     the DB holds the year, but with another accession (a newer filing or amendment exists, or the K6a placeholder accession)
  not_available  nothing to load (no annual report for that year, or before the first XBRL year)
The effective filing of a year is the newest one; an amendment counts only when its financial data is in companyfacts (``xbrl_accessions``), because most 10-K/A carry only Part III.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.etl.db_io import PLACEHOLDER_ACCESSION

WINDOW = 10
FIRST_XBRL_YEAR = 2009
STATUSES = ("present", "missing", "superseded", "not_available")


@dataclass
class YearPlan:
    fiscal_year: int
    status: str
    accession: Optional[str] = None          # the effective filing of the year
    form: Optional[str] = None
    filed: Optional[object] = None
    db_accession: Optional[str] = None
    reason: str = ""

    @property
    def needs_load(self) -> bool:
        return self.status in ("missing", "superseded")


def latest_fiscal_year(resolved) -> Optional[int]:
    years = [f.fiscal_year for f in resolved.annual if f.fiscal_year]
    return max(years) if years else None


def effective_filing(filings: list, xbrl_accessions: Optional[set] = None):
    """The newest filing of a year whose data counts: an original 10-K always, an amendment only when its data is in companyfacts."""
    ok = [f for f in filings if not f.form.endswith("/A") or xbrl_accessions is None or f.accession in xbrl_accessions]
    pool = ok or filings
    return max(pool, key=lambda f: (f.filed, f.accession)) if pool else None


def plan(resolved, db_periods: list, window: int = WINDOW, xbrl_accessions: Optional[set] = None) -> list:
    """``db_periods``: rows of ``filing_periods`` ({"fiscal_year", "accession", ...}) of the company. -> [YearPlan] oldest first."""
    t = latest_fiscal_year(resolved)
    if t is None:
        return []
    in_db = {p["fiscal_year"]: p for p in db_periods}
    by_year: dict = {}
    for f in resolved.annual:
        if f.fiscal_year:
            by_year.setdefault(f.fiscal_year, []).append(f)
    out = []
    for fy in range(t - window + 1, t + 1):
        filings = by_year.get(fy, [])
        eff = effective_filing(filings, xbrl_accessions)
        if eff is None or fy < FIRST_XBRL_YEAR:
            why = "before the first XBRL year" if fy < FIRST_XBRL_YEAR else "no annual report for this fiscal year in the submissions list"
            out.append(YearPlan(fy, "not_available", reason=why))
            continue
        row = in_db.get(fy)
        if row is None:
            out.append(YearPlan(fy, "missing", eff.accession, eff.form, eff.filed, None, "not in the DB"))
        elif row["accession"] == eff.accession:
            out.append(YearPlan(fy, "present", eff.accession, eff.form, eff.filed, row["accession"]))
        else:
            why = "placeholder accession from the cache load" if row["accession"] == PLACEHOLDER_ACCESSION else f"newer filing {eff.form} {eff.accession} (filed {eff.filed})"
            out.append(YearPlan(fy, "superseded", eff.accession, eff.form, eff.filed, row["accession"], why))
    return out


def years_to_load(plans: list) -> list:
    return [p.fiscal_year for p in plans if p.needs_load]


def render(resolved, plans: list) -> str:
    lines = [f"{resolved.ticker}  CIK {resolved.cik}  {resolved.name}  (SIC {resolved.sic}, fiscal year end {resolved.fiscal_year_end})"]
    if resolved.unsupported_reason:
        lines.append(f"UNSUPPORTED: {resolved.unsupported_reason}")
        return "\n".join(lines)
    lines.append(f"{'year':<8}{'status':<14}{'form':<9}{'filed':<12}{'accession (effective)':<24}reason")
    for p in plans:
        lines.append(f"{'FY' + str(p.fiscal_year):<8}{p.status:<14}{(p.form or '-'):<9}{str(p.filed or '-'):<12}{(p.accession or '-'):<24}{p.reason}")
    counts = {s: sum(1 for p in plans if p.status == s) for s in STATUSES}
    lines.append("summary: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return "\n".join(lines)

"""In-memory model of the ``financial_facts`` / ``extraction_items`` rows (migrations 3-4) used by the code-stage input layer.

No I/O. A ``FactSet`` is one company: its fiscal periods, its fact rows and the pass-through data that is not a fact
(extras = series that have no dictionary key and are not read by scoring). Rules mirror the table checks of migration 3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

STATUSES = ("found", "reported_none", "assumed_zero", "not_applicable")
SOURCE_KINDS = ("xbrl", "ixbrl", "quarterly_sum", "extraction", "derived")
APPROVAL = ("pending", "approved", "rejected")


def label_to_year(label: str) -> int:
    m = re.fullmatch(r"FY(\d{4})", label)
    if not m:
        raise ValueError(f"not a fiscal-year label: {label!r}")
    return int(m.group(1))


def year_to_label(year: int) -> str:
    return f"FY{year}"


@dataclass(frozen=True)
class Fact:
    """One row of financial_facts (company is the ticker in memory, company_id in the database)."""
    ticker: str
    fiscal_year: int
    item_key: str
    value: Optional[float]
    status: str
    source_kind: str
    tag: Optional[str] = None          # fact_tags.tag
    flags: tuple = ()
    basis: Optional[str] = None
    extraction_ref: Optional[str] = None

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"bad status {self.status!r}")
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(f"bad source_kind {self.source_kind!r}")
        # financial_facts_value_check: only not_applicable may carry no value; reported_none / assumed_zero are zero
        if self.status != "not_applicable":
            if self.value is None:
                raise ValueError(f"{self.item_key} {self.fiscal_year}: value required for status {self.status}")
            if self.status != "found" and self.value != 0:
                raise ValueError(f"{self.item_key} {self.fiscal_year}: status {self.status} must be zero")


@dataclass(frozen=True)
class ExtractionRow:
    """One row of extraction_items. ``item_key`` is free text (a dictionary key or a multi-row key such as loan:<line>)."""
    ticker: str
    item_key: str
    period: str                        # fiscal-year label ("FY2025"), "" when the source row has no year
    value: object                      # number, or text for non-numeric rows (value_state tells which)
    value_state: str = "value"         # value | NA | MISSING | not_disclosed
    unit: str = ""
    document_ref: str = ""
    section: str = ""
    exact_quote: str = ""
    quote_verified: bool = False
    basis: str = ""
    note: str = ""
    approval_status: str = "approved"
    extra: tuple = ()                  # source columns that have no table column (kept so the engine sees the same row)

    def __post_init__(self):
        if self.approval_status not in APPROVAL:
            raise ValueError(f"bad approval_status {self.approval_status!r}")


@dataclass
class FactSet:
    ticker: str
    name: str
    engine: str                        # general | bank | insurance | realestate
    periods: list                      # [(fiscal_year int, label str, end date)]
    facts: list = field(default_factory=list)
    extras: dict = field(default_factory=dict)      # field -> list aligned with periods (no key / not read by scoring)
    extraction: list = field(default_factory=list)  # ExtractionRow
    context: dict = field(default_factory=dict)     # pass-through, not facts (prices, flags, run date, ...)
    extra_tags: dict = field(default_factory=dict)  # tag text of the extras, field -> {label: tag}
    series_fields: list = field(default_factory=list)  # series the provider emitted (including all-missing ones), in order
    has_reg: bool = False                            # the engine inputs carry an extraction dictionary (possibly empty)

    @property
    def labels(self) -> list:
        return [p[1] for p in self.periods]

    @property
    def ends(self) -> list:
        return [p[2] for p in self.periods]

    def by_key(self) -> dict:
        out: dict = {}
        for f in self.facts:
            out.setdefault(f.item_key, {})[f.fiscal_year] = f
        return out


def parse_date(x) -> Optional[date]:
    if x is None or isinstance(x, date):
        return x
    return date.fromisoformat(str(x)[:10])

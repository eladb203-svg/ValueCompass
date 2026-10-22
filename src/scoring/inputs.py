"""Plain data container handed to the scoring functions (no I/O)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# SBC states (Buffett price section A)
SBC_FOUND = "found"
SBC_REPORTED_NONE = "reported_none"
SBC_NOT_FOUND = "not_found"


@dataclass
class CompanyInputs:
    ticker: str
    name: str
    profile: str  # STANDARD / TECH_ASSET_LIGHT
    fy: list  # fiscal-year labels, oldest -> newest
    end: list  # fiscal-year-end dates
    f: dict  # field -> list aligned with fy (None = not available)
    sbc_state: list = field(default_factory=list)  # per year: found / reported_none / not_found
    price_current: Optional[float] = None
    price_avg: list = field(default_factory=list)  # annual average price per FY (split-adjusted)
    first_annual_report: Optional[date] = None
    as_of: Optional[date] = None
    currency: str = "USD"
    flags: list = field(default_factory=list)  # company-level flags
    data_problems: list = field(default_factory=list)
    tag_log: dict = field(default_factory=dict)  # field -> {fy: {...}}
    assumed_zero: dict = field(default_factory=dict)  # field -> [fy labels assumed 0]
    price_entity_issue: Optional[str] = None  # C16: price and financials of different listed entities (merger / successor price) -> cannot be priced
    ai_answers: dict = field(default_factory=dict)  # AI answers by skill id (code stage K5a); empty = the AI sub-items stay ai_pending

    @property
    def n(self) -> int:
        return len(self.fy)

    def series(self, name: str) -> list:
        return self.f.get(name) or [None] * self.n

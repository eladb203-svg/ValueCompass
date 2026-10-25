"""FactSet <-> database (K6a). ``write`` stores a company's facts, fiscal periods and extraction rows (idempotent); ``read`` rebuilds the FactSet from the database.

What is not in the database stays as the provider gave it (pass-through, not facts): ``context`` (prices, flags, run date), ``extras`` (series without a dictionary key), ``extra_tags``,
``series_fields`` and ``has_reg``. The engine input built from the database is therefore: facts + periods + extraction rows from the DB, pass-through from the provider run.
"""
from __future__ import annotations

import math
from dataclasses import replace
from datetime import date

from src.db import db_target
from src.etl.facts import Fact, FactSet, label_to_year, year_to_label
from src.repositories.company_repository import CompanyRepository
from src.repositories.extraction_repository import ExtractionRepository
from src.repositories.financial_repository import FinancialRepository

CALCULATION_VERSION = "k6a-cache-load"
PLACEHOLDER_ACCESSION = "n/a (local SEC cache, K6a load)"      # K6b replaces it with the real accession from the submissions list


def approval_for(row, approve_all: bool = False, k5b_matched: bool = False) -> tuple:
    """(approval_status, approval_source) of a CSV extraction row. Default rule:
    the quote was verified in the earlier CSV process (``quote_verified``) -> approved + legacy_verified;
    otherwise the value was matched by K5b (``k5b_matched``) -> approved + k5b_confirmed;  everything else -> pending.
    ``approve_all`` is for the identity test only (everything approved as human_review); it is refused on the production target."""
    if approve_all:
        return "approved", "human_review"
    if row.quote_verified:
        return "approved", "legacy_verified"
    if k5b_matched:
        return "approved", "k5b_confirmed"
    return "pending", ""


def check_approve_all(approve_all: bool) -> None:
    if approve_all and db_target() == "prod":
        raise ValueError("approve_all (every extraction row approved) is for the identity test and is refused when VC_DB_TARGET=prod")


class FactSetDb:
    def __init__(self, client=None, approve_all: bool = False, k5b_matched=None):
        """``k5b_matched``: optional set of (ticker, item_key, period) of CSV rows whose value K5b matched (the K5b results are not in the repository; none were needed for the K6a load)."""
        check_approve_all(approve_all)
        self.approve_all = approve_all
        self.k5b_matched = set(k5b_matched or ())
        self.companies = CompanyRepository(client) if client else CompanyRepository()
        self.financial = FinancialRepository(client) if client else FinancialRepository()
        self.extraction = ExtractionRepository(client) if client else ExtractionRepository()
        self._ids: dict = {}

    def company_id(self, fs: FactSet) -> int:
        if fs.ticker not in self._ids:
            self._ids[fs.ticker] = self.companies.ensure(fs.ticker, fs.name or fs.ticker)["id"]
        return self._ids[fs.ticker]

    def write(self, fs: FactSet) -> dict:
        """-> {"facts": stats, "periods": stats, "extraction": stats}; every stats dict has inserted / updated / unchanged; extraction also counts
        ``rule_legacy_verified`` / ``rule_k5b_confirmed`` / ``rule_pending`` (what the default rule gives these rows, whatever ``approve_all`` wrote)."""
        check_approve_all(self.approve_all)
        cid = self.company_id(fs)
        periods = [{"fiscal_year": y, "accession": PLACEHOLDER_ACCESSION, "form": "10-K", "fiscal_year_end": e.isoformat() if e else None, "reporting_currency": "USD",
                    "calculation_version": CALCULATION_VERSION} for y, _l, e in fs.periods]
        out = {"periods": self.financial.upsert_filing_periods(cid, periods), "facts": self.financial.upsert_facts(cid, fs.facts)}
        rows = []
        for r in fs.extraction:
            status, source = approval_for(r, self.approve_all, (r.ticker, r.item_key, r.period) in self.k5b_matched)
            rows.append(replace(r, approval_status=status, approval_source=source))
        out["extraction"] = self.extraction.upsert_rows(cid, rows) if rows else {"inserted": 0, "updated": 0, "unchanged": 0}
        rule = [approval_for(r, False, (r.ticker, r.item_key, r.period) in self.k5b_matched) for r in fs.extraction]
        out["extraction"].update({"rule_legacy_verified": rule.count(("approved", "legacy_verified")), "rule_k5b_confirmed": rule.count(("approved", "k5b_confirmed")),
                                  "rule_pending": rule.count(("pending", ""))})
        return out

    def read(self, template: FactSet) -> FactSet:
        """The FactSet of the database for the company of ``template`` (pass-through parts are copied from the template)."""
        cid = self.company_id(template)
        periods = [(p["fiscal_year"], year_to_label(p["fiscal_year"]), date.fromisoformat(p["fiscal_year_end"]) if p["fiscal_year_end"] else None) for p in self.financial.get_filing_periods(cid)]
        facts = [Fact(template.ticker, d["fiscal_year"], d["item_key"], _num(d["value"]), d["status"], d["source_kind"], tag=d["tag"], flags=tuple(d["flags"]), basis=d["basis"])
                 for d in self.financial.get_history(cid)]
        fs = FactSet(ticker=template.ticker, name=template.name, engine=template.engine, periods=periods, facts=facts, extras=template.extras, extraction=[],
                     context=template.context, extra_tags=template.extra_tags, series_fields=template.series_fields, has_reg=template.has_reg)
        fs.extraction = self.extraction.get_rows(cid, template.ticker) if template.has_reg else []
        return fs


def _num(v):
    """A numeric column comes back as int or float; whole numbers stay as the database returns them."""
    return v


def equal_values(a, b) -> bool:
    """Deep equality of two engine-input structures: numbers compare by value (5 == 5.0), NaN == NaN, containers element by element."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return (math.isnan(a) and math.isnan(b)) or a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal_values(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(equal_values(x, y) for x, y in zip(a, b))
    return a == b


def differences(a, b, path: str = "") -> list:
    """Paths where two engine-input structures differ (for the identity report)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'cache' if k in a else 'db'}")
            else:
                out += differences(a[k], b[k], f"{path}/{k}")
        return out
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += differences(x, y, f"{path}[{i}]")
        return out
    return [] if equal_values(a, b) else [f"{path}: cache={str(a)[:60]!r} db={str(b)[:60]!r}"]

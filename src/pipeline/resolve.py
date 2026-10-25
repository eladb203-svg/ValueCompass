"""RESOLVE (K6 spec 2.1): ticker -> CIK (SEC company_tickers.json) -> submissions JSON -> name, former names, SIC, fiscal-year end, exchanges, annual-report list.

One company = one CIK. A ticker change updates the listing, not the company. Issuers the system does not support yet (20-F / 40-F filers, SPACs, asset-backed issuers, no annual report)
come back with ``unsupported_reason`` set; nothing else runs for them. E2: the ticker must belong to the entity that files the report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.providers.sec_companyfacts import fy_label

ANNUAL_FORMS = ("10-K", "10-K/A", "10-KT", "10-KT/A", "10-K405", "10-K405/A")
FOREIGN_ANNUAL_FORMS = ("20-F", "20-F/A", "40-F", "40-F/A")
SPAC_SIC = {"6770"}                 # blank check
ABS_SIC = {"6189"}                  # asset-backed securities
MIC = {"NYSE": "XNYS", "NASDAQ": "XNAS", "CBOE": "BATS", "NYSE ARCA": "ARCX", "NYSE AMERICAN": "XASE", "OTC": "OTCM"}


class ResolveError(Exception):
    """The ticker could not be resolved (kind: not_found | no_submissions)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


@dataclass
class Filing:
    form: str
    accession: str
    filed: date
    report_date: Optional[date]
    primary_doc: str = ""

    @property
    def fiscal_year(self) -> Optional[int]:
        return int(fy_label(self.report_date)[2:]) if self.report_date else None


@dataclass
class Resolved:
    ticker: str
    cik: str                                    # 10 digits
    name: str
    former_names: list = field(default_factory=list)
    sic: str = ""
    sic_description: str = ""
    fiscal_year_end: str = ""                   # "MMDD"
    listings: list = field(default_factory=list)        # [{"symbol", "exchange", "mic", "is_primary"}]
    filings: list = field(default_factory=list)         # every filing in the submissions list
    annual: list = field(default_factory=list)          # annual-report filings (10-K family), newest first
    unsupported_reason: Optional[str] = None
    e2_ok: bool = True
    warnings: list = field(default_factory=list)

    @property
    def supported(self) -> bool:
        return self.unsupported_reason is None


def _d(s) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def _filings(block: dict) -> list:
    n = len(block.get("form", []))
    get = lambda k, i: (block.get(k) or [None] * n)[i] if i < len(block.get(k) or []) else None  # noqa: E731
    return [Filing(block["form"][i], block["accessionNumber"][i], _d(block["filingDate"][i]), _d(get("reportDate", i)), get("primaryDocument", i) or "") for i in range(n)]


def all_filings(sec, cik: str, sub: dict) -> list:
    out = _filings(sub.get("filings", {}).get("recent", {}))
    for f in sub.get("filings", {}).get("files", []):
        out += _filings(sec.get_json(f"https://data.sec.gov/submissions/{f['name']}", f"sub_{cik}_{f['name']}"))
    return out


def unsupported_reason(sub: dict, filings: list) -> Optional[str]:
    sic = str(sub.get("sic") or "")
    forms = [f.form for f in filings]
    if sic in SPAC_SIC:
        return "SPAC / blank check company (SIC 6770): not supported in this stage"
    if sic in ABS_SIC:
        return "asset-backed issuer (SIC 6189): not supported in this stage"
    annual = [f for f in filings if f.form in ANNUAL_FORMS]
    foreign = [f for f in filings if f.form in FOREIGN_ANNUAL_FORMS]
    if foreign and (not annual or max(f.filed for f in foreign) > max(f.filed for f in annual)):
        return f"files {foreign[0].form.split('/')[0]} (foreign private issuer, IFRS): not supported in this stage"
    if not annual:
        return "no annual report (10-K) on SEC" + (f"; forms seen: {', '.join(sorted(set(forms))[:6])}" if forms else "")
    return None


def resolve(sec, ticker: str) -> Resolved:
    ticker = ticker.strip().upper()
    try:
        cik, title = sec.cik_for(ticker)
    except KeyError as e:
        raise ResolveError("not_found", f"ticker {ticker} is not in the SEC company list") from e
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    if not sub:
        raise ResolveError("no_submissions", f"no submissions for CIK {cik}")
    filings = all_filings(sec, cik, sub)
    annual = sorted((f for f in filings if f.form in ANNUAL_FORMS), key=lambda f: (f.filed, f.accession), reverse=True)
    tickers = [t.upper() for t in sub.get("tickers", [])]
    exchanges = sub.get("exchanges", [])
    listings = []
    for i, t in enumerate(tickers):
        ex = exchanges[i] if i < len(exchanges) and exchanges[i] else (exchanges[0] if exchanges else "")
        listings.append({"symbol": t, "exchange": ex or "US", "mic": MIC.get((ex or "").upper()), "is_primary": t == ticker})
    r = Resolved(ticker=ticker, cik=cik, name=sub.get("name") or title, former_names=[x.get("name") for x in sub.get("formerNames", [])], sic=str(sub.get("sic") or ""),
                 sic_description=sub.get("sicDescription") or "", fiscal_year_end=sub.get("fiscalYearEnd") or "", listings=listings, filings=filings, annual=annual)
    r.unsupported_reason = unsupported_reason(sub, filings)
    if ticker not in tickers:                                            # E2: the ticker does not belong to the filing entity (e.g. after a merger)
        r.e2_ok = False
        r.warnings.append(f"E2: ticker {ticker} is not listed under CIK {cik} ({', '.join(tickers) or 'no current tickers'}); a price score is not possible until the successor files its own annual report")
        r.listings.append({"symbol": ticker, "exchange": "US", "mic": None, "is_primary": True})
    if not any(x["is_primary"] for x in r.listings) and r.listings:
        r.listings[0]["is_primary"] = True
    return r


STATE_RANK = {None: 0, "failed": 0, "unsupported": 0, "resolved": 1, "data_loaded": 2, "scored_partial": 3, "ai_in_progress": 4, "complete": 5}


def _rank(state) -> int:
    return STATE_RANK.get(state, 0)


def persist(r: Resolved, companies, client, state: Optional[str] = None) -> dict:
    """Write the company (one per CIK), its listings and the processing state. -> the companies row. Idempotent."""
    row = companies.get_by_cik(r.cik) or companies.get_by_symbol(r.ticker, "US")
    if row is None:
        row = companies.ensure(r.ticker, r.name, cik=r.cik, sic=r.sic or None)
    fields = {"company_name": r.name, "cik": r.cik, "sic": r.sic or None}
    if any(row.get(k) != v for k, v in fields.items()):
        companies.update(row["id"], fields)
    if r.unsupported_reason:
        companies.set_processing_state(row["id"], "unsupported", r.unsupported_reason)
    elif state and _rank(state) > _rank(row.get("processing_state")):
        companies.set_processing_state(row["id"], state)
    for ls in r.listings:
        want = {"company_id": row["id"], "symbol": ls["symbol"], "exchange": ls["exchange"], "mic": ls["mic"], "security_type": "common", "is_primary": ls["is_primary"],
                "is_active": r.e2_ok or not ls["is_primary"], "data_source": "sec_submissions"}
        old = client.table("company_listings").select("*").eq("symbol", ls["symbol"]).eq("exchange", ls["exchange"]).limit(1).execute().data
        if not old:
            client.table("company_listings").insert(want).execute()
        elif any(old[0].get(k) != v for k, v in want.items()):
            client.table("company_listings").update(want).eq("id", old[0]["id"]).execute()
    return companies.get_by_id(row["id"]) if hasattr(companies, "get_by_id") else row

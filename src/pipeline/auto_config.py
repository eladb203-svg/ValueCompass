"""Automatic inputs for a new bank, insurer or real-estate company (K6d-2). The golden companies had inputs prepared by hand (a table of required CET1 by ticker, the lists of covered tickers, an
asset type per REIT, the extracted-items CSV files). For a company that was never prepared, every such input comes from, in this order:

  (a) XBRL (the facts layer - the engines already read it),
  (b) the AI extraction of the existing blocks (B1-B13: the CET1 requirement and SCB in B1, the regulatory capital ratio in B3, the operating items of a REIT in B5-B13) and the business profile
      (the asset types of a REIT),
  (c) a documented default, marked ``default`` in the result: the score then shows a range wherever it matters (``coverage.evaluate_criterion``).

``derive`` returns the inputs with their source; ``apply`` puts them where the runners look (the ticker tables of the engines); ``flags`` are added to the result.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_REQUIRED_CET1 = 7.0                   # 4.5% minimum + 2.5% capital conservation buffer, when the personal buffer (SCB, G-SIB) is not known
BASE_CET1 = 4.5

# REIT asset type -> words (lower case) that identify it in the business profile / the business section / the name. The first type with the most hits wins; no hit = "diversified" (default).
ASSET_WORDS = {
    "communication towers": ("tower", "wireless", "broadcast"),
    "data centers": ("data center", "data centre", "colocation", "interconnection"),
    "self-storage": ("self-storage", "self storage", "storage facilit"),
    "residential": ("apartment", "multifamily", "multi-family", "single-family", "single family", "residential", "manufactured home", "student housing"),
    "healthcare": ("healthcare", "senior housing", "medical office", "skilled nursing", "life science"),
    "office": ("office",),
    "industrial": ("industrial", "logistics", "warehouse", "distribution center"),
    "retail (malls)": ("regional mall", "malls", "premium outlet"),
    "retail (shopping centers)": ("shopping center", "grocery-anchored", "retail propert", "retail center", "open-air"),
    "net lease": ("net lease", "triple-net", "triple net", "net-lease"),
}
DEFAULT_ASSET_TYPE = "diversified"

from src.providers import realestate_facts as _RF  # noqa: E402

from src.scoring import insurance as _INS  # noqa: E402

MANUAL_INS = frozenset(_INS.LINE_OF_BUSINESS)       # insurers with a hand-made line of business (the golden set)
MANUAL_RE = frozenset(_RF.ASSET_TYPE)             # the REITs whose asset type, utilization and NOI method were prepared by hand (the golden set): they keep their manual values


@dataclass
class AutoInputs:
    ticker: str
    engine: str
    values: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)        # name -> xbrl | ai | profile | default | manual
    notes: list = field(default_factory=list)

    @property
    def defaults(self) -> list:
        return [k for k, s in self.sources.items() if s == "default"]

    def flags(self) -> list:
        return [f"auto_input_default:{k}" for k in self.defaults]

    def as_list(self) -> list:
        return [{"name": k, "value": self.values[k], "source": self.sources[k]} for k in self.values]


def _latest(rows: list, key: str) -> Optional[float]:
    vals = [(r["year"], float(r["value_full"])) for r in rows if r.get("item_key") == key and r.get("state") == "value" and r.get("value_full") is not None]
    return max(vals)[1] if vals else None


def bank_required_cet1(rows: list) -> tuple:
    """-> (percent, source). The requirement the bank states (B1), else 4.5 + SCB + G-SIB surcharge (V9), else the default 7.0."""
    for key in ("cet1_required_standardized", "cet1_required_advanced"):
        v = _latest(rows, key)
        if v is not None:
            return v, "ai"
    scb = _latest(rows, "scb")
    if scb is not None:
        return BASE_CET1 + scb + (_latest(rows, "gsib_surcharge") or 0.0), "ai"
    return DEFAULT_REQUIRED_CET1, "default"


def reit_asset_type(text: str) -> tuple:
    """-> (asset type, source) from the words of the business description; the type with the most distinct hits."""
    t = (text or "").lower()
    best, n = None, 0
    for typ, words in ASSET_WORDS.items():
        hits = sum(t.count(w) for w in words)
        if hits > n:
            best, n = typ, hits
    return (best, "profile") if best and n >= 2 else (DEFAULT_ASSET_TYPE, "default")


def reit_utilization(asset_type: str) -> str:
    return {"communication towers": "not_applicable", "data centers": "leased_capacity"}.get(asset_type, "occupancy")


def reit_noi_method(has_prop_opex: bool):
    """The NOI is rental revenue less property operating expenses when the company reports them; otherwise total revenue less cost of revenue (flagged by the engine)."""
    return (["prop_opex"], "xbrl") if has_prop_opex else ("revenue_less_cost", "default")


def business_text(ticker: str, name: str, client=None) -> str:
    """The name, the stored business profile (if any) and the opening of Item 1 (if the filing is in the local cache)."""
    parts = [name or ""]
    try:
        if client is not None:
            from src.bp.stores import ProfileStore
            from src.repositories.company_repository import CompanyRepository
            co = CompanyRepository(client).get_by_symbol(ticker, "US")
            p = ProfileStore(client).latest(co["id"]) if co else None
            if p:
                for f in ("core_activity", "segments", "products_services"):
                    parts.append(str(p.get(f)))
    except Exception:   # noqa: BLE001 - the profile is one source among several
        pass
    try:
        from src.ai.sections import ext_section, find_filing
        filing = find_filing(ticker)
        if filing is not None:
            s = ext_section(filing.text, "TXT-001")
            parts.append((s.text if s.found else filing.text)[:12000])
    except Exception:   # noqa: BLE001
        pass
    return "\n".join(parts)


def derive(engine: str, ticker: str, company: dict, rows: list, client=None, facts: Optional[dict] = None) -> AutoInputs:
    """The inputs a runner would have read from the hand-made tables, for a company that has none. ``rows``: the approved AI extraction rows of the company (K5b row dicts)."""
    a = AutoInputs(ticker, engine)
    if engine == "bank":
        v, s = bank_required_cet1(rows)
        a.values["required_cet1"], a.sources["required_cet1"] = v, s
    elif engine == "realestate":
        typ, s = reit_asset_type(business_text(ticker, company.get("company_name", ""), client))
        a.values["asset_type"], a.sources["asset_type"] = typ, s
        a.values["utilization"], a.sources["utilization"] = reit_utilization(typ), s
        has = bool((facts or {}).get("property_opex"))
        m, ms = reit_noi_method(has)
        a.values["noi_method"], a.sources["noi_method"] = m, ms
    elif engine == "insurance":
        a.values["currency"], a.sources["currency"] = company.get("reporting_currency") or "USD", "xbrl"
        line, s = insurance_line(str(company.get("sic") or ""), company.get("company_name", ""))
        a.values["line_of_business"], a.sources["line_of_business"] = line, s
    return a


SIC_LINE = {"6311": "life", "6321": "health", "6324": "health", "6331": "P&C", "6351": "specialty", "6361": "title", "6399": "composite", "6411": "composite"}


def insurance_line(sic: str, name: str) -> tuple:
    """The line of business of an insurer (a label in the result): reinsurance when the name says so, else by SIC code (XBRL submissions), else "composite" (default)."""
    if re.search(r"\bre\b|reinsur", (name or "").lower()):
        return "reinsurance", "xbrl"
    return (SIC_LINE[sic], "xbrl") if sic in SIC_LINE else ("composite", "default")


def apply(auto: AutoInputs) -> None:
    """Put the inputs where the runners read them (module tables keyed by ticker). A ticker the hand-made tables know keeps its manual values."""
    t = auto.ticker
    if auto.engine == "bank":
        from src.scoring import bank as BK
        BK.REQUIRED_CET1_DEFAULT.discard(t)
        if "required_cet1" in auto.defaults:
            BK.REQUIRED_CET1_DEFAULT.add(t)
    elif auto.engine == "insurance":
        from src.scoring import insurance as INS
        if t not in MANUAL_INS:
            INS.LINE_OF_BUSINESS[t] = auto.values["line_of_business"]
    elif auto.engine == "realestate":
        from src.providers import realestate_facts as RF
        if t not in MANUAL_RE:
            RF.ASSET_TYPE[t] = auto.values["asset_type"]
            RF.UTILIZATION[t] = auto.values["utilization"]
            RF.NOI_METHOD[t] = auto.values["noi_method"]

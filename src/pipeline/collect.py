"""SRC + COLLECT (K6 spec 2.3 and 2.4): one company's annual facts from SEC, by the fixed source hierarchy.

The first source that has a value for an item wins; its kind goes to ``source_kind`` and the tag to ``tag_id``:
  1. SEC companyfacts (XBRL)                                  -> xbrl
  2. inline XBRL company-extension tags (E6)                   -> ixbrl     (done inside the insurance / real-estate providers)
  3. sum of four quarters when only quarters exist (E7)        -> quarterly_sum   (``fill_quarterly_sums``)
  4. FR Y-9C for bank holding companies (E8)                   -> NOT BUILT: the repository has no FR Y-9C data source; reported in ``SourceReport.skipped``
  5. approved extraction (``extraction_items``)                -> extraction (``fill_from_extraction``; only approved rows, only where 1-3 gave nothing)
  6. missing: no row. A failed collection is missing, never 0 (R17).
The providers (``src/providers``) are not changed; they run the tag chains of steps 1-2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

from src.etl import field_map as fm
from src.etl.facts import Fact, FactSet
from src.etl.from_providers import facts_from_kwargs
from src.providers import prices as price_provider
from src.providers.bank_facts import build_bank_series
from src.providers.insurance_facts import build_insurance_series
from src.providers.realestate_facts import build_realestate_series
from src.providers.sec_companyfacts import FIELD_MAP, _d, build_inputs


@dataclass
class SourceReport:
    by_kind: dict = field(default_factory=dict)          # source_kind -> number of facts
    missing_series: list = field(default_factory=list)   # provider series without any value
    filled: list = field(default_factory=list)           # (kind, fiscal_year, item_key) added by steps 3 and 5
    skipped: list = field(default_factory=list)          # hierarchy steps that could not run, with the reason
    not_in_dictionary: list = field(default_factory=list)   # extraction items mapped to a fact key that is not a dictionary item (stay in extraction_items only)


def provider_kwargs(engine: str, sec, ticker: str, profile: str, splits_fn: Callable = price_provider.get_splits, n_years: int = 10) -> tuple:
    """Run the provider of the engine. -> (kwargs for ``facts_from_kwargs``, raw provider dict)."""
    splits = splits_fn(ticker)
    if engine == "general":
        raw = build_inputs(sec, ticker, profile, splits, n_years)
    elif engine == "bank":
        raw = build_bank_series(sec, ticker, splits, n_years)
    elif engine == "insurance":
        raw = build_insurance_series(sec, ticker, splits, n_years)
    elif engine == "realestate":
        raw = build_realestate_series(sec, ticker, splits, n_years)
    else:
        raise ValueError(f"unknown engine {engine!r}")
    kw = {"ticker": ticker, "name": raw["name"], "fy": raw["labels"], "end": raw["ends"], "f": raw["f"], "tag_log": raw["tag_log"],
          "flags": list(raw.get("flags") or []), "data_problems": list(raw.get("problems") or []), "first_annual_report": raw.get("first_annual_report")}
    for k in ("sbc_state", "assumed_zero"):
        if k in raw:
            kw[k] = raw[k]
    return kw, raw


def facts_from_provider(engine: str, kw: dict) -> FactSet:
    return facts_from_kwargs(engine, kw)


# ---------------------------------------------------------------- step 3: sum of four quarters (E7)
def quarter_sum(facts_json: dict, tags: list, unit: str, start: date, end: date) -> Optional[tuple]:
    """Sum of four consecutive discrete quarters (about 91 days each) that fill the fiscal year (start, end]. -> (value, tag) or None."""
    node_all = facts_json.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        entries = node_all.get(tag, {}).get("units", {}).get(unit, [])
        quarters: dict = {}
        for e in entries:
            if "start" not in e:
                continue
            s, en = _d(e["start"]), _d(e["end"])
            if 80 <= (en - s).days <= 100 and start - timedelta(days=5) <= s and en <= end + timedelta(days=5):
                cur = quarters.get((s, en))
                if cur is None or e["filed"] > cur["filed"]:
                    quarters[(s, en)] = e
        chain = sorted(quarters)
        if len(chain) == 4 and all(abs((chain[i + 1][0] - chain[i][1]).days) <= 5 for i in range(3)) and abs((chain[0][0] - start).days) <= 10 and abs((chain[3][1] - end).days) <= 10:
            return sum(float(quarters[q]["val"]) for q in chain), tag
    return None


def fill_quarterly_sums(fs: FactSet, facts_json: dict, report: SourceReport) -> None:
    """E7 for the general model's flow series: the annual value is missing but four quarters exist."""
    if fs.engine != "general":
        return
    have = {(f.fiscal_year, f.item_key) for f in fs.facts}
    prev_end = None
    for year, _label, end in fs.periods:
        start = prev_end or (end - timedelta(days=365))
        prev_end = end
        for fld, key in fm.FIELDS["general"].items():
            spec = FIELD_MAP.get(fld)
            if not spec or spec[0] != "flow" or (year, key) in have or fld not in fs.series_fields:
                continue
            hit = quarter_sum(facts_json, spec[2], spec[1], start, end)
            if hit:
                fs.facts.append(Fact(fs.ticker, year, key, hit[0], "found", "quarterly_sum", tag=hit[1], flags=("quarterly_sum",)))
                have.add((year, key))
                report.filled.append(("quarterly_sum", year, key))


# ---------------------------------------------------------------- step 5: approved extraction
def fill_from_extraction(fs: FactSet, extraction_rows: list, report: SourceReport, dictionary_keys: Optional[set] = None) -> None:
    """``extraction_rows``: raw rows of ``extraction_items`` of the company (id, item_key, period, value, value_state, approval_status).
    Only an approved row with a number, mapped to a single fact by ``field_map.extraction_key`` (and present in the dictionary), and only where the fact is missing."""
    have = {(f.fiscal_year, f.item_key) for f in fs.facts}
    years = {lab: y for y, lab, _ in fs.periods}
    latest = max(years.values()) if years else None
    for r in extraction_rows:
        if r.get("approval_status") != "approved" or r.get("value_state") != "value" or r.get("value") is None:
            continue
        if r.get("skill_id") == "EXT-GENERAL":                      # K6d-2: a B14 item is named by the engine field it fills (gains_realized, re_tax ...): its fact is that field's item
            key, mode = fm.FIELDS.get(fs.engine, {}).get(r["item_key"]), "single"
        else:
            key, mode = fm.extraction_key(fs.engine, r["item_key"])
        if key is None or mode != "single":
            continue
        if dictionary_keys is not None and key not in dictionary_keys:
            if key not in report.not_in_dictionary:
                report.not_in_dictionary.append(key)
            continue
        year = years.get(r.get("period") or "", latest)
        if year is None or (year, key) in have:
            continue
        fs.facts.append(Fact(fs.ticker, year, key, float(r["value"]), "found", "extraction", tag=None, flags=("from_extraction",), extraction_ref=str(r["id"])))
        have.add((year, key))
        report.filled.append(("extraction", year, key))


def select_sources(fs: FactSet, facts_json: dict, extraction_rows: Optional[list] = None, dictionary_keys: Optional[set] = None) -> SourceReport:
    """Apply the hierarchy to the provider's FactSet (steps 1-2 are the provider's own). -> SourceReport."""
    rep = SourceReport()
    keys_with_value = {f.item_key for f in fs.facts}
    rep.missing_series = [s for s in fs.series_fields if s not in fs.extras and fm.FIELDS[fs.engine].get(s) not in keys_with_value]
    fill_quarterly_sums(fs, facts_json, rep)
    if fs.engine == "bank":
        rep.skipped.append("FR Y-9C (E8): no data source in the repository; bank items missing from XBRL stay missing or come from approved extraction")
    if extraction_rows:
        fill_from_extraction(fs, extraction_rows, rep, dictionary_keys)
    for f in fs.facts:
        rep.by_kind[f.source_kind] = rep.by_kind.get(f.source_kind, 0) + 1
    return rep

"""FactSet -> constructor arguments of the engines' inputs classes (code stage K2).

``kwargs_from_facts`` is the reverse of ``from_providers.facts_from_kwargs``: it rebuilds ``f`` (None where there is no fact row, 0.0 for
assumed_zero / reported_none), ``sbc_state`` (general: found / reported_none / not_found), the runner-side ``assumed_zero`` map (general), the
slice of ``tag_log`` that the engines read (the tag text only), and ``reg`` from the extraction rows. Context is passed through unchanged.
"""
from __future__ import annotations

from . import field_map as fm
from .extraction_store import reg_from_rows

# general: line items that become 0 when the parent statement exists (sec_companyfacts.ZERO_IF_ABSENT_CF / _BS)
ZERO_IF_ABSENT = ("acquisitions", "buybacks", "dividends", "impairments", "sti", "goodwill", "intangibles")
CASH_FUNDS_SUFFIX = " minus customer/restricted funds"


def series_from_facts(engine: str, fs) -> tuple:
    """-> (f, tag_log) over the periods of the fact set."""
    by = fs.by_key()
    f, tag_log = {}, {}
    fields = list(fm.FIELDS[engine]) + [x for x in fm.EXTRAS[engine]]
    for extra in fs.series_fields:                         # keep any series the provider emitted, in its order
        if extra not in fields:
            fields.append(extra)
    for field in fields:
        if field in fm.EXTRAS[engine]:
            f[field] = list(fs.extras.get(field, [None] * len(fs.periods)))
            tag_log[field] = {lab: {"tag": fs.extra_tags.get(field, {}).get(lab)} for _, lab, _ in fs.periods}
            continue
        rows = by.get(fm.FIELDS[engine][field], {})
        f[field] = [rows[y].value if y in rows else None for y, _, _ in fs.periods]
        tag_log[field] = {lab: {"tag": (rows[y].tag if y in rows else None)} for y, lab, _ in fs.periods}
    return f, tag_log


def general_state(fs, f, tag_log) -> tuple:
    """-> (sbc_state, assumed_zero) of the general model."""
    sbc_rows = fs.by_key().get(fm.FIELDS["general"]["sbc"], {})
    sbc_state = []
    for y, _, _ in fs.periods:
        r = sbc_rows.get(y)
        sbc_state.append("not_found" if r is None else ("reported_none" if r.status == "reported_none" else "found"))
    az: dict = {}
    by = fs.by_key()
    for field in ZERO_IF_ABSENT:
        rows = by.get(fm.FIELDS["general"][field], {})
        labs = [lab for y, lab, _ in fs.periods if y in rows and rows[y].status == "assumed_zero"]
        if labs:
            az[field] = labs

    def tag(field, lab):
        return (tag_log.get(field, {}).get(lab) or {}).get("tag") or ""
    labels = fs.labels
    pairs = (("acquisitions_proxy_goodwill", "acquisitions", lambda t: t.startswith("PROXY: GoodwillAcquiredDuringPeriod")),
             ("dps_derived", "dps", lambda t: t.startswith("DERIVED: dividends paid / weighted basic shares")),
             ("shares_out_cover_page", "shares_out", lambda t: t.startswith("dei:EntityCommonStockSharesOutstanding (cover page")))
    for name, field, test in pairs:
        labs = [l for l in labels if f[field][labels.index(l)] is not None and test(tag(field, l))]
        if labs:
            az[name] = labs
    cust = [l for l in labels if tag("cash", l).endswith(CASH_FUNDS_SUFFIX)]
    ca_rows = by.get(fm.FIELDS["general"]["cur_assets"], {})
    cust += [lab for y, lab, _ in fs.periods if y in ca_rows and "customer_funds_excluded" in ca_rows[y].flags]
    if cust:
        az["customer_funds_excluded"] = cust
    return sbc_state, az


def kwargs_from_facts(engine: str, fs) -> dict:
    f, tag_log = series_from_facts(engine, fs)
    kw = dict(fs.context)
    kw.update(ticker=fs.ticker, name=fs.name, fy=fs.labels, end=fs.ends, f=f, tag_log=tag_log)
    if engine == "general":
        kw["sbc_state"], kw["assumed_zero"] = general_state(fs, f, tag_log)
    if fs.has_reg:
        kw["reg"] = reg_from_rows(engine, fs.extraction)
    return kw


def via_facts(engine: str, cls):
    """Wrap an inputs class: the constructor arguments take the detour provider output -> facts -> inputs (used by the identity harness)."""
    from .from_providers import facts_from_kwargs

    def build(*args, **kw):
        assert not args, "inputs classes are built with keyword arguments"
        fs = facts_from_kwargs(engine, kw)
        return cls(**kwargs_from_facts(engine, fs))
    return build


def via_db(engine: str, cls, sink, report: list = None, write: bool = True):
    """Wrap an inputs class (K6a): provider output -> facts -> DATABASE (idempotent write; none when ``write`` is False) -> facts read back -> inputs. ``sink`` is a ``FactSetDb``; ``report`` collects the write statistics
    and the differences between the inputs from the cache path and from the database path (the identity test)."""
    from .db_io import differences
    from .from_providers import facts_from_kwargs

    def build(*args, **kw):
        assert not args, "inputs classes are built with keyword arguments"
        fs = facts_from_kwargs(engine, kw)
        stats = sink.write(fs) if write else {}                    # write=False (K6c score job): the facts already in the database are the input
        fs2 = sink.read(fs)
        if not write and not fs2.facts:
            raise RuntimeError(f"{fs.ticker}: the database holds no facts for this company: load it first")
        cache_kw, db_kw = kwargs_from_facts(engine, fs), kwargs_from_facts(engine, fs2)
        if report is not None:
            report.append({"ticker": fs.ticker, "engine": engine, "stats": stats, "differences": differences(cache_kw, db_kw)})
        return cls(**db_kw)
    return build


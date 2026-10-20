"""Provider output -> FactSet (code stage K2).

Takes the constructor arguments of an engine's inputs class (what a runner passes after the provider ran: ``fy``, ``end``, ``f``, ``tag_log``,
``sbc_state``, ``assumed_zero``, ``reg``, plus pass-through context) and turns the series into fact rows. Providers are not changed.

Status / source_kind are derived from the tag text the providers already write:
  'assumed_zero ...' / 'ASSUMED_ZERO ...' -> assumed_zero;  'ASSUMED reported_none ...' (SBC) -> reported_none;
  'ixbrl:...' or an inline-XBRL-only series -> ixbrl;  'DERIVED:', 'PROXY:', 'SUM:', ... or any text with a space -> derived;  a plain tag -> xbrl.
"""
from __future__ import annotations

from . import field_map as fm
from .extraction_store import rows_from_reg
from .facts import Fact, FactSet, label_to_year, parse_date

DATA_KEYS = ("fy", "end", "f", "tag_log", "sbc_state", "assumed_zero", "reg")
# inline-XBRL series that carry no tag text (insurance AOCI members and the LDTI roll-forward)
IXBRL_UNTAGGED = {"aoci_afs", "aoci_drr", "aoci_credit", "ldti_accretion_net"}
CUSTOMER_FUNDS_FIELDS = ("cash", "cur_assets", "cur_liab")


def classify(field: str, tag, sbc_state: str = None) -> tuple:
    """-> (status, source_kind) for a value that exists."""
    t = tag or ""
    low = t.lower()
    if sbc_state == "reported_none" or low.startswith("assumed reported_none"):
        return "reported_none", "derived"
    if low.startswith("assumed_zero"):
        return "assumed_zero", "derived"
    if t.startswith("ixbrl:") or (not t and field in IXBRL_UNTAGGED):
        return "found", "ixbrl"
    if t.startswith("dei:"):
        return "found", "xbrl"
    if t.startswith(("DERIVED", "PROXY", "SUM:")) or t.startswith("cost_of_revenue_derived") or " " in t:
        return "found", "derived"
    return "found", "xbrl"


def _flags(entry: dict) -> tuple:
    out = []
    if entry.get("customer_funds_excluded") is not None:
        out.append("customer_funds_excluded")
    if entry.get("share_scale_guard"):
        out.append("share_scale_guard")
    return tuple(out)


def facts_from_kwargs(engine: str, kw: dict) -> FactSet:
    labels, ends = list(kw["fy"]), [parse_date(e) for e in kw["end"]]
    periods = [(label_to_year(l), l, e) for l, e in zip(labels, ends)]
    f, tag_log = kw["f"], kw.get("tag_log") or {}
    sbc_state = kw.get("sbc_state") or []
    mp, extras = fm.FIELDS[engine], fm.EXTRAS[engine]
    fs = FactSet(ticker=kw["ticker"], name=kw.get("name", ""), engine=engine, periods=periods)
    fs.context = {k: v for k, v in kw.items() if k not in DATA_KEYS and k not in ("ticker", "name")}
    fs.series_fields = list(f)
    for field, vals in f.items():
        if field in extras:
            fs.extras[field] = list(vals)
            fs.extra_tags[field] = {lab: (tag_log.get(field, {}).get(lab) or {}).get("tag") for _, lab, _ in periods}
            continue
        key = mp[field]
        for i, (year, label, _) in enumerate(periods):
            v = vals[i]
            if v is None:
                continue
            entry = tag_log.get(field, {}).get(label) or {}
            tag = entry.get("tag")
            sbc = sbc_state[i] if (field == "sbc" and engine == "general" and i < len(sbc_state)) else None
            status, kind = classify(field, tag, sbc)
            fs.facts.append(Fact(fs.ticker, year, key, v, status, kind, tag=tag, flags=_flags(entry)))  # value kept as is (int stays int)
    if kw.get("reg") is not None:
        fs.has_reg = True
        fs.extraction = rows_from_reg(engine, fs.ticker, kw["reg"])
    return fs

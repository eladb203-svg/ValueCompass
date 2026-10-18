"""Inline-XBRL fallback for company-extension elements.

SEC ``companyfacts`` only carries standard-taxonomy tags. Some companies (e.g. Cigna: capex and the claims liability) report the line
under their own namespace (``ci:...``), which is then invisible to the tag chains. This module reads the annual 10-K inline XBRL
documents and returns the facts of the requested element local names (any prefix), without dimensions, for annual periods.

Cached under scripts/cache/filings like the other filing downloads; fair-access limits are the same as SecClient.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime
from typing import Optional

from .sec_companyfacts import Fact, SecClient
from .sec_filings import _get_raw

_CTX = re.compile(r"<xbrli:context\b[^>]*\bid=\"([^\"]+)\"[^>]*>(.*?)</xbrli:context>", re.S | re.I)
_NF = re.compile(r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", re.S | re.I)


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _attr(a: str, name: str) -> Optional[str]:
    m = re.search(r"\b" + re.escape(name) + r"=\"([^\"]*)\"", a)
    return m.group(1) if m else None


def parse_contexts(raw: str) -> dict:
    """context id -> {'start','end'(date),'instant'(bool),'dims': [(axis, member), ...]}; typed members make a context unusable."""
    out = {}
    for cid, body in _CTX.findall(raw):
        if re.search(r"typedMember", body, re.I):
            continue
        dims = [(a, m.strip()) for a, m in re.findall(r"<xbrldi:explicitMember[^>]*dimension=\"([^\"]+)\"[^>]*>([^<]+)<", body)]
        ins = re.search(r"<xbrli:instant>\s*([\d-]+)\s*<", body)
        if ins:
            out[cid] = {"start": None, "end": _d(ins.group(1)), "instant": True, "dims": dims}
            continue
        s, e = re.search(r"<xbrli:startDate>\s*([\d-]+)\s*<", body), re.search(r"<xbrli:endDate>\s*([\d-]+)\s*<", body)
        if s and e:
            out[cid] = {"start": _d(s.group(1)), "end": _d(e.group(1)), "instant": False, "dims": dims}
    return out


def parse_numeric(attrs: str, text: str) -> Optional[float]:
    """Numeric value of an ix:nonFraction (scale, sign, zero-dash handled); None when it is nil or not a number."""
    if _attr(attrs, "xsi:nil") == "true":
        return None
    fmt = (_attr(attrs, "format") or "").lower()
    t = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
    if "zerodash" in fmt or t in ("—", "–", "-"):
        return 0.0
    if not t:
        return None
    t = t.replace(",", "").replace(" ", "")
    if "numcommadecimal" in fmt:
        t = text.replace(".", "").replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    v *= 10 ** int(_attr(attrs, "scale") or 0)
    if _attr(attrs, "sign") == "-":
        v = -v
    return v


def extract_facts(raw: str, local_names: list, kind: str, segment_sum: bool = False) -> dict:
    """{local_name: {end: (value, full_name)}} for annual facts (flows of 340-380 days, or instants) without dimensions.

    segment_sum: when an element is reported only per business segment (no undimensioned value), the segment members are summed if
    they are exhaustive, i.e. one member is a remainder member ("AllSegmentsExcluding...", "AllOtherSegments..."); the full name is
    then suffixed with " [sum of segment members]".
    """
    ctx = parse_contexts(raw)
    out: dict = {}
    seg: dict = {}
    for attrs, text in _NF.findall(raw):
        full = _attr(attrs, "name") or ""
        local = full.split(":")[-1]
        if local not in local_names:
            continue
        unit = (_attr(attrs, "unitRef") or "").lower()
        if "usd" not in unit or "share" in unit:
            continue
        c = ctx.get(_attr(attrs, "contextRef") or "")
        if not c or (kind == "instant") != c["instant"]:
            continue
        if kind == "flow" and not 340 <= (c["end"] - c["start"]).days <= 380:
            continue
        v = parse_numeric(attrs, text)
        if v is None:
            continue
        if c["dims"]:
            if segment_sum and len(c["dims"]) == 1 and c["dims"][0][0].endswith("StatementBusinessSegmentsAxis"):
                seg.setdefault((local, c["end"]), {}).setdefault(c["dims"][0][1], (v, full))
            continue
        out.setdefault(local, {}).setdefault(c["end"], (v, full))
    for (local, end), members in seg.items():
        if end in out.get(local, {}):
            continue
        if any(m.split(":")[-1].startswith(("AllSegmentsExcluding", "AllOtherSegments")) for m in members) and len(members) >= 2:
            full = next(iter(members.values()))[1]
            out.setdefault(local, {})[end] = (sum(v for v, _ in members.values()), full + " [sum of segment members]")
    return out


def tenk_filings(sec: SecClient, cik: str) -> list:
    """10-K filings (newest first): accession, primary document, report date, filing date."""
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    blocks = [sub["filings"]["recent"]]
    for f in sub["filings"].get("files", []):
        try:
            blocks.append(sec.get_json(f"https://data.sec.gov/submissions/{f['name']}", f"sub_{cik}_{f['name']}"))
        except Exception:  # noqa: BLE001
            continue
    out = []
    for rec in blocks:
        for form, filed, acc, doc, rdate in zip(rec["form"], rec["filingDate"], rec["accessionNumber"], rec["primaryDocument"], rec["reportDate"]):
            if form == "10-K" and rdate:
                out.append({"accession": acc, "primary": doc, "report_date": _d(rdate), "filed": _d(filed)})
    return sorted(out, key=lambda x: x["report_date"], reverse=True)


def extension_series(sec: SecClient, cik: str, local_names: list, kind: str, needed_ends: list, max_filings: int = 6,
                     segment_sum: bool = False) -> dict:
    """{end: Fact} for the first element of ``local_names`` found per fiscal-year end, reading 10-K filings newest first
    until every needed year is covered. The Fact tag is recorded as ``ixbrl:<prefix:Name>`` for the tag log."""
    found: dict = {}
    missing = set(needed_ends)
    used = 0
    for k in tenk_filings(sec, cik):
        if not missing or used >= max_filings:
            break
        if all(abs((k["report_date"] - e).days) > 800 for e in missing):
            continue
        acc = k["accession"].replace("-", "")
        raw = _get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{k['primary']}", f"{acc}_{k['primary']}")
        used += 1
        facts = extract_facts(raw, local_names, kind, segment_sum)
        for name in local_names:
            for end, (v, full) in facts.get(name, {}).items():
                m = next((e for e in missing if abs((e - end).days) <= 10), None)
                if m is not None and m not in found:
                    found[m] = Fact(val=v, end=end, filed=k["filed"], form="10-K", accn=k["accession"], tag="ixbrl:" + full)
        missing -= set(found)
    return found

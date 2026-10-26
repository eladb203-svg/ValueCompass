"""Segments, product lines and regions from the inline XBRL of a 10-K (AI skills 2026-10-26_10-30, 3.1.3). Pure over text: ``extract_axes(ixbrl_html, labels_xml)``.

SEC ``companyfacts`` has no dimensional data, so the values are read from the filing itself. For the revenue concept the engine already uses (``REVENUE_CHAIN``), in the latest fiscal year, the
facts whose only dimension is one of three axes are read:

  segments           us-gaap:StatementBusinessSegmentsAxis
  products_services  srt:ProductOrServiceAxis
  regions            srt:StatementGeographicalAxis   (member -> region code through ``regions.yaml``)

Member names come from the filing's label linkbase (company extension labels), else from the member's own name. Shares are computed here. A member that is the sum of other members (a total, a
parent of other members) or is named like a reconciling line ("Corporate and other", "Eliminations") is not an item. An axis the filing does not have is reported missing, and BP-1 completes the field.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from itertools import combinations
from typing import Optional

from src.providers.sec_ixbrl import _NF, _attr, parse_contexts, parse_numeric

from .vocab import region_of

REVENUE_CHAIN = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet",
                 "SalesRevenueServicesNet", "RevenuesNetOfInterestExpense"]
_REVENUE_LIKE = re.compile(r"^(?!.*(?:Cost|Expense|Deferred|Unearned|Receivable|Liabilit|Tax|Percent|Remaining|Intersegment|Reinsurance|Ceded|Assumed|Direct)).*(?:Revenue|PremiumsEarned|InterestAndDividendIncomeOperating)", re.I)
AXES = {"segments": "StatementBusinessSegmentsAxis", "products_services": "ProductOrServiceAxis", "regions": "StatementGeographicalAxis"}
MAX_PRODUCTS = 5
_AGGREGATE_NAME = re.compile(r"total|consolidat|eliminat|reconcil|intersegment|corporateandother|corporateother|otherandeliminat|^operatingsegments|^segmentsmember|^reportablesegment|"
                             r"^allsegments|^allproducts|^productandservice(member)?$|^allregions|^allcountries|^geographicalareas?member", re.I)
TOLERANCE = 0.001          # a member is a sum of others when the difference is below 0.1% of its value (at least 1 million: the members are rounded)
MIN_TOLERANCE, MAX_TOLERANCE = 1_000_000.0, 0.005


def local(qname: str) -> str:
    return (qname or "").split(":")[-1]


def split_camel(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)).strip()


_SMALL = {"And", "Or", "Of", "The", "For", "In", "On", "To", "Or"}


def member_fallback_name(member: str) -> str:
    n = local(member)
    n = re.sub(r"Member$", "", n)
    t = split_camel(n) if n != n.upper() else n
    return " ".join(w.lower() if (k and w in _SMALL) else w for k, w in enumerate(t.split()))


# ---------------------------------------------------------------- label linkbase
def parse_labels(xml_text: Optional[str]) -> dict:
    """{'prefix_Name': label text} from a label linkbase (the standard label preferred; ' [Member]' removed)."""
    if not xml_text:
        return {}
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return {}
    XL = "{http://www.w3.org/1999/xlink}"
    locs, labs, arcs = {}, {}, []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "loc":
            locs[el.get(XL + "label")] = (el.get(XL + "href") or "").split("#")[-1]
        elif tag == "label":
            labs.setdefault(el.get(XL + "label"), []).append((el.get(XL + "role") or "", "".join(el.itertext()).strip()))
        elif tag == "labelArc":
            arcs.append((el.get(XL + "from"), el.get(XL + "to")))
    rank = {"http://www.xbrl.org/2003/role/label": 0, "http://www.xbrl.org/2003/role/terseLabel": 1, "http://www.xbrl.org/2003/role/verboseLabel": 2}
    best: dict = {}
    for frm, to in arcs:
        frag = locs.get(frm)
        for role, text in labs.get(to) or []:                 # one label id can carry several resources (standard, terse, verbose ...)
            r = rank.get(role)
            if not frag or not text or r is None or len(text) > 90:   # only the standard / terse / verbose labels; a definition is not a name
                continue
            if frag not in best or r < best[frag][0]:
                best[frag] = (r, text)
    return {k: re.sub(r"\s*\[Member\]\s*$", "", v[1]).strip() for k, v in best.items()}


_GENERIC_PREFIX = re.compile(r"^(?:product(?:s)? and services?,\s*|segments?\s+(?=[A-Za-z]))", re.I)


def member_name(member: str, labels: dict) -> str:
    """The company's label of the member (a generic "Product and Service, " lead-in removed), else a readable form of the member's own name."""
    lab = labels.get(member.replace(":", "_"))
    if lab:
        lab = _GENERIC_PREFIX.sub("", lab).strip() or lab
        return lab[:1].upper() + lab[1:]
    return member_fallback_name(member)


# ---------------------------------------------------------------- aggregates
def drop_aggregates(members: dict) -> tuple:
    """members {name: value} -> (kept {name: value}, dropped [(name, reason)]). A name that looks like a total / reconciling line is dropped; so is a member (largest first) that equals the sum of two or
    more of the other remaining members."""
    kept = {m: v for m, v in members.items() if v is not None}
    dropped = []
    for m in list(kept):
        if _AGGREGATE_NAME.search(local(m)):
            dropped.append((m, "name_is_aggregate"))
            del kept[m]
    for m in sorted(list(kept), key=lambda x: -kept[x]):
        v = kept[m]
        if v <= 0:
            continue
        others = sorted((o for o in kept if o != m and kept[o] > 0 and kept[o] < v), key=lambda x: -kept[x])[:14]
        found = None
        for k in range(2, min(len(others), 8) + 1):
            for combo in combinations(others, k):
                if abs(sum(kept[o] for o in combo) - v) <= min(max(TOLERANCE * v, MIN_TOLERANCE), MAX_TOLERANCE * v):
                    found = combo
                    break
            if found:
                break
        if found:
            dropped.append((m, "sum_of:" + ",".join(local(o) for o in found)))
            del kept[m]
    return kept, dropped


PARTITION_TOLERANCE = 0.005
MAX_PARTITION_MEMBERS = 16


def best_partition(kept: dict, total: float) -> Optional[dict]:
    """When the members add up to clearly more than the total (nested or overlapping members), the largest set of members that add up to the total (within 0.5%); None when there is none."""
    items = sorted(kept.items(), key=lambda kv: -kv[1])[:MAX_PARTITION_MEMBERS]
    n, best = len(items), None
    for mask in range(1, 1 << n):
        picked = [items[i] for i in range(n) if mask >> i & 1]
        if len(picked) < 2:
            continue
        d = abs(sum(v for _, v in picked) - total) / total
        if d <= PARTITION_TOLERANCE and (best is None or (len(picked), -d) > (len(best[0]), -best[1])):
            best = (picked, d)
    return dict(best[0]) if best else None


# ---------------------------------------------------------------- extraction
def _annual(c: dict) -> bool:
    return (not c["instant"]) and 340 <= (c["end"] - c["start"]).days <= 380


def extract_axes(raw: str, labels_xml: Optional[str] = None) -> dict:
    """-> {"end": date, "total_revenue": float, "total_tag": str, "axes": {"segments": {...}, "products_services": {...}, "regions": {...}}, "labels_found": int}.
    Each axis: {"found": bool, "concept": str, "items": [{"member", "name", "value", "share"}], "dropped": [(member, reason)], "coverage": float, "flags": [...]}."""
    ctx = parse_contexts(raw)
    labels = parse_labels(labels_xml)
    total: dict = {}                 # (concept, end) -> value, undimensioned (the revenue chain only)
    dim: dict = {}                   # (axis key, concept, end) -> {member: value}, for every revenue-like concept
    for attrs, text in _NF.findall(raw):
        full = _attr(attrs, "name") or ""
        concept = local(full)
        in_chain = concept in REVENUE_CHAIN
        if not in_chain and not _REVENUE_LIKE.search(concept):
            continue
        unit = (_attr(attrs, "unitRef") or "").lower()
        if "usd" not in unit or "share" in unit:
            continue
        c = ctx.get(_attr(attrs, "contextRef") or "")
        if not c or not _annual(c):
            continue
        v = parse_numeric(attrs, text)
        if v is None:
            continue
        if not c["dims"]:
            if in_chain:
                total.setdefault((concept, c["end"]), v)
            continue
        axis_dims = [(a, m) for a, m in c["dims"] if local(a) in AXES.values()]
        rest = [(a, m) for a, m in c["dims"] if local(a) not in AXES.values()]
        if len(axis_dims) != 1:
            continue
        axis, member = axis_dims[0]
        key = next(k for k, n in AXES.items() if n == local(axis))
        # a segment value is often reported with ConsolidationItemsAxis = OperatingSegmentsMember; any other extra dimension makes the context a different cut of the data
        if rest and not (key == "segments" and len(rest) == 1 and local(rest[0][0]) == "ConsolidationItemsAxis" and local(rest[0][1]) == "OperatingSegmentsMember"):
            continue
        dim.setdefault((key, concept, c["end"]), {}).setdefault(member, v)
    out = {"end": None, "total_revenue": None, "total_tag": None, "axes": {}, "labels_found": len(labels)}
    ends = sorted({e for (_c, e) in total}, reverse=True)
    if not ends:
        out["axes"] = {k: {"found": False, "concept": None, "items": [], "dropped": [], "coverage": None, "flags": ["no_total_revenue_fact"]} for k in AXES}
        return out
    end = ends[0]
    tconcept = next(c for c in REVENUE_CHAIN if (c, end) in total)
    out.update(end=end, total_revenue=total[(tconcept, end)], total_tag=tconcept)
    for key in AXES:
        tot = out["total_revenue"]
        cands = []
        for (k, c, e), members in dim.items():
            if k != key or e != end:
                continue
            kept, dropped = drop_aggregates(members)
            if len(kept) < (1 if key != "segments" else 1) or not kept:
                continue
            cov = sum(kept.values()) / tot if tot else 0
            if tot and cov > 1.02 and key == "segments":
                part = best_partition(kept, tot)
                if part:
                    dropped = dropped + [(m, "not_in_partition") for m in kept if m not in part]
                    kept, cov = part, sum(part.values()) / tot
            cands.append((c, kept, dropped, cov, len(members)))
        if not cands:
            out["axes"][key] = {"found": False, "concept": None, "items": [], "dropped": [], "coverage": None, "flags": ["axis_not_in_filing"]}
            continue
        # the concept whose members add up closest to the total revenue (ties: more members kept, then the revenue chain order)
        concept, kept, dropped, cov, _n = min(cands, key=lambda x: (round(abs(x[3] - 1.0), 3), -len(x[1]), -x[4], REVENUE_CHAIN.index(x[0]) if x[0] in REVENUE_CHAIN else 99))
        items = [{"member": m, "name": member_name(m, labels), "value": v, "share": (v / tot if tot else None)} for m, v in sorted(kept.items(), key=lambda kv: -kv[1])]
        flags = []
        if cov is not None and cov > 1.02:
            flags.append("members_overlap")
        if cov is not None and cov < 0.5:
            flags.append("low_coverage")
        out["axes"][key] = {"found": bool(items), "concept": concept, "items": items, "dropped": dropped, "coverage": cov, "flags": flags}
    return out


# ---------------------------------------------------------------- profile fields from the axes
def _tag(axis_key: str, concept: str) -> str:
    return f"{'srt' if axis_key != 'segments' else 'us-gaap'}:{AXES[axis_key]}|us-gaap:{concept}"


def segments_field(ax: dict) -> dict:
    a = ax["axes"]["segments"]
    if not a["found"]:
        return {"status": "not_found", "source": "xbrl", "items": [], "reasons": a["flags"]}
    tag = _tag("segments", a["concept"])
    return {"status": "ok", "source": "xbrl", "coverage": a["coverage"], "reasons": a["flags"], "dropped": a["dropped"],
            "items": [{"name": i["name"], "member": i["member"], "revenue": i["value"], "share": i["share"], "source": "xbrl", "tag": tag, "status": "ok"} for i in a["items"]]}


def products_field(ax: dict) -> dict:
    a = ax["axes"]["products_services"]
    if not a["found"]:
        return {"status": "not_found", "source": "xbrl", "items": [], "reasons": a["flags"]}
    tag = _tag("products_services", a["concept"])
    return {"status": "ok", "source": "xbrl", "coverage": a["coverage"], "reasons": a["flags"], "dropped": a["dropped"],
            "items": [{"name": i["name"], "member": i["member"], "kind": "product_line", "revenue": i["value"], "share": i["share"], "source": "xbrl", "tag": tag, "status": "ok"}
                      for i in a["items"][:MAX_PRODUCTS]]}


def regions_field(ax: dict) -> dict:
    """Members -> region codes (several countries of one region are summed); a member that is not in the map goes to `other`, with its names kept."""
    a = ax["axes"]["regions"]
    if not a["found"]:
        return {"status": "not_found", "source": "xbrl", "items": [], "reasons": a["flags"]}
    tag = _tag("regions", a["concept"])
    by: dict = {}
    for i in a["items"]:
        code = region_of(i["name"])
        if code == "other":
            code = region_of(member_fallback_name(i["member"]))
        d = by.setdefault(code, {"code": code, "revenue": 0.0, "names": []})
        d["revenue"] += i["value"]
        d["names"].append(i["name"])
    tot = ax["total_revenue"]
    items = []
    for code, d in sorted(by.items(), key=lambda kv: -kv[1]["revenue"]):
        it = {"code": code, "revenue": d["revenue"], "share": d["revenue"] / tot if tot else None, "members": d["names"], "source": "xbrl", "tag": tag, "status": "ok" if code != "other" else "other"}
        if code == "other":
            it["other_text"] = ", ".join(d["names"])
        items.append(it)
    return {"status": "other" if any(i["status"] == "other" for i in items) else "ok", "source": "xbrl", "coverage": a["coverage"], "reasons": a["flags"], "dropped": a["dropped"], "items": items}

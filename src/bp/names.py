"""Names of segments and product lines as they are shown and translated (BP round 3, 2026-10-26).

* generic words are removed from the name: "Segment", "Product Line(s)"; in segments also the prefixes "Property, " and "Insurance ";
* an item with a generic name (Property Revenue, Service, Product, Other ...) is not shown;
* a commercial name stays in Latin letters (kind = brand, or a Title-Case product name that the text itself gave: Windows, Azure, Microsoft 365 Copilot) and is not translated.

``display_items(profile, field)`` is the one place that applies this: the renderer and the list of phrases to translate both use it.
"""
from __future__ import annotations

import re
from typing import Optional

from .vocab import region_of, regions_of

_SEGMENT_WORD = re.compile(r"\s*\bSegments?\b\s*", re.I)
_PRODUCT_LINE = re.compile(r"\s*\bProduct\s+Lines?\b\s*", re.I)
_SEGMENT_PREFIX = re.compile(r"^(?:Property,\s*|Insurance\s+)", re.I)
_OTHER = re.compile(r"^(?:all\s+)?other\b", re.I)
_GENERIC = re.compile(r"^(?:property(?:\s+revenues?)?|services?|products?|product\s+and\s+services?|total.*|revenues?)$", re.I)


def clean_name(name: str, field: str) -> str:
    """The name without generic words (the original when nothing would be left)."""
    n = _PRODUCT_LINE.sub(" ", _SEGMENT_WORD.sub(" ", name or "")).strip(" ,")
    if field == "segments":
        n = _SEGMENT_PREFIX.sub("", n).strip(" ,")
    n = re.sub(r"\s{2,}", " ", n)
    return n or (name or "").strip()


def is_hidden(raw: str, cleaned: str) -> bool:
    """Other / Other Countries / Other Operating Segment, and generic product names (Property Revenue, Service, Product): not shown."""
    return bool(_OTHER.match(raw.strip()) or _OTHER.match(cleaned) or _GENERIC.match(cleaned))


def keeps_latin(item: dict) -> bool:
    """A commercial name: a brand, or a product the text named with capital letters (every word starts with a capital letter or is a number / acronym). Never an XBRL member label."""
    if item.get("kind") == "brand":
        return True
    if item.get("source") != "ai":
        return False
    toks = (item.get("name") or "").split()
    if len(toks) == 1 and re.fullmatch(r"[A-Z]{2,6}s", toks[0]):          # a general plural acronym (CPUs, GPUs) is not a commercial name: it is translated
        return False
    return 0 < len(toks) <= 4 and all(t[0].isupper() or t[0].isdigit() for t in toks)


def display_items(profile: dict, field: str) -> list:
    """The items of a profile field as they are shown: copies with the cleaned ``name`` (the original in ``raw_name``) and ``latin`` set for names that are not translated. A failed field has none.
    Regions from the text get their code from the name again (the map may have grown since the profile was made)."""
    fld = profile.get(field) or {}
    if fld.get("status") == "failed":
        return []
    out = []
    for it in fld.get("items") or []:
        it = dict(it)
        if field in ("segments", "products_services"):
            raw = it.get("name") or ""
            name = clean_name(raw, field)
            if is_hidden(raw, name):
                continue
            it.update(raw_name=raw, name=name, latin=keeps_latin(it) if field == "products_services" else False)
        elif field == "regions" and it.get("source") == "ai" and it.get("name"):
            codes = regions_of(it["name"]) if it.get("share") is None else [region_of(it["name"])]       # a mixed name is split only when there is no share to split
            for k, code in enumerate(codes):
                part = dict(it, code=code, status="ok" if code != "other" else "other")
                out.append(part)
            continue
        out.append(it)
    return out

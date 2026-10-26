"""The background text from the business profile, by code (AI skills 2026-10-26_10-30, 3.2.1-3.2.4). No model call.

``render(inp, lang)`` -> (text, info). Sentence after sentence, from the tables of the skills document; a sentence without data is not written. English uses the profile as it is; Hebrew needs the
Hebrew form of the free phrases (``core_activity``, product-line names, segment names): a sentence whose phrase has no translation yet is left out and the phrase is listed in ``info['missing']``
(with ``preview=True`` it is written as "[ממתין: phrase]" instead, for the report). Numbers, lists and conjunctions are formatted here.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from .translate import phrase_key
from .vocab import Vocab

TEMPLATE_VERSION = "1"
MAX_LINES, MAX_BRANDS, MAX_SEGMENTS, MAX_LIST = 3, 5, 3, 3
MOAT_PREFIX = {"he": {2: "יתרון תחרותי ברור:", 1: "יתרון תחרותי לא מוכח:", 0: "אין יתרון תחרותי מזוהה."},
               "en": {2: "A clear competitive advantage:", 1: "A competitive advantage that is not proven:", 0: "No identifiable competitive advantage."}}
MOAT_EN = {"brand": "brand", "switching_costs": "switching costs", "scale": "scale", "network_effect": "network effect", "regulation": "regulation", "data": "data",
           "infrastructure": "infrastructure", "location": "location"}
MOAT_HE = {"brand": "מותג", "switching_costs": "עלויות מעבר", "scale": "יתרון לגודל", "network_effect": "אפקט רשת", "regulation": "רגולציה", "data": "נתונים",
           "infrastructure": "תשתית", "location": "מיקום"}


@dataclass
class RenderInput:
    name: str                                  # display name of the company
    profile: dict                              # {field: {"status", "items": [...]}}
    vocab: Vocab
    revenue: Optional[float] = None
    fiscal_year: Optional[int] = None
    moat_level: Optional[int] = None           # A7: 0 / 1 / 2 or None
    moat_source: Optional[str] = None
    similar: list = field(default_factory=list)      # display names, already chosen (3.2.3)
    translations: dict = field(default_factory=dict)  # phrase_key(en) -> {"he": str, "status": "approved" | "unreviewed"}
    property_type: bool = False                       # INCOME_REAL_ESTATE: the "product lines" are property types


# ---------------------------------------------------------------- formatting
def pct(share: Optional[float]) -> Optional[str]:
    if share is None:
        return None
    v = share * 100
    return f"{v:.0f}%" if v >= 9.95 else f"{v:.1f}%"


def money_en(v: Optional[float]) -> Optional[str]:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    a = abs(v)
    s = f"${a / 1e9:.1f} billion" if a >= 1e9 else (f"${a / 1e6:.0f} million" if a >= 1e6 else f"${a:,.2f}")
    return ("-" + s) if v < 0 else s


def money_he(v: Optional[float]) -> Optional[str]:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    a = abs(v)
    s = f"{a / 1e9:.1f} מיליארד $" if a >= 1e9 else (f"{a / 1e6:.0f} מיליון $" if a >= 1e6 else f"${a:,.2f}")
    return ("-" + s) if v < 0 else s


def join_en(items: list) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else (", ".join(items[:-1]) + " and " + items[-1] if items else "")


def _conj_he(item: str) -> str:
    """'ו' before a Hebrew word, 'ו-' before a Latin letter or a digit (the item's first character)."""
    return "ו" if re.match(r"[֐-׿]", item) else "ו-"


def join_he(items: list) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " " + _conj_he(items[-1]) + items[-1]


def he_from(label_he: str) -> str:
    return label_he if label_he.startswith("מחוץ") else "מ" + label_he


class _Ctx:
    def __init__(self, inp: RenderInput, lang: str, preview: bool):
        self.i, self.lang, self.preview = inp, lang, preview
        self.missing: list = []          # English phrases without a Hebrew form
        self.used: list = []             # English phrases whose Hebrew form is in the text

    def phrase(self, en: str) -> Optional[str]:
        """The text of a free phrase in the language; None (Hebrew, no translation) when the sentence must be left out."""
        if self.lang == "en":
            return en
        t = self.i.translations.get(phrase_key(en))
        if t and t.get("he"):
            self.used.append(en)
            return t["he"]
        if en not in self.missing:
            self.missing.append(en)
        return f"[ממתין: {en}]" if self.preview else None


# ---------------------------------------------------------------- paragraph 1
_OTHER_NAME = re.compile(r"^(?:all\s+)?other\b", re.I)


def _items(inp: RenderInput, f: str) -> list:
    fld = inp.profile.get(f) or {}
    if fld.get("status") == "failed":                  # a field that failed its checks is not written (its partial items are kept in the profile only)
        return []
    items = list(fld.get("items") or [])
    if f in ("segments", "products_services"):          # an item named Other / Other Countries is not shown
        items = [i for i in items if not _OTHER_NAME.match((i.get("name") or "").strip())]
    return items


def share_of(it: dict) -> Optional[float]:
    """A share is shown only when it is a share of revenue read from XBRL; a share from the text (it can be of premiums, sites ...) is not."""
    return it.get("share") if it.get("source") == "xbrl" else None


def s_activity(c: _Ctx) -> Optional[str]:
    it = _items(c.i, "core_activity")
    if not it:
        return None
    act = c.phrase(it[0]["value"].strip().rstrip("."))
    if act is None:
        return None
    return f"{c.i.name} {act}." if c.lang == "en" else f"חברת {c.i.name} {act}."


def _line_part(c: _Ctx, f_items: list) -> Optional[str]:
    names = []
    for it in f_items:
        nm = c.phrase(it["name"])
        if nm is None:
            return None
        names.append((nm, pct(share_of(it))))
    if not names:
        return None
    parts = []
    for k, (nm, sh) in enumerate(names):
        if sh:
            parts.append(f"{nm} ({sh} of revenue)" if (k == 0 and c.lang == "en") else (f"{nm} ({sh} מההכנסות)" if k == 0 else f"{nm} ({sh})"))
        else:
            parts.append(nm)
    many = len(parts) > 1
    if c.lang == "en":
        lead = ("Its main property types are " if many else "Its main property type is ") if c.i.property_type else ("Its main product lines are " if many else "Its main product line is ")
        return lead + join_en(parts)
    lead = ("סוגי הנכסים העיקריים: " if many else "סוג הנכס העיקרי: ") if c.i.property_type else ("קווי המוצרים העיקריים: " if many else "קו המוצרים העיקרי: ")
    return lead + join_he(parts)


def s_products(c: _Ctx) -> Optional[str]:
    its = _items(c.i, "products_services")
    lines = [i for i in its if i.get("kind", "product_line") != "brand"][:MAX_LINES]
    brands = [i["name"] for i in its if i.get("kind") == "brand"][:MAX_BRANDS]
    a = _line_part(c, lines) if lines else None          # None also when a product-line name has no Hebrew yet: the whole lines half is left out
    b = None
    if brands:
        b = ("its brands include " + join_en(brands)) if c.lang == "en" else ("בין המותגים: " + join_he(brands))
    if a and b:
        return f"{a}; {b}."
    if a:
        return a + "."
    if b:
        return (b[0].upper() + b[1:] if c.lang == "en" else b) + "."
    return None


def _labels(c: _Ctx, field_: str, items: list, limit: int, prefix_he: str = "") -> list:
    out = []
    for it in items:
        if it["code"] == "other":
            continue
        lab = c.i.vocab.label(field_, it["code"], c.lang)
        out.append(prefix_he + lab if c.lang == "he" else lab)
        if len(out) >= limit:
            break
    return out


def s_customers_revenue(c: _Ctx) -> Optional[str]:
    cts = _labels(c, "customer_types", _items(c.i, "customer_types"), MAX_LIST)
    rms = _labels(c, "revenue_models", _items(c.i, "revenue_models"), MAX_LIST, prefix_he="מ")
    if c.lang == "en":
        if cts and rms:
            return f"It sells mainly to {join_en(cts)}, earning its revenue from {join_en(rms)}."
        return f"It sells mainly to {join_en(cts)}." if cts else (f"It earns its revenue from {join_en(rms)}." if rms else None)
    if cts and rms:
        return f"לקוחותיה הם בעיקר {join_he(cts)}, והכנסותיה {join_he(rms)}."
    return f"לקוחותיה הם בעיקר {join_he(cts)}." if cts else (f"הכנסותיה {join_he(rms)}." if rms else None)


def regions_clause(c: _Ctx) -> Optional[str]:
    its = [i for i in _items(c.i, "regions") if share_of(i) is not None and i.get("code") != "other"]
    its.sort(key=lambda i: -i["share"])
    if not its:
        return None
    top = its[:2]
    rest = sum(i["share"] for i in its[2:])
    lab = lambda i: c.i.vocab.label("regions", i["code"], c.lang)   # noqa: E731
    if c.lang == "en":
        txt = f"{pct(top[0]['share'])} of revenue comes from {lab(top[0])}"
        if len(top) > 1:
            txt += f" and {pct(top[1]['share'])} from {lab(top[1])}"
        if rest >= 0.01:
            txt += f", and {pct(rest)} from other regions"
        return txt
    txt = f"{pct(top[0]['share'])} מההכנסות {he_from(lab(top[0]))}"
    if len(top) > 1:
        txt += f" ו-{pct(top[1]['share'])} {he_from(lab(top[1]))}"
    if rest >= 0.01:
        txt += f", ו-{pct(rest)} מאזורים אחרים"
    return txt


def s_segments_regions(c: _Ctx) -> Optional[str]:
    segs = _items(c.i, "segments")
    reg = regions_clause(c)
    head = None
    if len(segs) >= 2:
        segs = sorted(segs, key=lambda i: (share_of(i) is None, -(share_of(i) or 0)))       # largest first when the shares are known (stable otherwise)
        shown = segs[:MAX_SEGMENTS]
        known = all(share_of(i) is not None for i in shown)                                    # "the largest" only when every named segment has its share
        top = []
        for it in shown:
            nm = c.phrase(it["name"])
            if nm is None:
                top = None
                break
            sh = pct(share_of(it))
            top.append(f"{nm} ({sh})" if sh else nm)
        if top:
            if c.lang == "en":
                head = f"It reports {len(segs)} segments, the largest being {join_en(top)}" if known else f"It reports {len(segs)} segments, including {join_en(top)}"
            else:
                head = f"היא מדווחת על {len(segs)} מגזרים, הגדולים שבהם {join_he(top)}" if known else f"היא מדווחת על {len(segs)} מגזרים, ביניהם {join_he(top)}"
    if head and reg:
        return f"{head}; {reg}."
    if head:
        return head + "."
    if reg:
        return (reg[0].upper() + reg[1:] if c.lang == "en" else reg) + "."
    return None


def s_operates(c: _Ctx) -> Optional[str]:
    """Regions without revenue shares (from the text, or without XBRL): "It operates in A, B and C." Not written when the revenue-share sentence already names the regions."""
    if regions_clause(c):
        return None
    codes = []
    for i in _items(c.i, "regions"):
        code = i.get("code")
        if code and code not in ("other", "outside_us") and code not in codes:
            codes.append(code)
    if not codes:
        return None
    labs = [c.i.vocab.label("regions", k, c.lang) for k in codes[:5]]
    if c.lang == "en":
        return f"It operates in {join_en(labs)}."
    return f"פועלת {join_he([('ב' + l[1:]) if l.startswith('ה') else 'ב' + l for l in labs])}."


def s_revenue(c: _Ctx) -> Optional[str]:
    if c.i.revenue is None or c.i.fiscal_year is None:
        return None
    return f"Revenue in FY{c.i.fiscal_year}: {money_en(c.i.revenue)}." if c.lang == "en" else f"הכנסות ב-FY{c.i.fiscal_year}: {money_he(c.i.revenue)}."


# ---------------------------------------------------------------- paragraph 2
def type_label(c: _Ctx, it: dict) -> Optional[str]:
    code = it["industry"]
    if code == "other" or code not in c.i.vocab.labels["competitor_types"]:
        return None
    lab = c.i.vocab.label("competitor_types", code, c.lang)
    scope = it.get("scope")
    if not scope or scope not in c.i.vocab.labels["competitor_types"]:
        return lab
    if c.lang == "en":
        return f"{c.i.vocab.label('competitor_types', scope, 'en')} {lab}"
    adj = c.i.vocab.label("competitor_types", scope, "he") if c.i.vocab.gender.get(code, "m") == "f" else c.i.vocab.scope_he_m[scope]
    return f"{lab} {adj}"


def s_competition(c: _Ctx) -> list:
    names = [i["name"] for i in _items(c.i, "competitors")][:5]
    out = []
    if names:
        if c.lang == "en":
            out.append(_end(f"Its main competitors include {join_en(names)}") if len(names) > 1 else _end(f"Its main competitor is {names[0]}"))
        else:
            out.append(_end(f"בין המתחרים העיקריים: {join_he(names)}") if len(names) > 1 else _end(f"המתחרה העיקרי: {names[0]}"))
        return out
    types = [t for t in (type_label(c, i) for i in _items(c.i, "competitor_types")) if t][:4]
    if types:
        out.append(f"It competes with {join_en(types)}." if c.lang == "en" else f"מתחרה ב{join_he(['ב' + t if k else t for k, t in enumerate(types)])}.")
    else:
        out.append("The report does not describe its competitors." if c.lang == "en" else "הדוח לא מפרט את מתחריה.")
    if c.i.similar:
        out.append(("Similar companies in ValueCompass: " if c.lang == "en" else "חברות דומות ב-ValueCompass: ") + ", ".join(c.i.similar) + ".")
    return out


def _end(sentence: str) -> str:
    return sentence if sentence.endswith(".") else sentence + "."


def s_moat(c: _Ctx) -> Optional[str]:
    lvl = c.i.moat_level
    if lvl not in (0, 1, 2):
        return None
    pre = MOAT_PREFIX[c.lang][lvl]
    if lvl == 0:
        return pre
    src = (MOAT_EN if c.lang == "en" else MOAT_HE).get(c.i.moat_source or "")
    return f"{pre} {src}." if src else None


def render(inp: RenderInput, lang: str, preview: bool = False) -> tuple:
    """-> (text, info). info: {"missing": [English phrases without Hebrew], "used": [English phrases whose Hebrew is in the text], "unreviewed": [...], "sentences": n}."""
    c = _Ctx(inp, lang, preview)
    p1 = [s for s in (s_activity(c), s_products(c), s_customers_revenue(c), s_segments_regions(c), s_operates(c), s_revenue(c)) if s]
    p2 = [s for s in (*s_competition(c), s_moat(c)) if s]
    text = "\n\n".join(" ".join(p) for p in (p1, p2) if p)
    # a Hebrew sentence that was left out because a phrase had no translation makes the text incomplete
    unreviewed = [e for e in dict.fromkeys(c.used) if (inp.translations.get(phrase_key(e)) or {}).get("status") != "approved"]
    return text, {"missing": c.missing, "used": list(dict.fromkeys(c.used)), "unreviewed": unreviewed, "sentences": len(p1) + len(p2)}

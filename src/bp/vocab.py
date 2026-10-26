"""The closed lists of the business profile (``business_vocab``) and the country -> region map.

``Vocab`` is built from ``data/vocab.yaml`` (seed, tests) or from the table rows (production); ``gender`` and the masculine scope forms are code-only and always come from the yaml.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

DATA = Path(__file__).with_name("data")
FIELDS = ("customer_types", "revenue_models", "regions", "competitor_types")
SCOPES = ("local", "regional", "national", "international")


def _yaml(name: str) -> dict:
    return yaml.safe_load((DATA / name).read_text(encoding="utf-8"))


class Vocab:
    def __init__(self, labels: dict, gender: dict, scope_he_m: dict, industry_codes: dict):
        self.labels = labels                  # {field: {code: {"en", "he"}}}
        self.gender = gender                  # {competitor code: "m" | "f"}
        self.scope_he_m = scope_he_m
        self.industry_codes = industry_codes  # {industry name: code}

    # ---------------------------------------------------------------- construction
    @classmethod
    def seed_rows(cls) -> list:
        """The rows of the table ``business_vocab`` as defined by the yaml: [{field, code, label_en, label_he, active}]."""
        y = _yaml("vocab.yaml")
        rows = []
        for f in ("customer_types", "revenue_models", "regions"):
            rows += [{"field": f, "code": c, "label_en": v["en"], "label_he": v["he"], "active": True} for c, v in y[f].items()]
        ct = y["competitor_types"]
        rows += [{"field": "competitor_types", "code": v["code"], "label_en": v["en"], "label_he": v["he"], "active": True} for v in ct["industry"].values()]   # approved by the owner 2026-10-26
        rows += [{"field": "competitor_types", "code": c, "label_en": v["en"], "label_he": v["he"], "active": True} for c, v in {**ct["scope"], **ct["generic"]}.items()]
        return rows

    @classmethod
    def from_rows(cls, rows: Optional[list] = None) -> "Vocab":
        y = _yaml("vocab.yaml")
        rows = rows if rows is not None else cls.seed_rows()
        labels: dict = {f: {} for f in FIELDS}
        for r in rows:
            labels[r["field"]][r["code"]] = {"en": r["label_en"], "he": r["label_he"]}
        ct = y["competitor_types"]
        gender = {v["code"]: v["gender"] for v in ct["industry"].values()}
        gender.update({c: v["gender"] for c, v in ct["generic"].items()})
        return cls(labels, gender, {c: v["he_m"] for c, v in ct["scope"].items()}, {n: v["code"] for n, v in ct["industry"].items()})

    @classmethod
    def from_db(cls, client) -> "Vocab":
        from src.ai.db_stores import select_all
        rows = select_all(client, "business_vocab")
        return cls.from_rows(rows) if rows else cls.from_rows()

    # ---------------------------------------------------------------- lookups
    def codes(self, field: str) -> list:
        return list(self.labels[field])

    def competitor_codes(self) -> dict:
        """The codes BP-1 may use for a competitor type: {"industry": [...], "generic": [...], "scope": [...]}."""
        ind = list(self.industry_codes.values())
        scope = [c for c in self.labels["competitor_types"] if c in SCOPES]
        generic = [c for c in self.labels["competitor_types"] if c not in ind and c not in SCOPES]
        return {"industry": [c for c in ind if c in self.labels["competitor_types"]], "generic": generic, "scope": scope}

    def label(self, field: str, code: str, lang: str) -> str:
        return self.labels[field][code][lang]

    def match_label(self, field: str, text: str) -> Optional[str]:
        """A code whose English or Hebrew label (or code) equals the text, case-insensitively; used to accept a label where the model returned a name instead of a code."""
        t = (text or "").strip().lower()
        for code, lab in self.labels[field].items():
            if t in (code.lower(), lab["en"].lower(), lab["he"].lower()) and code != "other":
                return code
        return None


# ---------------------------------------------------------------- regions
_REGIONS: Optional[dict] = None


def norm_region_name(name: str) -> str:
    t = re.sub(r"\[member\]|\bmember\b", " ", (name or "").lower())
    t = re.sub(r"[^a-z0-9 ]+", " ", t.replace("&", " and "))
    return re.sub(r"\s+", " ", t).strip()


def region_of(name: str) -> str:
    """Country / area name (a member label, or the local part of a member name) -> region code; ``other`` when it is not in the map."""
    global _REGIONS
    if _REGIONS is None:
        _REGIONS = _yaml("regions.yaml")["exact"]
    n = norm_region_name(name)
    if n in _REGIONS:
        return _REGIONS[n]
    n2 = re.sub(r"^(country|iso) ", "", n)
    return _REGIONS.get(n2, "other")


def industry_name(code: str) -> Optional[str]:
    """A ValueCompass industry code of the vocabulary (internet_platforms_advertising) -> the router's industry name ("Internet platforms and advertising"); None for an unknown code."""
    for name, c in Vocab.from_rows().industry_codes.items():
        if c == code:
            return name
    return None

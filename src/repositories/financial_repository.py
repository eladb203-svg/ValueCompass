"""Repository of ``financial_facts`` and ``filing_periods`` (K6a; replaces the legacy yearly-table repository).

A fact row is (company_id, fiscal_year, item_id) -> value, status, source_kind, tag_id, flags, basis, extraction_id. Items are named by their dictionary key
(``dictionary_items.item_key``), tags by their text (``fact_tags.tag``). Writes are idempotent: the existing rows are read first and only new or changed rows are written
(running the same load twice writes 0 rows).
"""
from __future__ import annotations

from typing import Optional

from src.db import get_supabase_client

PAGE = 1000
BATCH = 500


def _same_value(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return float(a) == float(b)


class FinancialRepository:
    def __init__(self, client=None):
        self.client = client or get_supabase_client()
        self._keys: Optional[dict] = None
        self._ids: Optional[dict] = None
        self._tags: dict = {}
        self._tag_text: dict = {}

    # ------------------------------------------------------------ dictionary and tags
    def _load_items(self) -> None:
        if self._keys is None:
            rows = self._select_all("dictionary_items", "id,item_key")
            self._keys = {r["id"]: r["item_key"] for r in rows}
            self._ids = {r["item_key"]: r["id"] for r in rows}

    def item_id(self, item_key: str) -> int:
        self._load_items()
        if item_key not in self._ids:
            raise KeyError(f"item_key {item_key!r} is not in dictionary_items")
        return self._ids[item_key]

    def item_key(self, item_id: int) -> str:
        self._load_items()
        return self._keys[item_id]

    def tag_id(self, tag: Optional[str]) -> Optional[int]:
        """fact_tags.id of a tag text (created when new); None for no tag."""
        if not tag:
            return None
        if tag not in self._tags:
            r = self.client.table("fact_tags").select("id").eq("tag", tag).limit(1).execute().data
            if not r:
                r = self.client.table("fact_tags").insert({"tag": tag}).execute().data
            self._tags[tag] = r[0]["id"]
            self._tag_text[r[0]["id"]] = tag
        return self._tags[tag]

    def tag_text(self, tag_id: Optional[int]) -> Optional[str]:
        if tag_id is None:
            return None
        if tag_id not in self._tag_text:
            r = self.client.table("fact_tags").select("tag").eq("id", tag_id).limit(1).execute().data
            self._tag_text[tag_id] = r[0]["tag"] if r else None
        return self._tag_text[tag_id]

    def preload_tags(self) -> None:
        for r in self._select_all("fact_tags", "id,tag"):
            self._tags[r["tag"]], self._tag_text[r["id"]] = r["id"], r["tag"]

    # ------------------------------------------------------------ reading
    def _select_all(self, table: str, columns: str, filters: Optional[dict] = None, order: Optional[str] = None) -> list:
        out, start = [], 0
        while True:
            q = self.client.table(table).select(columns)
            for k, v in (filters or {}).items():
                q = q.eq(k, v)
            if order:
                q = q.order(order, desc=False)
            page = q.range(start, start + PAGE - 1).execute().data
            out += page
            if len(page) < PAGE:
                return out
            start += PAGE

    def get_history(self, company_id: int) -> list:
        """All fact rows of a company as dicts (item_key, fiscal_year, value, status, source_kind, tag, flags, basis), ordered by fiscal year and item key."""
        self._load_items()
        rows = self._select_all("financial_facts", "*", {"company_id": company_id}, order="fiscal_year")
        out = [self._to_dict(r) for r in rows]
        return sorted(out, key=lambda d: (d["fiscal_year"], d["item_key"]))

    def get_wide_history(self, company_id: int) -> list:
        """One dict per fiscal year: {"fiscal_year": y, <item_key>: value, ...} (items without a value are absent)."""
        wide: dict = {}
        for d in self.get_history(company_id):
            wide.setdefault(d["fiscal_year"], {"fiscal_year": d["fiscal_year"]})[d["item_key"]] = d["value"]
        return [wide[y] for y in sorted(wide)]

    def get_year(self, company_id: int, fiscal_year: int) -> dict:
        """item_key -> row dict for one fiscal year."""
        self._load_items()
        rows = self._select_all("financial_facts", "*", {"company_id": company_id, "fiscal_year": fiscal_year})
        return {d["item_key"]: d for d in (self._to_dict(r) for r in rows)}

    def get_coverage_years(self, company_id: int) -> list:
        rows = self._select_all("financial_facts", "fiscal_year", {"company_id": company_id}, order="fiscal_year")
        return sorted({r["fiscal_year"] for r in rows})

    def _to_dict(self, r: dict) -> dict:
        return {"company_id": r["company_id"], "fiscal_year": r["fiscal_year"], "item_key": self.item_key(r["item_id"]), "value": r["value"], "status": r["status"],
                "source_kind": r["source_kind"], "tag": self.tag_text(r["tag_id"]), "flags": tuple(r.get("flags") or ()), "basis": r.get("basis"), "extraction_id": r.get("extraction_id")}

    # ------------------------------------------------------------ writing
    def _to_row(self, company_id: int, f) -> dict:
        return {"company_id": company_id, "fiscal_year": f.fiscal_year, "item_id": self.item_id(f.item_key), "value": f.value, "status": f.status, "source_kind": f.source_kind,
                "tag_id": self.tag_id(f.tag), "flags": list(f.flags), "basis": f.basis, "extraction_id": None}

    def upsert_facts(self, company_id: int, facts: list) -> dict:
        """Idempotent upsert of ``Fact`` objects. -> {"inserted", "updated", "unchanged"} (rows written = inserted + updated)."""
        self._load_items()
        existing = {(r["fiscal_year"], r["item_id"]): r for r in self._select_all("financial_facts", "*", {"company_id": company_id})}
        todo, stats = [], {"inserted": 0, "updated": 0, "unchanged": 0}
        for f in facts:
            row = self._to_row(company_id, f)
            old = existing.get((row["fiscal_year"], row["item_id"]))
            if old is None:
                stats["inserted"] += 1
            elif (_same_value(old["value"], row["value"]) and old["status"] == row["status"] and old["source_kind"] == row["source_kind"] and old["tag_id"] == row["tag_id"]
                  and list(old.get("flags") or []) == row["flags"] and old.get("basis") == row["basis"]):
                stats["unchanged"] += 1
                continue
            else:
                stats["updated"] += 1
            todo.append(row)
        for i in range(0, len(todo), BATCH):
            self.client.table("financial_facts").upsert(todo[i:i + BATCH], on_conflict="company_id,fiscal_year,item_id").execute()
        return stats

    def upsert_filing_periods(self, company_id: int, periods: list) -> dict:
        """``periods``: dicts with fiscal_year, accession, form, fiscal_year_end (iso), reporting_currency, calculation_version (+ optional filed_at). Idempotent."""
        old = {r["fiscal_year"]: r for r in self._select_all("filing_periods", "*", {"company_id": company_id})}
        todo, stats = [], {"inserted": 0, "updated": 0, "unchanged": 0}
        for p in periods:
            row = {"company_id": company_id, "filed_at": None, **p}
            o = old.get(row["fiscal_year"])
            if o is None:
                stats["inserted"] += 1
            elif all(str(o.get(k)) == str(row.get(k)) for k in row):
                stats["unchanged"] += 1
                continue
            else:
                stats["updated"] += 1
            todo.append(row)
        if todo:
            self.client.table("filing_periods").upsert(todo, on_conflict="company_id,fiscal_year").execute()
        return stats

    def get_filing_periods(self, company_id: int) -> list:
        return self._select_all("filing_periods", "*", {"company_id": company_id}, order="fiscal_year")

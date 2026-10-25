"""Repository of ``extraction_items`` (K6a). Rows <-> ``ExtractionRow`` (src/etl/facts.py).

``value`` is numeric in the table, but extraction rows also carry text values. They are stored without losing the text:
  NA / MISSING / not disclosed  -> value NULL with value_state NA / MISSING / not_disclosed
  any other text (YES, NO, "not extracted") -> value NULL (a number 1 / 0 is not invented), value_state MISSING and basis ``text:<the text>``;  numeric -> value_state value.
Reading reverses it, so the engines see the same ``reg`` as from the CSV. Rows are read in insertion order (``id``): the engines sum extracted lines in that order.
"""
from __future__ import annotations

from typing import Optional

from src.db import get_supabase_client
from src.etl.facts import ExtractionRow

BATCH = 500
PAGE = 1000
APPROVED_AT = "2026-10-25T00:00:00+00:00"      # the table requires approved_at and approval_source on an approved row; the K6a cache load is stamped with its date (approved_at is not compared when deciding "unchanged")
TEXT_STATES = {"NA": "NA", "MISSING": "MISSING", "not disclosed": "not_disclosed"}
STATE_TEXT = {"NA": "NA", "MISSING": "MISSING", "not_disclosed": "not disclosed"}


def encode(company_id: int, r: ExtractionRow, **provenance) -> dict:
    v, state, basis = r.value, r.value_state, r.basis or ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        value = v
    else:
        value = None
        text = str(v)
        if text in TEXT_STATES:
            state = TEXT_STATES[text]
        else:
            state, basis = "MISSING", f"text:{text}"
    return {"company_id": company_id, "item_key": r.item_key, "period": r.period or "", "value": value, "value_state": state, "unit": r.unit or None, "document_ref": r.document_ref or "",
            "section": r.section or None, "exact_quote": r.exact_quote or None, "quote_verified": bool(r.quote_verified), "basis": basis or None, "note": r.note or None,
            "approval_status": r.approval_status, "approval_source": r.approval_source or None,
            "approved_at": APPROVED_AT if r.approval_status == "approved" else None, **provenance}


def decode(ticker: str, row: dict) -> ExtractionRow:
    basis = row.get("basis") or ""
    if basis.startswith("text:"):
        value, state, basis = basis[5:], "value", ""
    elif row["value_state"] in STATE_TEXT:
        value, state = STATE_TEXT[row["value_state"]], row["value_state"]
        if state == "not_disclosed":
            state = "not_disclosed"
    else:
        value, state = float(row["value"]), "value"
    return ExtractionRow(ticker, row["item_key"], row.get("period") or "", value, state, row.get("unit") or "", row.get("document_ref") or "", row.get("section") or "",
                         row.get("exact_quote") or "", bool(row.get("quote_verified")), basis, row.get("note") or "", row.get("approval_status", "approved"),
                         approval_source=row.get("approval_source") or "")


class ExtractionRepository:
    def __init__(self, client=None):
        self.client = client or get_supabase_client()

    def _all(self, company_id: int) -> list:
        out, start = [], 0
        while True:
            page = self.client.table("extraction_items").select("*").eq("company_id", company_id).order("id", desc=False).range(start, start + PAGE - 1).execute().data
            out += page
            if len(page) < PAGE:
                return out
            start += PAGE

    def get_rows(self, company_id: int, ticker: str = "", source: str = "csv") -> list:
        """``source``: ``csv`` = the rows loaded from the extraction CSV files (the engines' ``reg``); ``ai`` = rows made by the AI extraction (``skill_id`` set); ``all``."""
        rows = self._all(company_id)
        if source == "csv":
            rows = [r for r in rows if not r.get("skill_id")]
        elif source == "ai":
            rows = [r for r in rows if r.get("skill_id")]
        return [decode(ticker, r) for r in rows]

    def upsert_rows(self, company_id: int, rows: list, **provenance) -> dict:
        """Idempotent: rows equal to the stored ones are not written. New rows are inserted in the given order (so ``id`` keeps the order)."""
        old = {(r["item_key"], r["period"], r["document_ref"]): r for r in self._all(company_id) if not r.get("skill_id")}
        todo, stats = [], {"inserted": 0, "updated": 0, "unchanged": 0}
        for r in rows:
            e = encode(company_id, r, **provenance)
            o = old.get((e["item_key"], e["period"], e["document_ref"]))
            if o is None:
                stats["inserted"] += 1
            elif all((str(o.get(k)) == str(v)) or (isinstance(v, (int, float)) and o.get(k) is not None and float(o[k]) == float(v)) for k, v in e.items() if k not in ("company_id", "approved_at")):
                stats["unchanged"] += 1
                continue
            else:
                stats["updated"] += 1
            todo.append(e)
        for i in range(0, len(todo), BATCH):
            self.client.table("extraction_items").upsert(todo[i:i + BATCH], on_conflict="company_id,item_key,period,document_ref").execute()
        return stats

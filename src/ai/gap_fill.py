"""A figure entered by the administrator through the development environment (K6d-2 fixes, decided 2026-11-02): ``vc.py gaps fill <ticker> <item> <fiscal_year> <value> --quote "..." [--source-url ...]``.

Only when the administrator decides that the pipeline does not manage to read the figure. The figure is stored as an approved ``human_review`` row of ``extraction_items`` with its quote, the rows the
pipeline had for the same item and year are set aside (rejected, with the reason), the change is written to the audit (``data_update_log``: who, when, before, after, quote, source), the score is
calculated again and the rows of ``data_gap_review`` that the new score no longer lists are closed.
"""
from __future__ import annotations

import getpass
from datetime import datetime, timezone
from typing import Callable, Optional

from src.etl.facts import ExtractionRow
from src.repositories.extraction_repository import ExtractionRepository

SOURCE = "human_review"


def _base(item_key: str) -> str:
    return (item_key or "").split("|")[0]


def fill(client, ticker: str, item: str, fiscal_year: int, value: float, quote: str, source_url: str = "", by: Optional[str] = None, unit: str = "",
         rescore: Optional[Callable] = None, now: Optional[datetime] = None) -> dict:
    """-> {"before": [...], "after": value, "rejected": n, "closed": [...], "audit_id": id}. ``rescore(company_id)`` calculates the score again (the caller passes the queue runner's)."""
    if not quote or len(quote.strip()) < 10:
        raise ValueError("--quote is required: the words of the report that contain the figure")
    now = now or datetime.now(timezone.utc)
    who = by or getpass.getuser()
    co = client.table("companies").select("id,symbol").eq("symbol", ticker.upper()).eq("exchange", "US").execute().data
    if not co:
        raise ValueError(f"{ticker} is not in the database")
    cid, period = co[0]["id"], f"FY{int(fiscal_year)}"
    rows = [r for r in client.table("extraction_items").select("*").eq("company_id", cid).execute().data if _base(r["item_key"]) == item and (r.get("period") or "") == period]
    before = [{"item_key": r["item_key"], "value": r.get("value"), "status": r.get("approval_status"), "source": r.get("approval_source") or r.get("model")} for r in rows if r.get("approval_source") != SOURCE]
    rejected = 0
    for r in rows:
        if r.get("approval_source") == SOURCE or r.get("approval_status") == "rejected":
            continue
        client.table("extraction_items").update({"approval_status": "rejected", "approval_source": None, "note": f"replaced by a figure entered by {who} on {now:%Y-%m-%d} (human_review)"}).eq("id", r["id"]).execute()
        rejected += 1
    note = f"entered by {who} on {now:%Y-%m-%d %H:%M} UTC; the pipeline did not read it" + (f"; source {source_url}" if source_url else "")
    ExtractionRepository(client).upsert_rows(cid, [ExtractionRow(ticker.upper(), item, period, float(value), "value", unit, document_ref=source_url or SOURCE, section="human_review", exact_quote=quote.strip(),
                                                                  quote_verified=False, basis="", note=note, approval_status="approved", approval_source=SOURCE)])
    audit = client.table("data_update_log").insert({"company_id": cid, "symbol": ticker.upper(), "exchange": "US", "operation_type": "full_refresh", "target_table": "financial_facts", "update_scope": "gaps_fill",
                                                    "data_source": "sec_edgar", "status": "success", "records_inserted": 1, "records_updated": rejected, "records_deleted": 0,
                                                    "warning_message": f"human_review: {item} {period} entered by {who}",
                                                    "source_details": [{"who": who, "when": now.isoformat(timespec="seconds"), "item": item, "fiscal_year": int(fiscal_year), "before": before, "after": float(value),
                                                                        "quote": quote.strip(), "source_url": source_url or None}]}).execute().data
    closed = []
    if rescore is not None:
        rescore(cid)
        from . import gap_review
        gap_review.refresh(client, cid)
        closed = [r["item_key"] for r in client.table("data_gap_review").select("item_key,state,closed_at").eq("company_id", cid).eq("state", "fixed").execute().data
                  if str(r.get("closed_at") or "") >= now.isoformat(timespec="seconds")[:19]]
    return {"before": before, "after": float(value), "rejected": rejected, "closed": closed, "audit_id": (audit or [{}])[0].get("id")}

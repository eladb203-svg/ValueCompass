"""Database back ends of the AI stores (K6c). Same interfaces as the file stores of the earlier stages, so the generation code does not change:

  DbTextStore        = content.TextStore       (table ai_texts)
  DbAssessmentStore  = store.AssessmentStore   (table ai_assessments)
  DbAiItemStore      = the K5b items.jsonl     (table extraction_items, rows with skill_id)

Rows go in and out as dicts of the file stores (keyed by ticker); the table keeps what it has columns for, and the rest of a row is kept in a jsonb column (``details``,
``evidence``, ``control``), so nothing is lost and the file row can be rebuilt.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.db import get_supabase_client

PAGE = 1000


class Companies:
    """ticker <-> companies.id (symbol on the "US" exchange row)."""

    def __init__(self, client):
        self.client, self._ids, self._syms = client, {}, {}

    def id(self, ticker: str) -> int:
        if ticker not in self._ids:
            r = self.client.table("companies").select("id,symbol").eq("symbol", ticker).eq("exchange", "US").limit(1).execute().data
            if not r:
                raise KeyError(f"{ticker} is not in the companies table")
            self._ids[ticker], self._syms[r[0]["id"]] = r[0]["id"], ticker
        return self._ids[ticker]

    def symbol(self, company_id: int) -> str:
        if company_id not in self._syms:
            r = self.client.table("companies").select("id,symbol").eq("id", company_id).limit(1).execute().data
            self._syms[company_id] = r[0]["symbol"]
            self._ids[r[0]["symbol"]] = company_id
        return self._syms[company_id]

    def has(self, ticker: str) -> bool:
        try:
            self.id(ticker)
            return True
        except KeyError:
            return False


def select_all(client, table: str, filters: Optional[dict] = None, order: str = "id") -> list:
    out, start = [], 0
    while True:
        q = client.table(table).select("*")
        for k, v in (filters or {}).items():
            q = q.eq(k, v)
        page = q.order(order).range(start, start + PAGE - 1).execute().data
        out += page
        if len(page) < PAGE:
            return out
        start += PAGE


# ---------------------------------------------------------------- texts (D1 / T1 / D2)
TEXT_COLUMNS = {"ticker", "fiscal_year", "kind", "language", "text", "model", "prompt_version", "run_id", "accession", "state", "approval_status", "edited_by", "human_reviewed",
                "checks", "quotes", "created_at", "id", "template_version", "profile_id"}


class DbTextStore:
    def __init__(self, client=None):
        self.client = client or get_supabase_client()
        self.co = Companies(self.client)

    @staticmethod
    def key(r: dict) -> tuple:
        return (r["ticker"], int(r["fiscal_year"]), r["kind"], r["language"], str(r["prompt_version"]), r.get("run_id") or "")

    def _to_db(self, row: dict) -> dict:
        d = self._base(row)
        for k in ("template_version", "profile_id"):                    # migration 17 columns: only written by the template-rendered background (production has them after its migration)
            if row.get(k) is not None:
                d[k] = row[k]
        return d

    def _base(self, row: dict) -> dict:
        return {"company_id": self.co.id(row["ticker"]), "fiscal_year": int(row["fiscal_year"]), "kind": row["kind"], "language": row["language"], "text": row.get("text"),
                "model": row.get("model"), "prompt_version": str(row["prompt_version"]), "run_label": str(row.get("run_id") or ""), "run_id": row.get("score_run_id"),
                "accession": row.get("accession"), "state": row.get("state") or "stored", "approval_status": row.get("approval_status") or ("approved" if row.get("state", "stored") == "stored" else "failed"),
                "edited_by": row.get("edited_by") or "ai", "human_reviewed": bool(row.get("human_reviewed", False)), "checks": row.get("checks") or {}, "quotes": row.get("quotes") or [],
                "details": {k: v for k, v in row.items() if k not in TEXT_COLUMNS and k not in ("score_run_id",)}, "updated_at": datetime.now(timezone.utc).isoformat()}

    def _from_db(self, r: dict) -> dict:
        row = {**(r.get("details") or {}), "ticker": self.co.symbol(r["company_id"]), "fiscal_year": r["fiscal_year"], "kind": r["kind"], "language": r["language"], "text": r["text"],
               "model": r["model"], "prompt_version": r["prompt_version"], "run_id": r["run_label"], "accession": r["accession"], "state": r["state"], "approval_status": r["approval_status"],
               "edited_by": r["edited_by"], "human_reviewed": r["human_reviewed"], "checks": r["checks"], "quotes": r["quotes"], "created_at": r.get("created_at"), "id": r["id"], "score_run_id": r["run_id"],
               "template_version": r.get("template_version"), "profile_id": r.get("profile_id")}
        return row

    def get(self, ticker, fiscal_year, kind, prompt_version, run_id="", language="he"):
        if not self.co.has(ticker):
            return None
        r = (self.client.table("ai_texts").select("*").eq("company_id", self.co.id(ticker)).eq("fiscal_year", int(fiscal_year)).eq("kind", kind).eq("language", language)
             .eq("prompt_version", str(prompt_version)).eq("run_label", run_id or "").limit(1).execute().data)
        return self._from_db(r[0]) if r else None

    def put(self, row: dict) -> dict:
        d = self._to_db(row)
        out = self.client.table("ai_texts").upsert(d, on_conflict="company_id,fiscal_year,kind,language,prompt_version,run_label").execute().data[0]
        return self._from_db(out)

    def rows(self, ticker: Optional[str] = None) -> list:
        filters = {"company_id": self.co.id(ticker)} if ticker else None
        return [self._from_db(r) for r in select_all(self.client, "ai_texts", filters)]

    def migrate_review_status(self) -> int:
        return 0

    def get_by_id(self, text_id: int) -> Optional[dict]:
        r = self.client.table("ai_texts").select("*").eq("id", text_id).limit(1).execute().data
        return self._from_db(r[0]) if r else None

    def update(self, text_id: int, **fields) -> dict:
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        return self._from_db(self.client.table("ai_texts").update(fields).eq("id", text_id).execute().data[0])


# ---------------------------------------------------------------- scoring answers (A1-A14, C1)
class DbAssessmentStore:
    def __init__(self, client=None, approved_only: bool = True):
        self.client = client or get_supabase_client()
        self.co = Companies(self.client)
        self.approved_only = approved_only

    key = staticmethod(lambda r: (r["ticker"], int(r["fiscal_year"]), r["question_id"], str(r["prompt_version"])))

    def _to_db(self, row: dict) -> dict:
        extra = {k: row[k] for k in ("raw_answer", "usage", "created_at") if k in row}
        ev = {**(row.get("evidence") or {}), "_extra": extra}
        return {"company_id": self.co.id(row["ticker"]), "fiscal_year": int(row["fiscal_year"]), "question_id": row["question_id"], "answer": row.get("answer"), "state": row["state"],
                "evidence": ev, "model": row.get("model") or "", "prompt_version": str(row["prompt_version"]), "approval_status": row.get("approval_status") or "approved",
                "accession": row.get("accession"), "skill_version": str(row["prompt_version"])}

    def _from_db(self, r: dict) -> dict:
        ev = dict(r["evidence"] or {})
        extra = ev.pop("_extra", {})
        return {**extra, "ticker": self.co.symbol(r["company_id"]), "fiscal_year": r["fiscal_year"], "question_id": r["question_id"], "answer": r["answer"], "state": r["state"], "evidence": ev,
                "model": r["model"], "prompt_version": r["prompt_version"], "approval_status": r["approval_status"], "accession": r["accession"], "created_at": extra.get("created_at") or r.get("created_at")}

    def get(self, ticker: str, fiscal_year: int, question_id: str, prompt_version) -> Optional[dict]:
        if not self.co.has(ticker):
            return None
        q = (self.client.table("ai_assessments").select("*").eq("company_id", self.co.id(ticker)).eq("fiscal_year", int(fiscal_year)).eq("question_id", question_id)
             .eq("prompt_version", str(prompt_version)).limit(1).execute().data)
        return self._from_db(q[0]) if q else None

    def put(self, row: dict) -> dict:
        row = {**row, "created_at": row.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")}
        out = self.client.table("ai_assessments").upsert(self._to_db(row), on_conflict="company_id,fiscal_year,question_id,prompt_version").execute().data[0]
        return self._from_db(out)

    def rows(self, ticker: Optional[str] = None) -> list:
        filters = {"company_id": self.co.id(ticker)} if ticker else None
        rows = [self._from_db(r) for r in select_all(self.client, "ai_assessments", filters)]
        return [r for r in rows if r["approval_status"] == "approved"] if self.approved_only else rows

    def answers_for(self, ticker: str, fiscal_year: int) -> dict:
        out = {}
        for r in self.rows(ticker):
            if r["fiscal_year"] == int(fiscal_year):
                v = r["prompt_version"]
                out[r["question_id"]] = {"state": r["state"], "answer": r["answer"], "version": int(v) if str(v).isdigit() else v, "flags": r.get("evidence", {}).get("flags", [])}
        return out


# ---------------------------------------------------------------- AI extraction items (B1-B14)
class DbAiItemStore:
    """The K5b items (``extraction_items`` rows that have a ``skill_id``). The original items.jsonl row is kept in ``control['k5b_row']`` and can be rebuilt exactly."""

    def __init__(self, client=None):
        self.client = client or get_supabase_client()
        self.co = Companies(self.client)

    def to_db(self, r: dict, item_key: str, source: str) -> dict:
        state = r["state"]
        value = r["value_full"] if r.get("value_full") is not None else r.get("value")
        if state in ("not_disclosed", "NA"):
            vstate, value = state, None
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            vstate = "value"
        else:
            vstate, value = "MISSING", None
        status = {"approved": "approved", "pending": "pending", "rejected": "rejected"}.get(r["approval_status"], "approved")          # 'n/a' (nothing to approve) is approved
        return {"company_id": self.co.id(r["ticker"]), "item_key": item_key, "period": f"FY{r['year']}", "value": value, "value_state": vstate, "unit": r.get("unit"),
                "document_ref": r["accession"], "section": r.get("section"), "exact_quote": r.get("quote"), "quote_verified": "quote_not_found" not in (r.get("reasons") or []) and state != "rejected",
                "basis": r.get("basis"), "note": "; ".join(r.get("reasons") or []) or None, "approval_status": status, "approval_source": source if status == "approved" else None,
                "approved_at": datetime.now(timezone.utc).isoformat() if status == "approved" else None, "skill_id": r["skill_id"], "skill_version": str(r.get("version")), "model": r.get("model"),
                "prompt_version": str(r.get("prompt_version")), "control": {"name": r.get("control"), "result": r.get("control_result"), "detail": r.get("control_detail"), "k5b_row": r}}

    @staticmethod
    def item_keys(rows: list) -> dict:
        """The table key is (company, item_key, period, document_ref): items that share it (loan lines, balance-sheet lines, one item with several bases) get the basis in their key."""
        from collections import defaultdict
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            groups[(r["ticker"], r["item_key"], r["year"], r["accession"])].append(i)
        keys = {}
        for g in groups.values():
            for n, i in enumerate(g):
                r = rows[i]
                keys[i] = r["item_key"] if len(g) == 1 else f"{r['item_key']}|{r.get('basis') or ''}|{n}"
        return keys

    def upsert_rows(self, rows: list, source: str = "ai_controls", dry_run: bool = False) -> dict:
        """Idempotent. -> {"inserted", "updated", "unchanged"} (rows of companies that are not in the table are skipped, counted as "skipped")."""
        from collections import Counter, defaultdict
        keys, c, by_company = self.item_keys(rows), Counter(), defaultdict(list)
        for i, r in enumerate(rows):
            if not self.co.has(r["ticker"]):
                c["skipped"] += 1
                continue
            by_company[self.co.id(r["ticker"])].append(self.to_db(r, keys[i], source))
        for cid, new in by_company.items():
            old = {(x["item_key"], x["period"], x["document_ref"]): x for x in select_all(self.client, "extraction_items", {"company_id": cid}) if x.get("skill_id")}
            todo = []
            for row in new:
                o = old.get((row["item_key"], row["period"], row["document_ref"]))
                if o and o["approval_status"] == row["approval_status"] and (o["control"] or {}).get("k5b_row") == row["control"]["k5b_row"] and o.get("approval_source") == row["approval_source"]:
                    c["unchanged"] += 1
                    continue
                c["updated" if o else "inserted"] += 1
                todo.append(row)
            for j in range(0, 0 if dry_run else len(todo), 200):
                self.client.table("extraction_items").upsert(todo[j:j + 200], on_conflict="company_id,item_key,period,document_ref").execute()
        return dict(c)

    def rows_for(self, ticker: Optional[str] = None) -> list:
        """The original K5b item rows (dicts of items.jsonl), with the approval status the DB holds now."""
        out = []
        rows = select_all(self.client, "extraction_items", {"company_id": self.co.id(ticker)} if ticker else None)
        for r in (x for x in rows if x.get("skill_id")):
            row = dict((r["control"] or {}).get("k5b_row") or {})
            if row:
                row["approval_status"] = r["approval_status"] if r["approval_status"] != "approved" or row.get("approval_status") != "n/a" else "n/a"
                out.append(row)
        return out

    def export_jsonl(self, path: Path, tickers: Optional[list] = None) -> int:
        rows = []
        for t in tickers or [None]:
            rows += self.rows_for(t)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
        return len(rows)

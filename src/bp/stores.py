"""Database access of the business profile (migration 17): ``company_business_profiles``, ``business_vocab``, ``term_translations``. Same client interface as the other stores (and the test fake)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.ai.db_stores import select_all

from .translate import glossary_pairs, phrase_key

PROFILE_FIELDS = ("core_activity", "segments", "products_services", "customer_types", "revenue_models", "regions", "competitors", "competitor_types")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProfileStore:
    def __init__(self, client):
        self.client = client

    def get(self, company_id: int, accession: str) -> Optional[dict]:
        r = self.client.table("company_business_profiles").select("*").eq("company_id", company_id).eq("accession", accession).limit(1).execute().data
        return r[0] if r else None

    def by_id(self, profile_id: int) -> Optional[dict]:
        r = self.client.table("company_business_profiles").select("*").eq("id", profile_id).limit(1).execute().data
        return r[0] if r else None

    def for_company(self, company_id: int) -> list:
        return sorted(select_all(self.client, "company_business_profiles", {"company_id": company_id}), key=lambda r: (r["fiscal_year"], r["id"]))

    def latest(self, company_id: int) -> Optional[dict]:
        rows = self.for_company(company_id)
        return rows[-1] if rows else None

    def put(self, row: dict) -> dict:
        row = {**row, "updated_at": _now()}
        return self.client.table("company_business_profiles").upsert(row, on_conflict="company_id,accession").execute().data[0]


class VocabStore:
    def __init__(self, client):
        self.client = client

    def rows(self) -> list:
        return select_all(self.client, "business_vocab")

    def seed(self, rows: list) -> dict:
        """Insert the rows that are not there yet; a row that exists is never changed (the owner's edits and approvals stay). -> {"inserted", "existing"}."""
        have = {(r["field"], r["code"]) for r in self.rows()}
        new = [r for r in rows if (r["field"], r["code"]) not in have]
        for i in range(0, len(new), 100):
            self.client.table("business_vocab").insert(new[i:i + 100]).execute()
        return {"inserted": len(new), "existing": len(rows) - len(new)}


class TermStore:
    def __init__(self, client):
        self.client = client

    def rows(self) -> list:
        return select_all(self.client, "term_translations")

    def map(self) -> dict:
        """phrase_key(en) -> {"he", "status", "id", "source"} for the renderer."""
        return {phrase_key(r["en"]): {"he": r["he"], "status": r["status"], "id": r["id"], "source": r["source"]} for r in self.rows()}

    def put(self, en: str, he: str, source: str, status: str = "unreviewed") -> dict:
        row = {"en": en.strip(), "he": he, "source": source, "status": status}
        if status == "approved":
            row["reviewed_at"] = _now()
        for r in self.rows():                                            # unique on the exact English text; compare normalised
            if phrase_key(r["en"]) == phrase_key(en):
                return self.client.table("term_translations").update({k: v for k, v in row.items() if k != "en"}).eq("id", r["id"]).execute().data[0]
        return self.client.table("term_translations").insert(row).execute().data[0]

    def seed_glossary(self) -> dict:
        """The T1 glossary becomes approved / human translations (a term that is already there is left as it is)."""
        have = {phrase_key(r["en"]) for r in self.rows()}
        new = [{"en": en, "he": he, "source": "human", "status": "approved", "reviewed_at": _now()} for en, he in glossary_pairs() if phrase_key(en) not in have]
        if new:
            self.client.table("term_translations").insert(new).execute()
        return {"inserted": len(new), "existing": len(glossary_pairs()) - len(new)}

    def get_by_id(self, tid: int) -> Optional[dict]:
        r = self.client.table("term_translations").select("*").eq("id", tid).limit(1).execute().data
        return r[0] if r else None

    def approve(self, tid: int) -> dict:
        return self.client.table("term_translations").update({"status": "approved", "reviewed_at": _now()}).eq("id", tid).execute().data[0]

    def edit(self, tid: int, he: str) -> dict:
        """A person's correction: stored as human / approved."""
        return self.client.table("term_translations").update({"he": he, "source": "human", "status": "approved", "reviewed_at": _now()}).eq("id", tid).execute().data[0]

    def unreviewed(self) -> list:
        return [r for r in self.rows() if r["status"] == "unreviewed"]

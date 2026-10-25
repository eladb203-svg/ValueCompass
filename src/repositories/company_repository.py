from datetime import datetime, timezone

from src.db import get_supabase_client


class CompanyRepository:
    def __init__(self, client=None):
        self.client = client or get_supabase_client()

    def get_by_id(self, company_id: int):
        # שליפת חברה קנונית לפי ID פנימי
        response = (
            self.client
            .table("companies")
            .select("*")
            .eq("id", company_id)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def get_by_name(self, company_name: str):
        # חיפוש לפי שם עלול להחזיר מספר מועמדים
        company_name = company_name.strip()

        response = (
            self.client
            .table("companies")
            .select("*")
            .ilike("company_name", company_name)
            .eq("is_active", True)
            .execute()
        )

        return response.data

    def insert(self, company_data: dict):
        # יצירת חברה קנונית חדשה
        response = (
            self.client
            .table("companies")
            .insert(company_data)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def update(self, company_id: int, company_data: dict):
        # עדכון שדות בחברה קיימת
        update_data = dict(company_data)
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        response = (
            self.client
            .table("companies")
            .update(update_data)
            .eq("id", company_id)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None
    # ------------------------------------------------------------ K6a: identifiers, classification and processing state (migration 9)
    PROCESSING_STATES = ("resolved", "data_loaded", "scored_partial", "ai_in_progress", "complete", "failed", "unsupported")

    def get_by_symbol(self, symbol: str, exchange: str = None):
        q = self.client.table("companies").select("*").eq("symbol", symbol)
        if exchange:
            q = q.eq("exchange", exchange)
        data = q.limit(2).execute().data
        return data[0] if data else None

    def find_without_cik(self, symbol: str) -> list:
        """Companies of this symbol (on any exchange) that have no CIK: rows made before RESOLVE existed (a legacy import)."""
        rows = self.client.table("companies").select("*").eq("symbol", symbol).execute().data
        return [r for r in rows if not r.get("cik")]

    def get_by_cik(self, cik: str):
        data = self.client.table("companies").select("*").eq("cik", cik).limit(1).execute().data
        return data[0] if data else None

    def set_processing_state(self, company_id: int, state: str, unsupported_reason: str = None):
        if state not in self.PROCESSING_STATES:
            raise ValueError(f"unknown processing_state {state!r}")
        if state == "unsupported" and not unsupported_reason:
            raise ValueError("an unsupported company needs a reason")
        return self.update(company_id, {"processing_state": state, "unsupported_reason": unsupported_reason if state == "unsupported" else None})

    def set_classification(self, company_id: int, sic: str = None, vc_industry: str = None, tier: str = None, status: str = None):
        fields = {"sic": sic, "vc_industry": vc_industry, "classification_tier": tier, "classification_status": status}
        return self.update(company_id, {k: v for k, v in fields.items() if v is not None})

    def ensure(self, symbol: str, name: str, exchange: str = "US", country: str = "US", reporting_currency: str = "USD", **extra):
        """The company with this (symbol, exchange), created when absent (idempotent). -> the row."""
        found = self.get_by_symbol(symbol, exchange)
        if found:
            return found
        return self.insert({"symbol": symbol, "company_name": name, "exchange": exchange, "country": country, "reporting_currency": reporting_currency, **extra})

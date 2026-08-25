from datetime import datetime, timezone

from src.db import get_supabase_client


class CompanyRepository:
    def __init__(self):
        # יצירת חיבור ל-Supabase
        self.client = get_supabase_client()

    def get_by_symbol_exchange(self, symbol: str, exchange: str):
        # חיפוש חברה לפי סימול ובורסה
        response = (
            self.client
            .table("companies")
            .select("*")
            .eq("symbol", symbol)
            .eq("exchange", exchange)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def insert(self, company_data: dict):
        # הכנסת חברה חדשה לטבלה
        response = (
            self.client
            .table("companies")
            .insert(company_data)
            .execute()
        )

        return response.data[0]

    def update(self, company_id: int, company_data: dict):
        # עדכון זמן השינוי האחרון
        company_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # עדכון חברה קיימת
        response = (
            self.client
            .table("companies")
            .update(company_data)
            .eq("id", company_id)
            .execute()
        )

        return response.data[0]

    def upsert_company(self, company_data: dict):
        # בדיקה האם החברה כבר קיימת
        existing_company = self.get_by_symbol_exchange(
            company_data["symbol"],
            company_data["exchange"]
        )

        if existing_company:
            # אם קיימת - מעדכנים
            return self.update(
                existing_company["id"],
                company_data
            )

        # אם לא קיימת - מוסיפים
        return self.insert(company_data)
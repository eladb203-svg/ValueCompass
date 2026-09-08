from datetime import datetime, timezone

from src.db import get_supabase_client


class CompanyRepository:
    def __init__(self):
        # יצירת חיבור ל-Supabase
        self.client = get_supabase_client()

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
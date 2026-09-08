from src.db import get_supabase_client


class FinancialRepository:
    def __init__(self):
        self.client = get_supabase_client()

    def get_history(self, company_id: int):
        response = (
            self.client
            .table("financial_yearly")
            .select("*")
            .eq("company_id", company_id)
            .order("fiscal_year", desc=False)
            .execute()
        )

        return response.data

    def get_year(self, company_id: int, fiscal_year: int):
        response = (
            self.client
            .table("financial_yearly")
            .select("*")
            .eq("company_id", company_id)
            .eq("fiscal_year", fiscal_year)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def get_coverage_years(self, company_id: int):
        response = (
            self.client
            .table("financial_yearly")
            .select("fiscal_year")
            .eq("company_id", company_id)
            .order("fiscal_year", desc=False)
            .execute()
        )

        return [
            row["fiscal_year"]
            for row in response.data
        ]

    def upsert_year(self, financial_data: dict):
        response = (
            self.client
            .table("financial_yearly")
            .upsert(
                financial_data,
                on_conflict="company_id,fiscal_year"
            )
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def update_fields(
        self,
        company_id: int,
        fiscal_year: int,
        fields: dict
    ):
        response = (
            self.client
            .table("financial_yearly")
            .update(fields)
            .eq("company_id", company_id)
            .eq("fiscal_year", fiscal_year)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

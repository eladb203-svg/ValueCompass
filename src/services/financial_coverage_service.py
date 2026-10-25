from src.repositories.company_repository import CompanyRepository
from src.repositories.financial_repository import FinancialRepository

# Dictionary keys (Part E) of the lines the audit expects in every year (the general model's key statement lines).
FINANCIAL_AUDIT_FIELDS = {
    "revenue",
    "gross_profit",
    "ebit",
    "net_income",
    "eps_diluted",
    "cfo",
    "capex",
    "total_assets",
    "total_liabilities",
    "equity",
    "long_term_debt",
    "cash",
    "current_assets",
    "current_liabilities",
    "shares_diluted_weighted",
}


class FinancialCoverageService:
    def __init__(self):
        self.company_repository = CompanyRepository()
        self.financial_repository = FinancialRepository()

    def get_existing_years(self, company_id: int):
        # השנים הקיימות לחברה
        company = self.company_repository.get_by_id(company_id)

        if not company:
            raise ValueError(
                f"Company with id {company_id} was not found."
            )

        return self.financial_repository.get_coverage_years(company_id)

    def get_missing_fields_by_year(self, company_id: int):
        # השדות החסרים בכל שנה קיימת
        company = self.company_repository.get_by_id(company_id)

        if not company:
            raise ValueError(
                f"Company with id {company_id} was not found."
            )

        history = self.financial_repository.get_wide_history(company_id)

        return self.audit_year_fields(history)

    def audit_year_fields(self, history: list[dict]):
        # history: one dict per fiscal year, {"fiscal_year": y, <item_key>: value, ...} (FinancialRepository.get_wide_history)
        incomplete_years = {}

        for year_data in history:
            fiscal_year = year_data.get("fiscal_year")

            missing_fields = sorted(
                field
                for field in FINANCIAL_AUDIT_FIELDS
                if year_data.get(field) is None
            )

            if missing_fields:
                incomplete_years[fiscal_year] = missing_fields

        return incomplete_years

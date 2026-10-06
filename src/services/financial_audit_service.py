from src.constants import FinancialWorkflow
from src.repositories.company_repository import CompanyRepository
from src.repositories.financial_repository import FinancialRepository

FINANCIAL_AUDIT_FIELDS = {
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "eps_diluted",
    "operating_cash_flow",
    "capex",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "total_debt",
    "long_term_debt",
    "cash_and_equivalents",
    "current_assets",
    "current_liabilities",
    "shares_outstanding",

}


class FinancialAuditService:
    def __init__(self):
        self.company_repository = CompanyRepository()
        self.financial_repository = FinancialRepository()

    def get_financial_state(self, company_id: int):
        company = self.company_repository.get_by_id(company_id)

        if not company:
            raise ValueError(
                f"Company with id {company_id} was not found."
            )

        history = self.financial_repository.get_history(company_id)
        coverage_years = self.financial_repository.get_coverage_years(
            company_id
        )

        return {
            "company": company,
            "history": history,
            "coverage_years": coverage_years,
        }

    def calculate_expected_years(
        self,
        company: dict,
        latest_expected_fiscal_year: int,
        target_years: int = 10
    ):
        public_since_date = company.get("public_since_date")

        if not public_since_date:
            return {
                "expected_years": [],
                "metadata_missing": ["public_since_date"],
            }

        public_since_year = int(
            str(public_since_date)[:4]
        )

        first_target_year = (
            latest_expected_fiscal_year - target_years + 1
        )

        first_expected_year = max(
            public_since_year,
            first_target_year
        )

        expected_years = list(
            range(
                first_expected_year,
                latest_expected_fiscal_year + 1
            )
        )

        return {
            "expected_years": expected_years,
            "metadata_missing": [],
        }

    def calculate_year_coverage(
        self,
        expected_years: list[int],
        present_years: list[int]
    ):
        expected_set = set(expected_years)
        present_set = set(present_years)

        missing_years = sorted(
            expected_set - present_set
        )

        covered_years = sorted(
            expected_set & present_set
        )

        return {
            "expected_years": sorted(expected_years),
            "present_years": sorted(present_years),
            "covered_years": covered_years,
            "missing_years": missing_years,
        }

    def audit_company(
        self,
        company_id: int,
        latest_expected_fiscal_year: int,
        target_years: int = 10
    ):
        # Get the current company and financial data from the database
        state = self.get_financial_state(company_id)

        # Determine which fiscal years are expected
        expected = self.calculate_expected_years(
            company=state["company"],
            latest_expected_fiscal_year=latest_expected_fiscal_year,
            target_years=target_years
        )

        # Compare expected years with the years stored in the database
        coverage = self.calculate_year_coverage(
            expected_years=expected["expected_years"],
            present_years=state["coverage_years"]
        )

        # Check existing fiscal years for missing financial fields
        incomplete_years = self.audit_year_fields(
            state["history"]
        )

        # Return the complete financial audit result
        return {
            "company_id": company_id,
            "company_name": state["company"]["company_name"],
            "public_since_date": state["company"].get(
                "public_since_date"
            ),
            "latest_expected_fiscal_year": latest_expected_fiscal_year,
            "target_years": target_years,
            "metadata_missing": expected["metadata_missing"],
            "incomplete_years": incomplete_years,
            **coverage,
        }

    def create_work_plan(self, audit: dict):
        # Critical company metadata must be repaired first
        if audit["metadata_missing"]:
            return {
                "workflow": FinancialWorkflow.METADATA_REPAIR,
                "metadata_fields": audit["metadata_missing"],
                "years": [],
                "missing_fields": {},
            }

        # No financial history exists yet
        if not audit["present_years"]:
            return {
                "workflow": FinancialWorkflow.INITIAL_IMPORT,
                "metadata_fields": [],
                "years": audit["expected_years"],
                "missing_fields": {},
            }

        # Entire fiscal years are missing
        if audit["missing_years"]:
            return {
                "workflow": FinancialWorkflow.BACKFILL,
                "metadata_fields": [],
                "years": audit["missing_years"],
                "missing_fields": {},
            }

        # Fiscal years exist, but some required fields are missing
        if audit["incomplete_years"]:
            return {
                "workflow": FinancialWorkflow.REPAIR,
                "metadata_fields": [],
                "years": sorted(audit["incomplete_years"].keys()),
                "missing_fields": audit["incomplete_years"],
            }

        # Financial history is complete
        return {
            "workflow": FinancialWorkflow.NO_ACTION,
            "metadata_fields": [],
            "years": [],
            "missing_fields": {},
        }

    def audit_year_fields(self, history: list[dict]):
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

from src.repositories.company_repository import CompanyRepository
from src.repositories.financial_repository import FinancialRepository
from src.services.financial_validation_service import FinancialValidationService


class FinancialYearService:
    def __init__(self):
        self.company_repository = CompanyRepository()
        self.financial_repository = FinancialRepository()
        self.financial_validation_service = FinancialValidationService()

    def _validate_company_id(self, company_id):
        return (
            isinstance(company_id, int)
            and not isinstance(company_id, bool)
            and company_id > 0
        )

    def save_financial_year(
        self,
        company_id: int,
        financial_data: dict,
    ):
        # בדיקות בסיסיות לפני גישה ל-DB
        if not self._validate_company_id(company_id):
            return {
                "status": "INVALID_REQUEST",
                "error": "Invalid company_id",
            }

        if not isinstance(financial_data, dict):
            return {
                "status": "INVALID_REQUEST",
                "error": "financial_data must be a dictionary",
            }

        # normalize + validate לפני persistence
        result = (
            self.financial_validation_service
            .normalize_and_validate(
                company_id=company_id,
                financial_data=financial_data,
            )
        )

        normalized_data = result["data"]
        validation = result["validation"]

        # נתון שנדחה לעולם לא נשמר
        if validation["status"] == "REJECTED":
            return {
                "status": "REJECTED",
                "validation": validation,
                "data": normalized_data,
            }

        fiscal_year = normalized_data.get("fiscal_year")

        company = self.company_repository.get_by_id(company_id)

        if company is None:
            return {
                "status": "NOT_FOUND",
                "company_id": company_id,
            }

        existing_year = self.financial_repository.get_year(
            company_id,
            fiscal_year,
        )

        if existing_year is None:
            # שנה חדשה - יצירת הרשומה
            persisted = self.financial_repository.upsert_year(
                normalized_data
            )
            persistence_action = "INSERTED"

        else:
            # שנה קיימת - מעדכנים רק את השדות שנשלחו
            update_data = {
                key: value
                for key, value in normalized_data.items()
                if key not in {
                    "company_id",
                    "fiscal_year",
                }
            }

            persisted = self.financial_repository.update_fields(
                company_id=company_id,
                fiscal_year=fiscal_year,
                fields=update_data,
            )
            persistence_action = "UPDATED"

        if persisted is None:
            return {
                "status": "FAILED",
                "error": "Financial year persistence failed",
                "company_id": company_id,
                "fiscal_year": fiscal_year,
            }

        return {
            "status": persistence_action,
            "company_id": company_id,
            "fiscal_year": fiscal_year,
            "validation": validation,
        }

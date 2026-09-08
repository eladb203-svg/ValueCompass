from src.models.company import (
    normalize_company_data,
    normalize_listing_data,
)
from src.repositories.company_repository import CompanyRepository
from src.repositories.listing_repository import ListingRepository
from src.services.financial_audit_service import FinancialAuditService
from src.repositories.update_log_repository import UpdateLogRepository


class CompanySyncService:
    def __init__(self):
        # יצירת גישה לשכבות ה-DB
        self.company_repository = CompanyRepository()
        self.listing_repository = ListingRepository()
        self.financial_audit_service = FinancialAuditService()
        self.update_log_repository = UpdateLogRepository()

    def resolve_existing_listing(
        self,
        symbol: str,
        exchange: str
    ):
        # חיפוש listing קיים לפי סימול ובורסה
        listing = self.listing_repository.get_by_symbol_exchange(
            symbol,
            exchange
        )

        if not listing:
            return None

        # קריאת החברה הקנונית של ה-listing
        company = self.company_repository.get_by_id(
            listing["company_id"]
        )

        if not company:
            raise ValueError(
                "Listing exists but its canonical company was not found."
            )

        return {
            "resolution_outcome": "RESOLVED_EXISTING",
            "company": company,
            "listing": listing,
        }

    def prepare_new_listing_for_existing_company(
        self,
        company_id: int,
        listing_data: dict
    ):
        # וידוא שהחברה הקנונית קיימת
        company = self.company_repository.get_by_id(company_id)

        if not company:
            raise ValueError(
                f"Company with id {company_id} was not found."
            )

        # עבודה על עותק כדי לא לשנות את הקלט המקורי
        listing_candidate = listing_data.copy()
        listing_candidate["company_id"] = company_id

        # נרמול נתוני ה-listing
        normalized_listing = normalize_listing_data(
            listing_candidate
        )

        # בדיקה אם ה-listing כבר קיים
        existing_listing = (
            self.listing_repository.get_by_symbol_exchange(
                normalized_listing["symbol"],
                normalized_listing["exchange"]
            )
        )

        if existing_listing:
            return {
                "resolution_outcome": "RESOLVED_EXISTING",
                "company": company,
                "listing": existing_listing,
                "listing_candidate": None,
            }

        # החזרת מועמד ל-listing חדש בלי כתיבה ל-DB
        return {
            "resolution_outcome": "RESOLVED_NEW_LISTING",
            "company": company,
            "listing": None,
            "listing_candidate": normalized_listing,
        }

    def prepare_new_company_with_listing(
        self,
        company_data: dict,
        listing_data: dict
    ):
        # Normalize canonical company data
        normalized_company = normalize_company_data(
            company_data
        )

        # Normalize listing data
        normalized_listing = normalize_listing_data(
            listing_data
        )

        # Required company identity
        if not normalized_company.get("company_name"):
            raise ValueError(
                "company_name is required for a new company."
            )

        # Required listing identity
        if not normalized_listing.get("symbol"):
            raise ValueError(
                "symbol is required for a new listing."
            )

        if not normalized_listing.get("exchange"):
            raise ValueError(
                "exchange is required for a new listing."
            )

        # Prevent creation if the listing already exists
        existing_listing = (
            self.listing_repository.get_by_symbol_exchange(
                normalized_listing["symbol"],
                normalized_listing["exchange"]
            )
        )

        if existing_listing:
            company = self.company_repository.get_by_id(
                existing_listing["company_id"]
            )

            return {
                "resolution_outcome": "RESOLVED_EXISTING",
                "company": company,
                "listing": existing_listing,
                "company_candidate": None,
                "listing_candidate": None,
            }

        # No company_id yet because the company has not been inserted
        normalized_listing.pop("company_id", None)

        return {
            "resolution_outcome": "RESOLVED_NEW_COMPANY",
            "company": None,
            "listing": None,
            "company_candidate": normalized_company,
            "listing_candidate": normalized_listing,
        }

    def persist_new_listing(
        self,
        company_id: int,
        listing_data: dict
    ):
        """
        Persist a new listing for an existing canonical company.
        """

        prepared = self.prepare_new_listing_for_existing_company(
            company_id=company_id,
            listing_data=listing_data
        )

        # Listing already exists - nothing to write
        if prepared["resolution_outcome"] == "RESOLVED_EXISTING":
            return prepared

        listing = self.listing_repository.insert(
            prepared["listing_candidate"]
        )

        return {
            "resolution_outcome": "RESOLVED_NEW_LISTING",
            "company": prepared["company"],
            "listing": listing,
        }

    def persist_new_company_with_listing(
        self,
        company_data: dict,
        listing_data: dict
    ):
        prepared = self.prepare_new_company_with_listing(
            company_data=company_data,
            listing_data=listing_data
        )

        if prepared["resolution_outcome"] == "RESOLVED_EXISTING":
            return prepared

        response = self.company_repository.client.rpc(
            "create_company_with_listing",
            {
                "p_company": prepared["company_candidate"],
                "p_listing": prepared["listing_candidate"],
            }
        ).execute()

        return response.data

    def sync_company(
        self,
        company_id: int,
        latest_expected_fiscal_year: int,
        target_years: int = 10
    ):
        # Audit the current financial state
        audit = self.financial_audit_service.audit_company(
            company_id=company_id,
            latest_expected_fiscal_year=latest_expected_fiscal_year,
            target_years=target_years
        )

        # Decide what ETL work is required
        work_plan = self.financial_audit_service.create_work_plan(
            audit
        )

        # Open a sync log before ETL execution
        log = self.update_log_repository.create_log({
            "company_id": company_id,
            "operation_type": "sync_company",
            "target_table": "financial_yearly",
            "update_scope": work_plan["workflow"],
            "data_source": "openai_etl_agent",
            "status": "running",
            "years_requested": work_plan["years"],
            "missing_years": audit["missing_years"],
        })

        etl_request = self.build_etl_request(
            audit=audit,
            work_plan=work_plan,
            log_id=log["id"]
        )

        return {
            "company_id": company_id,
            "audit": audit,
            "work_plan": work_plan,
            "log": log,
            "etl_request": etl_request,
        }

    def build_etl_request(
        self,
        audit: dict,
        work_plan: dict,
        log_id: int
    ):
        return {
            "sync_log_id": log_id,
            "company_id": audit["company_id"],
            "company_name": audit["company_name"],
            "workflow": work_plan["workflow"],
            "metadata_fields": work_plan["metadata_fields"],
            "years": work_plan["years"],
            "missing_fields": work_plan["missing_fields"],
        }

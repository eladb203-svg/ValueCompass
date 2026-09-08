from datetime import date

from src.repositories.update_log_repository import UpdateLogRepository
from src.repositories.company_repository import CompanyRepository
from src.repositories.listing_repository import ListingRepository
from src.repositories.financial_repository import FinancialRepository
from src.services.financial_validation_service import FinancialValidationService

class FinancialETLCapabilities:
    # שדות חברה שמותר לחשוף ל-Agent
    COMPANY_READ_FIELDS = (
        "id",
        "company_name",
        "country",
        "reporting_currency",
        "sector",
        "industry",
        "public_since_date",
        "is_active",
    )

    # שדות listing שמותר לחשוף ל-Agent
    LISTING_READ_FIELDS = (
        "id",
        "company_id",
        "symbol",
        "exchange",
        "mic",
        "isin",
        "figi",
        "trading_currency",
        "is_primary",
        "listing_start_date",
        "is_active",
    )
    # שדות metadata שה-Agent מורשה לעדכן
    COMPANY_METADATA_WRITE_FIELDS = {
        "public_since_date",
        "reporting_currency",
    }

        # workflows שמורשים לכתוב נתונים שנתיים
    FINANCIAL_WRITE_WORKFLOWS = {
        "INITIAL_IMPORT",
        "BACKFILL",
        "REPAIR",
    }

        # סטטוסים מותרים בסיום sync
    FINAL_SYNC_STATUSES = {
        "success",
        "partial_success",
        "no_change",
        "failed",
    }

    # שדות שה-Agent רשאי לעדכן בעת סיום sync
    SYNC_FINALIZE_FIELDS = {
        "records_inserted",
        "records_updated",
        "years_imported",
        "missing_fields",
        "missing_years",
        "error_message",
        "warning_message",
        "source_details",
    }

    def __init__(self):
        self.company_repository = CompanyRepository()
        self.listing_repository = ListingRepository()
        self.financial_repository = FinancialRepository()
        self.update_log_repository = UpdateLogRepository()
        self.financial_validation_service = FinancialValidationService()

    def _filter_fields(self, data: dict, allowed_fields: tuple):
        # החזרת שדות מאושרים בלבד
        return {
            field: data.get(field)
            for field in allowed_fields
        }

    def _validate_company_id(self, company_id):
        return (
            isinstance(company_id, int)
            and not isinstance(company_id, bool)
            and company_id > 0
        )

    def _validate_fiscal_year(self, fiscal_year):
        return (
            isinstance(fiscal_year, int)
            and not isinstance(fiscal_year, bool)
            and fiscal_year >= 1900
        )

    def get_company_context(self, company_id: int):
        # מידע בסיסי על החברה והרישומים שלה
        if not self._validate_company_id(company_id):
            return {
                "status": "INVALID_REQUEST",
                "error": "Invalid company_id",
            }

        company = self.company_repository.get_by_id(company_id)

        if company is None:
            return {
                "status": "NOT_FOUND",
                "company_id": company_id,
            }

        listings = self.listing_repository.get_by_company_id(
            company_id
        )

        return {
            "status": "OK",
            "company": self._filter_fields(
                company,
                self.COMPANY_READ_FIELDS,
            ),
            "listings": [
                self._filter_fields(
                    listing,
                    self.LISTING_READ_FIELDS,
                )
                for listing in listings
            ]
        }

    def get_financial_coverage(self, company_id: int):
        # אילו שנות כספים כבר קיימות ב-DB
        if not self._validate_company_id(company_id):
            return {
                "status": "INVALID_REQUEST",
                "error": "Invalid company_id",
            }

        company = self.company_repository.get_by_id(company_id)

        if company is None:
            return {
                "status": "NOT_FOUND",
                "company_id": company_id,
            }

        years = self.financial_repository.get_coverage_years(
            company_id
        )

        return {
            "status": "OK",
            "company_id": company_id,
            "years": years,
            "years_count": len(years),
            "earliest_year": years[0] if years else None,
            "latest_year": years[-1] if years else None,
        }

    def get_financial_year(
        self,
        company_id: int,
        fiscal_year: int,
    ):
        # קריאת שנת כספים מסוימת בלבד
        if not self._validate_company_id(company_id):
            return {
                "status": "INVALID_REQUEST",
                "error": "Invalid company_id",
            }

        if not self._validate_fiscal_year(fiscal_year):
            return {
                "status": "INVALID_REQUEST",
                "error": "Invalid fiscal_year",
            }

        company = self.company_repository.get_by_id(company_id)

        if company is None:
            return {
                "status": "NOT_FOUND",
                "company_id": company_id,
            }

        financial_year = self.financial_repository.get_year(
            company_id,
            fiscal_year,
        )

        if financial_year is None:
            return {
                "status": "NOT_FOUND",
                "company_id": company_id,
                "fiscal_year": fiscal_year,
            }

        # שדות DB פנימיים אינם נדרשים ל-Agent
        hidden_fields = {
            "id",
            "created_at",
            "updated_at",
        }

        safe_financial_year = {
            key: value
            for key, value in financial_year.items()
            if key not in hidden_fields
        }

        return {
            "status": "OK",
            "financial_year": safe_financial_year,
        }

    def _validate_sync_context(
        self,
        sync_log_id: int,
        company_id: int,
    ):
        # וידוא שהכתיבה שייכת לתהליך sync פעיל
        if (
            not isinstance(sync_log_id, int)
            or isinstance(sync_log_id, bool)
            or sync_log_id <= 0
        ):
            return {
                "status": "INVALID_REQUEST",
                "error": "Invalid sync_log_id",
            }

        log = self.update_log_repository.get_log(sync_log_id)

        if log is None:
            return {
                "status": "NOT_FOUND",
                "error": "Sync log not found",
            }

        if log.get("company_id") != company_id:
            return {
                "status": "FORBIDDEN",
                "error": "Sync log does not belong to company",
            }

        if log.get("operation_type") != "sync_company":
            return {
                "status": "FORBIDDEN",
                "error": "Invalid sync operation",
            }

        if log.get("status") != "running":
            return {
                "status": "FORBIDDEN",
                "error": "Sync log is not active",
            }

        return {
            "status": "OK",
            "log": log,
        }

    def _validate_company_metadata(self, metadata: dict):
        # בדיקת whitelist וערכי metadata
        if not isinstance(metadata, dict) or not metadata:
            return {
                "status": "INVALID_REQUEST",
                "error": "Metadata must be a non-empty dictionary",
            }

        unknown_fields = sorted(
            set(metadata)
            - self.COMPANY_METADATA_WRITE_FIELDS
        )

        if unknown_fields:
            return {
                "status": "REJECTED",
                "error": "Unauthorized metadata fields",
                "fields": unknown_fields,
            }

        normalized = {}

        if "public_since_date" in metadata:
            value = metadata["public_since_date"]

            if not isinstance(value, str):
                return {
                    "status": "REJECTED",
                    "error": "public_since_date must be ISO date string",
                }

            try:
                parsed_date = date.fromisoformat(value.strip())
            except ValueError:
                return {
                    "status": "REJECTED",
                    "error": "Invalid public_since_date",
                }

            normalized["public_since_date"] = (
                parsed_date.isoformat()
            )

        if "reporting_currency" in metadata:
            value = metadata["reporting_currency"]

            if not isinstance(value, str):
                return {
                    "status": "REJECTED",
                    "error": "reporting_currency must be a string",
                }

            currency = value.strip().upper()

            if (
                len(currency) != 3
                or not currency.isalpha()
            ):
                return {
                    "status": "REJECTED",
                    "error": "Invalid reporting_currency",
                }

            normalized["reporting_currency"] = currency

        return {
            "status": "OK",
            "metadata": normalized,
        }

    def update_company_metadata(
        self,
        sync_log_id: int,
        company_id: int,
        metadata: dict,
    ):
        # עדכון metadata מאושר בלבד במסגרת sync פעיל
        if not self._validate_company_id(company_id):
            return {
                "status": "INVALID_REQUEST",
                "error": "Invalid company_id",
            }

        # בדיקה מקומית לפני כל גישה ל-DB
        validation = self._validate_company_metadata(
            metadata
        )

        if validation["status"] != "OK":
            return validation

        company = self.company_repository.get_by_id(company_id)

        if company is None:
            return {
                "status": "NOT_FOUND",
                "company_id": company_id,
            }

        sync_context = self._validate_sync_context(
            sync_log_id,
            company_id,
        )

        if sync_context["status"] != "OK":
            return sync_context

        updated_company = self.company_repository.update(
            company_id,
            validation["metadata"],
        )

        if updated_company is None:
            return {
                "status": "FAILED",
                "error": "Company metadata update failed",
            }

        return {
            "status": "UPDATED",
            "company_id": company_id,
            "updated_fields": validation["metadata"],
        }

    def submit_financial_year(
        self,
        sync_log_id: int,
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

        # בדיקת החברה
        company = self.company_repository.get_by_id(company_id)

        if company is None:
            return {
                "status": "NOT_FOUND",
                "company_id": company_id,
            }

        # בדיקת sync פעיל ושיוך לחברה
        sync_context = self._validate_sync_context(
            sync_log_id,
            company_id,
        )

        if sync_context["status"] != "OK":
            return sync_context

        sync_log = sync_context["log"]

        # metadata-only workflows אינם מורשים לכתוב financial_yearly
        workflow = sync_log.get("update_scope")

        if workflow not in self.FINANCIAL_WRITE_WORKFLOWS:
            return {
                "status": "FORBIDDEN",
                "error": (
                    "Sync workflow is not allowed "
                    "to write financial data"
                ),
                "workflow": workflow,
            }

        # מותר לכתוב רק שנה שה-Orchestrator ביקש
        years_requested = sync_log.get("years_requested") or []

        if fiscal_year not in years_requested:
            return {
                "status": "FORBIDDEN",
                "error": "Fiscal year was not requested by sync",
                "fiscal_year": fiscal_year,
                "years_requested": years_requested,
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

    def _validate_sync_summary(self, summary: dict):
        # בדיקת שדות הסיכום המותרים
        if not isinstance(summary, dict):
            return {
                "status": "INVALID_REQUEST",
                "error": "summary must be a dictionary",
            }

        unknown_fields = sorted(
            set(summary) - self.SYNC_FINALIZE_FIELDS
        )

        if unknown_fields:
            return {
                "status": "REJECTED",
                "error": "Unauthorized sync summary fields",
                "fields": unknown_fields,
            }

        normalized = dict(summary)

        # ספירות חייבות להיות מספרים שלמים ולא שליליים
        for field in {
            "records_inserted",
            "records_updated",
        }:
            if field not in normalized:
                continue

            value = normalized[field]

            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                return {
                    "status": "REJECTED",
                    "error": f"Invalid {field}",
                }

        # שדות השנים חייבים להכיל שנים תקינות בלבד
        for field in {
            "years_imported",
            "missing_years",
        }:
            if field not in normalized:
                continue

            value = normalized[field]

            if not isinstance(value, list):
                return {
                    "status": "REJECTED",
                    "error": f"{field} must be a list",
                }

            if not all(
                self._validate_fiscal_year(year)
                for year in value
            ):
                return {
                    "status": "REJECTED",
                    "error": f"Invalid year in {field}",
                }

            normalized[field] = sorted(set(value))

        # missing_fields חייב להיות רשימת שמות שדות
        if "missing_fields" in normalized:
            value = normalized["missing_fields"]

            if not isinstance(value, list):
                return {
                    "status": "REJECTED",
                    "error": "missing_fields must be a list",
                }

            if not all(
                isinstance(field, str) and field.strip()
                for field in value
            ):
                return {
                    "status": "REJECTED",
                    "error": "Invalid missing_fields",
                }

            normalized["missing_fields"] = sorted({
                field.strip()
                for field in value
            })

               # provenance נשמר כרשימת מקורות JSON
        if "source_details" in normalized:
            source_details = normalized["source_details"]

            if not isinstance(source_details, list):
                return {
                    "status": "REJECTED",
                    "error": "source_details must be a list",
                }

            if not all(
                isinstance(source, dict)
                for source in source_details
            ):
                return {
                    "status": "REJECTED",
                    "error": (
                        "Each source_details item "
                        "must be a dictionary"
                    ),
                }

        # הודעות יכולות להיות טקסט או NULL
        for field in {
            "error_message",
            "warning_message",
        }:
            if field not in normalized:
                continue

            value = normalized[field]

            if value is not None and not isinstance(value, str):
                return {
                    "status": "REJECTED",
                    "error": f"{field} must be a string or None",
                }

        return {
            "status": "OK",
            "summary": normalized,
        }

    def finalize_sync(
        self,
        sync_log_id: int,
        company_id: int,
        status: str,
        summary: dict,
    ):
        # סיום sync פעיל בלבד
        if not self._validate_company_id(company_id):
            return {
                "status": "INVALID_REQUEST",
                "error": "Invalid company_id",
            }

        if status not in self.FINAL_SYNC_STATUSES:
            return {
                "status": "REJECTED",
                "error": "Invalid final sync status",
            }

        # בדיקה מקומית לפני גישה ל-DB
        summary_validation = self._validate_sync_summary(
            summary
        )

        if summary_validation["status"] != "OK":
            return summary_validation

        # בדיקה שה-log פעיל ושייך לחברה
        sync_context = self._validate_sync_context(
            sync_log_id,
            company_id,
        )

        if sync_context["status"] != "OK":
            return sync_context

        update_fields = dict(
            summary_validation["summary"]
        )
        update_fields["status"] = status

        updated_log = self.update_log_repository.update_log(
            sync_log_id,
            update_fields,
        )

        if updated_log is None:
            return {
                "status": "FAILED",
                "error": "Sync log finalization failed",
            }

        return {
            "status": "FINALIZED",
            "sync_log_id": sync_log_id,
            "company_id": company_id,
            "final_status": status,
        }
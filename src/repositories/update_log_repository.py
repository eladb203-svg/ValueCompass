from datetime import datetime, timezone
from src.db import get_supabase_client


class UpdateLogRepository:

    FINAL_SYNC_STATUSES = {
        "success",
        "partial_success",
        "no_change",
        "failed",
    }

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
        self.client = get_supabase_client()

    def create_log(self, log_data: dict):
        response = (
            self.client.table("data_update_log")
            .insert(log_data)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def get_log(self, log_id: int):
        response = (
            self.client.table("data_update_log")
            .select("*")
            .eq("id", log_id)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def update_log(self, log_id: int, fields: dict):
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()

        response = (
            self.client.table("data_update_log")
            .update(fields)
            .eq("id", log_id)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def _validate_sync_summary(self, summary: dict):
        # בדיקת שדות הסיכום שה-Agent מורשה לעדכן
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

        # שדות שנים חייבים להיות רשימות של שנים תקינות
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

        # missing_fields נשמר כרשימת שמות שדות
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

        # source_details הוא JSON מובנה
        if "source_details" in normalized:
            if not isinstance(
                normalized["source_details"],
                dict,
            ):
                return {
                    "status": "REJECTED",
                    "error": "source_details must be a dictionary",
                }

        # הודעות הן טקסט או NULL
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
        # סיום sync פעיל ועדכון שדות סיכום מאושרים בלבד
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

        summary_validation = self._validate_sync_summary(
            summary
        )

        if summary_validation["status"] != "OK":
            return summary_validation

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

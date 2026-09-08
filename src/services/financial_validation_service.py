from src.models.financials import normalize_financial_year_data

class FinancialValidationService:

    def validate_required_fields(self, financial_data: dict):
        missing_fields = []

        required_fields = {
            "company_id",
            "fiscal_year",
            "source",
        }

        for field in required_fields:
            if financial_data.get(field) is None:
                missing_fields.append(field)

        return sorted(missing_fields)

    def validate_fiscal_year(self, fiscal_year):
        if fiscal_year is None:
            return False

        if not isinstance(fiscal_year, int):
            return False

        if fiscal_year < 1900:
            return False

        return True

    def validate(self, financial_data: dict):
        errors = []
        warnings = []

        # Check required metadata fields
        missing_required_fields = self.validate_required_fields(
            financial_data
        )

        if missing_required_fields:
            errors.append({
                "type": "MISSING_REQUIRED_FIELDS",
                "fields": missing_required_fields,
            })

        # Validate fiscal year
        fiscal_year = financial_data.get("fiscal_year")

        if not self.validate_fiscal_year(fiscal_year):
            errors.append({
                "type": "INVALID_FISCAL_YEAR",
                "value": fiscal_year,
            })

                # Validate financial field data types
        invalid_numeric_fields = self.validate_numeric_fields(
            financial_data
        )

        if invalid_numeric_fields:
            errors.append({
                "type": "INVALID_NUMERIC_FIELDS",
                "fields": invalid_numeric_fields,
            })

        invalid_non_negative_fields = (
            self.validate_non_negative_fields(
                financial_data
            )
        )

        if invalid_non_negative_fields:
            errors.append({
                "type": "INVALID_NEGATIVE_VALUES",
                "fields": invalid_non_negative_fields,
            })

        # Check the balance sheet accounting identity
        balance_sheet_identity = (
            self.validate_balance_sheet_identity(
                financial_data
            )
        )

        zero_share_fields = self.validate_zero_share_counts(
            financial_data
        )

        if zero_share_fields:
            warnings.append({
                "type": "ZERO_SHARE_COUNT",
                "fields": zero_share_fields,
            })


        if balance_sheet_identity is False:
            warnings.append({
                "type": "BALANCE_SHEET_IDENTITY_MISMATCH",
                "message": (
                    "Total assets differ materially from "
                    "total liabilities plus total equity."
                ),
            })

        # Determine final validation status
        if errors:
            status = "REJECTED"
        elif warnings:
            status = "WARNING"
        else:
            status = "VALID"

        return {
            "status": status,
            "errors": errors,
            "warnings": warnings,
        }

    def validate_balance_sheet_identity(
        self,
        financial_data: dict,
        tolerance_ratio: float = 0.01
    ):
        total_assets = financial_data.get("total_assets")
        total_liabilities = financial_data.get("total_liabilities")
        total_equity = financial_data.get("total_equity")

        # The check cannot be performed if one of the values is missing
        if (
            total_assets is None
            or total_liabilities is None
            or total_equity is None
        ):
            return None

        expected_assets = total_liabilities + total_equity
        difference = abs(total_assets - expected_assets)

        # Avoid division by zero
        if total_assets == 0:
            return difference == 0

        difference_ratio = difference / abs(total_assets)

        return difference_ratio <= tolerance_ratio

    def validate_numeric_fields(self, financial_data: dict):
        invalid_fields = []

        metadata_fields = {
            "company_id",
            "fiscal_year",
            "fiscal_year_end_date",
            "filing_date",
            "reporting_currency",
            "source",
        }

        for field, value in financial_data.items():
            if field in metadata_fields:
                continue

            if value is None:
                continue

            if isinstance(value, bool) or not isinstance(
                value,
                (int, float)
            ):
                invalid_fields.append(field)

        return sorted(invalid_fields)

    def validate_non_negative_fields(self, financial_data: dict):
        invalid_fields = []

        non_negative_fields = {
            "total_assets",
            "total_liabilities",
            "total_debt",
            "long_term_debt",
            "cash_and_equivalents",
            "short_term_investments",
            "accounts_receivable",
            "current_assets",
            "current_liabilities",
            "goodwill",
            "intangible_assets",
            "shares_outstanding",
            "weighted_avg_shares_diluted",
        }

        for field in non_negative_fields:
            value = financial_data.get(field)

            if value is None:
                continue

            if value < 0:
                invalid_fields.append(field)

        return sorted(invalid_fields)

    def validate_zero_share_counts(self, financial_data: dict):
        warning_fields = []

        share_fields = {
            "shares_outstanding",
            "weighted_avg_shares_diluted",
        }

        for field in share_fields:
            value = financial_data.get(field)

            if value is None:
                continue

            if value == 0:
                warning_fields.append(field)

        return sorted(warning_fields)

    def normalize_and_validate(
        self,
        company_id: int,
        financial_data: dict
    ):
        normalized_data = normalize_financial_year_data(
            company_id=company_id,
            financial_data=financial_data
        )

        validation = self.validate(normalized_data)

        return {
            "data": normalized_data,
            "validation": validation,
        }

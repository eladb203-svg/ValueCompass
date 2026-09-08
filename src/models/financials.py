# שדות שמגיעים ממקורות פיננסיים
FINANCIAL_SOURCE_FIELDS = {
    "fiscal_year",
    "fiscal_year_end_date",
    "filing_date",
    "reporting_currency",
    "source",

    # Income Statement
    "revenue",
    "gross_profit",
    "operating_income",
    "ebit",
    "ebitda",
    "income_before_tax",
    "income_tax_expense",
    "net_income",
    "eps_diluted",
    "interest_expense",
    "depreciation_and_amortization",

    # Cash Flow
    "operating_cash_flow",
    "capex",
    "stock_based_compensation",
    "dividends_paid",
    "share_repurchases",
    "dividends_per_share",

    # Balance Sheet
    "total_assets",
    "total_liabilities",
    "total_equity",
    "total_debt",
    "long_term_debt",
    "cash_and_equivalents",
    "short_term_investments",
    "accounts_receivable",
    "current_assets",
    "current_liabilities",
    "goodwill",
    "intangible_assets",

    # Share Data
    "shares_outstanding",
    "weighted_avg_shares_diluted",
}


# שדות שמחושבים על ידי ValueCompass
FINANCIAL_CALCULATED_FIELDS = {
    "free_cash_flow",
    "adjusted_free_cash_flow",
}


# שדות הוצאה שנשמרים כמספר חיובי
POSITIVE_MAGNITUDE_FIELDS = {
    "income_tax_expense",
    "interest_expense",
    "depreciation_and_amortization",
    "capex",
    "stock_based_compensation",
    "dividends_paid",
    "share_repurchases",
}


def normalize_financial_year_data(
    company_id: int,
    financial_data: dict
) -> dict:
    # השארת שדות מקור חוקיים בלבד
    normalized = {
        key: value
        for key, value in financial_data.items()
        if key in FINANCIAL_SOURCE_FIELDS
    }

    # קישור הרשומה לחברה הקנונית
    normalized["company_id"] = company_id

    # נרמול שנת כספים
    if normalized.get("fiscal_year") is not None:
        normalized["fiscal_year"] = int(
            normalized["fiscal_year"]
        )

    # נרמול מטבע דיווח
    if normalized.get("reporting_currency"):
        normalized["reporting_currency"] = (
            normalized["reporting_currency"]
            .strip()
            .upper()
        )

    # נרמול שם המקור
    if normalized.get("source"):
        normalized["source"] = (
            normalized["source"].strip()
        )

    # הפיכת הוצאות למגניטודה חיובית
    for field in POSITIVE_MAGNITUDE_FIELDS:
        value = normalized.get(field)

        if value is not None:
            normalized[field] = abs(value)

    return normalized
def _positive_amount(value):
    # המרת תזרים שלילי להוצאה חיובית
    if value is None:
        return None

    return abs(value)


def map_fmp_statements_to_financial_year(
    company_id: int,
    income_statement: dict,
    balance_sheet: dict,
    cash_flow: dict
) -> dict:
    # חילוץ שנת הדוח
    fiscal_year = int(income_statement["fiscalYear"])

    # חישוב FCF מתואם לאחר SBC
    free_cash_flow = cash_flow.get("freeCashFlow")
    stock_based_compensation = cash_flow.get("stockBasedCompensation")

    adjusted_free_cash_flow = None

    if free_cash_flow is not None and stock_based_compensation is not None:
        adjusted_free_cash_flow = (
            free_cash_flow - stock_based_compensation
        )

    # בניית רשומה אחת לפי מבנה financial_yearly
    return {
        "company_id": company_id,
        "fiscal_year": fiscal_year,

        "fiscal_year_end_date": income_statement.get("date"),
        "filing_date": income_statement.get("filingDate"),

        # Income Statement
        "revenue": income_statement.get("revenue"),
        "gross_profit": income_statement.get("grossProfit"),
        "operating_income": income_statement.get("operatingIncome"),
        "ebit": income_statement.get("ebit"),
        "ebitda": income_statement.get("ebitda"),
        "income_before_tax": income_statement.get("incomeBeforeTax"),
        "income_tax_expense": income_statement.get("incomeTaxExpense"),
        "net_income": income_statement.get("netIncome"),
        "eps_diluted": income_statement.get("epsDiluted"),
        "interest_expense": income_statement.get("interestExpense"),
        "depreciation_and_amortization": income_statement.get(
            "depreciationAndAmortization"
        ),

        # Cash Flow
        "operating_cash_flow": cash_flow.get("operatingCashFlow"),
        "capex": _positive_amount(
            cash_flow.get("capitalExpenditure")
        ),
        "free_cash_flow": free_cash_flow,
        "stock_based_compensation": stock_based_compensation,
        "adjusted_free_cash_flow": adjusted_free_cash_flow,
        "dividends_paid": _positive_amount(
            cash_flow.get("netDividendsPaid")
        ),
        "share_repurchases": _positive_amount(
            cash_flow.get("commonStockRepurchased")
        ),

        # עדיין אין מקור ישיר
        "dividends_per_share": None,

        # Balance Sheet
        "total_assets": balance_sheet.get("totalAssets"),
        "total_liabilities": balance_sheet.get("totalLiabilities"),
        "total_equity": balance_sheet.get("totalEquity"),
        "total_debt": balance_sheet.get("totalDebt"),
        "long_term_debt": balance_sheet.get("longTermDebt"),
        "cash_and_equivalents": balance_sheet.get(
            "cashAndCashEquivalents"
        ),
        "short_term_investments": balance_sheet.get(
            "shortTermInvestments"
        ),
        "accounts_receivable": balance_sheet.get(
            "accountsReceivables"
        ),
        "current_assets": balance_sheet.get("totalCurrentAssets"),
        "current_liabilities": balance_sheet.get(
            "totalCurrentLiabilities"
        ),
        "goodwill": balance_sheet.get("goodwill"),
        "intangible_assets": balance_sheet.get("intangibleAssets"),

        # עדיין אין מקור ישיר
        "shares_outstanding": None,

        "weighted_avg_shares_diluted": income_statement.get(
            "weightedAverageShsOutDil"
        ),

        "source": "FMP",
    }
def map_fmp_statements_to_financial_years(
    company_id: int,
    income_statements: list,
    balance_sheets: list,
    cash_flows: list
) -> list:
    # יצירת אינדקס לפי שנת כספים
    income_by_year = {
        str(item["fiscalYear"]): item
        for item in income_statements
        if item.get("fiscalYear")
    }

    balance_by_year = {
        str(item["fiscalYear"]): item
        for item in balance_sheets
        if item.get("fiscalYear")
    }

    cash_flow_by_year = {
        str(item["fiscalYear"]): item
        for item in cash_flows
        if item.get("fiscalYear")
    }

    # מציאת השנים שקיימות בשלושת הדוחות
    common_years = (
        set(income_by_year)
        & set(balance_by_year)
        & set(cash_flow_by_year)
    )

    financial_years = []

    # בניית רשומה מלאה לכל שנה
    for fiscal_year in sorted(common_years, reverse=True):
        financial_year = map_fmp_statements_to_financial_year(
            company_id=company_id,
            income_statement=income_by_year[fiscal_year],
            balance_sheet=balance_by_year[fiscal_year],
            cash_flow=cash_flow_by_year[fiscal_year]
        )

        financial_years.append(financial_year)

    return financial_years

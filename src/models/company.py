COMPANY_FIELDS = {
    "company_name",
    "country",
    "reporting_currency",
    "sector",
    "industry",
    "public_since_date",
    "data_source",
    "is_active",
}


LISTING_FIELDS = {
    "company_id",
    "symbol",
    "exchange",
    "mic",
    "trading_currency",
    "security_type",
    "share_class",
    "is_adr",
    "adr_ratio",
    "isin",
    "figi",
    "share_class_figi",
    "is_primary",
    "listing_start_date",
    "data_source",
    "is_active",
}


def normalize_company_data(company_data: dict) -> dict:
    # השארת שדות חוקיים בלבד עבור canonical company
    normalized = {
        key: value
        for key, value in company_data.items()
        if key in COMPANY_FIELDS
    }

    # ניקוי שם החברה
    if normalized.get("company_name"):
        normalized["company_name"] = normalized["company_name"].strip()

    # נרמול קודים ומטבע
    for field in ("country", "reporting_currency"):
        if normalized.get(field):
            normalized[field] = normalized[field].strip().upper()

    return normalized


def normalize_listing_data(listing_data: dict) -> dict:
    # השארת שדות חוקיים בלבד עבור listing
    normalized = {
        key: value
        for key, value in listing_data.items()
        if key in LISTING_FIELDS
    }

    # נרמול מזהי רישום
    for field in (
        "symbol",
        "exchange",
        "mic",
        "trading_currency",
        "isin",
        "figi",
        "share_class_figi",
    ):
        if normalized.get(field):
            normalized[field] = normalized[field].strip().upper()

    return normalized
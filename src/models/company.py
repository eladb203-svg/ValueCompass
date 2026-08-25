def map_fmp_profile_to_company(profile: dict) -> dict:
    return {
        "symbol": profile.get("symbol"),
        "company_name": profile.get("companyName"),
        "exchange": profile.get("exchange"),
        "country": profile.get("country"),
        "currency": profile.get("currency"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "data_source": "FMP",
        "is_active": profile.get("isActivelyTrading", True),
    }
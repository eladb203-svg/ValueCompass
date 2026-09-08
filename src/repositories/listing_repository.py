from datetime import datetime, timezone

from src.db import get_supabase_client


class ListingRepository:
    def __init__(self):
        # יצירת חיבור ל-Supabase
        self.client = get_supabase_client()

    def get_by_symbol_exchange(self, symbol: str, exchange: str):
        # נרמול הסימול והבורסה
        symbol = symbol.strip().upper()
        exchange = exchange.strip().upper()

        # חיפוש רישום פעיל לפי סימול ובורסה
        response = (
            self.client
            .table("company_listings")
            .select("*")
            .eq("symbol", symbol)
            .eq("exchange", exchange)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def get_by_symbol_mic(self, symbol: str, mic: str):
        # נרמול הסימול וקוד ה-MIC
        symbol = symbol.strip().upper()
        mic = mic.strip().upper()

        # חיפוש רישום פעיל לפי סימול ו-MIC
        response = (
            self.client
            .table("company_listings")
            .select("*")
            .eq("symbol", symbol)
            .eq("mic", mic)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def get_by_symbol(self, symbol: str):
        # חיפוש כל הרישומים הפעילים עם אותו סימול
        symbol = symbol.strip().upper()

        response = (
            self.client
            .table("company_listings")
            .select("*")
            .eq("symbol", symbol)
            .eq("is_active", True)
            .execute()
        )

        return response.data

    def get_by_isin(self, isin: str):
        # חיפוש רישומים לפי ISIN
        isin = isin.strip().upper()

        response = (
            self.client
            .table("company_listings")
            .select("*")
            .eq("isin", isin)
            .eq("is_active", True)
            .execute()
        )

        return response.data

    def get_by_figi(self, figi: str):
        # חיפוש רישומים לפי FIGI
        figi = figi.strip().upper()

        response = (
            self.client
            .table("company_listings")
            .select("*")
            .eq("figi", figi)
            .eq("is_active", True)
            .execute()
        )

        return response.data

    def get_by_company_id(self, company_id: int):
        # החזרת כל הרישומים של חברה
        response = (
            self.client
            .table("company_listings")
            .select("*")
            .eq("company_id", company_id)
            .execute()
        )

        return response.data

    def get_primary_by_company_id(self, company_id: int):
        # חיפוש הרישום הראשי הפעיל של החברה
        response = (
            self.client
            .table("company_listings")
            .select("*")
            .eq("company_id", company_id)
            .eq("is_primary", True)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    def insert(self, listing_data: dict):
        # הכנסת רישום חדש
        response = (
            self.client
            .table("company_listings")
            .insert(listing_data)
            .execute()
        )

        return response.data[0]

    def update(self, listing_id: int, listing_data: dict):
        # עדכון זמן השינוי האחרון
        listing_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        # עדכון רישום קיים
        response = (
            self.client
            .table("company_listings")
            .update(listing_data)
            .eq("id", listing_id)
            .execute()
        )

        return response.data[0]
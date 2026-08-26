from src.clients.fmp_client import FMPClient
from src.models.company import map_fmp_profile_to_company
from src.repositories.company_repository import CompanyRepository


class StockImportService:
    def __init__(self):
        # יצירת החיבורים לשכבות החיצוניות
        self.fmp_client = FMPClient()
        self.company_repository = CompanyRepository()

    def ensure_company_exists(self, symbol: str):
        # נרמול סימול המניה
        symbol = symbol.strip().upper()

        # משיכת פרופיל החברה מ-FMP
        profiles = self.fmp_client.get_company_profile(symbol)

        # בדיקה שהתקבל פרופיל תקין
        if not profiles:
            raise ValueError(f"No company profile found for symbol: {symbol}")

        # FMP מחזיר רשימה, לכן לוקחים את הרשומה הראשונה
        profile = profiles[0]

        # מיפוי פרופיל FMP למבנה של טבלת companies
        company_data = map_fmp_profile_to_company(profile)

        # יצירה או עדכון של החברה וקבלת הרשומה מה-DB
        company = self.company_repository.upsert_company(company_data)

        return company

    def import_company(self, symbol: str):
        # בשלב זה הייבוא כולל רק וידוא שהחברה קיימת
        company = self.ensure_company_exists(symbol)

        return company
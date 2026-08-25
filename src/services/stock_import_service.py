from src.clients.fmp_client import FMPClient
from src.models.company import map_fmp_profile_to_company
from src.repositories.company_repository import CompanyRepository


class StockImportService:
    def __init__(self):
        # יצירת החיבורים לשכבות החיצוניות
        self.fmp_client = FMPClient()
        self.company_repository = CompanyRepository()

    def import_company(self, symbol: str):
        # נרמול הסימול
        symbol = symbol.strip().upper()

        # משיכת פרופיל החברה מ-FMP
        profiles = self.fmp_client.get_company_profile(symbol)

        # בדיקה שהתקבל מידע
        if not profiles:
            raise ValueError(f"No company profile found for symbol: {symbol}")

        # FMP מחזיר רשימה, לכן לוקחים את הרשומה הראשונה
        profile = profiles[0]

        # מיפוי מבנה FMP למבנה של טבלת companies
        company_data = map_fmp_profile_to_company(profile)

        # שמירה או עדכון של החברה ב-DB
        saved_company = self.company_repository.upsert_company(company_data)

        return saved_company
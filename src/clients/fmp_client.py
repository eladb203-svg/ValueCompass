import requests

from src.config import FMP_API_KEY


class FMPClient:
    BASE_URL = "https://financialmodelingprep.com/stable"

    def __init__(self):
        if not FMP_API_KEY:
            raise ValueError("FMP_API_KEY is missing from .env")

        self.api_key = FMP_API_KEY

    def get_company_profile(self, symbol):
        symbol = symbol.strip().upper()

        url = f"{self.BASE_URL}/profile"
        params = {
            "symbol": symbol,
            "apikey": self.api_key
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        return response.json()

    def get_income_statements(self, symbol, limit=10):
        # נרמול סימול המניה
        symbol = symbol.strip().upper()

        # משיכת דוחות רווח והפסד שנתיים
        url = f"{self.BASE_URL}/income-statement"
        params = {
            "symbol": symbol,
            "period": "annual",
            "limit": limit,
            "apikey": self.api_key
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        return response.json()

    def get_balance_sheet_statements(self, symbol, limit=10):
        # נרמול סימול המניה
        symbol = symbol.strip().upper()

        # משיכת מאזנים שנתיים
        url = f"{self.BASE_URL}/balance-sheet-statement"
        params = {
            "symbol": symbol,
            "period": "annual",
            "limit": limit,
            "apikey": self.api_key
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        return response.json()

    def get_cash_flow_statements(self, symbol, limit=10):
        # נרמול סימול המניה
        symbol = symbol.strip().upper()

        # משיכת דוחות תזרים מזומנים שנתיים
        url = f"{self.BASE_URL}/cash-flow-statement"
        params = {
            "symbol": symbol,
            "period": "annual",
            "limit": limit,
            "apikey": self.api_key
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        return response.json()        
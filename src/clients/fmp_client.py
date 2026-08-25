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
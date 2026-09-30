from src.clients.tavily_client import TavilySearchClient


class WebAccessService:
    def __init__(self):
        # ספק החיפוש הנוכחי של ValueCompass
        self.search_client = TavilySearchClient()

    def search_web(
        self,
        query: str,
        include_domains: list[str] | None = None,
        max_results: int = 5,
    ) -> dict:
        # שכבה כללית שמפרידה בין הסוכן לבין ספק החיפוש
        return self.search_client.search(
            query=query,
            include_domains=include_domains,
            max_results=max_results,
        )

    def extract_web_page(
        self,
        url: str,
        query: str | None = None,
    ) -> dict:
        # קריאת תוכן ממקור שכבר נבחר
        return self.search_client.extract(
            url=url,
            query=query,
        )
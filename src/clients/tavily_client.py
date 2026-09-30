from tavily import TavilyClient

from src.config import TAVILY_API_KEY


class TavilySearchClient:
    def __init__(self):
        # מוודא שמפתח ה-API קיים לפני ניסיון חיבור
        if not TAVILY_API_KEY:
            raise RuntimeError(
                "TAVILY_API_KEY is not configured"
            )

        # לקוח רשמי של Tavily
        self.client = TavilyClient(
            api_key=TAVILY_API_KEY
        )

    def search(
        self,
        query: str,
        include_domains: list[str] | None = None,
        max_results: int = 5,
    ) -> dict:
        # בדיקת קלט בסיסית לפני שליחת בקשה חיצונית
        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "Search query must be a non-empty string"
            )

        search_params = {
            "query": query.strip(),
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        # מגביל את החיפוש לדומיינים מסוימים רק כשנדרש
        if include_domains:
            search_params["include_domains"] = include_domains

        response = self.client.search(**search_params)

        # מנרמל את תשובת Tavily למבנה קבוע של ValueCompass
        results = []

        for result in response.get("results", []):
            results.append({
                "title": result.get("title"),
                "url": result.get("url"),
                "content": result.get("content"),
                "score": result.get("score"),
            })

        return {
            "query": query.strip(),
            "results": results,
        }

    def extract(
        self,
        url: str,
        query: str | None = None,
    ) -> dict:
        # כתובת תקינה נדרשת לפני פנייה לשירות חיצוני
        if not isinstance(url, str) or not url.strip():
            raise ValueError(
                "URL must be a non-empty string"
            )

        extract_params = {
            "urls": url.strip(),
            "extract_depth": "advanced",
            "format": "markdown",
            "include_images": False,
        }

        # בדוח ארוך אפשר לבקש רק קטעים שרלוונטיים למשימה
        if query:
            extract_params["query"] = query.strip()
            extract_params["chunks_per_source"] = 5

        response = self.client.extract(**extract_params)

        results = []

        for result in response.get("results", []):
            results.append({
                "url": result.get("url"),
                "content": result.get("raw_content"),
            })

        return {
            "results": results,
            "failed_results": response.get(
                "failed_results",
                [],
            ),
        }
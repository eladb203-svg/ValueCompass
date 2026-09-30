import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.services.web_access_service import WebAccessService


# טעינת משתני הסביבה
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
model_name = os.getenv("GEMINI_MODEL")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY was not found in .env")

if not model_name:
    raise RuntimeError("GEMINI_MODEL was not found in .env")


# טעינת ה-Financial Data ETL Skill
project_root = Path(__file__).resolve().parent.parent

skill_path = (
    project_root
    / ".agents"
    / "skills"
    / "financial-data-etl"
    / "SKILL.md"
)

skill_text = skill_path.read_text(encoding="utf-8")


# יצירת שכבת הגישה הכללית לאינטרנט
web_access = WebAccessService()


def search_web(
    query: str,
    include_domains: list[str] | None = None,
    max_results: int = 5,
) -> dict:
    """Search the web for sources relevant to a ValueCompass ETL task.

    Args:
        query: The search query.
        include_domains: Optional domains to restrict the search to.
        max_results: Maximum number of search results.

    Returns:
        Search results containing titles, URLs, relevant content,
        and relevance scores.
    """

    print(
        f"[TOOL] search_web called: {query}",
        flush=True,
    )

    return web_access.search_web(
        query=query,
        include_domains=include_domains,
        max_results=max_results,
    )


# יצירת לקוח Gemini
client = genai.Client(
    api_key=api_key,
    http_options=types.HttpOptions(
        timeout=180000,
        retry_options=types.HttpRetryOptions(
            attempts=3,
            initial_delay=2.0,
            max_delay=10.0,
            exp_base=2.0,
            jitter=1.0,
        ),
    ),
)


# יצירת שיחת Agent עם ה-Skill וכלי החיפוש
chat = client.chats.create(
    model=model_name,
    config=types.GenerateContentConfig(
        system_instruction=skill_text,
        temperature=0.1,
        thinking_config=types.ThinkingConfig(
            thinking_level="low",
        ),
        tools=[search_web],
    ),
)


print("[TEST] Asking Gemini to research Microsoft...", flush=True)

response = chat.send_message(
    """
    You are executing a ValueCompass metadata research task.

    Company:
    Microsoft Corporation

    Required field:
    public_since_date

    Use the approved search_web tool.
    Follow the Financial Data ETL Skill source hierarchy.

    Prefer an official or authoritative source.
    Do not rely on your internal knowledge for the date.
    Do not invent or estimate missing information.

    Return:
    1. public_since_date in YYYY-MM-DD format
    2. source name
    3. source URL
    4. short reasoning for why the source is appropriate

    Do not write anything to the ValueCompass database.
    """
)

print("\nGemini response:")
print(response.text)
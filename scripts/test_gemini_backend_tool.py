import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.capabilities.financial_etl_capabilities import (
    FinancialETLCapabilities,
)


# טוען את משתני הסביבה
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
model_name = os.getenv("GEMINI_MODEL")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY was not found in .env")

if not model_name:
    raise RuntimeError("GEMINI_MODEL was not found in .env")


# טוען את ה-Skill
project_root = Path(__file__).resolve().parent.parent
skill_path = (
    project_root
    / ".agents"
    / "skills"
    / "financial-data-etl"
    / "SKILL.md"
)

skill_text = skill_path.read_text(encoding="utf-8")


# יוצר את שכבת היכולות שכבר מחוברת ל-Backend
capabilities = FinancialETLCapabilities()


def get_company_context(company_id: int) -> dict:
    """Read an existing ValueCompass company and its listings.

    Args:
        company_id: The canonical ValueCompass company ID.

    Returns:
        The approved company and listing context returned by the
        ValueCompass Financial ETL backend.
    """
    print(f"[TOOL] get_company_context called with company_id={company_id}")

    return capabilities.get_company_context(company_id)


# יוצר לקוח Gemini
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


# יוצר Agent עם ה-Skill ועם כלי קריאה אחד בלבד
chat = client.chats.create(
    model=model_name,
    config=types.GenerateContentConfig(
        system_instruction=skill_text,
        temperature=0.1,
        thinking_config=types.ThinkingConfig(
            thinking_level="low",
        ),
        tools=[get_company_context],
    ),
)


response = chat.send_message(
    """
    Use the approved ValueCompass backend tool to inspect company_id 1.

    Do not use external sources.

    Tell me:
    1. the company name;
    2. its primary ticker;
    3. its exchange;
    4. its reporting currency.

    You must obtain the company information through the backend tool.
    """
)

print("\nGemini response:")
print(response.text)
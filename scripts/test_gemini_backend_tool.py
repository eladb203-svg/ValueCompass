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

def get_financial_coverage(company_id: int) -> dict:
    """Read the existing annual financial-data coverage for a company.

    Args:
        company_id: The canonical ValueCompass company ID.

    Returns:
        The fiscal years currently stored for the company in ValueCompass.
    """
    print(
        f"[TOOL] get_financial_coverage called with company_id={company_id}",
        flush=True,
    )

    return capabilities.get_financial_coverage(company_id)
    
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
        tools=[
    get_company_context,
    get_financial_coverage,
    ],
    ),
)


response = chat.send_message(
    """
Inspect company_id 1 using the approved ValueCompass backend tools.

Determine:
1. which company this is;
2. which fiscal years are currently stored in ValueCompass;
3. how many financial years are stored;
4. based only on the backend state and the Financial Data ETL Skill,
   whether this company requires an Initial Import, Backfill/Repair,
   Incremental Update, or no financial-data work.

Do not use external sources.
"""
)

print("\nGemini response:")
print(response.text)


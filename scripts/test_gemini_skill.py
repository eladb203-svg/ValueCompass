import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
import random
import time

from google.genai.errors import ServerError

# טוען הגדרות מקובץ .env
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
model_name = os.getenv("GEMINI_MODEL")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY was not found in .env")

if not model_name:
    raise RuntimeError("GEMINI_MODEL was not found in .env")


# נתיב לקובץ ה-Skill
project_root = Path(__file__).resolve().parent.parent
skill_path = (
    project_root
    / ".agents"
    / "skills"
    / "financial-data-etl"
    / "SKILL.md"
)

if not skill_path.exists():
    raise FileNotFoundError(f"Skill file not found: {skill_path}")


# קורא את הוראות ה-Skill
skill_text = skill_path.read_text(encoding="utf-8")

print(f"Skill loaded successfully: {len(skill_text)} characters")


# יוצר לקוח Gemini
client = genai.Client(api_key=api_key)


# יוצר שיחה שבה ה-Skill הוא הוראת המערכת
chat = client.chats.create(
    model=model_name,
    config=types.GenerateContentConfig(
        system_instruction=skill_text,
        temperature=0.1,
    ),
)


# בדיקה שהמודל הבין את תפקידו
test_message = """
Do not access external sources and do not perform any database operation.

Based only on your system instructions, briefly state:
1. your primary entry point;
2. whether you may execute arbitrary SQL;
3. how many fiscal years Initial Import targets;
4. what you must do when a financial value cannot be reliably determined.
"""

max_attempts = 3

for attempt in range(1, max_attempts + 1):
    try:
        print(f"Gemini request attempt {attempt}/{max_attempts}...")

        response = chat.send_message(test_message)

        print("\nGemini response:")
        print(response.text)
        break

    except ServerError as error:
        if error.code != 503:
            raise

        if attempt == max_attempts:
            print(
                "\nGemini is still unavailable after the allowed retries. "
                "Please try again later."
            )
            raise

        delay = (10 * (2 ** (attempt - 1))) + random.uniform(0, 3)

        print(
            f"Gemini returned 503 (temporary overload). "
            f"Retrying in {delay:.1f} seconds..."
        )

        time.sleep(delay)
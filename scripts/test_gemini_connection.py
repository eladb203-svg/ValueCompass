import os

from dotenv import load_dotenv
from google import genai


# טוען את משתני הסביבה מקובץ .env
load_dotenv()

# קורא את מפתח Gemini בלי לכתוב אותו בקוד
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY was not found in .env")

# יוצר לקוח שמתקשר עם Gemini API
client = genai.Client(api_key=api_key)

# שולח בקשת בדיקה פשוטה
response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents="Reply with exactly: VALUECOMPASS_GEMINI_OK",
)

print(response.text)
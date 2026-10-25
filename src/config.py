import os
from dotenv import load_dotenv

load_dotenv()

# Production project (ValueInvestConsult). Never written by the K6a code unless VC_DB_TARGET=prod is set explicitly.
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
# Test project (valuecompass-test): its own URL and service-role key, kept only in .env (never printed, never in another file).
SUPABASE_TEST_URL = os.getenv("SUPABASE_TEST_URL")
SUPABASE_TEST_SECRET_KEY = os.getenv("SUPABASE_TEST_SECRET_KEY")
PROJECT_REFS = {"test": "wbhxjcegoobkbnjnuise", "prod": "zwpftrjryxyymrxsprqh"}
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")

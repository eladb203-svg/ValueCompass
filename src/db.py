from supabase import create_client, Client

from src.config import SUPABASE_URL, SUPABASE_SECRET_KEY


def get_supabase_client() -> Client:
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL is missing from .env")

    if not SUPABASE_SECRET_KEY:
        raise ValueError("SUPABASE_SECRET_KEY is missing from .env")

    return create_client(
        SUPABASE_URL,
        SUPABASE_SECRET_KEY
    )
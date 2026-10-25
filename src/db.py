"""Supabase connection (K6a). The target project is chosen by ``VC_DB_TARGET`` = ``test`` | ``prod`` (default: test).

Keys come only from .env and are never printed or logged: an error names the missing variable, not a value. A URL that does not belong to the chosen target
(wrong project ref) is refused, so a production key can never be used as a test connection by mistake.
"""
import os

from supabase import Client, create_client

from src import config

VARS = {"test": ("SUPABASE_TEST_URL", "SUPABASE_TEST_SECRET_KEY"), "prod": ("SUPABASE_URL", "SUPABASE_SECRET_KEY")}


def db_target() -> str:
    t = (os.environ.get("VC_DB_TARGET") or "test").strip().lower()
    if t not in VARS:
        raise ValueError(f"VC_DB_TARGET must be 'test' or 'prod', got {t!r}")
    return t


def credentials(target: str = None) -> tuple:
    """-> (url, key) of the target project. Raises ValueError (naming the variable only) when missing or when the URL is another project's."""
    target = target or db_target()
    url_var, key_var = VARS[target]
    url, key = getattr(config, url_var), getattr(config, key_var)
    if not url:
        raise ValueError(f"{url_var} is missing from .env (target {target})")
    if not key:
        raise ValueError(f"{key_var} is missing from .env (target {target})")
    if config.PROJECT_REFS[target] not in url:
        raise ValueError(f"{url_var} is not the {target} project ({config.PROJECT_REFS[target]})")
    return url, key


def get_supabase_client(target: str = None) -> Client:
    url, key = credentials(target)
    return create_client(url, key)

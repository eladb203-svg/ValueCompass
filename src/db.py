"""Supabase connection (K6a). The target project is chosen by ``VC_DB_TARGET`` = ``test`` | ``prod`` (default: test).

Keys come only from .env and are never printed or logged: an error names the missing variable, not a value. A URL that does not belong to the chosen target
(wrong project ref) is refused, so a production key can never be used as a test connection by mistake.
"""
import os

import httpx
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from src import config
from src.net import RetryTransport

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
    """The client retries a failed connection with a gradual wait (30, 60, 120, 120 s; five attempts - ``src/net.py``) before it raises."""
    url, key = credentials(target)
    http = httpx.Client(transport=RetryTransport(), timeout=httpx.Timeout(120.0, connect=30.0), follow_redirects=True)
    return create_client(url, key, options=SyncClientOptions(httpx_client=http))

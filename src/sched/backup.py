"""Weekly backup of the production data (security spec 10): ``pg_dump --data-only`` to ``backups/`` on this PC (outside git), the last 4 copies are kept.

Off by default: it runs only when ``SUPABASE_PROD_DB_URL`` (the production connection string) is in ``.env``. It rides on the weekly cleanup job, so the scheduler has no new job.
The schema is in git (migrations); the dump holds the data of the ``public`` and ``auth`` schemas (the auth users are needed for the foreign keys on restore).
The connection string is passed to ``pg_dump`` in the environment, never on the command line, and never written to the log.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
BACKUPS_DIR = ROOT / "backups"
KEEP = 4
PREFIX = "vc_prod_data_"


def prune(directory: Path, keep: int = KEEP) -> list:
    """Deletes the oldest dumps, keeps the newest ``keep`` (names carry the timestamp). -> the deleted names."""
    files = sorted(directory.glob(PREFIX + "*.dump"))
    gone = files[:-keep] if keep > 0 else files
    for f in gone:
        f.unlink()
    return [f.name for f in gone]


def pg_env(url: str, base: dict) -> dict:
    """The connection string as PG* variables, so the password is not on the command line."""
    u = urlparse(url)
    return {**base, "PGHOST": u.hostname or "", "PGPORT": str(u.port or 5432), "PGUSER": unquote(u.username or ""), "PGPASSWORD": unquote(u.password or ""), "PGDATABASE": (u.path or "/postgres").lstrip("/") or "postgres"}


def run_weekly_backup(now: datetime, directory: Path = BACKUPS_DIR, env: Optional[dict] = None, which: Callable = shutil.which, run: Callable = subprocess.run, keep: int = KEEP) -> dict:
    """-> {"status": "disabled" | "no_pg_dump" | "failed" | "success", ...}. Never raises: a failed backup must not stop the cleanup job."""
    env = dict(os.environ if env is None else env)
    url = env.get("SUPABASE_PROD_DB_URL")
    if not url:
        return {"status": "disabled", "reason": "SUPABASE_PROD_DB_URL is not set"}
    exe = which("pg_dump")
    if not exe:
        return {"status": "no_pg_dump", "reason": "pg_dump is not installed on this PC"}
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{PREFIX}{now.strftime('%Y%m%d_%H%M%S')}.dump"
        proc = run([exe, "--data-only", "--format=custom", "--schema=public", "--schema=auth", "--no-owner", "--file", str(target)],
                   env=pg_env(url, env), capture_output=True, text=True, timeout=3600, check=False)
        if proc.returncode != 0 or not target.exists() or target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            return {"status": "failed", "error": (proc.stderr or "")[:300]}
        return {"status": "success", "file": target.name, "bytes": target.stat().st_size, "pruned": prune(directory, keep)}
    except Exception as e:                                             # noqa: BLE001 - the job must go on
        return {"status": "failed", "error": str(e)[:300]}

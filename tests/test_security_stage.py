"""Security stage (spec 7 and 10): no key in a file that git holds; the weekly backup job and its keep-4 rule; the retention hook of the cleanup job."""
from __future__ import annotations

import base64
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from src.sched.backup import PREFIX, prune, run_weekly_backup

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "supabase secret key": re.compile(r"sb_secret_[A-Za-z0-9_\-]{16,}"),
    "gemini key": re.compile(r"AIza[0-9A-Za-z_\-]{35}|AQ\.[A-Za-z0-9_\-]{30,}"),
    "tavily key": re.compile(r"tvly-[A-Za-z0-9\-]{16,}"),
    "resend key": re.compile(r"\bre_[A-Za-z0-9]{20,}"),
    "azure translator key": re.compile(r"AZURE_TRANSLATOR_KEY\s*[=:]\s*['\"]?[A-Za-z0-9]{20,}"),
    "key assignment": re.compile(r"(?i)(?:api_?key|secret_?key|service_?role_?key|db_url)\s*[=:]\s*['\"][A-Za-z0-9_\-/+=.:@]{24,}['\"]"),
    "postgres url with password": re.compile(r"postgres(?:ql)?://[^:\s/]+:[^@\s]{4,}@"),
}
JWT = re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.(eyJ[A-Za-z0-9_\-]{10,})\.[A-Za-z0-9_\-]{10,}")
SKIP_SUFFIX = (".docx", ".png", ".jpg", ".pdf", ".xlsx", ".dump", ".parquet", ".gz", ".zip")


def _files() -> list:
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    return [ROOT / f for f in out if not f.endswith(SKIP_SUFFIX) and (ROOT / f).is_file()]


def test_no_key_pattern_in_a_file_git_holds():
    hits = []
    for f in _files():
        if f.name == "test_security_stage.py":
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for name, rx in PATTERNS.items():
            if rx.search(text):
                hits.append((f.relative_to(ROOT).as_posix(), name))
        for m in JWT.finditer(text):                                         # a JWT is allowed only when it is the publishable (anon) key, never service_role
            try:
                payload = json.loads(base64.urlsafe_b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4)))
            except Exception:
                continue
            if payload.get("role") not in (None, "anon"):
                hits.append((f.relative_to(ROOT).as_posix(), f"jwt role {payload.get('role')}"))
    assert not hits, f"key pattern in tracked files: {hits}"


def test_env_is_ignored_and_example_has_no_values():
    ignored = subprocess.run(["git", "check-ignore", ".env"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    assert ignored == ".env"
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            assert line.split("=", 1)[1].strip() == "", line


def test_backups_dir_is_outside_git():
    assert subprocess.run(["git", "check-ignore", "backups/x.dump"], cwd=ROOT, capture_output=True, text=True).stdout.strip() == "backups/x.dump"


NOW = datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc)


def test_backup_is_off_without_the_connection_string(tmp_path):
    assert run_weekly_backup(NOW, tmp_path, env={})["status"] == "disabled"
    assert list(tmp_path.iterdir()) == []


def test_backup_reports_a_missing_pg_dump(tmp_path):
    r = run_weekly_backup(NOW, tmp_path, env={"SUPABASE_PROD_DB_URL": "postgresql://u:p@h:5432/d"}, which=lambda _: None)
    assert r["status"] == "no_pg_dump"


def test_backup_runs_pg_dump_data_only_without_the_password_on_the_command_line_and_keeps_four(tmp_path):
    for i in range(1, 6):
        (tmp_path / f"{PREFIX}2026100{i}_040000.dump").write_text("old")
    calls = []

    def fake_run(cmd, env=None, **kw):
        calls.append((cmd, env))
        Path(cmd[cmd.index("--file") + 1]).write_text("data")
        return SimpleNamespace(returncode=0, stderr="")

    r = run_weekly_backup(NOW, tmp_path, env={"SUPABASE_PROD_DB_URL": "postgresql://postgres.abc:s3cret%21@db.example.co:5432/postgres"}, which=lambda _: "pg_dump", run=fake_run)
    cmd, env = calls[0]
    assert r["status"] == "success" and "--data-only" in cmd
    assert not any("s3cret" in c for c in cmd) and env["PGPASSWORD"] == "s3cret!" and env["PGHOST"] == "db.example.co" and env["PGUSER"] == "postgres.abc"
    assert len(list(tmp_path.glob(PREFIX + "*.dump"))) == 4 and f"{PREFIX}20261101_040000.dump" in [p.name for p in tmp_path.iterdir()]


def test_a_failed_dump_leaves_no_file_and_does_not_raise(tmp_path):
    def bad(cmd, **kw):
        Path(cmd[cmd.index("--file") + 1]).write_text("")
        return SimpleNamespace(returncode=1, stderr="connection refused")

    r = run_weekly_backup(NOW, tmp_path, env={"SUPABASE_PROD_DB_URL": "postgresql://u:p@h/d"}, which=lambda _: "pg_dump", run=bad)
    assert r["status"] == "failed" and list(tmp_path.iterdir()) == []


def test_prune_keeps_the_newest(tmp_path):
    for i in range(1, 8):
        (tmp_path / f"{PREFIX}2026010{i}_000000.dump").write_text("x")
    gone = prune(tmp_path, 4)
    assert len(gone) == 3 and sorted(p.name for p in tmp_path.iterdir())[0].endswith("20260104_000000.dump")

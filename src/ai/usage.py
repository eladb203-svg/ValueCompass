"""Shared daily request counter and single-process lock for the Gemini client (decision 2026-10-22).

The free tier allows 500 requests per day per model (counted in Pacific time); the cap here is 450 for ALL processes together: every request attempt is counted in
``scripts/ai_store/usage.json`` (day = Pacific date). Only one model-calling process may run at a time: ``scripts/ai_store/run.lock`` holds the pid and is refreshed on every
request; a new process does not start while the lock is held by a live process whose last request is recent.
"""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "scripts" / "ai_store"
DAILY_CAP = 450
PACIFIC = ZoneInfo("America/Los_Angeles")
STALE_LOCK_S = 900          # a lock whose owner has not made a request for 15 minutes is stale even if the pid is alive (hung owner)


def pacific_day(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(PACIFIC)).astimezone(PACIFIC).strftime("%Y-%m-%d")


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=10).stdout
            return str(pid) in out
        os.kill(pid, 0)
        return True
    except Exception:  # noqa: BLE001
        return False


class DailyCounter:
    def __init__(self, path: Path = STORE / "usage.json", cap: int = DAILY_CAP, day=pacific_day):
        self.path, self.cap, self._day = Path(path), cap, day

    def _lock(self):
        lk = self.path.with_suffix(".lck")
        for _ in range(200):
            try:
                return os.open(str(lk), os.O_CREAT | os.O_EXCL | os.O_WRONLY), lk
            except FileExistsError:
                try:
                    if time.time() - lk.stat().st_mtime > 10:
                        lk.unlink()
                except OSError:
                    pass
                time.sleep(0.05)
        raise RuntimeError("could not lock the usage counter")

    def _read(self) -> dict:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        return d if d.get("day") == self._day() else {"day": self._day(), "calls": 0}

    def used(self) -> int:
        return self._read()["calls"]

    def reserve(self) -> int:
        """Count one request attempt; refuse (RuntimeError) when the shared daily cap is reached. -> requests used today including this one."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, lk = self._lock()
        try:
            d = self._read()
            if d["calls"] >= self.cap:
                raise RuntimeError(f"shared daily request cap of {self.cap} reached for {d['day']} (Pacific); {d['calls']} used by all processes")
            d["calls"] += 1
            self.path.write_text(json.dumps(d), encoding="utf-8")
            return d["calls"]
        finally:
            os.close(fd)
            try:
                lk.unlink()
            except OSError:
                pass


class SingleProcess:
    """Lock file with the owner's pid; ``acquire`` raises when another live, recently active process holds it."""

    def __init__(self, path: Path = STORE / "run.lock", stale_s: int = STALE_LOCK_S, alive=pid_alive):
        self.path, self.stale_s, self.alive, self.held = Path(path), stale_s, alive, False

    def acquire(self) -> None:
        if self.held:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                pid = int(json.loads(self.path.read_text(encoding="utf-8")).get("pid", 0))
            except (OSError, ValueError):
                pid = 0
            fresh = time.time() - self.path.stat().st_mtime < self.stale_s
            if pid and pid != os.getpid() and fresh and self.alive(pid):
                raise RuntimeError(f"another model-calling process (pid {pid}) is running; only one at a time ({self.path})")
        self.path.write_text(json.dumps({"pid": os.getpid(), "started": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
        self.held = True
        atexit.register(self.release)

    def touch(self) -> None:
        if self.held:
            try:
                os.utime(self.path, None)
            except OSError:
                pass

    def release(self) -> None:
        if self.held:
            self.held = False
            try:
                if json.loads(self.path.read_text(encoding="utf-8")).get("pid") == os.getpid():
                    self.path.unlink()
            except (OSError, ValueError):
                pass

"""The scheduler process (K6 spec 3.1, decision 2026-10-26): one process holds the whole schedule (APScheduler) and records every run in ``data_update_log``. No operating-system scheduler is used.

  serve()   the process: one instance only (a second one exits with a message), the jobs on their times, the jobs missed while the PC was off once at the start, an orderly stop
  ensure()  start ``serve`` in the background (detached from the window) when it is not running; do nothing when it is
  stop()    ask the running process to stop: a job in the middle finishes, then the process leaves and the lock is released
  status()  per job: the last run and its result, and the next due time

One instance = an exclusive lock on ``scripts/state/scheduler.lock`` (the operating system drops it when the process dies, so a crash never leaves a stale lock). The stop request is the file
``scripts/state/scheduler.stop``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from src.sched.jobs import STATE_DIR, JobRunner
from src.sched.schedule import JOB_NAMES, SlotTrigger, Config

ROOT = Path(__file__).resolve().parents[2]
VC = ROOT / "scripts" / "vc.py"
PRICE_JOBS = ("close_prices", "intraday_prices")


class InstanceLock:
    """An exclusive, non-blocking lock on a file; released with the process."""

    def __init__(self, path: Path):
        self.path, self.fh = Path(path), None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self.fh = fh
        return True

    def release(self) -> None:
        if self.fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()
            self.fh = None


def lock_path(state_dir: Path = STATE_DIR) -> Path:
    return Path(state_dir) / "scheduler.lock"


def is_running(state_dir: Path = STATE_DIR) -> bool:
    """Is a scheduler process holding the lock? (the lock is taken and given back at once when it is free)"""
    lk = InstanceLock(lock_path(state_dir))
    if lk.acquire():
        lk.release()
        return False
    return True


def read_info(state_dir: Path = STATE_DIR) -> dict:
    try:
        return json.loads((Path(state_dir) / "scheduler.info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- the process
def serve(cfg: Config, make_client: Callable, state_dir: Path = STATE_DIR, poll_seconds: float = 2.0, jobs: Optional[JobRunner] = None, log: Callable = print) -> int:
    """Run until a stop is requested. -> exit code (0 stopped, 1 another instance is running)."""
    from apscheduler.executors.pool import ThreadPoolExecutor
    from apscheduler.schedulers.background import BackgroundScheduler
    lk = InstanceLock(lock_path(state_dir))
    if not lk.acquire():
        log("The scheduler is already running (only one instance is allowed). Nothing was started.")
        return 1
    stop_file = Path(state_dir) / "scheduler.stop"
    stop_file.unlink(missing_ok=True)
    try:
        client = make_client()
        jobs = jobs or JobRunner(client, cfg)
        info = {"pid": os.getpid(), "started": datetime.now(timezone.utc).isoformat(), "config": str(cfg.path), "database": os.environ.get("VC_DB_TARGET", "test")}
        (Path(state_dir) / "scheduler.info.json").write_text(json.dumps(info), encoding="utf-8")
        sched = BackgroundScheduler(executors={"default": ThreadPoolExecutor(1), "prices": ThreadPoolExecutor(1)}, timezone=cfg.tz,
                                    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": None})
        for name in JOB_NAMES:
            if cfg.enabled(name):
                sched.add_job(jobs.run, SlotTrigger(cfg, name), args=[name], id=name, name=name, executor="prices" if name in PRICE_JOBS else "default")
        sched.start()
        log(f"[scheduler] started pid {os.getpid()}  database={info['database']}  config={cfg.path}")
        for name in JOB_NAMES:
            job = sched.get_job(name)
            if job:
                log(f"  {name:<16} next {job.next_run_time}")
        catcher = threading.Thread(target=catch_up, args=(jobs, log), name="catch-up", daemon=False)
        catcher.start()
        try:
            while not stop_file.exists():
                time.sleep(poll_seconds)
        except KeyboardInterrupt:
            log("[scheduler] interrupted: stopping in order")
        log("[scheduler] stop requested: the running job (if any) finishes first")
        sched.shutdown(wait=True)
        catcher.join()
        log("[scheduler] stopped")
        return 0
    finally:
        stop_file.unlink(missing_ok=True)
        try:
            (Path(state_dir) / "scheduler.info.json").unlink(missing_ok=True)
        except OSError:
            pass
        lk.release()


def catch_up(jobs: JobRunner, log: Callable = print) -> list:
    """Jobs missed while the scheduler (the PC) was off run once now, in the catch-up order: close prices, new SEC reports, the audit, yields, FX, cleanup, the AI queue."""
    names = jobs.missed()
    log(f"[catch-up] missed: {', '.join(names) if names else 'nothing'}")
    for name in names:
        out = jobs.run(name)
        log(f"[catch-up] {name}: {out.status}" + (f"  {out.error}" if out.error else ""))
    return names


# ---------------------------------------------------------------- ensure / stop / status
def ensure(config_path: Optional[Path] = None, state_dir: Path = STATE_DIR, popen: Callable = subprocess.Popen) -> tuple:
    """-> (started: bool, message). Starts ``vc.py scheduler`` detached from the window when no scheduler runs."""
    if is_running(state_dir):
        info = read_info(state_dir)
        return False, f"The scheduler is already running (pid {info.get('pid', '?')}, since {info.get('started', '?')}). Nothing was started."
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-u", str(VC), "scheduler"] + (["--config", str(config_path)] if config_path else [])
    logfile = open(Path(state_dir) / "scheduler.log", "ab")
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": logfile, "stderr": logfile, "cwd": str(ROOT), "close_fds": True}
    if os.name == "nt":
        base = 0x00000008 | 0x00000200                               # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:
            p = popen(cmd, creationflags=base | 0x01000000, **kw)       # CREATE_BREAKAWAY_FROM_JOB: survives the window or tool that started it
        except OSError:
            p = popen(cmd, creationflags=base, **kw)
    else:
        p = popen(cmd, start_new_session=True, **kw)
    return True, f"The scheduler was started in the background (pid {p.pid}). Log: {Path(state_dir) / 'scheduler.log'}"


def stop(state_dir: Path = STATE_DIR, wait_seconds: float = 120.0, poll: float = 1.0) -> tuple:
    """-> (stopped: bool, message). Asks the process to stop and waits for it (a running job finishes first)."""
    if not is_running(state_dir):
        (Path(state_dir) / "scheduler.stop").unlink(missing_ok=True)
        return False, "The scheduler is not running."
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    (Path(state_dir) / "scheduler.stop").write_text("stop", encoding="utf-8")
    t0 = time.time()
    while time.time() - t0 < wait_seconds:
        if not is_running(state_dir):
            return True, "The scheduler stopped."
        time.sleep(poll)
    return False, f"Stop was requested but the scheduler is still finishing a job (waited {wait_seconds:.0f}s). It will stop when the job ends."


def status(cfg: Config, jobs: Optional[JobRunner], state_dir: Path = STATE_DIR, now: Optional[datetime] = None) -> list:
    """-> lines: the process state, then per job: last run, result, next due."""
    now = now or datetime.now(timezone.utc)
    info = read_info(state_dir)
    lines = [("Scheduler: RUNNING (pid %s, since %s, database %s)" % (info.get("pid", "?"), info.get("started", "?"), info.get("database", "?"))) if is_running(state_dir) else "Scheduler: not running"]
    missed = set(jobs.missed(now)) if jobs else set()
    lines.append(f"{'job':<16}{'last run (Israel)':<20}{'result':<17}{'next due (Israel)':<20}note")
    for name in JOB_NAMES:
        if not cfg.enabled(name):
            lines.append(f"{name:<16}{'-':<20}{'disabled':<17}{'-':<20}")
            continue
        row = (jobs.last_rows(name, 1) or [None])[0] if jobs else None
        last = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00")).astimezone(cfg.tz).strftime("%Y-%m-%d %H:%M") if row else "never"
        res = (row["status"] if row else "-")
        nxt = cfg.next_due(name, now)
        note = ("MISSED: runs when the scheduler starts" if name in missed else "") + (f"  error: {row['error_message'][:80]}" if row and row.get("error_message") else "")
        lines.append(f"{name:<16}{last:<20}{res:<17}{(nxt.strftime('%Y-%m-%d %H:%M') if nxt else '-'):<20}{note.strip()}")
    return lines

"""Keep Windows awake while a long job runs (K6d-2 fixes): ``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)``. The screen may turn off; the computer does not sleep.
The state belongs to the calling thread and ends with it; ``release`` (or leaving the ``with`` block) clears it. On a system without the call it does nothing.
"""
from __future__ import annotations

from typing import Optional

import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _set(flags: int) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))
    except Exception:   # noqa: BLE001 - staying awake is a convenience, never a reason to stop the job
        return False


def hold() -> bool:
    """Ask Windows not to sleep. -> True when the request was accepted."""
    return _set(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def release() -> bool:
    return _set(ES_CONTINUOUS)


class Heartbeat:
    """A line in the log every ``interval`` seconds while a run is alive (K6d-2 fixes, 2026-11-01): ``[heartbeat] 12:05:01 +300 s``. The gap is measured on the wall clock; when it is much longer than
    the interval the computer was asleep (the monotonic clock of a sleeping Windows machine stops while the wall clock goes on), and the line says so."""

    def __init__(self, interval: float = 300.0, emit=None, wall=time.time):
        self.interval, self.wall = interval, wall
        self.emit = emit or (lambda m: print(m, flush=True))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last = None

    def beat(self) -> str:
        now = self.wall()
        gap = 0.0 if self.last is None else now - self.last
        self.last = now
        late = gap > self.interval * 1.5
        msg = f"[heartbeat] {datetime.fromtimestamp(now):%H:%M:%S} +{gap:.0f} s" + (f"  GAP: {gap - self.interval:.0f} s longer than expected - the computer was probably asleep or suspended" if late else "")
        self.emit(msg)
        return msg

    def __enter__(self):
        self.beat()
        self._thread = threading.Thread(target=self._run, name="heartbeat", daemon=True)
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.wait(self.interval):
            self.beat()

    def __exit__(self, *a):
        self._stop.set()
        self.beat()


@contextmanager
def keep_awake(heartbeat: bool = True, interval: float = 300.0):
    ok = hold()
    hb = Heartbeat(interval) if heartbeat else None
    if hb:
        hb.__enter__()
    try:
        yield ok
    finally:
        if hb:
            hb.__exit__()
        if ok:
            release()

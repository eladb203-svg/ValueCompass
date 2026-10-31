"""Keep Windows awake while a long job runs (K6d-2 fixes): ``SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)``. The screen may turn off; the computer does not sleep.
The state belongs to the calling thread and ends with it; ``release`` (or leaving the ``with`` block) clears it. On a system without the call it does nothing.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager

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


@contextmanager
def keep_awake():
    ok = hold()
    try:
        yield ok
    finally:
        if ok:
            release()

"""The same network-retry rule as the queue (K6d-2 fixes, 2026-11-01) for the commands that run a data load directly (`vc.py load`, `--job repair`): a temporary network error
(ConnectError, ReadError, timeout, DNS, WinError 10054) waits 1, 2, 4, 8 minutes and tries again, up to 5 attempts; anything else is raised at once."""
from __future__ import annotations

import time
from typing import Callable

from src.pipeline.queue_runner import is_transient

WAITS = (60, 120, 240, 480)


def with_network_retry(fn: Callable, sleep: Callable = time.sleep, waits: tuple = WAITS, log: Callable = print):
    """-> (result of fn(), seconds waited). The last error is raised when the attempts are over."""
    waited = 0.0
    for attempt in range(len(waits) + 1):
        try:
            return fn(), waited
        except Exception as e:   # noqa: BLE001 - only a temporary network error is retried
            if not is_transient(e) or attempt == len(waits):
                raise
            log(f"[network] {type(e).__name__}: attempt {attempt + 1} of {len(waits) + 1} failed, waiting {waits[attempt]} s")
            sleep(waits[attempt])
            waited += waits[attempt]

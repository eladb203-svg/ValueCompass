"""Network resilience (K6c follow-up): a gradual wait between attempts on network errors, the default of the DB client and of the SEC clients.

A connection that cannot be made (DNS failure ``getaddrinfo failed``, host unreachable, connection refused, connect timeout) is tried again after 30, 60, 120 and 120 seconds - five attempts in
all - before the error is raised. Only the connect phase is retried: nothing has reached the server yet, so a write is not repeated. Any other error is raised at once.
"""
from __future__ import annotations

import socket
import time
from typing import Callable, Optional

import httpx

NETWORK_WAITS = (30, 60, 120, 120)          # seconds between the five attempts


def is_network_error(e: BaseException) -> bool:
    """A failure to reach the server (not an answer from it)."""
    if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout, socket.gaierror)):
        return True
    try:
        import requests
        if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout)):
            return True
    except ImportError:                       # pragma: no cover
        pass
    return False


def retry_network(fn: Callable, waits: tuple = NETWORK_WAITS, sleep: Optional[Callable] = None, on_retry: Optional[Callable] = None):
    """Call ``fn()``; on a network error wait ``waits[i]`` seconds and try again, up to ``len(waits) + 1`` attempts. The last error is raised unchanged."""
    sleep = sleep or time.sleep
    for i in range(len(waits) + 1):
        try:
            return fn()
        except Exception as e:   # noqa: BLE001 - only network errors are retried, the rest is re-raised below
            if not is_network_error(e) or i == len(waits):
                raise
            if on_retry:
                on_retry(i + 1, waits[i], e)
            sleep(waits[i])


class RetryTransport(httpx.BaseTransport):
    """An httpx transport that retries a failed connection with the gradual wait (all methods: nothing was sent when the connection failed)."""

    def __init__(self, inner: Optional[httpx.BaseTransport] = None, waits: tuple = NETWORK_WAITS, sleep: Optional[Callable] = None):
        self.inner, self.waits, self.sleep = inner or httpx.HTTPTransport(), waits, sleep

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return retry_network(lambda: self.inner.handle_request(request), self.waits, self.sleep,
                             on_retry=lambda n, w, e: print(f"[network] {type(e).__name__}: attempt {n} failed, waiting {w}s", flush=True))

    def close(self) -> None:
        self.inner.close()

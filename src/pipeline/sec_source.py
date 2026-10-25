"""SEC access for the K6b pipeline: a rate-limited, cached client with its own cache directory.

* At most 10 requests per second is enforced in code (sliding window of one second, plus a minimum gap between two requests).
* Every downloaded file is saved in the cache directory (``scripts/cache/sec_live`` by default - not ``scripts/cache/sec``, which feeds the golden regression).
* Mutable documents (the ticker list, submissions, companyfacts) are downloaded again when the cached copy is older than ``max_age_hours``; filing documents never change and are
  fetched once.
* ``fetch`` replaces the network (tests); ``transform(cache_name, data)`` lets an acceptance run overlay a simulated amendment or a simulated new annual report on a real document.
"""
from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

from src.providers.sec_companyfacts import SecClient

ROOT = Path(__file__).resolve().parents[2]
LIVE_CACHE = ROOT / "scripts" / "cache" / "sec_live"
FILINGS_CACHE = ROOT / "scripts" / "cache" / "filings"
MAX_PER_SECOND = 10
MIN_GAP = 0.12                      # seconds between two requests (about 8 per second at most)
MUTABLE_PREFIXES = ("company_tickers", "sub_", "facts_")


class RateLimiter:
    """No more than ``limit`` requests in any window of one second; ``clock`` and ``sleep`` can be replaced in tests."""

    def __init__(self, limit: int = MAX_PER_SECOND, min_gap: float = MIN_GAP, clock: Callable = time.monotonic, sleep: Callable = time.sleep):
        self.limit, self.min_gap, self.clock, self.sleep = limit, min_gap, clock, sleep
        self.stamps: deque = deque()

    def wait(self) -> None:
        now = self.clock()
        if self.stamps:
            gap = self.min_gap - (now - self.stamps[-1])
            if gap > 0:
                self.sleep(gap)
                now = self.clock()
        while len(self.stamps) >= self.limit and now - self.stamps[0] < 1.0:
            self.sleep(1.0 - (now - self.stamps[0]))
            now = self.clock()
        while self.stamps and now - self.stamps[0] >= 1.0:
            self.stamps.popleft()
        self.stamps.append(now)


class PipelineSec(SecClient):
    def __init__(self, cache_dir: Optional[Path] = None, user_agent: Optional[str] = None, max_age_hours: float = 20.0, fetch: Optional[Callable] = None,
                 transform: Optional[Callable] = None, limiter: Optional[RateLimiter] = None, now: Callable = time.time):
        if fetch is None:
            super().__init__(user_agent)
        else:                                            # tests: no User-Agent needed, no network
            self._headers, self._last, self.requests_made = {}, 0.0, 0
        self.cache_dir = Path(cache_dir) if cache_dir else LIVE_CACHE
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_age = max_age_hours * 3600
        self._fetch, self.transform, self.limiter, self._now = fetch, transform, limiter or RateLimiter(), now
        self.downloads: list = []                        # (cache_name, url) of every file fetched from SEC in this run

    def _fresh(self, path: Path, name: str) -> bool:
        if not path.exists():
            return False
        if not name.startswith(MUTABLE_PREFIXES):
            return True
        return self._now() - path.stat().st_mtime < self.max_age

    def _download(self, url: str) -> str:
        self.limiter.wait()
        if self._fetch is not None:
            text = self._fetch(url)
        else:
            import requests
            r = requests.get(url, headers=self._headers, timeout=60)
            r.raise_for_status()
            text = r.text
        self.requests_made += 1
        return text

    def get_json(self, url: str, cache_name: str, refresh: bool = False):
        path = self.cache_dir / cache_name
        if refresh or not self._fresh(path, cache_name):
            text = self._download(url)
            path.write_text(text, encoding="utf-8")
            self.downloads.append((cache_name, url))
        data = json.loads(path.read_text(encoding="utf-8"))
        return self.transform(cache_name, data) if self.transform else data

    def get_text(self, url: str, cache_name: str) -> str:
        """A filing document (HTML / text). It never changes: the local filings cache of the earlier stages is reused read-only, else it is fetched once into this cache."""
        legacy = FILINGS_CACHE / cache_name
        if legacy.exists():
            return legacy.read_text(encoding="utf-8", errors="replace")
        path = self.cache_dir / cache_name
        if not path.exists():
            path.write_text(self._download(url), encoding="utf-8")
            self.downloads.append((cache_name, url))
        return path.read_text(encoding="utf-8", errors="replace")

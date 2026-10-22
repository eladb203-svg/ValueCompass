"""Gemini client (AI spec section 4/8): key from .env (never printed), one fixed model, temperature 0, JSON output, retry, rate limiting.

Free-tier limits are not published in the documentation (it says to look them up per project in AI Studio), so the limiter is configurable
(``GEMINI_RPM`` requests/min, ``GEMINI_TPM`` input tokens/min, ``GEMINI_RPD`` requests/day) and additionally obeys the server: a 429 response waits for the
retry delay it carries and then halves the request rate.
"""
from __future__ import annotations

import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
# Fixed model of the AI layer (recorded on every answer). The model named in .env (GEMINI_MODEL = gemini-3.8-flash) answered a trivial prompt with 504 DEADLINE_EXCEEDED
# after 90 s on 2026-10-21 (3.7-flash: 64 s, 3.5-flash: 503 high demand), so the free tier cannot serve it reliably; 3.5-flash-lite answers in ~1 s. Override with VC_AI_MODEL.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_RPM, DEFAULT_TPM, DEFAULT_RPD = 5, 200_000, 200
MAX_RETRIES = int(os.environ.get("VC_AI_RETRIES", 8))   # 503 / 504 / 429 / network: exponential back-off up to ~10 minutes between attempts
SEED = int(os.environ.get("VC_AI_SEED", 20261021))      # fixed seed in addition to temperature 0


def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:  # noqa: BLE001
        pass


@dataclass
class RateLimiter:
    rpm: int = DEFAULT_RPM
    tpm: int = DEFAULT_TPM
    rpd: int = DEFAULT_RPD
    clock: callable = time.monotonic
    sleep: callable = time.sleep
    calls: deque = field(default_factory=deque)        # (time, tokens) in the last 60 s
    day_calls: int = 0
    waited: float = 0.0

    def wait(self, tokens: int) -> None:
        if self.day_calls >= self.rpd:
            raise RuntimeError(f"daily request budget of {self.rpd} reached (GEMINI_RPD)")
        while True:
            now = self.clock()
            while self.calls and now - self.calls[0][0] >= 60:
                self.calls.popleft()
            used = sum(t for _, t in self.calls)
            if len(self.calls) < self.rpm and used + tokens <= self.tpm:
                break
            wait = max(0.5, 60 - (now - self.calls[0][0])) if self.calls else 1.0
            self.waited += wait
            self.sleep(wait)
        self.calls.append((self.clock(), tokens))
        self.day_calls += 1

    def slow_down(self) -> None:
        self.rpm = max(1, self.rpm // 2)


@dataclass
class Reply:
    text: str
    model: str
    prompt_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0
    latency: float = 0.0
    attempts: int = 1


class GeminiClient:
    def __init__(self, model: Optional[str] = None, limiter: Optional[RateLimiter] = None, api_client=None):
        load_env()
        self.model = model or os.environ.get("VC_AI_MODEL") or DEFAULT_MODEL
        self.limiter = limiter or RateLimiter(int(os.environ.get("GEMINI_RPM", DEFAULT_RPM)), int(os.environ.get("GEMINI_TPM", DEFAULT_TPM)),
                                              int(os.environ.get("GEMINI_RPD", DEFAULT_RPD)))
        self._api = api_client
        self.calls = 0
        self.retries = 0
        self.failures = 0
        self.total_latency = 0.0
        self.prompt_tokens = self.output_tokens = 0

    def _client(self):
        if self._api is None:
            key = os.environ.get("GEMINI_API_KEY")
            if not key:
                raise RuntimeError("GEMINI_API_KEY is not set (.env)")
            from google import genai
            from google.genai import types
            self._api = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(os.environ.get("VC_AI_TIMEOUT_MS", 120000))))
        return self._api

    @staticmethod
    def estimate_tokens(prompt: str) -> int:
        return len(prompt) // 3 + 1          # conservative: about 3 characters per token

    def generate(self, prompt: str) -> Reply:
        from google.genai import types
        cfg = types.GenerateContentConfig(temperature=0, seed=SEED, response_mime_type="application/json")
        err: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            self.limiter.wait(self.estimate_tokens(prompt))
            t0 = time.monotonic()
            try:
                r = self._client().models.generate_content(model=self.model, contents=prompt, config=cfg)
                lat = time.monotonic() - t0
                um = getattr(r, "usage_metadata", None)
                rep = Reply(r.text or "", self.model, getattr(um, "prompt_token_count", 0) or 0, getattr(um, "candidates_token_count", 0) or 0,
                            getattr(um, "thoughts_token_count", 0) or 0, lat, attempt)
                self.calls += 1
                self.total_latency += lat
                self.prompt_tokens += rep.prompt_tokens
                self.output_tokens += rep.output_tokens
                return rep
            except Exception as e:  # noqa: BLE001
                err = e
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    m = re.search(r"retry in ([\d\.]+)s|retryDelay['\"]?:\s*['\"]?([\d\.]+)s", msg)
                    delay = float(next(g for g in (m.groups() if m else ()) if g)) if m and any(m.groups()) else 30.0
                    self.limiter.slow_down()
                    self.retries += 1
                    self.limiter.sleep(min(delay + 1, 600))
                elif any(c in msg for c in ("500", "502", "503", "504", "UNAVAILABLE", "DEADLINE")) or type(e).__name__ in ("ConnectError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError", "ReadError", "ConnectionError"):
                    self.retries += 1
                    self.limiter.sleep(min(10 * 2 ** attempt, 600))
                else:
                    raise
        self.failures += 1
        raise RuntimeError(f"Gemini call failed after {MAX_RETRIES} attempts: {str(err)[:200]}")

"""Gemini client (AI spec section 4/8): key from .env (never printed), one fixed model, temperature 0, JSON output, retry, rate limiting.

Free-tier limits are not published in the documentation (it says to look them up per project in AI Studio), so the limiter is configurable
(``GEMINI_RPM`` requests/min, ``GEMINI_TPM`` input tokens/min, ``GEMINI_RPD`` requests/day) and additionally obeys the server: a 429 response waits for the
retry delay it carries and then halves the request rate.
"""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
# ---- The pinned configuration of the AI layer (decision 2026-10-22): one model, temperature 0, a fixed seed. Every stored answer carries the model name and the prompt version.
# A change of model is a new version of every answer (R18), not a fallback.
AI_MODEL = "gemini-3.5-flash-lite"
AI_TEMPERATURE = 0
AI_SEED = 20261021
DEFAULT_MODEL = AI_MODEL
DEFAULT_RPM, DEFAULT_TPM, DEFAULT_RPD = 5, 200_000, 200
MAX_RETRIES = int(os.environ.get("VC_AI_RETRIES", 8))   # 503 / 504 / 429 / network: exponential back-off up to ~10 minutes between attempts
MAX_OUTPUT_TOKENS = int(os.environ.get("VC_AI_MAX_OUTPUT_TOKENS", 8192))
SEED = AI_SEED


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
    finish_reason: str = ""
    attempt_log: list = field(default_factory=list)   # one entry per failed attempt: {attempt, at (Israel time), error_code, waited_s}


def error_code(e: Exception) -> str:
    """HTTP-like code of a failed attempt (429, 500, 502, 503, 504) or the exception class name."""
    m = re.search(r"\b(429|500|502|503|504)\b", str(e))
    if m:
        return m.group(1)
    for k, v in (("RESOURCE_EXHAUSTED", "429"), ("UNAVAILABLE", "503"), ("DEADLINE", "504")):
        if k in str(e):
            return v
    return type(e).__name__


class GeminiClient:
    def __init__(self, model: Optional[str] = None, limiter: Optional[RateLimiter] = None, api_client=None):
        load_env()
        self.model = model or AI_MODEL          # the model is a parameter only for the model-comparison tools; the default is the pinned model
        self.limiter = limiter or RateLimiter(int(os.environ.get("GEMINI_RPM", DEFAULT_RPM)), int(os.environ.get("GEMINI_TPM", DEFAULT_TPM)),
                                              int(os.environ.get("GEMINI_RPD", DEFAULT_RPD)))
        self._api = api_client
        # decision 2026-10-22: a real client (no injected api) counts every attempt in the shared daily counter (cap 450 for all processes) and runs one process at a time
        self.shared = (api_client is None) and not os.environ.get("VC_AI_NO_SHARED")
        self._usage = self._single = None
        self.calls = 0
        self.retries = 0
        self.failures = 0
        self.total_latency = 0.0
        self.prompt_tokens = self.output_tokens = 0

    def _shared_guard(self) -> None:
        if not self.shared:
            return
        from .usage import DailyCounter, SingleProcess
        if self._usage is None:
            self._single, self._usage = SingleProcess(), DailyCounter()
            self._single.acquire()
        self._usage.reserve()
        self._single.touch()

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

    def generate(self, prompt: str, seed_offset: int = 0, thinking_budget: Optional[int] = None) -> Reply:
        from google.genai import types
        kw = {"temperature": AI_TEMPERATURE, "seed": SEED + seed_offset, "response_mime_type": "application/json", "max_output_tokens": MAX_OUTPUT_TOKENS}
        if thinking_budget is not None:
            kw["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)
        cfg = types.GenerateContentConfig(**kw)
        err: Optional[Exception] = None
        log: list = []
        for attempt in range(1, MAX_RETRIES + 1):
            self._shared_guard()
            self.limiter.wait(self.estimate_tokens(prompt))
            t0 = time.monotonic()
            try:
                r = self._client().models.generate_content(model=self.model, contents=prompt, config=cfg)
                lat = time.monotonic() - t0
                um = getattr(r, "usage_metadata", None)
                rep = Reply(r.text or "", self.model, getattr(um, "prompt_token_count", 0) or 0, getattr(um, "candidates_token_count", 0) or 0,
                            getattr(um, "thoughts_token_count", 0) or 0, lat, attempt,
                            str(getattr((getattr(r, "candidates", None) or [None])[0], "finish_reason", "") or ""), log)
                self.calls += 1
                self.total_latency += lat
                self.prompt_tokens += rep.prompt_tokens
                self.output_tokens += rep.output_tokens
                return rep
            except Exception as e:  # noqa: BLE001
                err = e
                msg = str(e)
                entry = {"attempt": attempt, "at": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%H:%M:%S"), "error_code": error_code(e), "waited_s": 0}
                log.append(entry)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    m = re.search(r"retry in ([\d\.]+)s|retryDelay['\"]?:\s*['\"]?([\d\.]+)s", msg)
                    delay = float(next(g for g in (m.groups() if m else ()) if g)) if m and any(m.groups()) else 30.0
                    self.limiter.slow_down()
                    self.retries += 1
                    entry["waited_s"] = min(delay + 1, 600)
                    self.limiter.sleep(min(delay + 1, 600))
                elif any(c in msg for c in ("500", "502", "503", "504", "UNAVAILABLE", "DEADLINE")) or type(e).__name__ in ("ConnectError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError", "ReadError", "ConnectionError"):
                    self.retries += 1
                    entry["waited_s"] = min(10 * 2 ** attempt, 600)
                    self.limiter.sleep(min(10 * 2 ** attempt, 600))
                else:
                    raise
        self.failures += 1
        raise RuntimeError(f"Gemini call failed after {MAX_RETRIES} attempts: {str(err)[:200]}")

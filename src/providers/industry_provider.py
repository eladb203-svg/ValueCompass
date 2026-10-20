"""Provider industry (FIN-189, yfinance ``industry``) for the profile router, tier 2 of Part B.1.

Lookup order: a fixed CSV when one is active (``use_fixed``: golden / tests, no network) -> the local cache -> yfinance (result cached).
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
CACHE_FILE = ROOT / "scripts" / "cache" / "yfinance_industry.json"
_FIXED: Optional[dict] = None


def use_fixed(path: Optional[Path]) -> None:
    """Activate a fixed ticker -> industry CSV (columns ticker, provider_industry); None switches back to cache / network."""
    global _FIXED
    if path is None:
        _FIXED = None
        return
    with Path(path).open(encoding="utf-8", newline="") as fh:
        _FIXED = {r["ticker"].upper(): (r["provider_industry"] or None) for r in csv.DictReader(fh)}


def get_industry(ticker: str) -> Optional[str]:
    t = ticker.upper()
    if _FIXED is not None:
        return _FIXED.get(t)
    cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}
    if t in cache:
        return cache[t]
    try:
        import yfinance as yf
        ind = yf.Ticker(t).info.get("industry") or None
    except Exception:  # noqa: BLE001  (no network / no data: tier 2 simply has no answer)
        return None
    cache[t] = ind
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    return ind

"""Price snapshot (K6 spec 2.4, E1): one row per stock in ``market_snapshot``, updated in place. Freshness check: ``dq.price_freshness``."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from src.pipeline.dq import price_freshness


def fetch_last_price(ticker: str) -> Optional[dict]:
    """The last close from yfinance: {"price", "previous_close", "market_date"} or None."""
    import yfinance as yf
    h = yf.Ticker(ticker).history(period="7d", auto_adjust=False)
    if h is None or h.empty:
        return None
    closes = [float(x) for x in h["Close"].tolist()]
    last = h.index[-1]
    return {"price": closes[-1], "previous_close": closes[-2] if len(closes) > 1 else None, "market_date": (last.date() if hasattr(last, "date") else last)}


def refresh_snapshot(client, company_id: int, ticker: str, fetch: Callable = fetch_last_price, now: Optional[datetime] = None) -> dict:
    """Update the stock's row in ``market_snapshot``. -> {"status": "updated" | "unchanged" | "no_price", ...}. No price = no row change (the old row stays, flagged stale)."""
    now = now or datetime.now(timezone.utc)
    p = fetch(ticker)
    if not p:
        old = client.table("market_snapshot").select("company_id").eq("company_id", company_id).limit(1).execute().data
        if old:
            client.table("market_snapshot").update({"is_stale": True, "updated_at": now.isoformat()}).eq("company_id", company_id).execute()
        return {"status": "no_price", "detail": "no price from yfinance"}
    last = datetime(p["market_date"].year, p["market_date"].month, p["market_date"].day, 21, 0, tzinfo=timezone.utc)
    stale, detail = price_freshness(last, now)
    row = {"company_id": company_id, "snapshot_at": now.isoformat(), "market_date": p["market_date"].isoformat(), "current_price": p["price"], "previous_close": p["previous_close"],
           "price_currency": "USD", "source": "yfinance", "last_price_at": last.isoformat(), "is_stale": stale, "updated_at": now.isoformat()}
    client.table("market_snapshot").upsert(row, on_conflict="company_id").execute()
    return {"status": "updated", "price": p["price"], "market_date": p["market_date"].isoformat(), "is_stale": stale, "detail": detail}

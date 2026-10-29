"""Price snapshot (K6 spec 2.4, E1): one row per stock in ``market_snapshot``, updated in place. Freshness check: ``dq.price_freshness``.

``fetch_last_price``    one ticker (the load of a company)
``fetch_prices_batch``  many tickers in ONE request (the daily close job, the intraday job); ``parse_batch`` is the pure part
``apply_snapshot``      writes a fetched price into ``market_snapshot``; the price part of the score follows in place (``src/pipeline/reprice.py``)
"""
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


def parse_batch(df, tickers: list) -> dict:
    """A yfinance ``download`` frame (one ticker or several; one column level or two) -> {ticker: {"price", "previous_close", "market_date"}}. The price is the last close of the frame,
    the previous close the last close of an earlier date; a ticker without a price is left out."""
    out = {}
    if df is None or len(df) == 0:
        return out
    multi = hasattr(df.columns, "nlevels") and df.columns.nlevels > 1
    for t in tickers:
        col = None
        try:
            if multi:
                for level in (0, 1):
                    names = df.columns.get_level_values(level)
                    if t in names:
                        sub = df.xs(t, axis=1, level=level)
                        col = sub["Close"] if "Close" in sub.columns else None
                        break
            elif len(tickers) == 1:
                col = df["Close"]
        except KeyError:
            col = None
        if col is None:
            continue
        col = col.dropna()
        if len(col) == 0:
            continue
        last = col.index[-1]
        last_date = last.date() if hasattr(last, "date") else last
        earlier = [float(v) for ts, v in col.items() if (ts.date() if hasattr(ts, "date") else ts) < last_date]
        out[t] = {"price": float(col.iloc[-1]), "previous_close": earlier[-1] if earlier else None, "market_date": last_date}
    return out


def fetch_prices_batch(tickers: list, intraday: bool = True, retry_missing: bool = False) -> dict:
    """One yfinance request for all tickers: the LAST PRICE (K6d-2) - the last traded 1-minute bar of the last two days, not the daily close row (which does not exist while the day is open
    and may lag after it). The previous close is the last bar of the day before. ``intraday=False`` reads the daily rows of the last week. No second attempt unless ``retry_missing``."""
    tickers = sorted({t for t in tickers if t})
    if not tickers:
        return {}
    import yfinance as yf
    kw = {"period": "2d", "interval": "1m"} if intraday else {"period": "7d", "interval": "1d"}
    def one_request(names: list) -> dict:
        df = yf.download(names if len(names) > 1 else names[0], auto_adjust=False, progress=False, group_by="ticker", threads=False, **kw)
        return parse_batch(df, names)

    out = one_request(tickers)
    missing = [t for t in tickers if t not in out]
    if missing and retry_missing:                     # the source sometimes drops a ticker from a batch: one more request for those only
        out.update(one_request(missing))
    return out


def snapshot_row(company_id: int, p: dict, now: datetime) -> tuple:
    """-> (market_snapshot row, is_stale, detail)."""
    last = datetime(p["market_date"].year, p["market_date"].month, p["market_date"].day, 21, 0, tzinfo=timezone.utc)
    stale, detail = price_freshness(last, now)
    row = {"company_id": company_id, "snapshot_at": now.isoformat(), "market_date": p["market_date"].isoformat(), "current_price": p["price"], "previous_close": p.get("previous_close"),
           "price_currency": "USD", "source": "yfinance", "last_price_at": last.isoformat(), "is_stale": stale, "updated_at": now.isoformat()}
    return row, stale, detail


def apply_snapshot(client, company_id: int, p: Optional[dict], now: Optional[datetime] = None) -> dict:
    """Write a fetched price (or the lack of one) into ``market_snapshot``. -> {"status": "updated" | "no_price", ...}. No price = the old row stays as it is: a failed request is not a stale
    price - staleness is decided by the date of the last price (E1, ``dq.price_freshness`` and the database check)."""
    now = now or datetime.now(timezone.utc)
    if not p:
        return {"status": "no_price", "detail": "no price from yfinance"}
    row, stale, detail = snapshot_row(company_id, p, now)
    client.table("market_snapshot").upsert(row, on_conflict="company_id").execute()
    return {"status": "updated", "price": p["price"], "market_date": p["market_date"].isoformat(), "is_stale": stale, "detail": detail, "snapshot_at": row["snapshot_at"]}


def refresh_snapshot(client, company_id: int, ticker: str, fetch: Callable = fetch_last_price, now: Optional[datetime] = None) -> dict:
    """Update the stock's row in ``market_snapshot`` (one ticker). -> {"status": "updated" | "no_price", ...}."""
    return apply_snapshot(client, company_id, fetch(ticker), now)

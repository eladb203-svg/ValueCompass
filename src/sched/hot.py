"""The "hot" stocks (K6 spec 3.1): held in a portfolio or on a watchlist of any user, AND the price is at most ``ratio`` (110%) of the buy price of Buffett or of Graham.

A stock without a buy price (not suitable, coverage below 80%, not scored) is not hot; no hot stock = the intraday job sends no request. The basis for the buy-price alerts of K7.
"""
from __future__ import annotations

from typing import Optional

from src.ai.db_stores import select_all

HOT_RATIO = 1.10


def is_hot(price: Optional[float], buy_prices: list, ratio: float = HOT_RATIO) -> bool:
    """The price is at most ``ratio`` x any of the buy prices (a missing or non-positive buy price does not count)."""
    if price is None:
        return False
    return any(isinstance(b, (int, float)) and b > 0 and price <= b * ratio for b in buy_prices)


def followed_company_ids(client) -> set:
    """Companies in some portfolio or on some watchlist."""
    held = {r["company_id"] for r in select_all(client, "portfolio_holdings")}
    watched = {r["company_id"] for r in select_all(client, "user_watchlist")}
    return held | watched


def hot_stocks(client, ratio: float = HOT_RATIO) -> list:
    """-> [{"company_id", "symbol", "price", "buffett_buy_price", "graham_buy_price"}] of the hot stocks."""
    ids = followed_company_ids(client)
    if not ids:
        return []
    comps = {r["id"]: r for r in select_all(client, "companies") if r["id"] in ids}
    snaps = {r["company_id"]: r for r in select_all(client, "market_snapshot", order="company_id") if r["company_id"] in ids}
    summ = {r["company_id"]: r for r in select_all(client, "company_score_summary", order="company_id") if r["company_id"] in ids}
    out = []
    for cid, c in sorted(comps.items()):
        price = (snaps.get(cid) or {}).get("current_price")
        s = summ.get(cid) or {}
        buys = [s.get("buffett_buy_price"), s.get("graham_buy_price")]
        price = None if price is None else float(price)
        if is_hot(price, [None if b is None else float(b) for b in buys], ratio):
            out.append({"company_id": cid, "symbol": c["symbol"], "price": price, "buffett_buy_price": s.get("buffett_buy_price"), "graham_buy_price": s.get("graham_buy_price")})
    return out

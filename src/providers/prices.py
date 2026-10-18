"""Price provider: current price, annual average price per fiscal year, split history.

Primary source: yfinance (cached under scripts/cache/prices). Fallback: scripts/prices.csv with columns
``ticker,fy,avg_price`` (fy = FY label such as FY2024, or CURRENT for the current price).
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "scripts" / "cache" / "prices"
MANUAL = ROOT / "scripts" / "prices.csv"


def _load_history(ticker: str):
    """Return (list of (date, close, split_ratio)) from cache or yfinance."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{ticker}.csv"
    rows: list = []
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.append((date.fromisoformat(r["date"]), float(r["close"]), float(r["split"] or 0)))
        return rows
    import yfinance as yf
    h = yf.Ticker(ticker).history(period="max", auto_adjust=False, actions=True)
    if h is None or h.empty:
        raise RuntimeError(f"yfinance returned no data for {ticker}")
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "close", "split"])
        for ts, row in h.iterrows():
            d = ts.date() if hasattr(ts, "date") else ts
            rows.append((d, float(row["Close"]), float(row.get("Stock Splits", 0) or 0)))
            w.writerow([d.isoformat(), float(row["Close"]), float(row.get("Stock Splits", 0) or 0)])
    return rows


def get_splits(ticker: str) -> list:
    """Stock splits as (date, ratio); empty list when price history is unavailable."""
    try:
        return [(d, r) for d, _, r in _load_history(ticker) if r and r > 0]
    except Exception:  # noqa: BLE001 - reported later by load_prices
        return []


def _manual(ticker: str) -> dict:
    out: dict = {}
    if MANUAL.exists():
        with MANUAL.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["ticker"].upper() == ticker.upper() and r.get("avg_price"):
                    out[r["fy"].strip()] = float(r["avg_price"])
    return out


def load_prices(ticker: str, ends: list, labels: list):
    """Return dict(current, current_date, avg=[...], splits=[(date, ratio)], source, notes)."""
    notes: list = []
    try:
        rows = _load_history(ticker)
        splits = [(d, r) for d, _, r in rows if r and r > 0]
        avg: list = []
        for i, end in enumerate(ends):
            start = ends[i - 1] if i else end - timedelta(days=365)
            vals = [c for d, c, _ in rows if start < d <= end]
            avg.append(sum(vals) / len(vals) if len(vals) >= 100 else None)
            if avg[-1] is None:
                notes.append(f"{labels[i]}: fewer than 100 trading days of price data")
        cur_row = rows[-1]
        return {"current": cur_row[1], "current_date": cur_row[0], "avg": avg, "splits": splits,
                "source": "yfinance (Close, split-adjusted, not dividend-adjusted)", "notes": notes}
    except Exception as e:  # noqa: BLE001 - fall back to manual csv, report the reason
        notes.append(f"yfinance failed ({type(e).__name__}: {e}); trying scripts/prices.csv")
    m = _manual(ticker)
    avg = [m.get(l) for l in labels]
    cur: Optional[float] = m.get("CURRENT")
    if cur is None and not any(avg):
        notes.append("no manual prices either: fill scripts/prices.csv (ticker,fy,avg_price; fy=CURRENT for now)")
    return {"current": cur, "current_date": None, "avg": avg, "splits": [], "source": "manual csv", "notes": notes}

"""Reference tables the scheduler keeps current: ``gov_yields`` (E4) and ``fx_rates`` (R15, storage only until the Israel stage).

Yields: the existing scripts (``scripts/build_gov_yields_monthly.py``: the latest monthly average of the US 10-year, FRED GS10; ``scripts/build_gov_yields.py``: the annual averages) keep
``scripts/gov_yields.csv`` - the file the engines read - and this module copies the CSV into the table (idempotent upsert). FX: the ECB reference rates (one free request) -> USD per one unit of
ILS, EUR, GBP, JPY, one row per currency (``period_type = 'current'``, the latest value only: no history is kept, K6 spec 3.3).
"""
from __future__ import annotations

import csv
import importlib.util
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[2]
YIELDS_CSV = ROOT / "scripts" / "gov_yields.csv"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
FX_CURRENCIES = ("ILS", "EUR", "GBP", "JPY")


# ---------------------------------------------------------------- FX
def fetch_ecb(get: Optional[Callable] = None) -> str:
    if get is None:
        import requests
        from src.net import retry_network
        def get(url):                                                # noqa: E306
            r = retry_network(lambda: requests.get(url, timeout=60, headers={"User-Agent": "valuecompass research (eladb203@gmail.com)"}))
            r.raise_for_status()
            return r.text
    return get(ECB_URL)


def parse_ecb(xml_text: str) -> tuple:
    """-> (rate date, {currency: units per 1 EUR}) from the ECB daily reference-rate XML."""
    root = ET.fromstring(xml_text)
    day, rates = None, {}
    for el in root.iter():
        if el.attrib.get("time"):
            day = date.fromisoformat(el.attrib["time"])
        if el.attrib.get("currency") and el.attrib.get("rate"):
            rates[el.attrib["currency"]] = float(el.attrib["rate"])
    if day is None or "USD" not in rates:
        raise ValueError("the ECB file has no date or no USD rate")
    return day, rates


def usd_per_unit(per_eur: dict) -> dict:
    """USD for one unit of each currency, from the rates per 1 EUR: EUR -> USD/EUR; X -> (USD per EUR) / (X per EUR)."""
    usd = per_eur["USD"]
    return {c: (usd if c == "EUR" else usd / per_eur[c]) for c in FX_CURRENCIES if c == "EUR" or c in per_eur}


def update_fx(client, get: Optional[Callable] = None, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    day, per_eur = parse_ecb(fetch_ecb(get))
    rates = usd_per_unit(per_eur)
    missing = [c for c in FX_CURRENCIES if c not in rates]
    rows = [{"currency": c, "period_type": "current", "period": "current", "rate_to_usd": round(v, 8), "source": f"ECB euro foreign exchange reference rates {day.isoformat()}",
             "rate_date": day.isoformat(), "retrieved_at": now.isoformat()} for c, v in rates.items()]
    old = {r["currency"]: r for r in client.table("fx_rates").select("*").eq("period_type", "current").execute().data}
    changed = [r for r in rows if r["currency"] not in old or float(old[r["currency"]]["rate_to_usd"]) != r["rate_to_usd"] or str(old[r["currency"]].get("rate_date")) != r["rate_date"]]
    if changed:
        client.table("fx_rates").upsert(changed, on_conflict="currency,period_type,period").execute()
    return {"date": day.isoformat(), "rates": {r["currency"]: r["rate_to_usd"] for r in rows}, "written": len(changed), "missing": missing}


# ---------------------------------------------------------------- yields
def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def refresh_yield_csv(today: Optional[date] = None, run_monthly: Optional[Callable] = None, run_annual: Optional[Callable] = None, csv_path: Path = YIELDS_CSV) -> dict:
    """Run the existing builders: the monthly one every time; the annual one when the CSV has no row for the last completed year. A source that cannot be reached leaves the file as it is."""
    today = today or date.today()
    out = {"monthly": None, "annual": None}
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline=""))) if csv_path.exists() else []
    have_years = {int(r["year"]) for r in rows if r["year"].isdigit() and r["currency"] == "USD"}
    if (today.year - 1) not in have_years:                            # the annual builder rewrites the file (annual rows only), so it runs first and the monthly row is added after it
        run_annual = run_annual or (lambda: _load_script("build_gov_yields").main())
        out["annual"] = f"annual builder run (no USD row for {today.year - 1})"
        try:
            run_annual()
        except SystemExit as e:                                      # the builder stops instead of estimating a year the sources do not have yet
            out["annual"] = f"annual builder stopped: {e}"
    run_monthly = run_monthly or (lambda: _load_script("build_gov_yields_monthly").main())
    out["monthly"] = run_monthly()
    return out


def sync_yields_to_db(client, csv_path: Path = YIELDS_CSV) -> dict:
    """``scripts/gov_yields.csv`` -> table ``gov_yields`` (annual: period 'YYYY'; monthly: 'YYYY-MM'). -> {"read", "written"}; a repeated call writes nothing."""
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    want = []
    for r in rows:
        monthly = "-" in r["year"]
        want.append({"currency": r["currency"], "period_type": "monthly" if monthly else "annual", "period": r["year"], "yield_pct": round(float(r["yield_pct"]), 4),
                     "series": r["series"], "source": r["source"]})
    have = {(x["currency"], x["period_type"], x["period"]): x for x in client.table("gov_yields").select("*").execute().data}
    todo = [w for w in want if (w["currency"], w["period_type"], w["period"]) not in have
            or float(have[(w["currency"], w["period_type"], w["period"])]["yield_pct"]) != w["yield_pct"]
            or have[(w["currency"], w["period_type"], w["period"])]["series"] != w["series"]]
    for i in range(0, len(todo), 200):
        client.table("gov_yields").upsert(todo[i:i + 200], on_conflict="currency,period_type,period").execute()
    return {"read": len(want), "written": len(todo)}

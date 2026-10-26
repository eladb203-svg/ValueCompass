"""Build scripts/gov_yields.csv: annual-average 10-year government bond yield per currency and year (INSURANCE spec 2026-10-13_12-05, 'Government yield').

USD: Federal Reserve series DGS10 (FRED, daily, constant-maturity 10-year Treasury), annual average of the daily observations.
JPY: Japan Ministry of Finance, JGB benchmark 10-year yield (official daily history), annual average of the daily observations.
Cross-check (not stored as the yield): OECD monthly Japan long-term yield on FRED (IRLTLT01JPM156N), annual average.
No value is estimated: if a series cannot be fetched or a year has no observations the script stops with an error.
Run:  .venv/Scripts/python scripts/build_gov_yields.py   (set REQUESTS_CA_BUNDLE to an ASCII-path CA file on this machine)
"""
from __future__ import annotations

import csv
import io
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "gov_yields.csv"
VERSION = "v1"
YEARS = range(2016, date.today().year)               # the completed years (the scheduler runs this script when a year has ended)
UA = {"User-Agent": "Mozilla/5.0 (valuecompass research; eladb203@gmail.com)"}
SRC = {
    "USD": ("DGS10", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
            "Board of Governors of the Federal Reserve System (H.15) via FRED: Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity"),
    "JPY": ("JGB 10Y", "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv",
            "Japan Ministry of Finance: Japanese Government Bond interest rates, historical, 10-year"),
}
CROSS = ("IRLTLT01JPM156N", "https://fred.stlouisfed.org/graph/fredgraph.csv?id=IRLTLT01JPM156N")


def _get(url: str) -> str:
    r = requests.get(url, timeout=120, headers=UA)
    r.raise_for_status()
    return r.text


def usd_series(text: str) -> dict:
    out = defaultdict(list)
    for row in csv.DictReader(io.StringIO(text)):
        v = row["DGS10"].strip()
        if v in ("", "."):
            continue
        out[int(row["observation_date"][:4])].append(float(v))
    return out


def jpy_series(text: str) -> dict:
    out = defaultdict(list)
    lines = text.splitlines()
    hdr = next(i for i, ln in enumerate(lines) if ln.startswith("Date"))
    cols = lines[hdr].split(",")
    k = cols.index("10Y")
    for ln in lines[hdr + 1:]:
        p = ln.split(",")
        if len(p) <= k or p[k].strip() in ("", "-"):
            continue
        out[int(p[0].split("/")[0])].append(float(p[k]))
    return out


def main():
    retrieved = date.today().isoformat()
    rows = []
    cross = defaultdict(list)
    for row in csv.DictReader(io.StringIO(_get(CROSS[1]))):
        if row[CROSS[0]].strip() not in ("", "."):
            cross[int(row["observation_date"][:4])].append(float(row[CROSS[0]]))
    for cur, fn in (("USD", usd_series), ("JPY", jpy_series)):
        series, url, desc = SRC[cur]
        data = fn(_get(url))
        for y in YEARS:
            obs = data.get(y, [])
            if len(obs) < 200:  # a full year has about 245-250 business days
                sys.exit(f"STOP: {cur} {series} has only {len(obs)} observations for {y} (source {url}); not estimating")
            rows.append({"currency": cur, "year": y, "yield_pct": round(statistics.mean(obs), 4), "n_obs": len(obs), "series": series,
                         "source": desc, "url": url, "retrieved": retrieved, "version": VERSION,
                         "cross_check": (f"OECD/FRED {CROSS[0]} annual average {statistics.mean(cross[y]):.3f}" if cur == "JPY" and cross.get(y) else "")})
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()

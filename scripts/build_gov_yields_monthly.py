"""Add the latest complete monthly average of the US 10-year Treasury yield (FRED GS10) to scripts/gov_yields.csv (real-estate RP2 conservative cap rate, rules 2026-10-14_22-35).

The row carries year = 'YYYY-MM' and series = GS10; annual rows (DGS10 / JGB) are untouched, and an existing GS10 row is replaced (idempotent).
If FRED is not reachable the script stops without changing the file (the annual average is then used and flagged by the real-estate engine).
Run:  .venv/Scripts/python scripts/build_gov_yields_monthly.py   (set REQUESTS_CA_BUNDLE to an ASCII-path CA file on this machine)
"""
from __future__ import annotations

import csv
import io
import sys
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "gov_yields.csv"
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GS10"
UA = {"User-Agent": "Mozilla/5.0 (valuecompass research; eladb203@gmail.com)"}
SRC = "Board of Governors of the Federal Reserve System (H.15) via FRED: Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity, monthly average (GS10)"


def main() -> int:
    r = requests.get(URL, timeout=120, headers=UA)
    r.raise_for_status()
    obs = [(row["observation_date"], float(row["GS10"])) for row in csv.DictReader(io.StringIO(r.text)) if row["GS10"].strip() not in ("", ".")]
    last_d, last_v = obs[-1]
    month = last_d[:7]
    rows = list(csv.DictReader(OUT.open(encoding="utf-8", newline="")))
    fields = list(rows[0].keys())
    rows = [x for x in rows if x["series"] != "GS10"]
    rows.append({"currency": "USD", "year": month, "yield_pct": f"{last_v:.4f}", "n_obs": "1", "series": "GS10", "source": SRC, "url": URL, "retrieved": date.today().isoformat(),
                 "version": "v1", "cross_check": f"previous months: {', '.join(f'{d[:7]} {v:.2f}' for d, v in obs[-4:-1])}"})
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"GS10 {month}: {last_v:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())

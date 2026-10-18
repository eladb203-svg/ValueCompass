"""Fetch (cached) the 8-K exhibits of a ticker filed inside an explicit date window: python scripts/re_sup_fetch.py TICKER LABEL YYYY-MM-DD YYYY-MM-DD
LABEL is the cache tag, e.g. SUP2025Q2 -> scripts/cache/filings/RE_<T>_SUP2025Q2_<accession>_<exhibit>.txt (read by re_grep.py with the same tag)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.providers.realestate_facts import CIK_OVERRIDE  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.providers.sec_filings import FILINGS, _get_raw, html_to_text  # noqa: E402


def fetch_window(sec, t, label, lo, hi, pat=r"ex[-_]?99|supp|release|earnings|pr"):
    cik = (CIK_OVERRIDE.get(t) or sec.cik_for(t))[0]
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    rec = sub["filings"]["recent"]
    paths = []
    for form, filed, acc in zip(rec["form"], rec["filingDate"], rec["accessionNumber"]):
        if form != "8-K" or not (lo <= filed <= hi):
            continue
        a = acc.replace("-", "")
        idx = sec.get_json(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/index.json", f"idx_{a}.json")
        for it in idx["directory"]["item"]:
            n = it["name"]
            if n.lower().endswith((".htm", ".html")) and re.search(pat, n, re.I):
                out = FILINGS / f"RE_{t}_{label}_{a}_{n}.txt"
                if not out.exists():
                    raw = _get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{n}", f"{a}_{n}")
                    out.write_text(f"[source: {t} 8-K filed {filed}, accession {acc}, exhibit {n}]\n" + html_to_text(raw), encoding="utf-8")
                paths.append((out.name, filed))
    return paths


if __name__ == "__main__":
    s = SecClient()
    for p in fetch_window(s, sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]):
        print(p)
    print("requests:", s.requests_made)

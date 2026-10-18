"""Real-estate extraction helper: fetch / cache the 10-K text per ticker and fiscal year, and grep it.

Usage:
  python scripts/re_filings.py fetch O,PLD,... 2025,2023,2021      # downloads (cached) and converts the 10-Ks
  python scripts/re_filings.py grep O 2025 "regex" [width] [max]   # prints the matches with context
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.providers import sec_ixbrl as ix  # noqa: E402
from src.providers.realestate_facts import CIK_OVERRIDE  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.providers.sec_filings import FILINGS, _get_raw, html_to_text  # noqa: E402


def text_path(t: str, fy: int) -> Path:
    return FILINGS / f"RE_{t}_FY{fy}.txt"


def fetch(sec: SecClient, t: str, fy: int) -> Path:
    p = text_path(t, fy)
    if p.exists():
        return p
    cik = (CIK_OVERRIDE.get(t) or sec.cik_for(t))[0]
    ks = [k for k in ix.tenk_filings(sec, cik) if k["report_date"].year == fy or (k["report_date"].year == fy + 1 and k["report_date"].month <= 2)]
    if not ks:
        raise RuntimeError(f"no 10-K for {t} FY{fy}")
    k = ks[0]
    acc = k["accession"].replace("-", "")
    raw = _get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{k['primary']}", f"{acc}_{k['primary']}")
    p.write_text(f"[source: {t} 10-K FY{fy}, accession {k['accession']}, filed {k['filed']}, document {k['primary']}]\n" + html_to_text(raw), encoding="utf-8")
    return p


def load(t: str, fy: int) -> str:
    return text_path(t, fy).read_text(encoding="utf-8")


def grep(t: str, fy: int, pattern: str, width: int = 300, limit: int = 8) -> None:
    text = load(t, fy)
    n = 0
    for m in re.finditer(pattern, text, re.I):
        s, e = max(0, m.start() - width), min(len(text), m.end() + width)
        print(f"--- [{t} FY{fy} char {m.start():,}] " + re.sub(r"\s+", " ", text[s:e]))
        n += 1
        if n >= limit:
            break
    if n == 0:
        print(f"--- [{t} FY{fy}] no match for /{pattern}/ in {len(text):,} characters")


def supplemental(sec: SecClient, t: str, fy: int, window=("-01-15", "-03-31")) -> list:
    """Fetch the 8-K exhibits (EX-99.x) filed between mid-January and end-March of fy+1 (Q4 earnings release / supplemental package); returns the cached text paths."""
    import json as _json
    cik = (CIK_OVERRIDE.get(t) or sec.cik_for(t))[0]
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    rec = sub["filings"]["recent"]
    lo, hi = f"{fy + 1}{window[0]}", f"{fy + 1}{window[1]}"
    paths = []
    for form, filed, acc in zip(rec["form"], rec["filingDate"], rec["accessionNumber"]):
        if form != "8-K" or not (lo <= filed <= hi):
            continue
        a = acc.replace("-", "")
        idx = sec.get_json(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/index.json", f"idx_{a}.json")
        for it in idx["directory"]["item"]:
            n = it["name"]
            if n.lower().endswith((".htm", ".html")) and re.search(r"ex[-_]?99|supp|release|earnings|pr", n, re.I):
                out = FILINGS / f"RE_{t}_SUP{fy}_{a}_{n}.txt"
                if not out.exists():
                    raw = _get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{n}", f"{a}_{n}")
                    out.write_text(f"[source: {t} 8-K filed {filed}, accession {acc}, exhibit {n}]\n" + html_to_text(raw), encoding="utf-8")
                paths.append((str(out), filed, n))
    return paths


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        sec = SecClient()
        for t in sys.argv[2].split(","):
            for fy in sys.argv[3].split(","):
                try:
                    p = fetch(sec, t, int(fy))
                    print(t, fy, p.stat().st_size)
                except Exception as e:  # noqa: BLE001
                    print(t, fy, "FAILED", e)
        print("requests", sec.requests_made)
    elif sys.argv[1] == "sup":
        sec = SecClient()
        for t in sys.argv[2].split(","):
            for path, filed, n in supplemental(sec, t, int(sys.argv[3])):
                print(t, filed, n, Path(path).stat().st_size)
        print("requests", sec.requests_made)
    else:
        grep(sys.argv[2], int(sys.argv[3]), sys.argv[4], int(sys.argv[5]) if len(sys.argv) > 5 else 300, int(sys.argv[6]) if len(sys.argv) > 6 else 8)



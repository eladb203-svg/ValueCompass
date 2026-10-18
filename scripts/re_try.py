"""Try a regex on the normalized 10-K texts of one ticker: python scripts/re_try.py TICKER "regex" [years]"""
import re
import sys
from pathlib import Path

base = Path(__file__).resolve().parent / "cache" / "filings"
for fy in (sys.argv[3].split(",") if len(sys.argv) > 3 else ["2021", "2022", "2023", "2024", "2025"]):
    p = base / f"RE_{sys.argv[1]}_FY{fy}.txt"
    if not p.exists():
        continue
    t = re.sub(r"[\s|]+", " ", p.read_text(encoding="utf-8").replace(chr(0x200b), ""))
    m = re.search(sys.argv[2], t, re.S | re.I)
    print(fy, m.groups() if m else None)

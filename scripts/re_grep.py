"""Light grep over the cached real-estate filing texts: python scripts/re_grep.py TICKER FY|SUPyyyy "regex" [width] [max] [skip]
FY = 10-K text of that fiscal year; SUPyyyy = all cached 8-K exhibits (earnings release / supplemental) of that fiscal year, largest first."""
import re
import sys
from pathlib import Path

base = Path(__file__).resolve().parent / "cache" / "filings"
if sys.argv[2].startswith("SUP"):
    files = sorted(base.glob(f"RE_{sys.argv[1]}_{sys.argv[2]}_*.txt"), key=lambda q: -q.stat().st_size)
    text = "\n".join(f"<<{q.name}>>\n" + q.read_text(encoding="utf-8") for q in files).replace(chr(0x200b), "")
    tag = sys.argv[2]
else:
    text = (base / f"RE_{sys.argv[1]}_FY{sys.argv[2]}.txt").read_text(encoding="utf-8").replace(chr(0x200b), "")
    tag = "FY" + sys.argv[2]
width = int(sys.argv[4]) if len(sys.argv) > 4 else 250
limit = int(sys.argv[5]) if len(sys.argv) > 5 else 6
skip = int(sys.argv[6]) if len(sys.argv) > 6 else 0
n = 0
for i, m in enumerate(re.finditer(sys.argv[3], text, re.I)):
    if i < skip:
        continue
    s, e = max(0, m.start() - width), min(len(text), m.end() + width)
    print(f"--- [{sys.argv[1]} {tag} @{m.start():,}] " + re.sub(r"\s+", " ", text[s:e]))
    n += 1
    if n >= limit:
        break
if n == 0:
    print(f"--- [{sys.argv[1]} {tag}] no match for /{sys.argv[3]}/ ({len(text):,} chars)")

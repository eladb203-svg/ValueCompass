"""Compact dossier of the extraction items in a cached 10-K text: python scripts/re_dossier.py TICKER FY [width]"""
import re
import sys
from pathlib import Path

base = Path(__file__).resolve().parent / "cache" / "filings"
t = re.sub(r"[\s|]+", " ", (base / f"RE_{sys.argv[1]}_FY{sys.argv[2]}.txt").read_text(encoding="utf-8").replace(chr(0x200b), ""))
w = int(sys.argv[3]) if len(sys.argv) > 3 else 150
PAT = {
    "OCC": r"(?:\d\d\.\d|\d\d)% (?:leased|occupied)|occupancy (?:was|of|at|rate)[^.]{0,50}\d\d\.\d%|(?:leased|occupancy)[^.]{0,40}\d\d\.\d%[^.]{0,30}December 31, 20\d\d",
    "SAME": r"same[- ]?(?:property|store|center|community|facility|site)[^.]{0,80}(?:NOI|net operating income|revenue)[^.]{0,60}\d+\.\d+ ?%|(?:NOI|net operating income)[^.]{0,60}same[- ]?(?:property|store)[^.]{0,60}\d+\.\d+ ?%|(?:comparable|same)[- ](?:property|store|center)[^.]{0,60}(?:increase|decrease|growth)[^.]{0,40}\d+\.\d ?%",
    "FFO": r"(?:Nareit |NAREIT )?(?:FFO|Funds from operations)[^.$]{0,80} \$? ?\(?\d{1,3},\d{3}[,\d]* ?\)? \$? ?\(?\d{1,3},\d{3}",
    "TENANT": r"(?:largest|top (?:ten|10|five|\d+)) (?:tenants?|customers?|clients?)[^.]{0,120}|no (?:single )?(?:tenant|customer)[^.]{0,80}\d+(?:\.\d+)? ?%|1\. [A-Z][A-Za-z&.,' ]{2,30} [\d,.]+ [\d.]+ ?%",
    "FACIL": r"(?:available|remaining|unused|undrawn)[^.]{0,40}(?:capacity|borrowing|under)[^.]{0,80}\$ ?[\d.,]+ (?:billion|million)|\$ ?[\d.,]+ (?:billion|million)[^.]{0,60}(?:available|undrawn|unused)",
    "UNENC": r"unencumbered[^.]{0,120}\d+(?:\.\d+)? ?%|\d+(?:\.\d+)? ?%[^.]{0,80}unencumbered",
    "CAPEX": r"(?:recurring|maintenance) (?:capital|capex)[^.]{0,40}\$ ?\(?[\d.,]+|(?:tenant improvements|leasing commissions|tenant (?:allowances|inducements))[^.]{0,20}\$? ?\(?\d{1,3}[,.]\d",
    "YIELD": r"(?:stabilized|initial|projected|expected|untrended) (?:yield|return|ROI)[^.]{0,80}\d+(?:\.\d+)? ?%|\d+(?:\.\d+)? ?%[^.]{0,40}(?:stabilized|initial|expected) (?:yield|return)",
    "FV": r"(?:fair value|estimated fair value) of (?:our |the )?(?:real estate|properties|portfolio|investment propert)[^.]{0,100}",
}
for k, p in PAT.items():
    ms = list(re.finditer(p, t, re.I))
    print(f"## {k}: {len(ms)} matches")
    for m in ms[:3]:
        print("   ", t[max(0, m.start() - w // 2): m.end() + w][:w * 3])

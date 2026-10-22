"""Code stage K5a / K5a-2: which sections (text sections and notes) of the 10-K matching the engines' latest fiscal year were found, and their length, for every golden company.

Usage: python scripts/ai_sections_report.py [extra tickers]  -> markdown table; also scripts/ai_store/sections_report.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from src.ai.sections import ALL_IDS, section_report  # noqa: E402
from run_ai_k5a import ENGINE_OF, meta  # noqa: E402

tickers = list(ENGINE_OF) + sys.argv[1:]
rows = []
for t in tickers:
    end = str(meta(t)["end"][-1])[:10] if t in ENGINE_OF else None
    rows.append(section_report(t, end))
(ROOT / "scripts" / "ai_store").mkdir(exist_ok=True)
(ROOT / "scripts" / "ai_store" / "sections_report.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
print("| ticker | filing | " + " | ".join(ALL_IDS) + " |")
print("|---|---|" + "---|" * len(ALL_IDS))
for r in rows:
    if r["filing"] is None:
        print(f"| {r['ticker']} | not in cache | " + " | ".join("-" for _ in ALL_IDS) + " |")
        continue
    cells = []
    for s in ALL_IDS:
        x = r["sections"][s]
        if not x["found"]:
            cells.append("NOT FOUND")
            continue
        tag = ("T" if "trimmed" in x["flags"] else "") + ("X" if any(f.startswith("source_exhibit") for f in x["flags"]) else "") + ("F" if "topic_fallback" in x["flags"] else "")
        cells.append(f"{x['chars']:,}{tag}")
    print(f"| {r['ticker']} | {r['filing']['accession']} | " + " | ".join(cells) + " |")
print("\nT = trimmed, X = taken from an exhibit document, F = topic fallback")

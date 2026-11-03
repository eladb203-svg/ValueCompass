"""K6d-2 fixes 2026-11-02: a light cross-check of the XBRL figures that enter a score against the report itself: for the latest fiscal year of the given companies, does the value of revenue / net income / total
assets / equity appear in the text of the annual report (as printed: in thousands or in millions, with the thousands separator)? A figure that does not appear is a candidate for "wrong data" (source, year, unit).
Usage: python scripts/k17_facts_in_report.py TICKER ..."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai.checks import normalize  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.db import get_supabase_client  # noqa: E402

KEYS = ("revenue", "net_income", "total_assets", "equity", "eps_diluted")
c = get_supabase_client()
ids = {r["id"]: r["item_key"] for r in c.table("dictionary_items").select("id,item_key").execute().data}
for t in sys.argv[1:]:
    co = c.table("companies").select("id,symbol").eq("symbol", t.upper()).eq("exchange", "US").execute().data[0]
    facts = c.table("financial_facts").select("fiscal_year,item_id,value").eq("company_id", co["id"]).execute().data
    fp = c.table("filing_periods").select("fiscal_year,fiscal_year_end").eq("company_id", co["id"]).order("fiscal_year", desc=True).limit(1).execute().data[0]
    f = find_filing(t.upper(), str(fp["fiscal_year_end"]))
    text = normalize(f.text)
    out = []
    for x in facts:
        k = ids.get(x["item_id"])
        if x["fiscal_year"] != fp["fiscal_year"] or k not in KEYS or x["value"] is None:
            continue
        v = abs(float(x["value"]))
        if k == "eps_diluted":
            cands = [f"{v:.2f}"]
        else:
            cands = [f"{round(v / 1e3):,}", f"{round(v / 1e6):,}", f"{v / 1e6:,.1f}", f"{round(v / 1e9, 1):,.1f}"]
        ok = any(re.search(r"(?<![\d,.])" + re.escape(cd) + r"(?![\d,]|\.\d)", text) for cd in cands)
        out.append(f"{k} {'ok' if ok else 'NOT FOUND'}")
    print(f"{t.upper():6} FY{fp['fiscal_year']}: " + "; ".join(out))

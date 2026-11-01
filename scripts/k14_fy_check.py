"""K6d-2 fixes 2026-11-01: for every company of the database - the fiscal year end of the latest loaded period against the report that the extraction reads (old rule: the latest cached 10-K; new rule: the 10-K
of that fiscal year end). Prints the companies where the two differ."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai.sections import find_filing  # noqa: E402
from src.db import get_supabase_client  # noqa: E402

c = get_supabase_client()
cos = c.table("companies").select("id,symbol,processing_state").execute().data
periods = {}
for p in c.table("filing_periods").select("company_id,fiscal_year,fiscal_year_end").execute().data:
    if p["company_id"] not in periods or p["fiscal_year"] > periods[p["company_id"]]["fiscal_year"]:
        periods[p["company_id"]] = p
print(f"{'ticker':7}{'state':14}{'latest period end':19}{'old rule: latest cached 10-K':32}{'new rule: 10-K of that year'}")
diff = 0
for co in sorted(cos, key=lambda x: x["symbol"]):
    p = periods.get(co["id"])
    if not p:
        continue
    end = str(p["fiscal_year_end"])
    try:
        old = find_filing(co["symbol"])
        new = find_filing(co["symbol"], end)
    except Exception as e:   # noqa: BLE001
        print(co["symbol"], "error", e)
        continue
    o, n = (old.accession if old else None), (new.accession if new else None)
    if o != n:
        diff += 1
        print(f"{co['symbol']:7}{str(co['processing_state']):14}{end:19}{str(o):32}{n}")
print(f"companies checked: {len(periods)}; where the old rule reads another report than the engine's year: {diff}")

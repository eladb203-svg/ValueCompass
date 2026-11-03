"""K6d-2 fixes 2026-11-02: does any value of a bank or an insurer in the database come from the pages of the parent company alone (Schedule II / Parent Company Only / Condensed Financial Information of
Registrant)? For every bank and insurer: the parent spans of the latest report, every extraction row (any status) whose quote lies only inside one, and the rows that are approved.
Usage: python scripts/k17_parent_check.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai import parent_only as PO  # noqa: E402
from src.ai.checks import normalize  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.db import get_supabase_client  # noqa: E402

c = get_supabase_client()
cos = [x for x in c.table("companies").select("id,symbol,exchange,profile").in_("profile", ["BANK", "INSURANCE"]).execute().data if x["exchange"] == "US"]
fp = {}
from src.ai.db_stores import select_all  # noqa: E402

for p in select_all(c, "filing_periods", order="company_id"):
    if p["company_id"] not in fp or p["fiscal_year"] > fp[p["company_id"]]["fiscal_year"]:
        fp[p["company_id"]] = p
print(f"{'ticker':7}{'profile':11}{'parent pages':14}{'rows in them (approved/other)':32}items")
total = 0
for co in sorted(cos, key=lambda x: x["symbol"]):
    p = fp.get(co["id"])
    if not p:
        print(f"{co['symbol']:7}{co['profile']:11}(no loaded period)")
        continue
    f = find_filing(co["symbol"], str(p["fiscal_year_end"]))
    if f is None:
        print(f"{co['symbol']:7}{co['profile']:11}(no report in the cache)")
        continue
    text = normalize(f.text)
    spans = PO.parent_spans(text)
    hits = []
    if spans:
        for r in c.table("extraction_items").select("item_key,period,value,approval_status,exact_quote").eq("company_id", co["id"]).execute().data:
            q = normalize(r.get("exact_quote") or "")
            if len(q) >= 20 and PO.in_parent(text, q, spans):
                hits.append(r)
    appr = [h for h in hits if h["approval_status"] == "approved"]
    total += len(appr)
    print(f"{co['symbol']:7}{co['profile']:11}{len(spans):<14}{len(appr)}/{len(hits) - len(appr):<30}" + "; ".join(f"{h['item_key'][:28]} {h['period']} {h['value']} [{h['approval_status']}]" for h in hits[:6]))
print("approved rows read from the parent company alone:", total)

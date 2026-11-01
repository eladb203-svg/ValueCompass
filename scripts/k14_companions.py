"""K6d-2 fixes 2026-11-01: which companies of the database file their financial statements (or other parts) in a companion document of the inline-XBRL filing (<primary>_d2.htm ...), whether the document
is in the cache, and whether data is missing because of it (extraction calls that found no sections; assessments answered without sections). Usage: python scripts/k14_companions.py"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import get_supabase_client  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402

FILINGS = ROOT / "scripts" / "cache" / "filings"
c = get_supabase_client()
sec = SecClient()
cos = {x["id"]: x for x in c.table("companies").select("id,symbol,cik").execute().data}
latest = {}
for p in c.table("filing_periods").select("company_id,fiscal_year,accession").execute().data:
    if p["company_id"] not in latest or p["fiscal_year"] > latest[p["company_id"]]["fiscal_year"]:
        latest[p["company_id"]] = p
calls = {}
cp = ROOT / "scripts" / "ai_store" / "k6c" / "extraction" / "calls.jsonl"
if cp.exists():
    for ln in cp.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            if r.get("no_call"):
                calls.setdefault(r["ticker"], []).append(r["skill_id"])
ass = {}
for r in c.table("ai_assessments").select("company_id,question_id,state,evidence").eq("state", "insufficient_evidence").execute().data:
    ev = r["evidence"] or {}
    if any(f.startswith("section_not_found") for f in (ev.get("flags") or [])) or "primary_section_missing" in (ev.get("reasons") or []):
        ass.setdefault(cos[r["company_id"]]["symbol"], []).append(r["question_id"])
rows, errors = [], 0
for cid, p in sorted(latest.items(), key=lambda kv: cos[kv[0]]["symbol"]):
    co = cos[cid]
    if not co.get("cik"):
        continue
    acc = p["accession"].replace("-", "")
    try:
        idx = sec.get_json(f"https://www.sec.gov/Archives/edgar/data/{int(co['cik'])}/{acc}/index.json", f"idx_{acc}.json")
    except Exception:   # noqa: BLE001
        errors += 1
        continue
    names = [i["name"] for i in idx["directory"]["item"]]
    prim = next((n for n in names if re.fullmatch(r".*\d{8}(x10k)?\.htm", n, re.I) and not re.search(r"_d\d+", n)), None)
    comp = [n for n in names if re.search(r"_d\d+\.htm$", n, re.I)]
    if not comp:
        continue
    have = [n for n in comp if (FILINGS / f"{acc}_{n}").exists()]
    rows.append((co["symbol"], p["fiscal_year"], comp, have, calls.get(co["symbol"], []), ass.get(co["symbol"], [])))
print(f"{'ticker':7}{'FY':6}{'companion docs':32}{'in cache':10}{'extraction calls without sections':36}assessments without sections")
for r in rows:
    print(f"{r[0]:7}{r[1]:<6}{','.join(r[2])[:30]:32}{len(r[3])}/{len(r[2]):<8}{','.join(r[4])[:34]:36}{','.join(r[5])}")
print(f"companies with a companion document in the latest filing: {len(rows)} of {len(latest)} (index not readable: {errors}); not in cache: {sum(1 for r in rows if len(r[3]) < len(r[2]))}; "
      f"with data missing for the reason: {sum(1 for r in rows if r[4] or r[5])}")

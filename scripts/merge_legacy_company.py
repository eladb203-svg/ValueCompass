"""Merge a legacy company row into the company the pipeline made for the same stock (approved by the user, 2026-10-25, for MSFT: legacy id 1 -> id 10 on production).

    VC_DB_TARGET=prod .venv/Scripts/python scripts/merge_legacy_company.py <legacy_id> <target_id> [--apply]

Without --apply it only prints the plan. With --apply, in this order:
 1. backup to scripts/backup/ (the legacy row and every row that points at it, plus the counts of the target before);
 2. copy to the target ONLY the fields it lacks and the pipeline does not write (public_since_date, sector, industry); nothing the pipeline wrote is overwritten
    (company_name, cik, sic, exchange, profile ... stay);
 3. move the data_update_log rows to the target; merge the listing (the legacy listing is dropped when the target has one of the same symbol, and the target's exchange is written as the
    legacy upper-case name, e.g. NASDAQ; trading currency is filled when missing), otherwise the listing is moved;
 4. check that no row in any table points at the legacy company, and only then delete it; then check that the target's counts are unchanged except the log.
Stops at the first mismatch.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target, get_supabase_client  # noqa: E402

REFERENCING = ("ai_assessments", "ai_texts", "company_listings", "company_profile_history", "company_score_summary", "data_update_log", "extraction_items", "filing_periods",
               "financial_facts", "market_snapshot", "portfolio_holdings", "score_runs", "user_watchlist", "work_queue")
FILL = ("public_since_date", "sector", "industry")          # fields the pipeline does not write


def count(c, table: str, cid: int) -> int:
    return len(c.table(table).select("company_id" if table != "company_listings" else "id").eq("company_id", cid).execute().data)


def counts(c, cid: int) -> dict:
    return {t: count(c, t, cid) for t in REFERENCING}


def main(argv) -> int:
    legacy, target = int(argv[0]), int(argv[1])
    apply = "--apply" in argv
    c = get_supabase_client()
    print(f"[database target: {db_target()}] merge company {legacy} -> {target}" + ("" if apply else "  (plan only)"))
    old = c.table("companies").select("*").eq("id", legacy).execute().data
    new = c.table("companies").select("*").eq("id", target).execute().data
    if not old or not new:
        raise SystemExit("one of the companies does not exist")
    old, new = old[0], new[0]
    if old["symbol"] != new["symbol"]:
        raise SystemExit(f"symbols differ ({old['symbol']} / {new['symbol']}): not the same stock")
    before_old, before_new = counts(c, legacy), counts(c, target)
    leg_listings = c.table("company_listings").select("*").eq("company_id", legacy).execute().data
    tgt_listings = c.table("company_listings").select("*").eq("company_id", target).execute().data
    logs = c.table("data_update_log").select("*").eq("company_id", legacy).order("id").execute().data
    others = {t: n for t, n in before_old.items() if n and t not in ("company_listings", "data_update_log")}
    print("rows pointing at the legacy company:", {t: n for t, n in before_old.items() if n})
    if others:
        raise SystemExit(f"other tables hold rows of the legacy company {others}: not merged here, decide first")
    fill = {k: old[k] for k in FILL if old.get(k) is not None and new.get(k) is None}
    print("fields copied to the target:", fill, "| kept as the pipeline wrote them:", {k: new[k] for k in ("company_name", "exchange", "cik", "sic", "profile")})
    print("log rows moved:", [r["id"] for r in logs], "| legacy listings:", [(r["id"], r["symbol"], r["exchange"]) for r in leg_listings], "| target listings:", [(r["id"], r["symbol"], r["exchange"]) for r in tgt_listings])
    if not apply:
        return 0

    # 1. backup
    bdir = ROOT / "scripts" / "backup"
    bdir.mkdir(parents=True, exist_ok=True)
    path = bdir / f"merge_company_{legacy}_into_{target}_{db_target()}_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    path.write_text(json.dumps({"taken": datetime.now(timezone.utc).isoformat(), "target_db": db_target(), "companies_legacy": old, "company_listings_legacy": leg_listings, "data_update_log_legacy": logs,
                                "legacy_counts": before_old, "target_row_before": new, "target_listings_before": tgt_listings, "target_counts_before": before_new}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print("backup:", path.relative_to(ROOT))
    # 2. missing fields
    if fill:
        c.table("companies").update(fill).eq("id", target).execute()
    # 3. log rows and listings
    if logs:
        c.table("data_update_log").update({"company_id": target}).eq("company_id", legacy).execute()
    twin = next((t for t in tgt_listings if t["symbol"].upper() == old["symbol"].upper()), None)
    for lg in leg_listings:
        if twin and lg["symbol"].upper() == twin["symbol"].upper() and lg["exchange"].upper() == twin["exchange"].upper():
            c.table("company_listings").delete().eq("id", lg["id"]).execute()                      # the duplicate is dropped first: (symbol, exchange) is unique
            fields = {"exchange": lg["exchange"]}
            if twin.get("trading_currency") is None and lg.get("trading_currency"):
                fields["trading_currency"] = lg["trading_currency"]
            c.table("company_listings").update(fields).eq("id", twin["id"]).execute()
        else:
            c.table("company_listings").update({"company_id": target, "is_primary": False if tgt_listings else lg["is_primary"]}).eq("id", lg["id"]).execute()
    # 4. no reference left -> delete, then verify
    left = {t: n for t, n in counts(c, legacy).items() if n}
    if left:
        raise SystemExit(f"STOP: rows still point at the legacy company: {left}; nothing deleted")
    c.table("companies").delete().eq("id", legacy).execute()
    gone = not c.table("companies").select("id").eq("id", legacy).execute().data
    after = counts(c, target)
    expect = {**before_new, "data_update_log": before_new["data_update_log"] + len(logs)}
    ok = gone and after == expect
    print("legacy company deleted:", gone, "| target counts before:", before_new)
    print("                          target counts after :", after)
    print("verification:", "OK (unchanged except the log, +%d)" % len(logs) if ok else f"MISMATCH expected {expect}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""K6b section 0: rows that K5b matched get approval_source = k5b_confirmed (they were legacy_verified). Only that column changes; target = VC_DB_TARGET (default test)."""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target, get_supabase_client  # noqa: E402
from src.etl.extraction_store import load_rows  # noqa: E402
from src.etl.k5b_match import k5b_matched_keys  # noqa: E402


def counts(c) -> Counter:
    out, start = Counter(), 0
    while True:
        page = c.table("extraction_items").select("approval_status,approval_source").range(start, start + 999).execute().data
        out.update((r["approval_status"], r["approval_source"]) for r in page)
        if len(page) < 1000:
            return out
        start += 1000


def main(dry: bool) -> None:
    c = get_supabase_client()
    print("target:", db_target(), "| before:", dict(counts(c)))
    keys = k5b_matched_keys()
    ids = {r["symbol"]: r["id"] for r in c.table("companies").select("id,symbol").execute().data}
    changed = 0
    for engine in ("bank", "insurance", "realestate"):
        for ticker, rows in load_rows(engine).items():
            for r in rows:
                if (ticker, r.item_key, r.period) not in keys or ticker not in ids:
                    continue
                q = c.table("extraction_items").select("id,approval_source").eq("company_id", ids[ticker]).eq("item_key", r.item_key).eq("period", r.period or "").eq("document_ref", r.document_ref or "").execute().data
                for row in q:
                    if row["approval_source"] != "k5b_confirmed":
                        changed += 1
                        if not dry:
                            c.table("extraction_items").update({"approval_source": "k5b_confirmed"}).eq("id", row["id"]).execute()
    print("keys:", len(keys), "| rows set to k5b_confirmed:", changed, "(dry run)" if dry else "")
    print("after:", dict(counts(c)))


if __name__ == "__main__":
    main("--dry-run" in sys.argv)

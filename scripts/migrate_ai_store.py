"""K6c section 3: move the file store (scripts/ai_store) into the database, once. Idempotent (a second run changes nothing). Target = VC_DB_TARGET (default test).

  scoring answers   scripts/ai_store/k5b/scoring/<model>/v3.1/assessments.jsonl  -> ai_assessments  (the final K5 run; the older v1 file is superseded and not moved)
  AI extraction     scripts/ai_store/k5b/extraction/items.jsonl                    -> extraction_items (skill_id set; the original row is kept in ``control``)
  texts             scripts/ai_store/k5c/texts.jsonl                               -> ai_texts  (the current versions only: D1 prompt version 4 in both languages and the code-made D2 "t4";
                    older versions are the history of earlier attempts, and the older AI-written D2 is replaced by the code-made one)
Every row keeps model, prompt version / skill version and accession. Texts: what passed the checks is ``approved`` with ``human_reviewed = false`` (the Hebrew backgrounds are shown with the
"automatic translation" marker); what failed (JPM and O among the first five) is ``failed``. Rows of companies that are not in the database are skipped and listed.

    .venv/Scripts/python scripts/migrate_ai_store.py [--dry-run] [--skip-texts]
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai.db_stores import DbAiItemStore, DbAssessmentStore, DbTextStore  # noqa: E402
from src.ai.content import TextStore  # noqa: E402
from src.ai.store import AssessmentStore  # noqa: E402
from src.db import db_target, get_supabase_client  # noqa: E402
from src.repositories.extraction_repository import ExtractionRepository  # noqa: E402

STORE = ROOT / "scripts" / "ai_store"
ASSESSMENTS = STORE / "k5b" / "scoring" / "gemini-3.5-flash-lite" / "v3.1" / "assessments.jsonl"
ITEMS = STORE / "k5b" / "extraction" / "items.jsonl"
TEXTS = STORE / "k5c" / "texts.jsonl"
CURRENT = {("background", "4"), ("analysis", "t4")}


def jl(path: Path) -> list:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def item_keys(rows: list) -> dict:
    """The table key is (company, item_key, period, document_ref): items that share it (loan lines, balance-sheet lines, one item with several bases) get the basis in their key."""
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r["ticker"], r["item_key"], r["year"], r["accession"])].append(i)
    keys = {}
    for g in groups.values():
        for n, i in enumerate(g):
            r = rows[i]
            keys[i] = r["item_key"] if len(g) == 1 else f"{r['item_key']}|{r.get('basis') or ''}|{n}"
    return keys


def main(argv) -> int:
    dry = "--dry-run" in argv
    skip_texts = "--skip-texts" in argv                  # production: the texts are copied from test by copy_texts.py, after their checks are run again
    client = get_supabase_client()
    print(f"[database target: {db_target()}]" + ("  (dry run: nothing written)" if dry else ""))
    report, skipped = {}, defaultdict(set)

    # ---- scoring answers
    store = DbAssessmentStore(client, approved_only=False)
    c = Counter()
    for r in AssessmentStore(ASSESSMENTS).rows():           # the last line of a key wins
        if not store.co.has(r["ticker"]):
            skipped["assessments"].add(r["ticker"])
            continue
        old = store.get(r["ticker"], r["fiscal_year"], r["question_id"], r["prompt_version"])
        if old and old["answer"] == r["answer"] and old["state"] == r["state"] and old["approval_status"] == r["approval_status"]:
            c["unchanged"] += 1
            continue
        c["updated" if old else "inserted"] += 1
        if not dry:
            store.put(r)
    report["ai_assessments"] = dict(c)

    # ---- AI extraction items
    items, ds = jl(ITEMS), DbAiItemStore(client)
    keys = item_keys(items)
    repo = ExtractionRepository(client)
    c, by_company = Counter(), defaultdict(list)
    for i, r in enumerate(items):
        if not ds.co.has(r["ticker"]):
            skipped["extraction_items"].add(r["ticker"])
            continue
        by_company[ds.co.id(r["ticker"])].append(ds.to_db(r, keys[i], "ai_controls"))
    for cid, rows in by_company.items():
        old = {(x["item_key"], x["period"], x["document_ref"]): x for x in repo._all(cid) if x.get("skill_id")}
        todo = []
        for row in rows:
            o = old.get((row["item_key"], row["period"], row["document_ref"]))
            if o and o["approval_status"] == row["approval_status"] and (o["control"] or {}).get("k5b_row") == row["control"]["k5b_row"] and o.get("approval_source") == row["approval_source"]:
                c["unchanged"] += 1
                continue
            c["updated" if o else "inserted"] += 1
            todo.append(row)
        for j in range(0, 0 if dry else len(todo), 200):
            client.table("extraction_items").upsert(todo[j:j + 200], on_conflict="company_id,item_key,period,document_ref").execute()
    report["extraction_items (AI)"] = dict(c)

    # ---- texts
    ts = DbTextStore(client)
    c, per = Counter(), Counter()
    for r in ([] if skip_texts else TextStore(TEXTS).rows()):
        if (r["kind"], str(r["prompt_version"])) not in CURRENT:
            c["superseded version (not moved)"] += 1
            continue
        if not ts.co.has(r["ticker"]):
            skipped["ai_texts"].add(r["ticker"])
            continue
        ok = r.get("state") == "stored"
        row = {**r, "approval_status": "approved" if ok else "failed", "edited_by": r.get("edited_by", "ai"), "human_reviewed": False}
        old = ts.get(r["ticker"], r["fiscal_year"], r["kind"], r["prompt_version"], r.get("run_id") or "", r["language"])
        if old and old["approval_status"] == row["approval_status"] and old["text"] == row["text"] and old["state"] == row["state"]:
            c["unchanged"] += 1
            continue
        c["updated" if old else "inserted"] += 1
        per[(r["kind"], r["language"], row["approval_status"])] += 1
        if not dry:
            ts.put(row)
    report["ai_texts"] = dict(c)
    for k, v in report.items():
        print(f"  {k}: {v}")
    print("  texts written by kind/language/status:", {"/".join(k): v for k, v in sorted(per.items())})
    for k, v in skipped.items():
        print(f"  skipped (company not in the database) {k}: {sorted(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

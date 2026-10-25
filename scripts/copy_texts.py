"""K6c follow-up: copy the current D1 background texts (``ai_texts``, kind background, both languages, failed ones included) from the TEST database to another database (production), after
re-running the current code checks on each of them. Idempotent. No model call; nothing is translated or corrected here.

* A text that passes the current checks keeps its status (approved, ``human_reviewed`` as it is); a text that fails them is written as ``failed`` with the reasons in ``checks.recheck`` (it
  would not be shown). A text that was already ``failed`` stays failed. The English text is checked against the report sections (``check_background_en``), the Hebrew one against the
  English text (``check_translation``: numbers, names, script, length, glossary terms, moat phrase).
* The D2 analyses (kind analysis) are not copied: they are made by code from the score run of the target database (the ``analysis`` queue task).
* The company must exist in the target (run ``load_extraction.py`` / ``load`` first); others are listed and skipped.

    VC_DB_TARGET=prod .venv/Scripts/python scripts/copy_texts.py [--dry-run] [--tickers KO JPM ...]
The source is always the test project; the target is VC_DB_TARGET (refused when it is test).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai import content as C  # noqa: E402
from src.ai.db_stores import DbTextStore  # noqa: E402
from src.db import db_target, get_supabase_client  # noqa: E402
from src.pipeline import texts as TX  # noqa: E402
from src.pipeline.queue_runner import QueueRunner  # noqa: E402


def verify(row: dict, en_row: dict, ctx: dict) -> list:
    """The reasons the current code checks reject this stored text (empty = it passes)."""
    facts = ctx["facts"]
    if row["language"] == "en":
        raw = row.get("raw_answer") or json.dumps({"text_en": row["text"]}, ensure_ascii=False)
        return list(C.check_background_en(raw, facts, ctx["text_sent"], ctx["sent"], ctx["fiscal_year"]).reasons)
    return TX.check_edit(row["text"], (en_row or {}).get("text") or "", facts, (en_row or {}).get("competitors", []))


def main(argv) -> int:
    dry = "--dry-run" in argv
    only = {a.upper() for a in argv[argv.index("--tickers") + 1:] if not a.startswith("--")} if "--tickers" in argv else None
    if db_target() == "test":
        raise SystemExit("the target is the test project: set VC_DB_TARGET=prod")
    src_client = get_supabase_client("test")
    dst_client = get_supabase_client(db_target())
    src, dst = DbTextStore(src_client), DbTextStore(dst_client)
    runner = QueueRunner(src_client)
    print(f"[source: test -> target: {db_target()}]" + ("  (dry run: nothing written)" if dry else ""))
    rows = [r for r in src.rows() if r["kind"] == "background" and (not only or r["ticker"] in only)]
    c, ctxs, skipped, changed = Counter(), {}, set(), []
    for r in sorted(rows, key=lambda r: (r["ticker"], r["fiscal_year"], str(r["prompt_version"]), r["language"])):
        t = r["ticker"]
        if not dst.co.has(t):
            skipped.add(t)
            continue
        out = {k: v for k, v in r.items() if k not in ("id", "created_at", "score_run_id")}
        if r["state"] == "stored" and r["approval_status"] == "approved":
            if t not in ctxs:
                try:
                    ctxs[t] = runner.d1_context(t)
                except Exception as e:   # noqa: BLE001
                    ctxs[t] = e
            ctx = ctxs[t]
            if isinstance(ctx, Exception):
                reasons = [f"could not re-run the checks: {type(ctx).__name__}: {ctx}"[:200]]
            else:
                en = src.get(t, r["fiscal_year"], "background", r["prompt_version"], r.get("run_id") or "", "en")
                reasons = verify(r, en, ctx)
            if reasons:
                out.update({"state": "failed", "approval_status": "failed", "text": r["text"], "checks": {**(r.get("checks") or {}), "recheck": {"ok": False, "reasons": reasons}}})
                changed.append((t, r["language"], str(r["prompt_version"]), reasons[:3]))
            else:
                out["checks"] = {**(r.get("checks") or {}), "recheck": {"ok": True, "reasons": []}}
        old = dst.get(t, r["fiscal_year"], "background", r["prompt_version"], r.get("run_id") or "", r["language"])
        same = old and all(old.get(k) == out.get(k) for k in ("text", "state", "approval_status", "edited_by", "human_reviewed", "checks", "quotes", "model", "accession"))
        c[f"{r['language']} {out['approval_status']} v{r['prompt_version']} " + ("unchanged" if same else "written" if not old else "updated")] += 1
        if not dry and not same:
            dst.put(out)
    for k, v in sorted(c.items()):
        print(f"  {k}: {v}")
    for ch in changed:
        print("  DOWNGRADED by the current checks:", ch)
    if skipped:
        print("  skipped (company not in the target):", sorted(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

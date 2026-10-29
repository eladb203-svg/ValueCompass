"""Code stage K5b, section 5: the AI extraction (B1-B14) on a sample of companies, latest report only (including its comparative periods). Calls Gemini - needs GEMINI_API_KEY in .env.

Usage: python scripts/run_ai_k5b_extract.py [--companies JPM USB CB PGR O AMT PLD] [--rpm 20] [--rpd 70] [--out-root scripts/ai_store/k5b/extraction] [--no-calls]
Writes <out-root>/calls.jsonl (one record per skill call, raw reply kept), items.jsonl (one row per extracted item and year, with the checks, the control and the approval status),
approval_queue.md and run_log.json. A stored call is never asked again; --no-calls re-runs checks, controls and approvals from the stored replies (no API key needed).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.ai import b14 as B14  # noqa: E402
from src.ai import extract as E  # noqa: E402
from src.ai.client import GeminiClient, RateLimiter  # noqa: E402
from src.ai.prompt import extraction_blocks  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.scoring.ext_items import re_controls  # noqa: E402
from run_ai_k5a import ENGINE_OF, golden, meta  # noqa: E402

TZ = ZoneInfo("Asia/Jerusalem")
SAMPLE = ["JPM", "USB", "CB", "PGR", "O", "AMT", "PLD"]
BLOCKS_OF = {"BANK": ["EXT-BANK-CAP", "EXT-BANK-LOANS"], "INSURANCE": ["EXT-INS-CAP", "EXT-INS-INV"],
             "INCOME_REAL_ESTATE": ["EXT-RE-OPS", "EXT-RE-MAINT", "EXT-RE-VALUE", "EXT-RE-LIQ", "EXT-RE-UNENC", "EXT-RE-NAV", "EXT-RE-OPU", "EXT-RE-FFO", "EXT-PROFILE"]}
# B14: the items come from the Rulebook Part E dictionary (src/ai/b14.py): profile items without a tag value, not covered by B1-B13; all missing items of a report in one call
_DICT = None


def b14_items(t: str, m: dict) -> tuple:
    """-> (items, sections, counts) in item-years over the last 3 fiscal years of the report."""
    global _DICT
    if _DICT is None:
        _DICT = B14.parse_dictionary(B14.dictionary_path().read_text(encoding="utf-8"))
    return B14.b14_items(_DICT, ENGINE_OF[t], m["fins"], m["fy"][-3:])


def record_failure(calls, rep, skill_id: str, block: dict, err: Exception, items=None) -> None:
    """K6d-2: one extraction attempt per skill per annual report. A call that failed for good (the model client gave up) is stored as a failure, and a stored call is never asked again - a failure
    stays a failure until a new annual report. A run that only ran out of budget is not a failure of the call and is asked again."""
    from src.ai.content import BudgetExceeded
    if isinstance(err, BudgetExceeded) or "budget" in str(err).lower():
        return
    calls.put({"ticker": rep.ticker, "fiscal_year": rep.fiscal_year, "skill_id": skill_id, "version": block["version"], "prompt_version": E.PROMPT_VERSION, "accession": rep.filing.accession,
               "items_asked": [i["key"] for i in (items if items is not None else block["items"])], "section_flags": [], "model": "", "raw": None, "usage": {},
               "sections_sent": [], "no_call": f"failed: {str(err)[:120]}"})


def main(argv=None, client=None) -> None:
    """``client``: an injected model client (the K6c queue passes one with a request budget); without it a real client is built."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--companies", nargs="*")
    ap.add_argument("--model", default=None)
    ap.add_argument("--rpm", type=int, default=20)
    ap.add_argument("--rpd", type=int, default=70)
    ap.add_argument("--out-root", default=str(ROOT / "scripts" / "ai_store" / "k5b" / "extraction"))
    ap.add_argument("--no-calls", action="store_true")
    ap.add_argument("--no-b14", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out_root)
    calls = E.CallStore(out / "calls.jsonl")
    if not a.no_calls and client is None:
        client = GeminiClient(model=a.model, limiter=RateLimiter(rpm=a.rpm, rpd=a.rpd)) if a.model else GeminiClient(limiter=RateLimiter(rpm=a.rpm, rpd=a.rpd))
    blocks = extraction_blocks()
    all_rows, log = [], {"start": datetime.now(TZ).isoformat(timespec="seconds"), "companies": {}, "b14_counts": {}, "errors": {}}
    for t in a.companies or SAMPLE:
        m = meta(t)
        fy = int(m["fy"][-1][2:])
        filing = find_filing(t, str(m["end"][-1])[:10])
        rep = E.Report(t, m["name"], m["profile"], fy, filing)
        t0 = time.time()
        rows_by_block, per_block = {}, {}
        for sid in BLOCKS_OF.get(m["profile"], []):
            b = blocks[sid]
            before = client.calls if client else 0
            try:
                rec = E.ask_block(rep, b, client, calls) if client else (calls.get(t, fy, sid) or {"raw": None, "no_call": "not_asked"})
            except RuntimeError as e:
                log["errors"][f"{t}:{sid}"] = str(e)[:150]
                print(f"  FAILED {t} {sid}: {str(e)[:120]}", flush=True)
                record_failure(calls, rep, sid, b, e)
                continue
            rows, creasons = E.rows_from_call(rep, b, rec)
            rows_by_block[sid] = rows
            per_block[sid] = {"calls": (client.calls - before) if client else 0, "cached": bool(rec.get("_cached")), "call_reasons": creasons, "section_flags": rec.get("section_flags"),
                              "finish": (rec.get("usage") or {}).get("finish_reason"), "asked": rec.get("items_asked"), "rows": len(rows)}
            print(f"  {t} {sid}: {len(rows)} rows {creasons}", flush=True)
        if not a.no_b14:
            items, secs, counts = b14_items(t, m)
            log["b14_counts"][t] = {**counts, "items": [i["key"] for i in items], "sections": secs}
            if items:
                b = {**blocks["EXT-GENERAL"], "sections": secs}
                rows_all, parts = [], []
                for part, chunk in enumerate([items[i:i + 15] for i in range(0, len(items), 15)], 1):          # at most 15 items per call
                    try:
                        before = client.calls if client else 0
                        pid = "EXT-GENERAL" if part == 1 else f"EXT-GENERAL#{part}"
                        rec = E.ask_block(rep, b, client, calls, items=chunk, part=part) if client else (calls.get(t, fy, pid) or {"raw": None, "no_call": "not_asked"})
                        rows, creasons = E.rows_from_call(rep, b, rec, items=chunk)
                        rows_all += rows
                        parts.append({"calls": (client.calls - before) if client else 0, "cached": bool(rec.get("_cached")), "call_reasons": creasons, "asked": rec.get("items_asked"), "rows": len(rows)})
                        print(f"  {t} {pid}: {len(chunk)} items asked, {len(rows)} rows {creasons}", flush=True)
                    except RuntimeError as e:
                        log["errors"][f"{t}:EXT-GENERAL#{part}"] = str(e)[:150]
                        record_failure(calls, rep, pid, b, e, chunk)
                rows_by_block["EXT-GENERAL"] = rows_all
                per_block["EXT-GENERAL"] = {"calls": sum(p["calls"] for p in parts), "parts": parts, "rows": len(rows_all), "asked": [k for p in parts for k in (p["asked"] or [])]}
        # engine-based controls (real estate): computed on the engine inputs with this company's accepted items merged in
        engine_ctl = None
        if ENGINE_OF[t] == "realestate":
            from datetime import date as _d
            from src.scoring.realestate import REInputs
            inp = golden(t)["inputs"]
            ri = REInputs(ticker=t, name=t, fy=inp["fy"], end=[_d.fromisoformat(e) for e in inp["end"]], f=inp["f"], reg=inp["reg"], asset_type=inp.get("asset_type"),
                          utilization=None, noi_method=inp.get("noi_method"))
            engine_ctl = re_controls(ri, [r for rs in rows_by_block.values() for r in rs])
        ctls = {}
        for sid, rows in rows_by_block.items():
            c = E.apply_controls(blocks[sid], rows, engine_ctl)
            ctls[sid] = c
            per_block[sid]["control"] = None if not c else {"name": c["name"], "result": c["result"], "detail": c["detail"][:300]}
            all_rows += rows
        log["companies"][t] = {"seconds": round(time.time() - t0, 1), "profile": m["profile"], "blocks": per_block}
    write = E.write_items(out / "items.jsonl", all_rows)
    n = E.write_queue(out / "approval_queue.md", all_rows)
    log.update({"end": datetime.now(TZ).isoformat(timespec="seconds"), "calls": client.calls if client else 0, "retries": client.retries if client else 0,
                "failures": client.failures if client else 0, "prompt_tokens": client.prompt_tokens if client else 0, "output_tokens": client.output_tokens if client else 0,
                "rows": len(all_rows), "pending": n})
    (out / "run_log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    print("end", log["end"], "calls", log["calls"], "rows", len(all_rows), "pending", n, flush=True)


if __name__ == "__main__":
    main()

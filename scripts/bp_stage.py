"""BP stage runner (business profile: XBRL + BP-1, closed vocabulary, term translations, template rendering). TEST database only.

  bp_stage.py seed                 load the closed lists (business_vocab) and the T1 glossary (term_translations, approved / human); never overwrites an existing row
  bp_stage.py dry [T ...]          XBRL axes and the BP-1 prompt (size, sections) for the development set; no model call, nothing written
  bp_stage.py run [T ...] [--cap N]  the whole background task for each company (BP-1 only when its profile does not exist yet); the model cap of the stage is 25 attempts, enforced in code
  bp_stage.py refresh [T ...]      one more BP-1 call for a profile whose fields failed (the exact reasons in the first attempt); counts in the 25-attempt cap of the stage
  bp_stage.py recheck [T ...]      no model call: failed fields are checked again against the stored raw BP-1 answers with the current checks, then phrases and texts are done again
  bp_stage.py report               scripts/code_stage_bp_<date>.md (Hebrew) from what is stored
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.db import db_target, get_supabase_client  # noqa: E402

DEV = ["KO", "MSFT", "INTC", "JPM", "CB", "O", "AMT"]
STAGE_CAP = 25
USED_BEFORE_REFRESH = 12         # the first run of the stage used 12 of the 25 attempts (see scripts/ai_store/bp_calls.json); the cap of the stage is for all runs together
CALL_LOG = ROOT / "scripts" / "ai_store" / "bp_calls.json"


def make_builder(cap: int, with_model: bool):
    from src.ai.db_stores import DbAiItemStore, DbAssessmentStore, DbTextStore
    from src.bp.pipeline import BackgroundBuilder
    from src.bp.translate import GoogleTranslate
    from src.pipeline import scoring as S
    from src.pipeline.queue_runner import CappedGemini
    from src.pipeline.sec_source import PipelineSec
    client = get_supabase_client()
    gem = None
    if with_model:
        from src.ai.client import GeminiClient, RateLimiter
        gem = CappedGemini(GeminiClient(limiter=RateLimiter(rpm=12, rpd=450)), cap)
    S.seed_results(S.RESULTS_DIR)
    from src.pipeline.queue_runner import QueueRunner
    runner = QueueRunner(client, gemini=None, budget=0, pipeline_factory=None)
    b = BackgroundBuilder(client, DbAssessmentStore(client), DbTextStore(client), gemini=gem, translator=GoogleTranslate(), results_dir=S.RESULTS_DIR, sec=PipelineSec(),
                          ensure_filing=runner.ensure_filing)
    return b, gem


def cmd_seed() -> None:
    from src.bp.stores import TermStore, VocabStore
    from src.bp.vocab import Vocab
    b, _ = make_builder(0, False)
    print("vocab:", VocabStore(b.client).seed(Vocab.seed_rows()))
    print("glossary -> term_translations:", TermStore(b.client).seed_glossary())


def cmd_dry(tickers: list) -> None:
    from src.bp import bp1
    b, _ = make_builder(0, False)
    for t in tickers:
        ctx = b.load(t)
        xb = b.xbrl_fields(ctx["filing"], ctx["co"].get("cik"))
        ax = xb["axes"]
        print(f"== {t}  accession {ctx['filing'].accession}  FY{ctx['fy']}  filing {Path(ctx['filing'].path).name}")
        if ax:
            print(f"   total revenue {ax['total_revenue']}  end {ax['end']}  labels in linkbase: {ax['labels_found']}")
            for k, a in ax["axes"].items():
                print(f"   axis {k:18} found={a['found']!s:5} usable={xb['usable'][k]!s:5} coverage={a['coverage']} flags={a['flags']} items={[(i['name'], round(i['share'], 3)) for i in a['items'][:6]]} dropped={[d[0] for d in a['dropped']]}")
        secs, err = bp1.select_text(ctx["filing"].text, need_products=not xb["usable"].get("products_services"))
        wanted = bp1.fields_wanted(xb["usable"].get("segments", False), xb["usable"].get("products_services", False), xb["usable"].get("regions", False))
        prompt = bp1.build_prompt(b.vocab, ctx["filing"].accession, secs, wanted)
        print(f"   BP-1 sections {[(s, len(x)) for s, x in secs]} err={err} fields={wanted} prompt chars={len(prompt)}")


def cmd_run(tickers: list, cap: int, force: bool = False, seed_base: int = 0) -> None:
    b, gem = make_builder(cap, True)
    results = {}
    for t in tickers:
        before = gem.attempts
        try:
            results[t] = b.run(t, force_profile=force, seed_base=seed_base)
            results[t]["gemini_attempts"] = gem.attempts - before
        except Exception as e:   # noqa: BLE001
            results[t] = {"error": f"{type(e).__name__}: {e}", "gemini_attempts": gem.attempts - before}
        print(t, json.dumps(results[t], ensure_ascii=False, default=str))
    summary = {"gemini_attempts": gem.attempts, "cap": cap, "google_phrases": b.translator.calls, "google_key_present": b.translator.available, "per_company": results, "log": b.log}
    CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
    CALL_LOG.write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"Gemini request attempts this run: {gem.attempts} (cap {cap}); Google Translate phrases: {b.translator.calls}; key present: {b.translator.available}")


def cmd_refresh(tickers: list, cap: int, seed_base: int) -> None:
    """One more BP-1 call for a profile whose fields failed or no longer pass the current checks; then the phrases and the texts are done again."""
    b, gem = make_builder(cap, True)
    for t in tickers:
        before = gem.attempts
        try:
            r = b.refresh_failed(t, seed_base)
            r.update(b.run(t))
        except Exception as e:   # noqa: BLE001
            r = {"error": f"{type(e).__name__}: {e}"}
        r["gemini_attempts"] = gem.attempts - before
        print(t, json.dumps(r, ensure_ascii=False, default=str))
    print(f"Gemini request attempts this run: {gem.attempts} (cap {cap}); Google Translate phrases: {b.translator.calls}")
    prev = json.loads(CALL_LOG.read_text(encoding="utf-8")) if CALL_LOG.exists() else {}
    prev.setdefault("refresh_runs", []).append({"gemini_attempts": gem.attempts, "cap": cap, "tickers": tickers})
    CALL_LOG.write_text(json.dumps(prev, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("seed", "dry", "run", "refresh", "recheck", "report"))
    ap.add_argument("tickers", nargs="*")
    ap.add_argument("--cap", type=int, default=STAGE_CAP)
    ap.add_argument("--force", action="store_true", help="run: ask BP-1 again for a profile that exists (an operator decision; the automatic run never does)")
    ap.add_argument("--seed-base", type=int, default=0, help="run: seed offset of the BP-1 calls (a forced run of the same text uses other seeds)")
    a = ap.parse_args(argv)
    if db_target() != "test":
        print("This stage writes to the TEST database only (VC_DB_TARGET must be test).")
        return 2
    print(f"[database target: {db_target()}]")
    tickers = [t.upper() for t in a.tickers] or DEV
    if a.command == "seed":
        cmd_seed()
    elif a.command == "dry":
        cmd_dry(tickers)
    elif a.command == "recheck":
        b, _ = make_builder(0, False)
        for t in tickers:
            r = b.recheck_stored(t)
            r.update(b.run(t))
            print(t, json.dumps(r, ensure_ascii=False, default=str))
    elif a.command == "refresh":
        cmd_refresh(tickers, min(a.cap, STAGE_CAP - USED_BEFORE_REFRESH), a.seed_base)
    elif a.command == "run":
        cmd_run(tickers, min(a.cap, STAGE_CAP), a.force, a.seed_base)
    else:
        from bp_report import write_report
        print(write_report(ROOT / "scripts" / f"code_stage_bp_{date.today().isoformat()}.md", tickers))
    return 0


if __name__ == "__main__":
    sys.exit(main())

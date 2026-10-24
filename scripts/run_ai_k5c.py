"""Code stage K5c: peer groups, D1 background and D2 analysis for a set of companies.

Usage: python scripts/run_ai_k5c.py [--companies KO MSFT JPM CB O AMT INTC] [--no-calls] [--golden tests/golden/2026-10-20] [--answers <assessments.jsonl>] [--out-root scripts/ai_store/k5c]
--no-calls (dry run): builds the peer groups, RESULTS, PEERS and both prompts and saves them to <out-root>/dry_run.jsonl; nothing is sent. Without it the Gemini client is used; it counts every
request in the shared daily counter (cap 450) and refuses to start while another model-calling process is running.
Writes <out-root>/peer_groups.jsonl (always), texts.jsonl (real runs; the structure of the K6 table ai_texts).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.ai import assess, content as C, d2 as D2, d2_template as T  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.ai.store import AssessmentStore  # noqa: E402
from src.scoring import peer_source as PS, peers as P  # noqa: E402

DEV = ["KO", "MSFT", "JPM", "CB", "O", "AMT", "INTC"]
DEFAULT_ANSWERS = ROOT / "scripts" / "ai_store" / "k5b" / "scoring" / "gemini-3.5-flash-lite" / "v3.1" / "assessments.jsonl"
DEFAULT_GOLDEN = ROOT / "scripts" / "output_k5c" / "golden"          # the golden of the K5b run with the AI scoring answers (the current run)
PREVIOUS_GOLDEN = ROOT / "tests" / "golden" / "2026-10-20"                 # the previous run of every company (no AI answers) - for the CHANGE line


def stored_answer(store: AssessmentStore, ticker: str, fy: int, question: str) -> dict:
    """The stored scoring answer of one question (any prompt version), or {}."""
    rows = [r for r in store.rows() if r["ticker"] == ticker and r["fiscal_year"] == fy and r["question_id"] == question and r["state"] == "answered"]
    return rows[-1] if rows else {}


def d1_inputs(rec: dict, store: AssessmentStore) -> tuple:
    fy = int(rec["fiscal_year"][2:])
    a5, a7 = stored_answer(store, rec["ticker"], fy, "B3.1-Q5"), stored_answer(store, rec["ticker"], fy, "B3.2-Q5")
    ex5, ex7 = (a5.get("evidence") or {}).get("extra") or {}, (a7.get("evidence") or {}).get("extra") or {}
    moat_source = ex7.get("moat_source") or ("none" if a7.get("answer") == 0 else None)
    missing = [q for q, a in (("B3.1-Q5 (one_sentence)", ex5.get("one_sentence")), ("B3.2-Q5 (moat)", ex7.get("moat_source") or a7)) if not a]
    facts = C.d1_facts(rec["industry"], rec["metrics"].get("revenue"), "USD", fy, ex5.get("one_sentence"), a7.get("answer"), moat_source, (a7.get("evidence") or {}).get("reasoning"), company_name=rec["name"])
    return facts, moat_source, missing


def write_peer_groups(path: Path, rows: list) -> None:
    keep = {}
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                keep[(r["ticker"], r["run_id"])] = r
    for r in rows:
        keep[(r["ticker"], r["run_id"])] = r
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in keep.values()) + "\n", encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--companies", nargs="*", default=DEV)
    ap.add_argument("--no-calls", action="store_true")
    ap.add_argument("--golden", default=str(DEFAULT_GOLDEN))
    ap.add_argument("--previous", default=str(PREVIOUS_GOLDEN))
    ap.add_argument("--answers", default=str(DEFAULT_ANSWERS))
    ap.add_argument("--out-root", default=str(ROOT / "scripts" / "ai_store" / "k5c"))
    ap.add_argument("--rpm", type=int, default=20)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--kind", choices=["both", "d1", "d2"], default="both")
    ap.add_argument("--recheck", action="store_true", help="no calls: re-run the current checks on the stored raw answers of both D1 stages")
    ap.add_argument("--max-calls", type=int, default=20, help="hard cap on the model calls of the run (D1 only: D2 is written by code), enforced in code")
    ap.add_argument("--seed-shift", type=int, default=0, help="seed offset added to the calls (to retry failed texts with other seeds)")
    a = ap.parse_args(argv)
    out = Path(a.out_root)
    C.SEED_SHIFT = a.seed_shift
    records = PS.load_records(a.golden)
    answers = AssessmentStore(Path(a.answers))
    from run_ai_k5a import meta
    client = store = None
    store = C.TextStore(out / "texts.jsonl")
    if not a.no_calls and not a.recheck and a.kind in ("both", "d1"):
        from src.ai.client import GeminiClient, RateLimiter
        client = C.BudgetClient(GeminiClient(limiter=RateLimiter(rpm=a.rpm, rpd=450)), a.max_calls)
    dry, groups = [], []
    for t in a.companies:
        rec = next(r for r in records if r["ticker"] == t)
        j, _eng = PS.load_json(a.golden, t)
        run_id = f"{Path(a.golden).name}:{t}"
        g = P.peer_group(rec, records)
        pc = P.peer_percentiles(rec, g, records)
        try:
            prev_j, _ = PS.load_json(a.previous, t)
        except KeyError:
            prev_j = None
        inputs = D2.build_d2_inputs(j, rec, run_id, pc, prev_j, Path(a.previous).name if prev_j else None)
        results = inputs["results"]
        groups.append({"ticker": t, "fiscal_year": int(rec["fiscal_year"][2:]), "run_id": run_id, "peer_group": {"ids": g["ids"], "definition": g["definition"], "n": g["n"], "fallback": g["fallback"]}})
        facts, moat_source, missing = d1_inputs(rec, answers)
        m = meta(t)
        co = assess.Company(t, m["name"], m["profile"], int(rec["fiscal_year"][2:]), find_filing(t, str(m["end"][-1])[:10]))
        secs = {k: v.text for k, v in co.sections().items() if k in ("TXT-001", "TXT-003", "TXT-005") and v.found}
        secs_t, trimmed = C.trim_d1_sections(facts, co.filing.accession, secs)
        d1_prompt, _txt, sent = C.build_d1_prompt(facts, co.filing.accession, secs_t)
        d2_prompt = C.build_d2_prompt(inputs)
        if a.no_calls:
            dry.append({"ticker": t, "run_id": run_id, "peer_group": g, "peers": pc, "results": results, "d1_facts": facts, "d1_sections": sent, "d1_trimmed": trimmed, "d1_missing_inputs": missing, "d2_inputs": inputs,
                        "d1_prompt": d1_prompt, "d2_prompt": d2_prompt, "d1_prompt_chars": len(d1_prompt), "d2_prompt_chars": len(d2_prompt)})
            print(f"  {t}: group n={g['n']} fallback={g['fallback']}; D1 prompt {len(d1_prompt)} chars (sections {sent}, missing inputs {missing}); D2 prompt {len(d2_prompt)} chars", flush=True)
            continue
        if a.recheck:
            rr = C.recheck_background(co, facts, secs, store)
            print(f"  {t}: D1 en {rr['en'] and rr['en']['state']}, he {rr['he'] and rr['he']['state']} (recheck) {rr['he'] and rr['he']['checks']['reasons']}", flush=True)
            continue
        r1 = C.generate_background(co, facts, secs, client, store, force=a.force) if a.kind in ("both", "d1") else {"state": "-", "checks": {"reasons": []}}
        r2 = T.generate_analysis_template(t, co.fiscal_year, inputs, store, force=a.force) if a.kind in ("both", "d2") else {"state": "-", "checks": {"reasons": []}}
        print(f"  {t}: D1 {r1['state']} {r1['checks']['reasons']} {r1.get('regeneration_failed', '') or r1.get('stage_failed', '')}; D2 {r2['state']} {r2['checks']['reasons']}", flush=True)
    write_peer_groups(out / "peer_groups.jsonl", groups)
    if a.no_calls:
        (out / "dry_run.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in dry) + "\n", encoding="utf-8")
    print("done; calls", client.calls if client else 0)


if __name__ == "__main__":
    main()

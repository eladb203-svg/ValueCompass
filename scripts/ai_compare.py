"""Code stage K5a-2: compare a model's stored answers with the reference set (tests/ai_reference/reference_set_v2.csv).

Usage: python scripts/ai_compare.py <dir with assessments.jsonl and assessments_repeat.jsonl> [--details]
Agreement = run 1 equals `expected`, on the rows whose confidence is not low (`low` rows are reported separately). Close = equals `borderline_alt`. Stability = same state and
answer in both runs (all rows). "Insufficient evidence" or a rejected answer = not agreement (reported separately).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "tests" / "ai_reference" / "reference_set_v2.csv"


def load(path: Path) -> dict:
    out = {}
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                out[(r["ticker"], r["question_id"])] = r
    return out


def ans(r):
    if r is None:
        return "missing"
    return r["answer"] if r["state"] == "answered" else "insufficient"


def compare(directory: Path, ref_path: Path = REF) -> dict:
    ref = list(csv.DictReader(ref_path.open(encoding="utf-8")))
    r1, r2 = load(directory / "assessments.jsonl"), load(directory / "assessments_repeat.jsonl")
    rows, per_skill, per_company = [], defaultdict(Counter), defaultdict(Counter)
    for x in ref:
        k = (x["ticker"], x["question"])
        a1, a2 = ans(r1.get(k)), ans(r2.get(k))
        exp = int(x["expected"])
        alt = int(x["borderline_alt"]) if x["borderline_alt"] != "" else None
        low = x["confidence"] == "low"
        res = "match" if a1 == exp else ("close" if (alt is not None and a1 == alt) else ("insufficient" if a1 == "insufficient" else ("missing" if a1 == "missing" else "differ")))
        stable = (a1, a2) if a2 != "missing" else None
        rows.append({**x, "a1": a1, "a2": a2, "result": res, "low": low, "stable": (a1 == a2) if a2 != "missing" and a1 != "missing" else None,
                     "row": r1.get(k), "p": exp})
        for grp, key in ((per_skill, x["skill"]), (per_company, x["ticker"])):
            c = grp[key]
            c["n"] += 1
            if not low:
                c["n_eval"] += 1
                c["match"] += res == "match"
                c["close"] += res == "close"
            c["stable"] += bool(rows[-1]["stable"])
            c["stable_n"] += rows[-1]["stable"] is not None
    ev = [r for r in rows if not r["low"] and r["a1"] != "missing"]
    called = [r["row"] for r in rows if r["row"] and r["row"].get("usage")]
    quotes = [q for r in called for q in (r["evidence"].get("quotes") or [])]
    stable = [r for r in rows if r["stable"] is not None]
    summary = {
        "rows": len(rows), "answered_run1": sum(1 for r in rows if r["a1"] not in ("missing",)), "evaluated": len(ev),
        "match": sum(r["result"] == "match" for r in ev), "close": sum(r["result"] == "close" for r in ev),
        "insufficient": sum(r["a1"] == "insufficient" for r in rows), "missing_rows": sum(r["a1"] == "missing" for r in rows),
        "stable": sum(r["stable"] for r in stable), "stable_n": len(stable),
        "distribution": dict(sorted(Counter(r["a1"] for r in rows if isinstance(r["a1"], int)).items())),
        "checks_passed": sum(1 for r in called if r["evidence"].get("check_ok")), "calls": len(called),
        "quotes_found": sum(1 for q in quotes if q.get("found")), "quotes": len(quotes),
        "prompt_tokens": sum(r["usage"].get("prompt_tokens", 0) for r in called), "output_tokens": sum(r["usage"].get("output_tokens", 0) for r in called),
        "thought_tokens": sum(r["usage"].get("thought_tokens", 0) for r in called), "latency_s": round(sum(r["usage"].get("latency_s", 0) for r in called), 1),
        "attempts_gt1": sum(1 for r in called if r["usage"].get("attempts", 1) > 1),
        "low_rows": [(r["ticker"], r["question"], r["expected"], r["a1"]) for r in rows if r["low"]],
    }
    return {"summary": summary, "rows": rows, "per_skill": per_skill, "per_company": per_company}


def pct(a, b):
    return "-" if not b else f"{a / b:.0%}"


def main(argv):
    d = Path(argv[0])
    res = compare(d)
    s = res["summary"]
    print(f"rows {s['rows']} | evaluated (not low) {s['evaluated']} | match {s['match']} ({pct(s['match'], s['evaluated'])}) | match+close {s['match'] + s['close']} ({pct(s['match'] + s['close'], s['evaluated'])}) | "
          f"insufficient {s['insufficient']} | missing rows {s['missing_rows']}")
    print(f"stability {s['stable']}/{s['stable_n']} ({pct(s['stable'], s['stable_n'])}) | distribution {s['distribution']} | checks {s['checks_passed']}/{s['calls']} | quotes {s['quotes_found']}/{s['quotes']} | "
          f"latency {s['latency_s']}s | tokens in {s['prompt_tokens']:,} out {s['output_tokens']:,} thought {s['thought_tokens']:,} | calls with retries {s['attempts_gt1']}")
    print("\nper skill:")
    for k in sorted(res["per_skill"], key=lambda x: int(x[1:])):
        c = res["per_skill"][k]
        print(f"  {k}: match {c['match']}/{c['n_eval']} ({pct(c['match'], c['n_eval'])}), match+close {pct(c['match'] + c['close'], c['n_eval'])}, stable {c['stable']}/{c['stable_n']}")
    print("per company:")
    for k, c in res["per_company"].items():
        print(f"  {k}: match {c['match']}/{c['n_eval']} ({pct(c['match'], c['n_eval'])}), stable {c['stable']}/{c['stable_n']}")
    if "--details" in argv:
        print("\ndisagreements:")
        for r in res["rows"]:
            if r["result"] not in ("match", "close") and not r["low"]:
                e = (r["row"] or {}).get("evidence", {})
                q = (e.get("quotes") or [{}])[0].get("text", "")
                print(f"  {r['ticker']} {r['question']} expected {r['expected']} got {r['a1']}: {q[:100]!r} | {str(e.get('reasoning'))[:100]!r}")


if __name__ == "__main__":
    main(sys.argv[1:])

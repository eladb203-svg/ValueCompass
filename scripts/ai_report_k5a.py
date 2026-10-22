"""Code stage K5a: build the report tables from the AI store and from the golden comparison (before = tests/golden/2026-10-20, after = a golden made with VC_AI_STORE).

Usage: python scripts/ai_report_k5a.py <after_golden_dir>      -> prints markdown
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "scripts" / "ai_store"
G = ROOT / "tests" / "golden" / "2026-10-20"


def rows(name):
    p = STORE / name
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def short(s, n):
    s = " ".join(str(s or "").split())
    return (s[:n] + "…") if len(s) > n else s


def esc(s):
    return str(s).replace("|", "/")


def main(after_dir):
    main_rows, rep_rows = [r for r in rows("assessments.jsonl") if r["question_id"] != "CLS-1"], rows("assessments_repeat.jsonl")
    rep = {(r["ticker"], r["question_id"]): r for r in rep_rows}
    out = []
    by_t = defaultdict(list)
    for r in main_rows:
        by_t[r["ticker"]].append(r)
    out.append("### Answers per company and question\n")
    for t, rs in by_t.items():
        out.append(f"\n**{t}** (filing {rs[0]['accession']}, FY{rs[0]['fiscal_year']})\n")
        out.append("| Question | Answer run 1 | Run 2 | Same | Checks | First quote | Reasoning |")
        out.append("|---|---|---|---|---|---|---|")
        for r in sorted(rs, key=lambda x: x["question_id"]):
            r2 = rep.get((t, r["question_id"]))
            a1 = r["answer"] if r["state"] == "answered" else "insufficient"
            a2 = "-" if r2 is None else (r2["answer"] if r2["state"] == "answered" else "insufficient")
            e = r["evidence"]
            q = (e.get("quotes") or [{}])[0].get("text", "")
            chk = "ok" if e.get("check_ok") else "REJECTED: " + ",".join(sorted(set(e.get("reasons", []))))
            if "model_insufficient_evidence" in e.get("flags", []):
                chk = "ok (model: insufficient evidence)"
            if "primary_section_missing" in e.get("reasons", []):
                chk = "no call: section not found"
            out.append(f"| {r['question_id']} | {a1} | {a2} | {'yes' if a1 == a2 else 'NO'} | {esc(chk)} | {esc(short(q, 110))} | {esc(short(e.get('reasoning'), 150))} |")
    # aggregates
    tot_q = sum(len((r["evidence"].get("quotes") or [])) for r in main_rows)
    found_q = sum(1 for r in main_rows for q in (r["evidence"].get("quotes") or []) if q.get("found"))
    called = [r for r in main_rows if r["usage"]]
    answered = [r for r in main_rows if r["state"] == "answered"]
    checks_ok = sum(1 for r in called if r["evidence"].get("check_ok"))
    pairs = [(r, rep[(r["ticker"], r["question_id"])]) for r in main_rows if (r["ticker"], r["question_id"]) in rep and r["usage"]]
    same = sum(1 for a, b in pairs if (a["state"], a["answer"]) == (b["state"], b["answer"]))
    both_ans = [(a, b) for a, b in pairs if a["state"] == b["state"] == "answered"]
    diffs = Counter(abs(a["answer"] - b["answer"]) for a, b in both_ans)
    dist = Counter(r["answer"] for r in answered)
    lat = sum(r["usage"].get("latency_s", 0) for r in called)
    pt = sum(r["usage"].get("prompt_tokens", 0) for r in called)
    ot = sum(r["usage"].get("output_tokens", 0) for r in called)
    out.append("\n### Totals\n")
    out.append(f"- Rows: {len(main_rows)} (calls made: {len(called)}; no call because the primary section was not found: {len(main_rows) - len(called)}); answered {len(answered)}, insufficient evidence {len(main_rows) - len(answered)}.")
    out.append(f"- Check pass rate (rows with a call): {checks_ok}/{len(called)} = {checks_ok / max(1, len(called)):.0%}.")
    out.append(f"- Quotes found verbatim: {found_q}/{tot_q} = {found_q / max(1, tot_q):.0%} (all quotes, including those of rejected answers).")
    out.append(f"- Answer distribution (answered): {dict(sorted(dist.items()))}.")
    out.append(f"- Stability (same state and answer in both runs): {same}/{len(pairs)} = {same / max(1, len(pairs)):.0%}; among pairs answered twice: differences {dict(diffs)}.")
    out.append(f"- Model time (sum of call latencies, main run): {lat:.0f} s; tokens in {pt:,} / out {ot:,}.")
    # effect on the quality scores
    out.append("\n### Effect on the quality scores (before = golden 2026-10-20, after = golden with the AI answers)\n")
    out.append("| Company | Model | Criterion | Before: normalized | After: normalized | Before: min–max | After: min–max |")
    out.append("|---|---|---|---:|---:|---|---|")
    summ = ["\n| Company | Model | Score before | Score after | Range before | Range after | Coverage before | Coverage after | Buy price before | Buy price after |", "|---|---|---:|---:|---|---|---|---|---|---|"]
    idx = json.loads((G / "index.json").read_text(encoding="utf-8"))
    eng = {t: e for e in idx for t in idx[e]}
    for t in by_t:
        if t not in eng:
            continue
        a = json.loads((G / eng[t] / f"{t}.json").read_text(encoding="utf-8"))
        b = json.loads((Path(after_dir) / eng[t] / f"{t}.json").read_text(encoding="utf-8"))
        for key in ("buffett_quality", "graham_quality"):
            ca = {c["id"]: c for c in a[key]["criteria"]}
            for c in b[key]["criteria"]:
                x = ca[c["id"]]
                if (x["normalized"], x["range_min"], x["range_max"]) != (c["normalized"], c["range_min"], c["range_max"]):
                    f = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
                    out.append(f"| {t} | {key.split('_')[0]} | {c['id']} {c['name']} | {f(x['normalized'])} | {f(c['normalized'])} | {f(x['range_min'])}–{f(x['range_max'])} | {f(c['range_min'])}–{f(c['range_max'])} |")
            pk = "buffett_price" if key.startswith("buffett") else "graham_price"
            pa = (a.get(pk) or (a.get("pricing_file") or {}).get(pk) or {})
            pb = (b.get(pk) or (b.get("pricing_file") or {}).get(pk) or {})

            def bp(p):
                x = (p or {}).get("buy_price") or {}
                return x.get("buy_price") if isinstance(x, dict) else None
            g = lambda v: "-" if v is None else (f"{v:.2f}" if isinstance(v, (int, float)) else str(v))  # noqa: E731
            qa, qb = a[key], b[key]
            summ.append(f"| {t} | {key.split('_')[0]} | {g(qa['score'])} | {g(qb['score'])} | {g(qa['range_min'])}–{g(qa['range_max'])} | {g(qb['range_min'])}–{g(qb['range_max'])} | "
                        f"{qa['status']} {g(qa['coverage'])} | {qb['status']} {g(qb['coverage'])} | {g(bp(pa))} | {g(bp(pb))} |")
    out += summ
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])

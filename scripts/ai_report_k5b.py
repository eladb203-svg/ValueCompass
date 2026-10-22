"""Code stage K5b, section 2: report tables of the scoring run with template 3.1 (default) - agreement vs the reference set v2, against K5a-3 (v3.1), the four rows, rejections by reason, score impact.

Usage: python scripts/ai_report_k5b.py <after_golden_dir>   -> markdown on stdout
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ai_compare import compare  # noqa: E402
from ai_report_k5a2 import esc, impact, pct  # noqa: E402

M = "gemini-3.5-flash-lite"
DIRS = {"K5a-3 (v3.1)": ROOT / "scripts" / "ai_store" / "k5a3" / M / "v3.1", "K5b (3.1 default)": ROOT / "scripts" / "ai_store" / "k5b" / "scoring" / M / "v3.1"}
ROWS = [("AMT", "A8"), ("INTC", "A11"), ("UBER", "A13"), ("O", "A10")]


def table() -> str:
    out = ["| Run | Rows | Agreement (not low) | Agreement + close | Distribution 2/1/0 | Checks passed | Quotes found | Insufficient | Latency (sum) | Tokens in / out |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, d in DIRS.items():
        r = compare(d)["summary"]
        dist = r["distribution"]
        out.append(f"| {name} | {r['rows'] - r['missing_rows']}/108 | {r['match']}/{r['evaluated']} = {pct(r['match'], r['evaluated'])} | {r['match'] + r['close']}/{r['evaluated']} = {pct(r['match'] + r['close'], r['evaluated'])} | "
                   f"{dist.get(2, 0)}/{dist.get(1, 0)}/{dist.get(0, 0)} | {r['checks_passed']}/{r['calls']} = {pct(r['checks_passed'], r['calls'])} | {r['quotes_found']}/{r['quotes']} = {pct(r['quotes_found'], r['quotes'])} | "
                   f"{r['insufficient']} | {r['latency_s']:.0f} s | {r['prompt_tokens']:,} / {r['output_tokens']:,} |")
    return "\n".join(out)


def per_skill() -> str:
    res = {n: compare(d) for n, d in DIRS.items()}
    names = list(res)
    out = ["| Skill | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for sk in [f"A{i}" for i in range(1, 14)]:
        out.append(f"| {sk} | " + " | ".join(f"{res[n]['per_skill'][sk]['match']}/{res[n]['per_skill'][sk]['n_eval']}" for n in names) + " |")
    return "\n".join(out)


def four_rows() -> str:
    res = {n: {(r["ticker"], r["skill"]): r for r in compare(d)["rows"]} for n, d in DIRS.items()}
    out = ["| Company | Skill | Expected (alt) | " + " | ".join(f"{n}: answer / result" for n in res) + " | K5b reasoning (200) | K5b facts_check (200) |", "|---|---|---|" + "---|" * len(res) + "---|---|"]
    for t, sk in ROWS:
        cells, last = [], None
        for n, rows in res.items():
            x = rows.get((t, sk))
            cells.append("-" if not x else f"{x['a1']} / {x['result']}")
            last = x or last
        x = res["K5b (3.1 default)"].get((t, sk))
        e = ((x or {}).get("row") or {}).get("evidence", {})
        exp = f"{last['expected']}" + (f" ({last['borderline_alt']})" if last and last["borderline_alt"] else "") if last else "-"
        out.append(f"| {t} | {sk} | {exp} | " + " | ".join(cells) + f" | {esc(e.get('reasoning'), 200)} | {esc((e.get('extra') or {}).get('facts_check', ''), 200)} |")
    return "\n".join(out)


def rejections() -> str:
    rows = compare(DIRS["K5b (3.1 default)"])["rows"]
    c = Counter()
    out = ["| Company | Question | Reasons |", "|---|---|---|"]
    for r in rows:
        if r["a1"] == "insufficient":
            e = (r["row"] or {}).get("evidence", {})
            reasons = e.get("reasons") or ["model: insufficient evidence"]
            c.update(reasons)
            out.append(f"| {r['ticker']} | {r['question']} ({r['skill']}) | {', '.join(reasons)} |")
    return "\n".join(out) + "\n\nBy reason: " + ", ".join(f"{k} {v}" for k, v in c.most_common())


def disagreements() -> str:
    res = compare(DIRS["K5b (3.1 default)"])
    out = ["| Company | Question | Expected (alt) | Answer | First quote (150) | Reasoning (150) | facts_check (150) |", "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        if r["result"] in ("match", "close") or r["low"]:
            continue
        e = (r["row"] or {}).get("evidence", {})
        q = (e.get("quotes") or [{}])[0].get("text", "")
        out.append(f"| {r['ticker']} | {r['question']} ({r['skill']}) | {r['expected']}" + (f" ({r['borderline_alt']})" if r["borderline_alt"] else "") +
                   f" | {r['a1']} | {esc(q, 150)} | {esc(e.get('reasoning'), 150)} | {esc((e.get('extra') or {}).get('facts_check', ''), 150)} |")
    return "\n".join(out)


def a11_exposure() -> str:
    d = DIRS["K5b (3.1 default)"] / "assessments.jsonl"
    out = ["| Company | Answer | largest_exposure | attempts |", "|---|---|---|---|"]
    for ln in d.read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)
        if r["question_id"] == "G3.1-Q3":
            out.append(f"| {r['ticker']} | {r['answer']} ({r['state']}) | {(r['evidence'].get('extra') or {}).get('largest_exposure')} | {r['usage'].get('attempts')} / {len(r['usage'].get('finish_reasons') or [])} calls |")
    return "\n".join(out)


if __name__ == "__main__":
    after = sys.argv[1]
    print("## TABLE\n" + table())
    print("\n## PERSKILL\n" + per_skill())
    print("\n## FOURROWS\n" + four_rows())
    print("\n## A11\n" + a11_exposure())
    print("\n## REJECTIONS\n" + rejections())
    print("\n## DISAGREEMENTS\n" + disagreements())
    print("\n## IMPACT\n" + impact("x", after))

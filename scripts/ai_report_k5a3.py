"""Code stage K5a-3: report tables - K5a-2 vs version 3 (fixed) vs version 3.1, the 8 rejections, remaining disagreements (with facts_check), score impact.

Usage: python scripts/ai_report_k5a3.py <best: v3|v3.1> <after_golden_dir>   -> markdown on stdout
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ai_compare import compare  # noqa: E402
from ai_report_k5a2 import esc, impact, pct  # noqa: E402

M = "gemini-3.5-flash-lite"
DIRS = {"K5a-2 (v3, before the fixes)": ROOT / "scripts" / "ai_store" / "k5a2" / M, "v3 (fixed)": ROOT / "scripts" / "ai_store" / "k5a3" / M / "v3",
        "v3.1 (facts_check)": ROOT / "scripts" / "ai_store" / "k5a3" / M / "v3.1"}


def table():
    out = ["| Run | Rows | Agreement (not low) | Agreement + close | Stability | Distribution 2/1/0 | Checks passed | Quotes found | Insufficient | Latency (sum) | Tokens in / out |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, d in DIRS.items():
        if not (d / "assessments.jsonl").exists():
            out.append(f"| {name} | not run | | | | | | | | | |")
            continue
        r = compare(d)["summary"]
        dist = r["distribution"]
        out.append(f"| {name} | {r['rows'] - r['missing_rows']}/108 | {r['match']}/{r['evaluated']} = {pct(r['match'], r['evaluated'])} | {r['match'] + r['close']}/{r['evaluated']} = {pct(r['match'] + r['close'], r['evaluated'])} | "
                   f"{r['stable']}/{r['stable_n']} = {pct(r['stable'], r['stable_n'])} | {dist.get(2, 0)}/{dist.get(1, 0)}/{dist.get(0, 0)} | {r['checks_passed']}/{r['calls']} = {pct(r['checks_passed'], r['calls'])} | "
                   f"{r['quotes_found']}/{r['quotes']} = {pct(r['quotes_found'], r['quotes'])} | {r['insufficient']} | {r['latency_s']:.0f} s | {r['prompt_tokens']:,} / {r['output_tokens']:,} |")
    return "\n".join(out)


def per_skill():
    res = {n: compare(d) for n, d in DIRS.items() if (d / "assessments.jsonl").exists()}
    names = list(res)
    out = ["| Skill | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for sk in [f"A{i}" for i in range(1, 14)]:
        out.append(f"| {sk} | " + " | ".join(f"{res[n]['per_skill'][sk]['match']}/{res[n]['per_skill'][sk]['n_eval']}" for n in names) + " |")
    out += ["", "| Company | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for t in ["MSFT", "KO", "INTC", "UBER", "JPM", "CB", "PGR", "O", "AMT"]:
        out.append(f"| {t} | " + " | ".join(f"{res[n]['per_company'][t]['match']}/{res[n]['per_company'][t]['n_eval']}" for n in names) + " |")
    return "\n".join(out)


def rejections():
    """The rows rejected by the checks in K5a-2 and what happened to them in v3 (fixed) and v3.1."""
    base = compare(DIRS["K5a-2 (v3, before the fixes)"])["rows"]
    later = {n: {(r["ticker"], r["question"]): r for r in compare(d)["rows"]} for n, d in DIRS.items() if n != "K5a-2 (v3, before the fixes)" and (d / "assessments.jsonl").exists()}
    out = ["| Company | Question | K5a-2 reason | " + " | ".join(f"{n}: state / reasons" for n in later) + " |", "|---|---|---|" + "---|" * len(later)]
    for r in base:
        if r["a1"] != "insufficient":
            continue
        e = (r["row"] or {}).get("evidence", {})
        cells = []
        for n, rows in later.items():
            x = rows.get((r["ticker"], r["question"]))
            ev = (x["row"] or {}).get("evidence", {}) if x else {}
            cells.append("-" if not x else f"{x['a1']} / {','.join(ev.get('reasons') or ['ok']) }")
        out.append(f"| {r['ticker']} | {r['question']} | {','.join(e.get('reasons') or ['model: insufficient evidence'])} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def disagreements(variant):
    res = compare(DIRS[variant])
    out = ["| Company | Question | Expected (alt) | Answer | First quote (150) | Reasoning (150) | facts_check |", "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        if r["result"] in ("match", "close") or r["low"]:
            continue
        e = (r["row"] or {}).get("evidence", {})
        q = (e.get("quotes") or [{}])[0].get("text", "")
        fc = (e.get("extra") or {}).get("facts_check", "")
        out.append(f"| {r['ticker']} | {r['question']} ({r['skill']}) | {r['expected']}" + (f" ({r['borderline_alt']})" if r["borderline_alt"] else "") +
                   f" | {r['a1']}{'' if r['a1'] not in ('insufficient',) else ' (' + ','.join((e.get('reasons') or ['model']))+ ')'} | {esc(q, 150)} | {esc(e.get('reasoning'), 150)} | {esc(fc, 150)} |")
    return "\n".join(out)


if __name__ == "__main__":
    best, after = sys.argv[1], sys.argv[2]
    name = "v3 (fixed)" if best == "v3" else "v3.1 (facts_check)"
    print("## TABLE\n" + table())
    print("\n## PERSKILL\n" + per_skill())
    print("\n## REJECTIONS\n" + rejections())
    print("\n## DISAGREEMENTS " + name + "\n" + disagreements(name))
    print("\n## IMPACT " + name + "\n" + impact("x", after))

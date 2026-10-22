"""Code stage K5a-2: report tables - model comparison, disagreements with the reference set (best model), score impact.

Usage: python scripts/ai_report_k5a2.py <best-model-name> <after_golden_dir> model1 model2 ...   -> markdown on stdout
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ai_compare import compare  # noqa: E402

K = ROOT / "scripts" / "ai_store" / "k5a2"
G = ROOT / "tests" / "golden" / "2026-10-20"


def pct(a, b):
    return "-" if not b else f"{a / b:.0%}"


def esc(s, n):
    s = " ".join(str(s or "").split()).replace("|", "/")
    return s[:n] + ("…" if len(s) > n else "")


def models_table(models):
    out = ["| Model | Status | Agreement (not low) | Agreement + close | Stability | Distribution 2/1/0 | Checks passed | Quotes found | Insufficient / rejected | Latency (sum) | Tokens in / out / thought | Retries | Failed calls | Start – end (Israel) |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in models:
        d = K / m
        if not (d / "assessments.jsonl").exists():
            out.append(f"| {m} | not run | | | | | | | | | | | | |")
            continue
        r = compare(d)["summary"]
        logs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("run_log*.json"))]
        start = min((l["start"] for l in logs), default="?")
        end = max((l.get("end", "?") for l in logs), default="?")
        retries = sum(l.get("retries", 0) for l in logs)
        failed = sum(l.get("failed_calls", 0) for l in logs)
        dist = r["distribution"]
        status = "complete" if not r["missing_rows"] else f"PARTIAL sample: {r['rows'] - r['missing_rows']}/108 rows in run 1"
        out.append(f"| {m} | {status} | {r['match']}/{r['evaluated']} = {pct(r['match'], r['evaluated'])} | {r['match'] + r['close']}/{r['evaluated']} = {pct(r['match'] + r['close'], r['evaluated'])} | "
                   f"{r['stable']}/{r['stable_n']} = {pct(r['stable'], r['stable_n'])} | {dist.get(2, 0)}/{dist.get(1, 0)}/{dist.get(0, 0)} | {r['checks_passed']}/{r['calls']} = {pct(r['checks_passed'], r['calls'])} | "
                   f"{r['quotes_found']}/{r['quotes']} = {pct(r['quotes_found'], r['quotes'])} | {r['insufficient']} | {r['latency_s']:.0f} s | {r['prompt_tokens']:,} / {r['output_tokens']:,} / {r['thought_tokens']:,} | {retries} | {failed} | {start[11:19]} – {end[:10]} {end[11:19]} |")
    return "\n".join(out)


def per_skill(models):
    out = ["| Skill | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    res = {m: compare(K / m) for m in models if (K / m / "assessments.jsonl").exists()}
    for sk in [f"A{i}" for i in range(1, 14)]:
        cells = []
        for m in models:
            if m not in res:
                cells.append("-")
                continue
            c = res[m]["per_skill"][sk]
            cells.append(f"{c['match']}/{c['n_eval']}")
        out.append(f"| {sk} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def disagreements(model):
    res = compare(K / model)
    out = ["| Company | Question | Expected (alt) | Answer | First quote (150) | Reasoning (150) | Reference rationale |", "|---|---|---|---|---|---|---|"]
    for r in res["rows"]:
        if r["result"] in ("match", "close") or r["low"]:
            continue
        e = (r["row"] or {}).get("evidence", {})
        q = (e.get("quotes") or [{}])[0].get("text", "")
        out.append(f"| {r['ticker']} | {r['question']} ({r['skill']}) | {r['expected']}" + (f" ({r['borderline_alt']})" if r["borderline_alt"] else "") +
                   f" | {r['a1']} | {esc(q, 150)} | {esc(e.get('reasoning'), 150)} | {esc(r['rationale'], 110)} |")
    return "\n".join(out)


def impact(model, after_dir):
    from ai_report_k5a import STORE  # noqa: F401  (module import only for the shared helpers)
    idx = json.loads((G / "index.json").read_text(encoding="utf-8"))
    eng = {t: e for e in idx for t in idx[e]}
    tickers = ["MSFT", "KO", "INTC", "UBER", "JPM", "CB", "PGR", "O", "AMT"]
    f = lambda v: "-" if v is None else (f"{v:.2f}" if isinstance(v, (int, float)) else str(v))  # noqa: E731
    out = ["| Company | Model | Score before | Score after | Range before | Range after | Coverage before / after | Buy price before | Buy price after |", "|---|---|---:|---:|---|---|---|---:|---:|"]
    crit = ["| Company | Model | Criterion | Normalized before | Normalized after | Min–max before | Min–max after |", "|---|---|---|---:|---:|---|---|"]
    for t in tickers:
        a = json.loads((G / eng[t] / f"{t}.json").read_text(encoding="utf-8"))
        b = json.loads((Path(after_dir) / eng[t] / f"{t}.json").read_text(encoding="utf-8"))
        for key in ("buffett_quality", "graham_quality"):
            qa, qb = a[key], b[key]
            pk = key.replace("quality", "price")

            def bp(x):
                p = x.get(pk) or (x.get("pricing_file") or {}).get(pk) or {}
                y = p.get("buy_price") or {}
                return y.get("buy_price") if isinstance(y, dict) else None
            out.append(f"| {t} | {key.split('_')[0]} | {f(qa['score'])} | {f(qb['score'])} | {f(qa['range_min'])}–{f(qa['range_max'])} | {f(qb['range_min'])}–{f(qb['range_max'])} | "
                       f"{qa['status']} {f(qa['coverage'])} / {qb['status']} {f(qb['coverage'])} | {f(bp(a))} | {f(bp(b))} |")
            ca = {c["id"]: c for c in qa["criteria"]}
            for c in qb["criteria"]:
                x = ca[c["id"]]
                if (x["normalized"], x["range_min"], x["range_max"]) != (c["normalized"], c["range_min"], c["range_max"]):
                    crit.append(f"| {t} | {key.split('_')[0]} | {c['id']} {c['name']} | {f(x['normalized'])} | {f(c['normalized'])} | {f(x['range_min'])}–{f(x['range_max'])} | {f(c['range_min'])}–{f(c['range_max'])} |")
    return "\n".join(out) + "\n\n" + "\n".join(crit)


if __name__ == "__main__":
    best, after, models = sys.argv[1], sys.argv[2], sys.argv[3:]
    print("## MODELS\n" + models_table(models))
    print("\n## PERSKILL\n" + per_skill(models))
    print("\n## DISAGREEMENTS " + best + "\n" + disagreements(best))
    print("\n## IMPACT " + best + "\n" + impact(best, after))

"""K6c section 4.5: the scores of the 54 golden companies, written to the database and read back, equal the golden files (score, range, coverage, every criterion and sub-item, fair value,
price score, buy price). No AI (the golden is the no-AI run). Writing a result twice makes no new run. Target = VC_DB_TARGET (default test).

    .venv/Scripts/python scripts/k6c_score_identity.py [--golden tests/golden/2026-10-20] [--out scripts/output_k6c/score_identity.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target, get_supabase_client  # noqa: E402
from src.repositories.company_repository import CompanyRepository  # noqa: E402
from src.repositories.score_repository import ScoreRepository, compare_with_golden  # noqa: E402


def main(argv) -> int:
    golden_dir = Path(argv[argv.index("--golden") + 1]) if "--golden" in argv else ROOT / "tests" / "golden" / "2026-10-20"
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    client = get_supabase_client()
    companies, scores = CompanyRepository(client), ScoreRepository(client)
    print(f"[database target: {db_target()}]")
    report, ok = {}, 0
    files = sorted(p for p in golden_dir.glob("*/*.json"))
    for p in files:
        g = json.loads(p.read_text(encoding="utf-8"))
        t = g.get("ticker") or p.stem
        row = companies.get_by_symbol(t, "US")
        if not row:
            report[t] = {"error": "company not in the database"}
            continue
        run_id, state = scores.write_result(row["id"], g)
        again = scores.write_result(row["id"], g)[1]
        diffs = compare_with_golden(scores.read_latest(row["id"]), g)
        report[t] = {"engine": p.parent.name, "run_id": run_id, "first_write": state, "second_write": again, "differences": diffs}
        ok += (not diffs and again == "unchanged")
        print(f"  {t:<6}{p.parent.name:<13}{state:<10}second write: {again:<10}differences: {len(diffs)}" + (f"  {diffs[:2]}" if diffs else ""))
    print(f"{ok}/{len(files)} companies: database = golden and a second write changes nothing")
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

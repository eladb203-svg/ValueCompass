"""K6d-2 fixes 2026-11-01: run the keyword depth steps (no model) for REITs / insurers already in the database, then re-score. Usage: python scripts/k13_depth.py TICKER ..."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import vc  # noqa: E402
from src.ai import keyword_depth as KD  # noqa: E402
from src.ai import recheck as RC  # noqa: E402

runner = vc.make_runner(0)
for t in sys.argv[1:]:
    co = runner.companies.get_by_symbol(t.upper(), "US")
    sec = runner.pipeline_factory().sec
    if co["profile"] == "INCOME_REAL_ESTATE":
        out = KD.run(runner.client, runner.item_store, sec, t.upper())
    else:
        out = KD.run_insurer(runner.client, runner.item_store, sec, t.upper())
    print(t, out)
    if out["rows"]:
        print("  recheck applied:", RC.recheck(runner.client, t.upper(), apply=True)["applied"])
    runner.enqueue(co["id"], "score", None, "first", 1)
    vc.print_report(runner.run(50, only={t.upper()}))

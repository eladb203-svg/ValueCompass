"""Owner decision 2026-11-05 (item 5): run the queued ai_assess tasks of the 8 REITs only (new REIT wording), model attempts capped at 150."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts")); sys.stdout.reconfigure(encoding="utf-8")
import vc
runner = vc.make_runner(150)
rep = runner.run(max_tasks=40, only={"SPG", "FRT", "ARE", "PLD", "BXP", "EQR", "PSA", "EQIX"})
print(rep)
print("model request attempts:", runner.gemini.attempts)

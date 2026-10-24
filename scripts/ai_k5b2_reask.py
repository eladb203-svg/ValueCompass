"""Code stage K5b-2: ask again ONE scoring question (default INTC A11 = G3.1-Q3) with the corrected checks / template and store the new answer in the K5b scoring store (last row wins).

Usage: python scripts/ai_k5b2_reask.py [--ticker INTC] [--question G3.1-Q3]   (one process at a time; the shared daily counter applies)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.ai import assess  # noqa: E402
from src.ai.client import GeminiClient, RateLimiter  # noqa: E402
from src.ai.prompt import scoring_skills  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.ai.store import AssessmentStore  # noqa: E402
from run_ai_k5a import meta  # noqa: E402

STORE = ROOT / "scripts" / "ai_store" / "k5b" / "scoring" / "gemini-3.5-flash-lite" / "v3.1" / "assessments.jsonl"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="INTC")
    ap.add_argument("--question", default="G3.1-Q3")
    a = ap.parse_args()
    m = meta(a.ticker)
    co = assess.Company(a.ticker, m["name"], m["profile"], int(m["fy"][-1][2:]), find_filing(a.ticker, str(m["end"][-1])[:10]))
    client = GeminiClient(limiter=RateLimiter(rpm=20, rpd=450))
    store = AssessmentStore(STORE)
    old = store.get(a.ticker, co.fiscal_year, a.question, assess.prompt_version_of(scoring_skills()[a.question]))
    row = assess.ask(co, scoring_skills()[a.question], client, store, assess.Stats(), force=True)
    print("old:", old and (old["answer"], old["state"], old["evidence"]["reasons"]))
    print("new:", row["answer"], row["state"], row["evidence"]["reasons"], row["evidence"]["extra"].get("largest_exposure"), "| calls", client.calls, "| attempts", row["usage"].get("attempts"))
    print("reasoning:", row["evidence"]["reasoning"])


if __name__ == "__main__":
    main()

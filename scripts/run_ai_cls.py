"""Code stage K5a: C1 / CLS-1 (router tier 3) for companies whose industry tiers 1-2 did not decide (default: ABNB, BKNG). Calls Gemini.

Prints the router result before the AI answer (classification_pending) and after it. Stores the C1 row in scripts/ai_store/assessments.jsonl.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.ai import assess  # noqa: E402
from src.ai.client import GeminiClient  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.ai.store import AssessmentStore  # noqa: E402
from src.providers import industry_provider  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.scoring.router import INDUSTRIES, AIAnswer  # noqa: E402
from router_runner import route_company  # noqa: E402


def main(argv):
    tickers = [a.upper() for a in argv] or ["ABNB", "BKNG"]
    industry_provider.use_fixed(ROOT / "scripts" / "provider_industry_2026-10-20.csv")
    sec, client, store, stats = SecClient(), GeminiClient(), AssessmentStore(), assess.Stats()
    out = {}
    for t in tickers:
        before = route_company(sec, t)
        cik, title = sec.cik_for(t)
        sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
        filing = find_filing(t)
        fy = int(filing.report_date[:4]) if filing.report_date else 2025
        co = assess.Company(t, title, before.profile, fy, filing)
        row = assess.classify_industry(co, sub.get("sic"), sub.get("sicDescription"), industry_provider.get_industry(t), client, store, stats, list(INDUSTRIES))
        ind = (row["evidence"].get("extra") or {}).get("industry")
        ai = AIAnswer(ind, (row["evidence"].get("quotes") or [{}])[0].get("text", "")) if ind else None
        after = route_company(sec, t, ai=ai)
        out[t] = {"sic": sub.get("sic"), "provider_industry": industry_provider.get_industry(t), "before": {"industry": before.industry, "status": before.classification.status, "profile": before.profile},
                  "ai": {"state": row["state"], "industry": ind, "quote": (row["evidence"].get("quotes") or [{}])[0].get("text"), "reasoning": row["evidence"].get("reasoning"),
                         "checks_ok": row["evidence"].get("check_ok"), "reasons": row["evidence"].get("reasons")},
                  "after": {"industry": after.industry, "status": after.classification.status, "tier": after.classification.tier, "profile": after.profile, "reasons": after.classification.reasons}}
        print(json.dumps({t: out[t]}, indent=1, ensure_ascii=False), flush=True)
    (ROOT / "scripts" / "ai_store" / "cls1_results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print("calls", stats.calls, "cached", stats.cached)


if __name__ == "__main__":
    main(sys.argv[1:])

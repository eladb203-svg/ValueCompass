"""Code stage K5a: run the AI skills on the sample companies, twice (stability). Calls Gemini - needs GEMINI_API_KEY in .env.

Usage: python scripts/run_ai_k5a.py [TICKER ...]     (default: the ten sample companies)
Writes scripts/ai_store/assessments.jsonl (main run), assessments_repeat.jsonl (second run) and cls1_*.json (C1 for ABNB, BKNG); an existing answer is not asked again.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.ai import assess  # noqa: E402
from src.ai.client import GeminiClient  # noqa: E402
from src.ai.prompt import scoring_skills  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.ai.store import STORE_DIR, AssessmentStore  # noqa: E402
from src.scoring.ai_items import PENDING_TO_SKILL  # noqa: E402
from src.scoring.router import INDUSTRIES  # noqa: E402

G = ROOT / "tests" / "golden" / "2026-10-20"
SAMPLE = ["MSFT", "KO", "INTC", "UBER", "JPM", "CB", "PGR", "O", "AMT", "ABNB"]
ENGINE_OF = {}
for p in (G / "index.json",):
    for eng, d in json.loads(p.read_text(encoding="utf-8")).items():
        for t in d:
            ENGINE_OF[t] = eng
PROFILE = {"bank": "BANK", "insurance": "INSURANCE", "realestate": "INCOME_REAL_ESTATE", "managed_care": "STANDARD"}


def golden(t: str) -> dict:
    return json.loads((G / ENGINE_OF[t] / f"{t}.json").read_text(encoding="utf-8"))


def meta(t: str) -> dict:
    j = golden(t)
    eng = ENGINE_OF[t]
    if eng == "realestate":
        fy, end = j["inputs"]["fy"], j["inputs"]["end"]
        fins = j["inputs"]["f"]
        fins = {k: dict(zip(fy, v)) for k, v in fins.items()}
    else:
        fy, end = list(j["fiscal_years"]), list(j["fiscal_years"].values())
        fins = j["financials"]
    pending = []
    for kind, key in (("buffett", "buffett_quality"), ("graham", "graham_quality")):
        for c in j[key]["criteria"]:
            for i in c["items"]:
                if i["state"] == "ai_pending":
                    pending.append(PENDING_TO_SKILL[(kind, c["id"], i["id"])])
    return {"name": j.get("name") or t, "profile": PROFILE.get(eng) or j["profile"], "fy": fy, "end": end, "fins": fins, "pending": sorted(set(pending))}


def facts_text(m: dict, skill: str):
    labels = m["fy"][-5:]
    fi = m["fins"]
    if skill == "G3.8-Q3" and fi.get("net_income"):
        return "net income per fiscal year: " + "; ".join(f"{l}: {fi['net_income'].get(l)}" for l in labels)
    if skill == "B3.7-Q3":
        return "acquisitions (cash paid) per fiscal year: " + "; ".join(f"{l}: {(fi.get('acquisitions') or {}).get(l)}" for l in labels) + \
               " | goodwill impairment: " + "; ".join(f"{l}: {(fi.get('impairments') or fi.get('goodwill_impairment') or {}).get(l)}" for l in labels)
    return None


def main(argv):
    tickers = [a.upper() for a in argv] or SAMPLE
    client = GeminiClient()
    print("model:", client.model, "| rpm:", client.limiter.rpm, flush=True)
    main_store, rep_store = AssessmentStore(), AssessmentStore(STORE_DIR / "assessments_repeat.jsonl")
    sk = scoring_skills()
    summary = {}
    for t in tickers:
        if t not in ENGINE_OF:
            if t in ("ABNB", "BKNG"):
                continue
            print(t, "not in golden", flush=True)
            continue
        m = meta(t)
        filing = find_filing(t, str(m["end"][-1])[:10])
        if filing is None:
            print(t, "no filing for", m["end"][-1], flush=True)
            continue
        co = assess.Company(t, m["name"], m["profile"], int(m["fy"][-1][2:]), filing, {s: facts_text(m, s) for s in m["pending"] if facts_text(m, s)})
        stats_main, stats_rep = assess.Stats(), assess.Stats()
        t0 = time.time()
        for s in m["pending"]:
            assess.ask(co, sk[s], client, main_store, stats_main)
            assess.ask(co, sk[s], client, rep_store, stats_rep)   # the repeat store is separate: asks again unless this repeat already exists
            print(f"  {t} {s} done", flush=True)
        summary[t] = {"skills": m["pending"], "main": vars(stats_main), "repeat": vars(stats_rep), "seconds": round(time.time() - t0, 1)}
        print(t, summary[t], flush=True)
    (STORE_DIR / "run_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("client calls:", client.calls, "latency total:", round(client.total_latency, 1), "rate-limit waits:", round(client.limiter.waited, 1), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

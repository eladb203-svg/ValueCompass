"""Code stage K5a-2: one model, the 9 sample companies, two runs (stability), skills version 3, corrected sections, facts from code. Calls Gemini.

Usage: python scripts/run_ai_k5a2.py --model gemini-3.5-flash-lite [--only MSFT KO ...] [--rpm 12]
Writes scripts/ai_store/k5a2/<model>/assessments.jsonl, assessments_repeat.jsonl, cls1_*.json and run_log.json. An existing answer is not asked again (a restart resumes).
The environment (.env) is not changed: the model is a parameter.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.ai import assess  # noqa: E402
from src.ai.client import GeminiClient, RateLimiter  # noqa: E402
from src.ai.facts import facts_for  # noqa: E402
from src.ai.prompt import scoring_skills  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.ai.store import AssessmentStore  # noqa: E402
from run_ai_k5a import ENGINE_OF, G, golden, meta  # noqa: E402

SAMPLE = ["MSFT", "KO", "INTC", "UBER", "JPM", "CB", "PGR", "O", "AMT"]


def facts_data(t: str, m: dict) -> dict:
    j = golden(t)
    eng = ENGINE_OF[t]
    L = m["fy"][-5:]
    d = j.get("derived") or {}
    fin = m["fins"]
    pick = lambda src, k: [(src.get(k) or {}).get(l) for l in L]  # noqa: E731
    out = {"labels": L, "net_income": pick(fin, "net_income"), "eps": pick(fin, "eps"), "acquisitions": pick(fin, "acquisitions"),
           "goodwill_impairment": pick(fin, "impairments") if eng in ("general", "managed_care") else pick(fin, "goodwill_impairment"),
           "first_annual_report": (j.get("first_annual_report") or (j.get("inputs") or {}).get("first_annual_report")), "as_of": "2026-10-20"}
    if eng in ("general", "managed_care"):
        out["revenue"] = pick(fin, "revenue")
        out["margins"] = {"Gross margin": pick(d, "gross_margin"), "Operating margin": pick(d, "op_margin")}
    elif eng == "bank":
        out["revenue"] = pick(d, "revenue")
        out["margins"] = {"Pre-tax margin": pick(d, "pretax_margin")}
    elif eng == "insurance":
        out["revenue"] = pick(d, "operating_revenue")
        out["margins"] = {"Total operating margin": pick(d, "total_operating_margin")}
    else:
        out["revenue"] = pick(fin, "total_revenue")
        from src.scoring.realestate import REInputs, derive_re
        from datetime import date
        inp = j["inputs"]
        ri = REInputs(ticker=t, name=t, fy=inp["fy"], end=[date.fromisoformat(e) for e in inp["end"]], f=inp["f"], reg=inp["reg"], asset_type=inp.get("asset_type"),
                      utilization=None, noi_method=inp.get("noi_method"))
        nm = dict(zip(inp["fy"], derive_re(ri)["noi_margin"]))
        out["margins"] = {"NOI margin": [nm.get(l) for l in L]}
    out["eps"] = [None if v is None else float(v) for v in out["eps"]]
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--rpm", type=int, default=12)
    ap.add_argument("--no-cls", action="store_true")
    a = ap.parse_args(argv)
    out_dir = ROOT / "scripts" / "ai_store" / "k5a2" / a.model
    out_dir.mkdir(parents=True, exist_ok=True)
    client = GeminiClient(model=a.model, limiter=RateLimiter(rpm=a.rpm))
    store, rep_store = AssessmentStore(out_dir / "assessments.jsonl"), AssessmentStore(out_dir / "assessments_repeat.jsonl")
    sk = scoring_skills()
    tz = ZoneInfo("Asia/Jerusalem")
    log = {"model": a.model, "start": datetime.now(tz).isoformat(timespec="seconds"), "companies": {}}
    print("model:", client.model, "start", log["start"], flush=True)
    calls_failed = calls_total = 0
    for t in a.only or SAMPLE:
        m = meta(t)
        filing = find_filing(t, str(m["end"][-1])[:10])
        co = assess.Company(t, m["name"], m["profile"], int(m["fy"][-1][2:]), filing)
        fd = facts_data(t, m)
        co.code_facts = {s: facts_for(s, fd) for s in m["pending"] if facts_for(s, fd)}
        st1, st2 = assess.Stats(), assess.Stats()
        t0 = time.time()
        for s in m["pending"]:
            for st, stt in ((store, st1), (rep_store, st2)):
                calls_total += 1
                try:
                    assess.ask(co, sk[s], client, st, stt)
                except RuntimeError as e:
                    calls_failed += 1
                    print(f"  FAILED {t} {s}: {str(e)[:120]}", flush=True)
            print(f"  {t} {s} done", flush=True)
        log["companies"][t] = {"skills": m["pending"], "main": vars(st1), "repeat": vars(st2), "seconds": round(time.time() - t0, 1)}
        print(t, "seconds", log["companies"][t]["seconds"], flush=True)
        if calls_total >= 20 and calls_failed / calls_total > 0.10:
            log["unavailable"] = True
            print("model marked UNAVAILABLE: more than 10% of the calls failed", flush=True)
            break
    log.update({"end": datetime.now(tz).isoformat(timespec="seconds"), "calls": client.calls, "retries": client.retries, "failed_calls": calls_failed, "attempted": calls_total,
                "prompt_tokens": client.prompt_tokens, "output_tokens": client.output_tokens, "latency_sum_s": round(client.total_latency, 1),
                "rate_limit_wait_s": round(client.limiter.waited, 1)})
    (out_dir / "run_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    print("end", log["end"], "calls", client.calls, "retries", client.retries, "failed", calls_failed, flush=True)
    if not a.no_cls and not log.get("unavailable"):
        cls(client, store, out_dir)


def cls(client, store, out_dir):
    from src.providers import industry_provider
    from src.providers.sec_companyfacts import SecClient
    from src.scoring.router import INDUSTRIES, AIAnswer
    from router_runner import route_company
    industry_provider.use_fixed(ROOT / "scripts" / "provider_industry_2026-10-20.csv")
    sec, stats, out = SecClient(), assess.Stats(), {}
    for t in ("ABNB", "BKNG"):
        before = route_company(sec, t)
        cik, title = sec.cik_for(t)
        sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
        filing = find_filing(t)
        co = assess.Company(t, title, before.profile, int(filing.report_date[:4]), filing)
        try:
            row = assess.classify_industry(co, sub.get("sic"), sub.get("sicDescription"), industry_provider.get_industry(t), client, store, stats, list(INDUSTRIES))
        except RuntimeError as e:
            out[t] = {"error": str(e)[:150]}
            continue
        ind = (row["evidence"].get("extra") or {}).get("industry")
        after = route_company(sec, t, ai=AIAnswer(ind, "") if ind else None)
        out[t] = {"state": row["state"], "industry": ind, "checks_ok": row["evidence"].get("check_ok"), "reasons": row["evidence"].get("reasons"),
                  "router": {"industry": after.industry, "status": after.classification.status, "profile": after.profile}}
    (out_dir / "cls1_results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("C1:", json.dumps(out), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

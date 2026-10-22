"""Code stage K5a-3: model comparison runner (one model, chosen companies / skills, two runs), prompt version 3 or 3.1. Calls Gemini.

Usage:
  python scripts/run_ai_k5a3.py --model gemini-3.5-flash-lite --prompt-version 3
  python scripts/run_ai_k5a3.py --model gemini-3.8-flash --companies INTC UBER AMT --prompt-version 3.1 --start-at 03:00 --rpd 150 --thinking-budget 1024

Flags: --companies (default: the nine sample companies), --only (skill ids, e.g. A6 A8 B3.2-Q4), --start-at HH:MM (Israel time; waits until then, today or tomorrow), --prompt-version 3|3.1,
--thinking-budget N (passed to the API), --rpm, --rpd (the daily request budget of the client; every attempt counts), --no-repeat, --no-cls, --out-root.
Output: <out-root>/<model>/v<prompt-version>/{assessments.jsonl, assessments_repeat.jsonl, run_log.json}; an existing answer is not asked again (a restart resumes).
Automatic stop: when, among 10 consecutive calls, more than 3 needed more than 2 attempts, the run stops and saves (stopped_reason in run_log.json).
The environment (.env) is not changed: the model is a parameter.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, deque
from datetime import datetime, timedelta
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
from run_ai_k5a import meta  # noqa: E402
from run_ai_k5a2 import SAMPLE, facts_data  # noqa: E402

TZ = ZoneInfo("Asia/Jerusalem")
STOP_WINDOW, STOP_SLOW_CALLS, STOP_ATTEMPTS = 10, 3, 2


def wait_until(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    now = datetime.now(TZ)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    print(f"waiting until {target.isoformat(timespec='minutes')} (Israel time)", flush=True)
    while datetime.now(TZ) < target:
        time.sleep(min(60, max(1, (target - datetime.now(TZ)).total_seconds())))
    return target.isoformat(timespec="seconds")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--companies", nargs="*")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--start-at")
    ap.add_argument("--prompt-version", default="3", choices=["3", "3.1"])
    ap.add_argument("--thinking-budget", type=int)
    ap.add_argument("--rpm", type=int, default=12)
    ap.add_argument("--rpd", type=int, default=200)   # the real quota cannot be read from the API (AI Studio shows it); 200 until it is known
    ap.add_argument("--no-repeat", action="store_true")
    ap.add_argument("--no-cls", action="store_true")
    ap.add_argument("--out-root", default=str(ROOT / "scripts" / "ai_store" / "k5a3"))
    a = ap.parse_args(argv)
    out_dir = Path(a.out_root) / a.model / f"v{a.prompt_version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.start_at:
        wait_until(a.start_at)
    client = GeminiClient(model=a.model, limiter=RateLimiter(rpm=a.rpm, rpd=a.rpd))
    stores = [(AssessmentStore(out_dir / "assessments.jsonl"), "main")]
    if not a.no_repeat:
        stores.append((AssessmentStore(out_dir / "assessments_repeat.jsonl"), "repeat"))
    sk = scoring_skills()
    wanted = set(a.only or [])
    log = {"model": a.model, "prompt_version": a.prompt_version, "start": datetime.now(TZ).isoformat(timespec="seconds"), "companies": {}, "errors": {}, "stopped_reason": None}
    print("model:", client.model, "prompt version", a.prompt_version, "start", log["start"], flush=True)
    recent: deque = deque(maxlen=STOP_WINDOW)
    stop = False
    for t in a.companies or SAMPLE:
        m = meta(t)
        co = assess.Company(t, m["name"], m["profile"], int(m["fy"][-1][2:]), find_filing(t, str(m["end"][-1])[:10]))
        fd = facts_data(t, m)
        co.code_facts = {s: facts_for(s, fd) for s in m["pending"] if facts_for(s, fd)}
        t0 = time.time()
        for s in m["pending"]:
            if wanted and s not in wanted and sk[s]["id"] not in wanted:
                continue
            for st, run in stores:
                stats = assess.Stats()
                try:
                    row = assess.ask(co, sk[s], client, st, stats, variant=a.prompt_version, thinking_budget=a.thinking_budget)
                except RuntimeError as e:
                    log["errors"]["call_failed"] = log["errors"].get("call_failed", 0) + 1
                    print(f"  FAILED {t} {s} ({run}): {str(e)[:120]}", flush=True)
                    continue
                if stats.calls:
                    recent.append(row["usage"].get("attempts", 1) > STOP_ATTEMPTS)
                    for ent in row["usage"].get("attempt_log", []):
                        log["errors"][ent["error_code"]] = log["errors"].get(ent["error_code"], 0) + 1
                if len(recent) == STOP_WINDOW and sum(recent) > STOP_SLOW_CALLS:
                    log["stopped_reason"] = f"more than {STOP_SLOW_CALLS} of {STOP_WINDOW} consecutive calls needed more than {STOP_ATTEMPTS} attempts"
                    stop = True
                    break
            print(f"  {t} {s} done", flush=True)
            if stop:
                break
        log["companies"][t] = {"seconds": round(time.time() - t0, 1)}
        if stop:
            print("STOPPED:", log["stopped_reason"], flush=True)
            break
    log.update({"end": datetime.now(TZ).isoformat(timespec="seconds"), "calls": client.calls, "retries": client.retries, "failures": client.failures, "prompt_tokens": client.prompt_tokens,
                "output_tokens": client.output_tokens, "latency_sum_s": round(client.total_latency, 1), "rate_limit_wait_s": round(client.limiter.waited, 1),
                "requests_counted_against_rpd": client.limiter.day_calls})
    (out_dir / "run_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    print("end", log["end"], "calls", client.calls, "retries", client.retries, "errors", log["errors"], flush=True)
    if not a.no_cls and not stop and not a.only:
        from run_ai_k5a2 import cls
        cls(client, stores[0][0], out_dir)


if __name__ == "__main__":
    main(sys.argv[1:])

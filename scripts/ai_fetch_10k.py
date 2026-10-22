"""Code stage K5a-2: download the 10-K (main document, cached as html) that matches the engines' latest fiscal year, plus the latest 10-K when it differs.

Usage: python scripts/ai_fetch_10k.py TICKER [TICKER ...]
SEC fair access: identifying User-Agent (SEC_USER_AGENT in .env), <= 10 requests per second (the SecClient / _get_raw throttle). Prints what was fetched.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.providers import sec_filings as F  # noqa: E402
from src.providers.realestate_facts import CIK_OVERRIDE  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from run_ai_k5a import ENGINE_OF, meta  # noqa: E402


def tenks(sub: dict) -> list:
    rec = sub["filings"]["recent"]
    return [{"filed": f, "accession": a, "primary": d, "report_date": r}
            for form, f, a, d, r in zip(rec["form"], rec["filingDate"], rec["accessionNumber"], rec["primaryDocument"], rec["reportDate"]) if form == "10-K"]


def main(tickers):
    sec = SecClient()
    out = {}
    for t in tickers:
        cik, _ = CIK_OVERRIDE.get(t) or sec.cik_for(t)
        sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
        ks = tenks(sub)
        end = date.fromisoformat(str(meta(t)["end"][-1])[:10]) if t in ENGINE_OF else None
        want = [ks[0]] if ks else []
        if end:
            near = [k for k in ks if abs((date.fromisoformat(k["report_date"]) - end).days) <= 20]
            if near and near[0] not in want:
                want.append(near[0])
        got = []
        for k in want:
            a = k["accession"].replace("-", "")
            F._get_raw(sec, f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{k['primary']}", f"{a}_{k['primary']}")
            got.append(f"{k['accession']} {k['primary']} (period {k['report_date']}, filed {k['filed']})")
        out[t] = {"engine_fy_end": str(end), "fetched": got}
        print(t, out[t], flush=True)
    print("SEC requests:", sec.requests_made)
    (ROOT / "scripts" / "ai_store" / "fetch_10k_log.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main([a.upper() for a in sys.argv[1:]])

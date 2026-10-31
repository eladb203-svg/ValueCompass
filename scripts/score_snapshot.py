"""Snapshot of the latest score of companies (criterion-level points) for before / after comparisons: python scripts/score_snapshot.py OUT.json T1 T2 ...  |  --diff A.json B.json"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def snap(tickers):
    from src.db import get_supabase_client
    c = get_supabase_client()
    out = {}
    for t in tickers:
        co = c.table("companies").select("id,profile").eq("symbol", t).execute().data[0]
        run = c.table("score_runs").select("id").eq("company_id", co["id"]).order("id", desc=True).limit(1).execute().data[0]
        rows = c.table("score_details").select("model,criterion_key,sub_criterion_key,detail_level,criterion_score,max_score,evidence").eq("run_id", run["id"]).execute().data
        s = c.table("company_score_summary").select("buffett_quality_score,graham_quality_score,buffett_quality_coverage,graham_quality_coverage").eq("company_id", co["id"]).execute().data[0]
        items = {}
        for r in rows:
            if r["criterion_key"] == "total" or r["detail_level"] == "criterion":
                continue
            ev = r["evidence"] or {}
            items[f"{r['model'][0]}{r['criterion_key']}.{r['sub_criterion_key']}"] = {"pts": r["criterion_score"], "max": r["max_score"], "state": ev.get("state"), "metric": ev.get("metric"), "label": ev.get("metric_label"), "note": ev.get("note")}
        out[t] = {"profile": co["profile"], "summary": s, "items": items}
    return out


def diff(a, b):
    for t in b:
        if t not in a:
            continue
        print(f"== {t}: profile {a[t]['profile']} -> {b[t]['profile']}   summary {a[t]['summary']} -> {b[t]['summary']}")
        keys = sorted(set(a[t]["items"]) | set(b[t]["items"]))
        for k in keys:
            x, y = a[t]["items"].get(k), b[t]["items"].get(k)
            if x != y and (x or {}).get("pts") != (y or {}).get("pts") or (x or {}).get("state") != (y or {}).get("state"):
                print(f"   {k:9} {str((x or {}).get('pts')):>6}/{(x or {}).get('max')} [{(x or {}).get('state')}] {str((x or {}).get('label'))[:34]!s:34} -> {str((y or {}).get('pts')):>6}/{(y or {}).get('max')} [{(y or {}).get('state')}] {str((y or {}).get('label'))[:34]}")


if __name__ == "__main__":
    if sys.argv[1] == "--diff":
        diff(json.load(open(sys.argv[2], encoding="utf8")), json.load(open(sys.argv[3], encoding="utf8")))
    else:
        Path(sys.argv[1]).write_text(json.dumps(snap(sys.argv[2:]), ensure_ascii=False, indent=1, default=str), encoding="utf8")
        print("written", sys.argv[1])

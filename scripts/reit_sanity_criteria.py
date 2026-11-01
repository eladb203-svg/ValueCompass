"""Report only: Buffett / Graham criterion-level strength (earned over covered points) of the golden REITs against the REITs scored in the database, and the score without the FFO_PROXY items."""
import glob
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import reit_sanity as RS  # noqa: E402

NEW = ["VTR", "VICI", "HST", "DLR", "MAA"]


def golden_crit(path):
    j = json.load(open(path, encoding="utf8"))
    out = {}
    for model in ("buffett", "graham"):
        for c in j[f"{model}_quality"]["criteria"]:
            if c.get("covered_points"):
                out[(model, c["id"])] = (c["observed_points"], c["covered_points"], c["weight"])
    return out


def db_crit(tickers):
    from src.db import get_supabase_client
    cl = get_supabase_client()
    res = {}
    for t in tickers:
        co = cl.table("companies").select("id").eq("symbol", t).execute().data[0]
        run = cl.table("score_runs").select("id").eq("company_id", co["id"]).order("id", desc=True).limit(1).execute().data[0]
        rows = cl.table("score_details").select("model,criterion_key,detail_level,criterion_score,max_score,evidence").eq("run_id", run["id"]).execute().data
        out = {}
        for r in rows:
            if r["detail_level"] == "criterion" and r["criterion_key"] != "total":
                ev = r["evidence"] or {}
                cov = ev.get("covered_points")
                if cov:
                    out[(r["model"], r["criterion_key"])] = (float(ev.get("observed_points") if ev.get("observed_points") is not None else (r["criterion_score"] or 0)), float(cov), float(r["max_score"] or 0))
        res[t] = out
    return res


def main():
    gold = {Path(p).stem: golden_crit(p) for p in sorted(glob.glob(str(ROOT / "tests/golden/*/realestate/*.json")))}
    new = db_crit(NEW)
    for model in ("buffett", "graham"):
        print(f"\n{model}: criterion strength = earned / covered points (golden mean | golden min-max | new REITs)")
        ids = sorted({k[1] for d in list(gold.values()) + list(new.values()) for k in d if k[0] == model}, key=lambda s: [int(x) for x in s.split(".")])
        for cid in ids:
            g = [d[(model, cid)][0] / d[(model, cid)][1] for d in gold.values() if (model, cid) in d]
            n = {t: new[t][(model, cid)][0] / new[t][(model, cid)][1] for t in NEW if (model, cid) in new[t]}
            if g:
                print(f"  {cid}  golden {st.mean(g):.0%} ({min(g):.0%}-{max(g):.0%})   new " + "  ".join(f"{t} {v:.0%}" for t, v in n.items()))
    print("\nscore without the FFO_PROXY items (earned - proxy) / (covered - proxy max):")
    for t, v in RS.from_db(NEW).items():
        for model in ("buffett", "graham"):
            m = v[model]
            if m["score"]:
                covered = m["earned"] / float(m["score"]) * 100
                ex = (m["earned"] - m["proxy"]) / (covered - m["proxy_max"]) * 100 if covered - m["proxy_max"] > 0 else None
                print(f"  {t} {model}: score {float(m['score']):.1f} -> without proxy items {ex:.1f}")


if __name__ == "__main__":
    main()

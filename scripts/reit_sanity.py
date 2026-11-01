"""Sanity table of REIT scores (report only): golden REITs (stored results) against the REITs scored in the database. For each company and model: score, coverage, points earned on
FFO_PROXY items and the share they have of all earned points.   python scripts/reit_sanity.py [OUT.md]"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = ["VTR", "VICI", "HST", "DLR", "MAA", "AMT", "O"]


def from_golden(path):
    j = json.load(open(path, encoding="utf8"))
    out = {}
    for model in ("buffett", "graham"):
        q = j[f"{model}_quality"]
        earned = proxy = proxy_max = 0.0
        n = npx = 0
        for c in q["criteria"]:
            for i in c["items"]:
                if i.get("state") in ("score", "true_zero") and i.get("points") is not None:
                    earned += i["points"]
                    n += 1
                    if "FFO_PROXY" in (i.get("flags") or []) or (i.get("inputs") or {}).get("metric_basis") == "FFO_PROXY":
                        proxy += i["points"]
                        proxy_max += i.get("max_pts") or 0
                        npx += 1
        out[model] = {"score": q.get("score"), "cov": q.get("coverage"), "earned": earned, "proxy": proxy, "proxy_max": proxy_max, "n": n, "npx": npx,
                      "pending": len(q.get("pending_criteria") or []), "status": q.get("status")}
    return out


def from_db(tickers):
    from src.db import get_supabase_client
    c = get_supabase_client()
    res = {}
    for t in tickers:
        co = c.table("companies").select("id").eq("symbol", t).execute().data[0]
        run = c.table("score_runs").select("id").eq("company_id", co["id"]).order("id", desc=True).limit(1).execute().data[0]
        rows = c.table("score_details").select("model,criterion_key,detail_level,criterion_score,max_score,evidence").eq("run_id", run["id"]).execute().data
        s = c.table("company_score_summary").select("*").eq("company_id", co["id"]).execute().data[0]
        out = {}
        for model in ("buffett", "graham"):
            earned = proxy = proxy_max = 0.0
            n = npx = 0
            for r in rows:
                if r["model"] != model or r["criterion_key"] == "total" or r["detail_level"] == "criterion":
                    continue
                ev = r["evidence"] or {}
                if ev.get("state") in ("score", "true_zero") and r["criterion_score"] is not None:
                    earned += float(r["criterion_score"])
                    n += 1
                    if "FFO_PROXY" in (ev.get("flags") or []):
                        proxy += float(r["criterion_score"])
                        proxy_max += float(r["max_score"] or 0)
                        npx += 1
            out[model] = {"score": s.get(f"{model}_quality_score"), "cov": s.get(f"{model}_quality_coverage"), "earned": earned, "proxy": proxy, "proxy_max": proxy_max, "n": n, "npx": npx,
                          "pending": 0, "status": s.get("overall_status")}
        res[t] = out
    return res


def fmt(m):
    sc = "-" if m["score"] is None else f"{float(m['score']):.1f}"
    return f"{sc} / {float(m['cov'] or 0):.0%} / {m['proxy']:.1f} of {m['earned']:.1f} ({(m['proxy'] / m['earned'] if m['earned'] else 0):.0%}, {m['npx']} items)"


def main():
    rows = []
    for p in sorted(glob.glob(str(ROOT / "tests/golden/*/realestate/*.json"))):
        t = Path(p).stem
        rows.append(("golden", t, from_golden(p)))
    for t, v in from_db(DB).items():
        rows.append(("test", t, v))
    lines = ["| source | company | Buffett: score / coverage / points on FFO_PROXY | Graham: score / coverage / points on FFO_PROXY |", "|---|---|---|---|"]
    for src, t, v in rows:
        lines.append(f"| {src} | {t} | {fmt(v['buffett'])} | {fmt(v['graham'])} |")
    text = "\n".join(lines)
    print(text)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf8")


if __name__ == "__main__":
    main()

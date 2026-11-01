"""Report only: the REIT scores of the database on the golden basis - without the AI-answered items (the golden results still had them pending) and without the FFO_PROXY items."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
AI = {"buffett": {"3.1.1", "3.1.2", "3.1.3", "3.1.4", "3.1.5", "3.2.4", "3.2.5", "3.7.5", "3.8.6"}, "graham": {"3.1.3", "3.1.4"}}


def main():
    from src.db import get_supabase_client
    c = get_supabase_client()
    print("| company | model | score | without AI items | without AI and FFO_PROXY items | AI points earned of max |")
    print("|---|---|---|---|---|---|")
    for t in ["VTR", "VICI", "HST", "DLR", "MAA", "AMT", "O"]:
        co = c.table("companies").select("id").eq("symbol", t).execute().data[0]
        run = c.table("score_runs").select("id").eq("company_id", co["id"]).order("id", desc=True).limit(1).execute().data[0]
        rows = c.table("score_details").select("model,criterion_key,sub_criterion_key,detail_level,criterion_score,max_score,evidence").eq("run_id", run["id"]).execute().data
        s = c.table("company_score_summary").select("*").eq("company_id", co["id"]).execute().data[0]
        for model in ("buffett", "graham"):
            sc = s.get(f"{model}_quality_score")
            if sc is None:
                continue
            e = ai_e = ai_m = px_e = px_m = 0.0
            for r in rows:
                if r["model"] != model or r["criterion_key"] == "total" or r["detail_level"] == "criterion":
                    continue
                ev = r["evidence"] or {}
                if ev.get("state") not in ("score", "true_zero") or r["criterion_score"] is None:
                    continue
                pts, mx = float(r["criterion_score"]), float(r["max_score"] or 0)
                e += pts
                key = f"{r['criterion_key']}.{r['sub_criterion_key']}"
                if key in AI[model]:
                    ai_e += pts
                    ai_m += mx
                elif "FFO_PROXY" in (ev.get("flags") or []):
                    px_e += pts
                    px_m += mx
            cov = e / float(sc) * 100
            ex_ai = (e - ai_e) / (cov - ai_m) * 100
            ex_both = (e - ai_e - px_e) / (cov - ai_m - px_m) * 100
            print(f"| {t} | {model} | {float(sc):.1f} | {ex_ai:.1f} | {ex_both:.1f} | {ai_e:.1f} of {ai_m:.1f} |")


if __name__ == "__main__":
    main()

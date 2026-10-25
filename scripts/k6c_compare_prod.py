"""K6c section 9.7: per company, production against test - facts (every value, status, source, tag, flags), filing periods (accession), extraction rows by origin / status / source, AI answers and items,
the latest score (Buffett / Graham quality, fair values, price scores, buy prices, valuations), processing state and ``v_company_status``. Reads both databases; writes nothing.

    .venv/Scripts/python scripts/k6c_compare_prod.py KO MSFT INTC JPM CB O AMT [--out scripts/output_k6c/prod/compare.json]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai.db_stores import select_all  # noqa: E402
from src.db import get_supabase_client  # noqa: E402

SCORE_FIELDS = ("buffett_quality_score", "graham_quality_score", "buffett_price_score", "graham_price_score", "buffett_fair_value", "graham_fair_value", "buffett_buy_price", "graham_buy_price",
                "buffett_quality_coverage", "graham_quality_coverage", "overall_status", "profile", "as_of_fiscal_year", "years_available")


def snapshot(c, symbol: str) -> dict:
    co = c.table("companies").select("*").eq("symbol", symbol).eq("exchange", "US").execute().data[0]
    cid = co["id"]
    items = {r["id"]: r["item_key"] for r in select_all(c, "dictionary_items")}
    tags = {r["id"]: r["tag"] for r in select_all(c, "fact_tags")}
    facts = {(f["fiscal_year"], items[f["item_id"]]): (f["value"], f["status"], f["source_kind"], tags.get(f["tag_id"]), tuple(f["flags"] or ())) for f in select_all(c, "financial_facts", {"company_id": cid}, order="fiscal_year")}
    periods = {p["fiscal_year"]: (p["accession"], p["form"], p["fiscal_year_end"]) for p in select_all(c, "filing_periods", {"company_id": cid}, order="fiscal_year")}
    ext = Counter()
    for r in select_all(c, "extraction_items", {"company_id": cid}):
        ext[("ai" if r.get("skill_id") else "csv", r["approval_status"], r.get("approval_source") or "-")] += 1
    summary = c.table("company_score_summary").select("*").eq("company_id", cid).execute().data
    vals = {}
    if summary and summary[0].get("latest_run_id"):
        for v in c.table("valuations").select("*").eq("run_id", summary[0]["latest_run_id"]).execute().data:
            vals[v["model"]] = (v["method"], v["fair_value"], v["price_score"], v["price_state"], v["buy_price"], v["buy_price_state"], v["margin_of_safety"])
    status = c.table("v_company_status").select("*").eq("company_id", cid).execute().data
    return {"facts": facts, "periods": periods, "ext": dict(ext), "ai_answers": len(select_all(c, "ai_assessments", {"company_id": cid})),
            "score": {k: (summary[0].get(k) if summary else None) for k in SCORE_FIELDS}, "valuations": vals, "state": co.get("processing_state"), "profile": co.get("profile"), "cik": co.get("cik"),
            "status_view": {k: status[0].get(k) for k in ("processing_state", "profile", "last_job_status")} if status else None}


def main(argv) -> int:
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    tickers = [a for a in argv if not a.startswith("--") and a != out]
    test, prod = get_supabase_client("test"), get_supabase_client("prod")
    report, bad = {}, 0
    print(f"{'':<6}{'facts t/p':<12}{'fact diffs':<11}{'periods':<9}{'extraction rows (csv|ai) t/p':<32}{'answers t/p':<12}{'scores':<8}{'valuations':<11}state test -> prod")
    for t in tickers:
        a, b = snapshot(test, t), snapshot(prod, t)
        fd = [k for k in sorted(set(a["facts"]) | set(b["facts"])) if a["facts"].get(k) != b["facts"].get(k)]
        pd = [k for k in sorted(set(a["periods"]) | set(b["periods"])) if a["periods"].get(k) != b["periods"].get(k)]
        sd = {k: (a["score"][k], b["score"][k]) for k in SCORE_FIELDS if (None if a["score"][k] is None else float(a["score"][k]) if isinstance(a["score"][k], (int, float, str)) and k.endswith(("score", "value", "price", "coverage")) else a["score"][k]) !=
              (None if b["score"][k] is None else float(b["score"][k]) if isinstance(b["score"][k], (int, float, str)) and k.endswith(("score", "value", "price", "coverage")) else b["score"][k])}
        vd = {m: (a["valuations"].get(m), b["valuations"].get(m)) for m in set(a["valuations"]) | set(b["valuations"]) if a["valuations"].get(m) != b["valuations"].get(m)}
        csv = lambda s: sum(n for k, n in s["ext"].items() if k[0] == "csv")  # noqa: E731
        ai = lambda s: sum(n for k, n in s["ext"].items() if k[0] == "ai")    # noqa: E731
        same_ext = a["ext"] == b["ext"]
        ok = not fd and not pd and not sd and not vd and same_ext and a["ai_answers"] == b["ai_answers"]
        bad += not ok
        report[t] = {"facts_test": len(a["facts"]), "facts_prod": len(b["facts"]), "fact_differences": [list(k) for k in fd][:20], "period_differences": pd, "extraction_test": {"|".join(k): n for k, n in a["ext"].items()},
                     "extraction_prod": {"|".join(k): n for k, n in b["ext"].items()}, "answers_test": a["ai_answers"], "answers_prod": b["ai_answers"], "score_differences": sd, "valuation_differences": vd,
                     "state_test": a["state"], "state_prod": b["state"], "profile_test": a["profile"], "profile_prod": b["profile"], "status_view_prod": b["status_view"], "score_prod": b["score"], "ok": ok}
        print(f"{t:<6}{str(len(a['facts'])) + '/' + str(len(b['facts'])):<12}{len(fd):<11}{'same' if not pd else len(pd):<9}{str(csv(a)) + '|' + str(ai(a)) + ' / ' + str(csv(b)) + '|' + str(ai(b)) + ('' if same_ext else ' DIFF'):<32}"
              f"{str(a['ai_answers']) + '/' + str(b['ai_answers']):<12}{'same' if not sd else 'DIFF':<8}{'same' if not vd else 'DIFF':<11}{a['state']} -> {b['state']}")
        for label, d in (("score", sd), ("valuation", vd)):
            for k, v in list(d.items())[:4]:
                print(f"        {label} {k}: test={v[0]} prod={v[1]}")
    if out:
        Path(out).write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n{len(tickers) - bad}/{len(tickers)} companies identical (facts, periods, extraction, answers, scores, valuations)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

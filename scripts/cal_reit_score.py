"""Calibration (item 4): the effect of the reworded REIT answers (scripts/state/cal_reit_reask.jsonl) on the REIT scores. For each REIT with new answers the Buffett quality score is calculated once with the
stored approved answers (before) and once with the four new answers laid over them (after); nothing is written to the database. Also: distribution of the points of the nine AI items (3.1.x, 3.2.4, 3.2.5, 3.7.5, 3.8.6;
max 17) before / after, strong against weak, and a dump of every new answer with reasoning and quotes (and whether each quote is found word for word in the report) for reading.
Usage: python scripts/cal_reit_score.py"""
import json
import statistics as st
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

import vc  # noqa: E402
from src.ai import assess  # noqa: E402
from src.ai.checks import normalize  # noqa: E402
from src.ai.db_stores import select_all  # noqa: E402
from src.ai.sections import find_filing  # noqa: E402
from src.ai.store import AssessmentStore  # noqa: E402
from src.etl.db_io import FactSetDb  # noqa: E402
from src.pipeline import scoring as S  # noqa: E402

QS = ["B3.2-Q4", "B3.2-Q5", "B3.7-Q5", "B3.8-Q6"]
ITEM = {"B3.2-Q4": "3.2.4", "B3.2-Q5": "3.2.5", "B3.7-Q5": "3.7.5", "B3.8-Q6": "3.8.6"}
WEAK = ["PK", "BDN", "DHC", "HPP", "MAC"]
runner = vc.make_runner(0)
new = {}
for r in AssessmentStore(ROOT / "scripts" / "state" / "cal_reit_reask.jsonl").rows():
    new[(r["ticker"], r["question_id"])] = r


class Overlay:
    """The approved store with the new answers laid over the stored ones (state answered only)."""

    def __init__(self, base):
        self.base = base

    def rows(self, ticker):
        rows = [dict(r) for r in self.base.rows(ticker)]
        if not rows:
            return rows                                     # a company without any approved answer stays pending: not part of the score comparison
        now = datetime.now(timezone.utc).isoformat()
        for q in QS:
            n = new.get((ticker, q))
            if n and n.get("state") == "answered":
                fy = max(r["fiscal_year"] for r in rows)
                rows = [r for r in rows if not (r["question_id"] == q and r["fiscal_year"] == fy)]
                rows.append({**n, "fiscal_year": fy, "approval_status": "approved", "created_at": now})
        return rows

    def __getattr__(self, name):
        return getattr(self.base, name)


c = runner.client
summ = {x["company_id"]: x for x in select_all(c, "company_score_summary", order="company_id")}
cos = {x["symbol"]: x for x in select_all(c, "companies", order="id") if x["exchange"] == "US"}
tmp = Path(tempfile.mkdtemp(prefix="cal_reit_"))
out = {}
tickers = sorted({t for t, _ in new})
for t in tickers:
    prof = "INCOME_REAL_ESTATE"
    row = {}
    for label, store in (("before", runner.ai_store), ("after", Overlay(runner.ai_store))):
        o = S.score_company(t, prof, FactSetDb(c), store, runner.item_store, tmp)
        if o.status != "scored":
            row[label] = None
            continue
        q = o.result["buffett_quality"]
        items = {f"{cr['id']}.{it['id']}": (it.get("state"), it.get("points")) for cr in q.get("criteria", []) for it in cr.get("items", [])}
        ai = {k: v for k, v in items.items() if k.startswith("3.1.") or k in ("3.2.4", "3.2.5", "3.7.5", "3.8.6")}
        row[label] = {"score": q.get("score"), "coverage": q.get("coverage"), "ai_pending": any(v[0] == "ai_pending" for v in ai.values()), "ai_points": sum(v[1] or 0 for v in ai.values()), "items": {k: v for k, v in ai.items() if k in ITEM.values()}}
    out[t] = row
    print(t, {k: (None if v is None else (round(v["score"], 1) if v["score"] is not None else None, v["ai_points"], v["ai_pending"])) for k, v in row.items()}, flush=True)
Path(ROOT / "scripts" / "state" / "cal_reit_score.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")


def stat(label, ts):
    ok = [t for t in ts if out[t].get("before") and out[t].get("after") and not out[t]["before"]["ai_pending"] and out[t]["before"]["score"] is not None and out[t]["after"]["score"] is not None]
    if not ok:
        print(f"{label}: none")
        return
    full_b = sum(1 for t in ok if out[t]["before"]["ai_points"] >= 17)
    full_a = sum(1 for t in ok if out[t]["after"]["ai_points"] >= 17)
    print(f"{label}: n={len(ok)}  17/17 before {full_b} after {full_a};  mean AI points {st.mean(out[t]['before']['ai_points'] for t in ok):.1f} -> {st.mean(out[t]['after']['ai_points'] for t in ok):.1f};  "
          f"mean Buffett quality {st.mean(out[t]['before']['score'] for t in ok):.1f} -> {st.mean(out[t]['after']['score'] for t in ok):.1f}")


print("\n" + "=" * 100)
stat("strong REITs", [t for t in tickers if t not in WEAK])
stat("weak REITs", [t for t in tickers if t in WEAK])
stat("all", tickers)
print("per weak REIT:", {t: (None if not out[t].get("before") else (out[t]["before"]["score"], out[t]["after"]["score"] if out[t].get("after") else None)) for t in WEAK if t in out})

print("\n" + "=" * 100 + "\nEVERY NEW ANSWER (answer, reasoning, quotes; verbatim check against the report)")
fulltext = {}
for (t, q) in sorted(new):
    r = new[(t, q)]
    ev = r.get("evidence") or {}
    if t not in fulltext:
        try:
            co = dict(runner.companies.get_by_symbol(t, "US"))
            co["profile"] = "INCOME_REAL_ESTATE"
            res = runner.load_result(t)
            K5 = runner._meta_context(co, res)
            m = K5.meta(t)
            a = assess.Company(t, m["name"], "INCOME_REAL_ESTATE", int(m["fy"][-1][2:]), find_filing(t, str(m["end"][-1])[:10]))
            fulltext[t] = normalize(" ".join((getattr(s, "text", s) or "") for s in a.sections().values()))
        except Exception as e:   # noqa: BLE001
            fulltext[t] = ""
    old = runner.ai_store.get(t, r["fiscal_year"], q, "2") or None
    prev = None
    for v in ("3.1", "2.1", "3", "2"):
        o = runner.ai_store.get(t, r["fiscal_year"], q, v)
        if o:
            prev = o.get("answer")
            break
    print(f"== {t} {q}  before={prev}  after={r.get('answer')} ({r.get('state')})")
    print("   reasoning:", str(ev.get("reasoning"))[:500])
    for qu in ev.get("quotes") or []:
        print(f"   quote [{ 'FOUND' if normalize(qu.get('text') or '') in fulltext[t] else 'NOT FOUND'}]: {str(qu.get('text'))[:420]}")

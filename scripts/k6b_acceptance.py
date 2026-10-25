"""K6b section 8.3: acceptance tests on the TEST database (refuses VC_DB_TARGET=prod).

  new company    a ticker that is not in the DB -> company created, listing, facts, periods, state data_loaded
  idempotency    the same load again -> 0 rows changed (facts and filing periods)
  dry run        computes and reports, writes nothing
  restatement    a simulated 10-K/A changes one value -> flag ``restated``, rewrite of that year, a line in data_update_log
  new report     a simulated new 10-K -> the new year, the router, "AI required" in the log
  unsupported    a 20-F filer -> state ``unsupported`` with a reason, no facts
The simulations are overlays on the real SEC documents (PipelineSec ``transform``): nothing is faked in the database. The simulated company is cleaned and reloaded from the real data afterwards.

    .venv/Scripts/python scripts/k6b_acceptance.py [--ticker PEP] [--out scripts/output_k6b/acceptance.json]
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target, get_supabase_client  # noqa: E402
from src.pipeline.runner import Pipeline  # noqa: E402
from src.pipeline.sec_source import PipelineSec  # noqa: E402

FAKE_AMENDMENT = "9999999999-26-000001"
FAKE_NEW_10K = "9999999999-27-000001"
RESULTS: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"test": name, "pass": bool(ok), "detail": detail})
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  - {detail}" if detail else ""))


def counts(client, company_id) -> dict:
    out = {}
    for t in ("financial_facts", "filing_periods", "company_listings", "company_profile_history", "market_snapshot"):
        out[t] = len(client.table(t).select("company_id").eq("company_id", company_id).execute().data) if company_id else 0
    return out


def overlay_amendment(cik: str, year: int):
    """A 10-K/A for ``year`` that restates revenue by +1% (annual revenue entries get a later-filed twin)."""
    def transform(name, data):
        if name == f"sub_{cik}.json":
            data = copy.deepcopy(data)
            r = data["filings"]["recent"]
            for k, v in (("form", "10-K/A"), ("accessionNumber", FAKE_AMENDMENT), ("filingDate", date.today().isoformat()), ("reportDate", None), ("primaryDocument", "amend.htm")):
                r[k].insert(0, v)
            r["reportDate"][0] = _report_date(data, year, r)
        elif name == f"facts_{cik}.json":
            data = copy.deepcopy(data)
            for tag in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"):
                node = data["facts"].get("us-gaap", {}).get(tag)
                for unit in (node or {}).get("units", {}).values():
                    twins = []
                    for e in unit:
                        if e.get("form") == "10-K" and e.get("fp") == "FY" and e["end"].startswith(str(year)) and "start" in e and 340 <= (date.fromisoformat(e["end"]) - date.fromisoformat(e["start"])).days <= 380:
                            t = dict(e, val=e["val"] * 1.01, form="10-K/A", accn=FAKE_AMENDMENT, filed=date.today().isoformat())
                            twins.append(t)
                    unit.extend(twins)
        return data
    return transform


def _report_date(data, year, recent) -> str:
    for form, rd in zip(recent["form"], recent["reportDate"]):
        if form == "10-K" and rd and rd.startswith(str(year)):
            return rd
    raise RuntimeError(f"no 10-K for {year}")


def overlay_new_report(cik: str, year: int):
    """A new 10-K for ``year + 1``: the last annual entries shifted one year, +5%."""
    def shift(s):
        d = date.fromisoformat(s)
        return d.replace(year=d.year + 1, day=min(d.day, 28)).isoformat() if (d.month, d.day) == (2, 29) else d.replace(year=d.year + 1).isoformat()

    def transform(name, data):
        if name == f"sub_{cik}.json":
            data = copy.deepcopy(data)
            r = data["filings"]["recent"]
            for k, v in (("form", "10-K"), ("accessionNumber", FAKE_NEW_10K), ("filingDate", date.today().isoformat()), ("primaryDocument", "new.htm")):
                r[k].insert(0, v)
            r["reportDate"].insert(0, shift(_report_date(data, year, r)))
        elif name == f"facts_{cik}.json":
            data = copy.deepcopy(data)
            for taxo in data["facts"].values():
                for node in taxo.values():
                    for unit in node.get("units", {}).values():
                        twins = []
                        for e in unit:
                            if e.get("form") == "10-K" and e.get("fp") == "FY" and e["end"].startswith(str(year)):
                                t = dict(e, end=shift(e["end"]), val=e["val"] * 1.05, accn=FAKE_NEW_10K, filed=date.today().isoformat(), fy=year + 1)
                                if "start" in e:
                                    t["start"] = shift(e["start"])
                                twins.append(t)
                        unit.extend(twins)
        return data
    return transform


def make(client, dry=False, transform=None, max_age=20.0) -> Pipeline:
    return Pipeline(PipelineSec(transform=transform, max_age_hours=max_age), client=client, dry_run=dry)


def clean_company(client, company_id) -> None:
    for t in ("financial_facts", "filing_periods", "company_profile_history", "market_snapshot"):
        client.table(t).delete().eq("company_id", company_id).execute()


def main(argv) -> int:
    if db_target() == "prod":
        raise SystemExit("the acceptance tests write to the database: refused for VC_DB_TARGET=prod")
    ticker = argv[argv.index("--ticker") + 1] if "--ticker" in argv else "PEP"
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    client = get_supabase_client()
    print(f"[database target: {db_target()}]  simulated company: {ticker}")
    if client.table("companies").select("id").eq("symbol", ticker).execute().data:
        raise SystemExit(f"{ticker} is already in the database: pick a ticker that is not (--ticker)")

    print("dry run on an unknown ticker")
    r = make(client, dry=True).load(ticker)
    check("dry run writes nothing", not client.table("companies").select("id").eq("symbol", ticker).execute().data and r.dry_run and r.facts["inserted"] > 0, f"{r.facts}")

    print("new company")
    r = make(client).load(ticker)
    row = client.table("companies").select("*").eq("symbol", ticker).execute().data[0]
    cid = row["id"]
    n = counts(client, cid)
    check("new company: created and data_loaded", row["processing_state"] == "data_loaded" and r.status in ("success", "partial_success") and n["financial_facts"] > 100 and n["filing_periods"] >= 8, f"{n}, profile {row['profile']}")
    pe = client.table("filing_periods").select("accession").eq("company_id", cid).execute().data
    check("new company: real accession numbers", all(p["accession"][:3].isdigit() and "placeholder" not in p["accession"] and "n/a" not in p["accession"] for p in pe))

    print("idempotency")
    r2 = make(client).load(ticker)
    check("second load changes 0 rows", r2.rows_written == 0 and r2.status == "no_change", f"facts {r2.facts}, periods {r2.periods}")
    check("second load: no SEC request", r2.requests == 0, f"{r2.requests} requests")

    latest = max(int(p["fiscal_year"]) for p in client.table("filing_periods").select("fiscal_year").eq("company_id", cid).execute().data)
    cik = row["cik"]
    print("restatement (simulated 10-K/A)")
    base = {(d["fiscal_year"], d["item_id"]): d["value"] for d in client.table("financial_facts").select("fiscal_year,item_id,value").eq("company_id", cid).execute().data}
    pipe = make(client, transform=overlay_amendment(cik, latest))
    resolved, plans = pipe.audit(ticker)
    sup = [p.fiscal_year for p in plans if p.status == "superseded"]
    check("restatement: audit finds the year superseded", sup == [latest], f"superseded: {sup}")
    r3 = pipe.load(ticker, "amendment")
    after = client.table("financial_facts").select("fiscal_year,item_id,value,flags").eq("company_id", cid).execute().data
    changed = [(d["fiscal_year"], d["item_id"]) for d in after if base.get((d["fiscal_year"], d["item_id"])) != d["value"]]
    restated = [d for d in after if "restated" in (d["flags"] or [])]
    p_row = client.table("filing_periods").select("accession,form").eq("company_id", cid).eq("fiscal_year", latest).execute().data[0]
    lg = client.table("data_update_log").select("update_scope,source_details,status").eq("company_id", cid).order("created_at", desc=True).limit(1).execute().data[0]
    check("restatement: one value rewritten and flagged restated", len(changed) >= 1 and all(c[0] == latest for c in changed) and len(restated) == len(changed) and r3.restated, f"changed {len(changed)}, restated {r3.restated}")
    check("restatement: filing period points at the amendment", p_row["accession"] == FAKE_AMENDMENT and p_row["form"] == "10-K/A", str(p_row))
    check("restatement: logged", lg["update_scope"] == "amendment" and bool(lg["source_details"][0]["restated"]), f"{lg['status']}")

    print("cleanup and reload from the real documents")
    clean_company(client, cid)
    r4 = make(client).load(ticker)
    check("reload from real data after the simulation", r4.rows_written > 100 and not [1 for d in client.table("financial_facts").select("flags").eq("company_id", cid).execute().data if "restated" in (d["flags"] or [])])

    print("new annual report (simulated)")
    before = counts(client, cid)
    pipe = make(client, transform=overlay_new_report(cik, latest))
    r5 = pipe.load(ticker, "new_report")
    after_n = counts(client, cid)
    new_years = sorted(p["fiscal_year"] for p in client.table("filing_periods").select("fiscal_year,accession").eq("company_id", cid).execute().data if p["accession"] == FAKE_NEW_10K)
    hist = sorted(h["fiscal_year"] for h in client.table("company_profile_history").select("fiscal_year").eq("company_id", cid).execute().data)
    lg = client.table("data_update_log").select("source_details").eq("company_id", cid).order("created_at", desc=True).limit(1).execute().data[0]
    check("new report: only the new year added", r5.years == [latest + 1] and new_years == [latest + 1] and after_n["filing_periods"] == before["filing_periods"] + 1, f"years {r5.years}, facts {r5.facts}")
    check("new report: router ran for the new year", (latest + 1) in hist, f"profile history years {hist}")
    check("new report: 'AI required' recorded", bool(lg["source_details"][0]["ai_required"]) and lg["source_details"][0]["ai_required"][0]["fiscal_year"] == latest + 1)
    clean_company(client, cid)
    r6 = make(client).load(ticker)
    check("final reload from real data", r6.rows_written > 100 and r6.state == "data_loaded", f"facts {r6.facts}")

    print("unsupported (20-F filer)")
    r7 = make(client).load("TSM")
    trow = client.table("companies").select("processing_state,unsupported_reason").eq("symbol", "TSM").execute().data
    check("unsupported: stored with a reason, nothing loaded", r7.state == "unsupported" and trow and trow[0]["processing_state"] == "unsupported" and "20-F" in (trow[0]["unsupported_reason"] or "") and r7.rows_written == 0, str(trow))

    failed = [r for r in RESULTS if not r["pass"]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if out:
        Path(out).write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

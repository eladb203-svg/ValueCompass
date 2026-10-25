"""K6b section 8.2: facts collected from SEC now (the pipeline's live cache) against facts built from the frozen local cache of the earlier stages (scripts/cache/sec).

For every development-set company: provider -> facts on both sides with the same provider code, then every difference (value, status, source kind, tag, missing on one side) is listed
with the fiscal year and item. Then the live facts are compared with what the database holds (the pipeline's DQ flags and held values show up there).

    .venv/Scripts/python scripts/k6b_compare_cache.py KO MSFT JPM CB O AMT INTC [--out scripts/output_k6b/compare_cache.json]
Reads the database of VC_DB_TARGET (default test); writes nothing to it. No download unless the live cache lacks a file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.db import db_target, get_supabase_client  # noqa: E402
from src.etl.db_io import equal_values  # noqa: E402
from src.etl.from_providers import facts_from_kwargs  # noqa: E402
from src.pipeline import collect as C  # noqa: E402
from src.pipeline.route import ENGINE_OF_PROFILE  # noqa: E402
from src.pipeline.sec_source import PipelineSec  # noqa: E402
from src.providers.sec_companyfacts import SecClient  # noqa: E402
from src.repositories.company_repository import CompanyRepository  # noqa: E402
from src.repositories.financial_repository import FinancialRepository  # noqa: E402


def index(facts) -> dict:
    return {(f.fiscal_year, f.item_key): f for f in facts}


def compare(a: dict, b: dict, left: str, right: str) -> list:
    out = []
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k), b.get(k)
        if x is None or y is None:
            f = x or y
            out.append({"fy": k[0], "item": k[1], "kind": f"only in {right if x is None else left}", left: None if x is None else x.value, right: None if y is None else y.value, "tag": f.tag, "flags": list(f.flags)})
        elif not equal_values(x.value, y.value):
            out.append({"fy": k[0], "item": k[1], "kind": "value", left: x.value, right: y.value, "tag": f"{x.tag} | {y.tag}", "flags": list(y.flags)})
        elif (x.status, x.source_kind, x.tag) != (y.status, y.source_kind, y.tag):
            out.append({"fy": k[0], "item": k[1], "kind": "source/tag", left: f"{x.status}/{x.source_kind}/{x.tag}", right: f"{y.status}/{y.source_kind}/{y.tag}", "tag": "", "flags": list(y.flags)})
        elif tuple(x.flags) != tuple(y.flags):
            out.append({"fy": k[0], "item": k[1], "kind": "flags", left: list(x.flags), right: list(y.flags), "tag": x.tag, "flags": list(y.flags)})
    return out


def main(argv) -> int:
    out_path = None
    tickers = []
    it = iter(argv)
    for a in it:
        if a == "--out":
            out_path = next(it)
        else:
            tickers.append(a.upper())
    client = get_supabase_client()
    companies, fin = CompanyRepository(client), FinancialRepository(client)
    old_sec, new_sec = SecClient(), PipelineSec(max_age_hours=float("inf"))          # the live cache is already fresh from the load; no new download
    print(f"[database target: {db_target()}]")
    report = {}
    for t in tickers:
        row = companies.get_by_symbol(t, "US")
        profile = row["profile"]
        engine = ENGINE_OF_PROFILE[profile]
        kw_old, _ = C.provider_kwargs(engine, old_sec, t, profile)
        kw_new, _ = C.provider_kwargs(engine, new_sec, t, profile)
        a, b = index(facts_from_kwargs(engine, kw_old).facts), index(facts_from_kwargs(engine, kw_new).facts)
        sec_vs_cache = compare(a, b, "cache", "sec")
        db = {(d["fiscal_year"], d["item_key"]): d for d in fin.get_history(row["id"])}
        from src.etl.facts import Fact
        dbf = index([Fact(t, k[0], k[1], d["value"], d["status"], d["source_kind"], tag=d["tag"], flags=tuple(d["flags"])) for k, d in db.items() if d["source_kind"] != "extraction"])
        sec_vs_db = compare(b, dbf, "sec", "db")
        report[t] = {"engine": engine, "profile": profile, "facts_cache": len(a), "facts_sec": len(b), "facts_db": len(dbf), "sec_vs_cache": sec_vs_cache, "sec_vs_db": sec_vs_db,
                     "years_cache": sorted({k[0] for k in a}), "years_sec": sorted({k[0] for k in b})}
        print(f"{t:<5}{engine:<11} facts cache {len(a):>5}  sec {len(b):>5}  db {len(dbf):>5}  | differences sec vs cache: {len(sec_vs_cache):>3}   sec vs db: {len(sec_vs_db):>3}")
    if out_path:
        Path(out_path).write_text(json.dumps(report, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
        print("written:", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

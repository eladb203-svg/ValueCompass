"""BP production load (approved by the owner in the chat, 2026-10-26). Copies the business vocabulary, the approved term translations and the 7 development-set profiles from TEST to PRODUCTION,
then renders the texts in production and marks the old D1/T1 texts superseded. 0 Gemini calls, 0 translation calls (the builder has no model and a translator without a key).

  bp_prod.py load      vocab + approved translations + profiles (idempotent: rows that exist are not touched)
  bp_prod.py render    render_store for the 7 companies in production (superseding the old texts)
  bp_prod.py verify    compare the 7 EN / HE texts with test, human_reviewed, a second render (0 changes), v_company_status

Migrations 17-19 must already be applied in production (done and verified through the Supabase tools before this script runs).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai.db_stores import DbAssessmentStore, DbTextStore  # noqa: E402
from src.bp.pipeline import BackgroundBuilder  # noqa: E402
from src.bp.stores import ProfileStore  # noqa: E402
from src.bp.translate import AzureTranslate  # noqa: E402
from src.db import get_supabase_client  # noqa: E402
from src.pipeline import scoring as S  # noqa: E402

DEV = ["KO", "MSFT", "INTC", "JPM", "CB", "O", "AMT"]
NEW_PROFILE_KEYS = ("accession", "fiscal_year", "source_market", "model", "skill_version", "core_activity", "segments", "products_services", "customer_types", "revenue_models", "regions",
                    "competitors", "competitor_types", "axes_found", "display_name")


def clients():
    return get_supabase_client("test"), get_supabase_client("prod")


def company_id(client, symbol: str) -> int:
    r = client.table("companies").select("id").eq("symbol", symbol).eq("exchange", "US").limit(1).execute().data
    return r[0]["id"]


def builder(prod) -> BackgroundBuilder:
    S.seed_results(S.RESULTS_DIR)
    return BackgroundBuilder(prod, DbAssessmentStore(prod), DbTextStore(prod), gemini=None, translator=AzureTranslate(key=""), results_dir=S.RESULTS_DIR, sec=None)


def cmd_load() -> None:
    test, prod = clients()
    have = {(r["field"], r["code"]) for r in prod.table("business_vocab").select("*").execute().data}
    vocab = [{k: r[k] for k in ("field", "code", "label_en", "label_he", "active")} for r in test.table("business_vocab").select("*").execute().data if (r["field"], r["code"]) not in have]
    for i in range(0, len(vocab), 100):
        prod.table("business_vocab").insert(vocab[i:i + 100]).execute()
    print("business_vocab inserted:", len(vocab))
    have_t = {r["en"] for r in prod.table("term_translations").select("en").execute().data}
    terms = [{k: r[k] for k in ("en", "he", "source", "status", "reviewed_at")} for r in test.table("term_translations").select("*").eq("status", "approved").execute().data if r["en"] not in have_t]
    for i in range(0, len(terms), 100):
        prod.table("term_translations").insert(terms[i:i + 100]).execute()
    print("term_translations (approved only) inserted:", len(terms), "| unreviewed in test not copied:",
          test.table("term_translations").select("id", count="exact").eq("status", "unreviewed").execute().count)
    ps = ProfileStore(prod)
    for t in DEV:
        tp = ProfileStore(test).latest(company_id(test, t))
        pid = company_id(prod, t)
        if ps.get(pid, tp["accession"]):
            print(t, "profile exists in production: left as it is")
            continue
        row = {"company_id": pid, **{k: tp[k] for k in NEW_PROFILE_KEYS}}
        saved = ps.put(row)
        print(t, "profile copied -> production profile", saved["id"], "accession", tp["accession"])


def cmd_render() -> None:
    _test, prod = clients()
    b = builder(prod)
    for t in DEV:
        print(t, b.render_only(t))
    print("gemini calls: 0; translation calls:", b.translator.calls)


def texts_of(client, symbol: str) -> dict:
    cid = company_id(client, symbol)
    rows = client.table("ai_texts").select("*").eq("company_id", cid).eq("kind", "background").execute().data
    return {r["language"]: r for r in rows if r.get("template_version")}


def cmd_verify() -> None:
    test, prod = clients()
    b = builder(prod)
    ok = True
    for t in DEV:
        a, p = texts_of(test, t), texts_of(prod, t)
        for lang in ("en", "he"):
            same = lang in a and lang in p and a[lang]["text"] == p[lang]["text"]
            flags = (p.get(lang) or {}).get("human_reviewed"), (p.get(lang) or {}).get("approval_status")
            print(f"{t} {lang}: identical to test={same}  human_reviewed/status in production={flags}")
            ok &= bool(same and flags == (True, "approved"))
    second = [b.render_only(t)["texts_changed"] for t in DEV]
    print("second render, texts changed per company:", second)
    ok &= not any(second)
    old = prod.table("ai_texts").select("approval_status,template_version,kind").eq("kind", "background").execute().data
    print("old D1/T1 texts in production by status:", {s: sum(1 for r in old if r["template_version"] is None and r["approval_status"] == s) for s in {r["approval_status"] for r in old if r["template_version"] is None}})
    st = prod.table("v_company_status").select("symbol,processing_state,background_status,background_human_reviewed").in_("symbol", DEV).execute().data
    for r in sorted(st, key=lambda r: r["symbol"]):
        print("v_company_status:", r)
        ok &= r["processing_state"] == "complete" and r["background_status"] == "approved" and r["background_human_reviewed"] is True
    print("ALL OK" if ok else "MISMATCH")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("load", "render", "verify"))
    a = ap.parse_args()
    {"load": cmd_load, "render": cmd_render, "verify": cmd_verify}[a.command]()

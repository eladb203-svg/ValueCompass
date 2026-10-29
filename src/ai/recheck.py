"""``vc.py approvals recheck``: the approval rules (``approval_rules.py``) applied to the extraction rows already in the database. ``--dry-run`` (default) lists every change and writes nothing;
``--apply`` writes the new status, the source (``ai_controls`` for an approval), the reason (``note``) and the rule (``control.approval_rule``) of each changed row. A rejected row is kept.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from src.ai import approval_rules as AR
from src.ai.db_stores import select_all
from src.etl import field_map as fm


def company_facts(client, company_id: int) -> dict:
    """{fact item_key: {fiscal_year: value}} from financial_facts."""
    global _ITEM_KEYS
    if _ITEM_KEYS is None:
        _ITEM_KEYS = {r["id"]: r["item_key"] for r in select_all(client, "dictionary_items")}
    out: dict = {}
    for d in select_all(client, "financial_facts", {"company_id": company_id}, order="fiscal_year"):
        if d.get("value") is not None and d["item_id"] in _ITEM_KEYS:
            out.setdefault(_ITEM_KEYS[d["item_id"]], {})[int(d["fiscal_year"])] = float(d["value"])
    return out


_ITEM_KEYS: Optional[dict] = None


def engine_of(company: dict) -> Optional[str]:
    from src.pipeline import scoring as S
    try:
        return S.runner_engine(company["profile"], company["symbol"]) if company.get("profile") else None
    except Exception:   # noqa: BLE001 - a company without a runner engine has no field map
        return None


def decisions_for(client, company: dict, labels: dict, rows: Optional[list] = None) -> list:
    if rows is None:
        rows = [r for r in select_all(client, "extraction_items", {"company_id": company["id"]}) if r.get("skill_id")]
    if not rows:
        return []
    eng = engine_of(company)
    fact_key_of = {f: k for f, k in (fm.FIELDS.get(eng) or {}).items()} if eng else {}
    return AR.evaluate(rows, company_facts(client, company["id"]), labels, fact_key_of, company["symbol"])


def apply_decisions(client, decisions: list, now: Optional[datetime] = None) -> int:
    now = (now or datetime.now(timezone.utc)).isoformat()
    n = 0
    for d in decisions:
        if not d.changed:
            continue
        cur = client.table("extraction_items").select("control,approved_at").eq("id", d.row_id).limit(1).execute().data[0]
        control = {**(cur.get("control") or {}), "approval_rule": {"rule": d.rule, "reason": d.reason, "previous_status": d.before, "at": now}}
        fields = {"approval_status": d.after, "approval_source": d.source if d.after == "approved" else None, "note": d.reason[:500], "control": control}
        if d.after == "approved" and not cur.get("approved_at"):
            fields["approved_at"] = now
        client.table("extraction_items").update(fields).eq("id", d.row_id).execute()
        n += 1
    return n


def recheck(client, ticker: Optional[str] = None, apply: bool = False) -> dict:
    """-> {"decisions": [Decision], "changed": n, "applied": n}."""
    labels = AR.load_labels()
    by_co: dict = {}
    for r in select_all(client, "extraction_items"):                  # one read of the table; only companies that have AI rows are judged
        if r.get("skill_id"):
            by_co.setdefault(r["company_id"], []).append(r)
    comps = [c for c in select_all(client, "companies") if c["id"] in by_co and (not ticker or c["symbol"] == ticker.upper())]
    all_d = []
    for c in comps:
        all_d += decisions_for(client, c, labels, by_co[c["id"]])
    applied = apply_decisions(client, all_d) if apply else 0
    return {"decisions": all_d, "changed": sum(1 for d in all_d if d.changed), "applied": applied}


def table(decisions: list) -> str:
    """Counts by company, skill and rule: before -> after."""
    c = Counter((d.ticker, d.skill, d.rule, d.before, d.after) for d in decisions if d.changed)
    lines = [f"{'company':<8}{'skill':<14}{'rule':<22}{'before':<10}{'after':<10}rows"]
    for (t, s, r, b, a), n in sorted(c.items()):
        lines.append(f"{t:<8}{(s or ''):<14}{r:<22}{b:<10}{a:<10}{n}")
    return "\n".join(lines)


def status_table(client, tickers: Optional[list] = None) -> dict:
    """{ticker: {skill: {status: n}}} of the figure rows in the database (for the before / after table)."""
    names = {c["id"]: c["symbol"] for c in select_all(client, "companies")}
    out: dict = {}
    for r in select_all(client, "extraction_items"):
        if not r.get("skill_id") or r.get("value_state") != "value":
            continue
        t = names.get(r["company_id"])
        if tickers and t not in tickers:
            continue
        out.setdefault(t, {}).setdefault(r["skill_id"], Counter())[r["approval_status"]] += 1
    return out

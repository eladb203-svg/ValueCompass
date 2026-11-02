"""The review list of data gaps (K6d-2 fixes, 2026-11-01; table ``data_gap_review``, administrator only). No model call.

After a score, every criterion that stays Missing (the engine's state ``missing``; ``not_applicable`` is a different state and never listed) gets a row: the company, the criterion, the annual report,
the engine's reason, the closest passage of that report by the keywords of the item (about 300 characters) and a family - the group of items with the same kind of gap, so one fix closes the
whole family. State: ``open``; ``genuine`` when the rulebook itself says the item is missing (OE proxy, no economic value basis, short history); ``fixed`` when a later score no longer lists
the item (``closed_at`` is set). A row closed more than 180 days ago goes in the weekly cleanup (``src/sched/cleanup.py``).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
FILINGS = ROOT / "scripts" / "cache" / "filings"
PASSAGE = 300

# (pattern of the engine's note, family, keywords of the item in the report, genuine by the rulebook)
FAMILIES = (
    (r"same-property NOI growth", "same_property_noi", r"same[- ](?:property|store)[^.]{0,120}(?:NOI|net operating income|revenues?)|comparable hotels?|RevPAR|same-store (?:cash |SHOP )?NOI", False),
    (r"largest tenant", "largest_tenant", r"no (?:single )?(?:tenant|operator)|largest (?:tenants?|operators?)|ten largest|10 largest|operators? represented|EBITDARM|triple-net", False),
    (r"unencumbered", "unencumbered", r"unencumbered", False),
    (r"occupancy|mapped metric", "occupancy", r"occupancy|% leased|percent leased|hotel occupancy|SHOP occupancy", False),
    (r"committed undrawn|undrawn", "undrawn_facilities", r"undrawn|unused (?:borrowing )?capacity|available (?:under|on) (?:our )?(?:revolving|credit)", False),
    (r"debt maturities", "debt_maturities", r"maturit(?:y|ies)[^.]{0,80}(?:thereafter|20\d\d)", False),
    (r"OE is a proxy|OE is a proxy or missing", "oe_proxy", r"recurring capital|maintenance capital|tenant improvements|leasing commissions", True),
    (r"economic value basis|economic value and matching", "economic_value_basis", r"fair value of (?:our )?(?:real estate|investment properties|properties)", True),
    (r"stabilized acquisition / development yield", "stabilized_yields", r"stabilized yield|initial cash yield|development yield", False),
    (r"LCR", "lcr", r"liquidity coverage ratio|\bLCR\b", False),
    (r"RWA", "rwa", r"risk[- ]weighted assets", False),
    (r"regulatory capital ratio", "capital_ratio", r"(?:risk[- ]based capital|\bRBC\b)[^.]{0,100}(?:ratio|%)|statutory (?:capital|surplus)", False),
    (r"investment-grade|credit-quality table|credit quality", "ig_share", r"investment[- ]grade|non-investment", False),
    (r"balance-sheet categories", "investments_block", r"total (?:cash and )?investments|fixed maturit", False),
    (r"dividend per share", "dividend_per_share", r"dividends?[^.]{0,60}per (?:common )?share", False),
    (r"share counts?", "share_counts", r"shares? outstanding|weighted[- ]average (?:diluted )?shares", False),
    (r"tangible BVPS", "tangible_bvps", r"tangible book value|goodwill", False),
    (r"cost of float|float", "float_cost", r"float|underwriting (?:income|loss)", False),
    (r"NCO|net charge", "nco", r"net charge-?offs?", False),
    (r"fewer than|need first|first or last|first-|last-|transitions|valid P/E|valid \(non-acquisition\)|computable for fewer", "short_history", r"", True),
    (r"AI: insufficient evidence", "ai_insufficient", r"", False),
)


def family_of(note: str) -> tuple:
    """-> (family, keyword regex, genuine by the rulebook) of the engine's note."""
    for pat, fam, kw, genuine in FAMILIES:
        if re.search(pat, note or "", re.I):
            return fam, kw, genuine
    return "other: " + re.sub(r"\d+", "#", (note or "unspecified")[:40]), "", False


def closest_passage(text: str, keywords: str, width: int = PASSAGE) -> str:
    """The passage of the report around the first match of the keywords, about ``width`` characters; empty when nothing matches."""
    if not text or not keywords:
        return ""
    m = re.search(keywords, text, re.I)
    if not m:
        return ""
    a = max(0, m.start() - (width - (m.end() - m.start())) // 2)
    return text[a:a + width].replace("\n", " ").strip()


def item_key(model: str, criterion_key: str, sub: str) -> str:
    return f"{'B' if str(model).lower().startswith('b') else 'G'} {criterion_key}.{sub}"


def missing_of_latest_run(client, company_id: int) -> list:
    """[{item_key, note, label}] of the latest score run of the company: the sub-items whose state is ``missing``."""
    run = client.table("score_runs").select("id").eq("company_id", company_id).order("id", desc=True).limit(1).execute().data
    if not run:
        return []
    rows = client.table("score_details").select("model,criterion_key,sub_criterion_key,detail_level,evidence").eq("run_id", run[0]["id"]).execute().data
    out = []
    for r in rows:
        ev = r.get("evidence") or {}
        if r["criterion_key"] == "total" or r["detail_level"] == "criterion" or ev.get("state") != "missing":
            continue
        out.append({"item_key": item_key(r["model"], r["criterion_key"], r["sub_criterion_key"]), "note": ev.get("note") or "", "label": ev.get("metric_label") or ""})
    return out


def latest_report(client, company_id: int, filings_dir: Path = FILINGS) -> tuple:
    """-> (fiscal year, accession, Path of the cached report or None) of the latest annual report of the company."""
    fp = client.table("filing_periods").select("fiscal_year,accession").eq("company_id", company_id).order("fiscal_year", desc=True).limit(1).execute().data
    if not fp:
        return None, None, None
    acc = (fp[0]["accession"] or "").replace("-", "")
    hits = [p for p in Path(filings_dir).glob(f"{acc}_*.htm")] if acc else []
    return fp[0]["fiscal_year"], fp[0]["accession"], (hits[0] if hits else None)


def refresh(client, company_id: int, filings_dir: Path = FILINGS, now: Optional[datetime] = None, text_of=None) -> dict:
    """Bring the rows of one company in line with its latest score: add / update the missing criteria, close the ones that are not missing any more. -> counts.
    ``text_of(path)`` reads a report as text (default: the same reader as the keyword steps); a failure to read gives a row without a passage."""
    now = now or datetime.now(timezone.utc)
    missing = missing_of_latest_run(client, company_id)
    fy, acc, path = latest_report(client, company_id, filings_dir)
    text = ""
    if path is not None and any(family_of(m["note"])[1] for m in missing):
        try:
            if text_of is None:
                from .keyword_depth import report_text as text_of
            text = text_of(path)
        except Exception:  # noqa: BLE001 - the passage is a help for the reviewer, never a reason to stop
            text = ""
    existing = {r["item_key"]: r for r in client.table("data_gap_review").select("*").eq("company_id", company_id).execute().data}
    counts = {"added": 0, "updated": 0, "closed": 0, "open": 0, "genuine": 0}
    seen = set()
    for m in missing:
        fam, kw, genuine = family_of(m["note"])
        seen.add(m["item_key"])
        row = {"company_id": company_id, "item_key": m["item_key"], "fiscal_year": fy, "accession": acc, "reason": m["note"][:500] or "missing", "closest_passage": closest_passage(text, kw) or None,
               "family": fam, "last_seen": now.isoformat()}
        old = existing.get(m["item_key"])
        if old is None:
            row.update({"state": "genuine" if genuine else "open", "first_seen": now.isoformat(), "closed_at": now.isoformat() if genuine else None})
            counts["added"] += 1
        else:
            keep = old["state"] if old["state"] in ("genuine",) else ("genuine" if genuine else "open")
            row.update({"state": keep, "closed_at": old.get("closed_at") if keep == "genuine" else None})
            counts["updated"] += 1
        counts["genuine" if row["state"] == "genuine" else "open"] += 1
        client.table("data_gap_review").upsert(row, on_conflict="company_id,item_key").execute()
    for key, old in existing.items():
        if key not in seen and old["state"] != "fixed":
            client.table("data_gap_review").update({"state": "fixed", "closed_at": now.isoformat(), "last_seen": now.isoformat()}).eq("company_id", company_id).eq("item_key", key).execute()
            counts["closed"] += 1
    return counts


def record_conflicts(client, company_id: int, conflicts: list, accession: Optional[str] = None, now: Optional[datetime] = None) -> int:
    """Two candidates of the wide XBRL search that disagree (or a class that could not be identified) leave the year missing; the conflict is a row of the list, family ``wide_xbrl_conflict``."""
    now = now or datetime.now(timezone.utc)
    n = 0
    for c in conflicts:
        client.table("data_gap_review").upsert({"company_id": company_id, "item_key": f"XBRL {c['field']} {c['end'][:4]}", "fiscal_year": int(c["end"][:4]), "accession": accession, "reason": c["reason"][:500],
                                                "family": "wide_xbrl_conflict", "state": "open", "last_seen": now.isoformat()}, on_conflict="company_id,item_key").execute()
        n += 1
    return n


def grouped(client, family: Optional[str] = None, state: Optional[str] = None) -> list:
    """[(family, state counts, number of companies, [(ticker, item_key, reason)])] sorted by the number of companies, largest first."""
    q = client.table("data_gap_review").select("company_id,item_key,family,state,reason,fiscal_year")
    if family:
        q = q.eq("family", family)
    if state:
        q = q.eq("state", state)
    rows = q.execute().data
    tick = {c["id"]: c["symbol"] for c in client.table("companies").select("id,symbol").execute().data}
    fams: dict = {}
    for r in rows:
        f = fams.setdefault(r["family"], {"states": {}, "companies": set(), "items": []})
        f["states"][r["state"]] = f["states"].get(r["state"], 0) + 1
        f["companies"].add(r["company_id"])
        f["items"].append((tick.get(r["company_id"], "?"), r["item_key"], r["state"], r["reason"]))
    return sorted(((k, v["states"], len(v["companies"]), sorted(v["items"])) for k, v in fams.items()), key=lambda x: (-x[2], x[0]))

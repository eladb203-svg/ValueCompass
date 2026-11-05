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
SPECIAL_FAMILIES = ("core_missing", "suspect_data", "wide_xbrl_conflict")

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


# the figures without which a company has no sound score: a missing one is an alert to the administrator and a top-priority row (decision 2026-11-02)
CORE_KEYS = {"general": ("revenue", "net_income", "eps_diluted", "equity", "cfo", "capex", "shares_diluted_weighted"),
             "bank": ("net_income", "equity", "loans", "deposits", "eps_diluted"),
             "insurance": ("premiums_earned", "net_income", "equity", "eps_diluted"),
             "realestate": ("revenue", "net_income", "eps_diluted", "total_assets",
                             "interest_expense", "da", "financial_debt", "cash")}          # the REIT dictionary has no equity item (NOI and FFO are computed by the engine from these and the property lines); decision 2026-11-05: the leverage components (interest, D&A -> EBITDAre; debt and cash -> net debt) are core, without them 3.6.1 / 3.6.2 / 3.8.4 are silently missing (MAC)
ENGINE_OF_PROFILE = {"BANK": "bank", "INSURANCE": "insurance", "INCOME_REAL_ESTATE": "realestate"}


def core_missing(client, company_id: int, profile: Optional[str]) -> list:
    """[(item key, fiscal year)] - the core figures of the profile that the latest loaded year does not have (a bank also needs its CET1 ratio, approved, for that year)."""
    engine = ENGINE_OF_PROFILE.get(profile or "", "general")
    facts = client.table("financial_facts").select("fiscal_year,item_id").eq("company_id", company_id).execute().data
    if not facts:
        return []
    ids = {r["id"]: r["item_key"] for r in client.table("dictionary_items").select("id,item_key").execute().data}
    latest = max(f["fiscal_year"] for f in facts)
    have = {ids.get(f["item_id"]) for f in facts if f["fiscal_year"] == latest}
    out = [(k, latest) for k in CORE_KEYS[engine] if k not in have]
    if engine == "bank":
        cet1 = [r for r in client.table("extraction_items").select("item_key,period,value,approval_status").eq("company_id", company_id).execute().data
                if (r["item_key"] or "").split("|")[0] in ("cet1_ratio_standardized", "cet1_ratio_advanced") and r.get("approval_status") == "approved" and r.get("value") is not None and r.get("period") == f"FY{latest}"]
        if not cet1:
            out.append(("cet1_ratio", latest))
    return out


def record_core(client, company_id: int, profile: Optional[str], alert=None, now: Optional[datetime] = None) -> dict:
    """Rows of the family ``core_missing`` (priority 1) for the core figures that are missing; closed (fixed) when the figure exists. ``alert(label, reason, detail)`` is called once for a NEW core gap
    (the administrator alert - an e-mail when Resend is connected)."""
    now = now or datetime.now(timezone.utc)
    missing = core_missing(client, company_id, profile)
    existing = {r["item_key"]: r for r in client.table("data_gap_review").select("*").eq("company_id", company_id).eq("family", "core_missing").execute().data}
    new = 0
    seen = set()
    for key, fy in missing:
        ik = f"CORE {key} FY{fy}"
        seen.add(ik)
        if ik in existing and existing[ik]["state"] == "open":
            continue
        client.table("data_gap_review").upsert({"company_id": company_id, "item_key": ik, "fiscal_year": fy, "reason": f"core figure {key} is missing for FY{fy}", "family": "core_missing", "state": "open",
                                                "priority": 1, "last_seen": now.isoformat(), "closed_at": None}, on_conflict="company_id,item_key").execute()
        new += 1
        if alert:
            alert(f"company {company_id}", f"core figure {key} missing for FY{fy}", {"company_id": company_id, "item": key, "fiscal_year": fy})
    for ik, old in existing.items():
        if ik not in seen and old["state"] == "open":
            client.table("data_gap_review").update({"state": "fixed", "closed_at": now.isoformat(), "last_seen": now.isoformat()}).eq("company_id", company_id).eq("item_key", ik).execute()
    return {"core_missing": len(missing), "new": new}


def record_suspects(client, company_id: int, dq_results: list, now: Optional[datetime] = None) -> int:
    """A figure that failed a control is held back (suspect): it is not in the calculation and the user sees it as missing; the administrator sees it as WRONG with the reason (family suspect_data, priority 1)."""
    now = now or datetime.now(timezone.utc)
    n = 0
    for r in dq_results:
        check, outcome, fy, item, detail = r if isinstance(r, (tuple, list)) else (r.check, r.outcome, r.fiscal_year, r.item_key, r.detail)
        if outcome != "held" or not str(check).startswith("suspect"):
            continue
        client.table("data_gap_review").upsert({"company_id": company_id, "item_key": f"SUSPECT {item} FY{fy}", "fiscal_year": fy, "reason": f"wrong ({check}): {detail}"[:500], "family": "suspect_data", "state": "open",
                                                "priority": 1, "last_seen": now.isoformat(), "closed_at": None}, on_conflict="company_id,item_key").execute()
        n += 1
    return n


def close_suspects(client, company_id: int, held_now: Optional[set] = None, now: Optional[datetime] = None) -> int:
    """Rule M10, the end of the life of a suspect figure (calibration stage, owner decision 2026-11-04): a ``suspect_data`` row is closed (``fixed``) when the figure is no longer held back.
    Two ways in: (1) a load (``held_now`` = the set of (item, fiscal year) the controls hold back in THIS load): an open row whose figure is not in the set is closed - the pipeline was fixed or the source corrected;
    (2) ``held_now`` is None (``gaps fill`` / ``refresh``): an open row whose figure is now stored in ``financial_facts`` is closed - a held figure is never stored, so a stored one was entered by hand or accepted. -> number of rows closed."""
    now = now or datetime.now(timezone.utc)
    rows = [r for r in client.table("data_gap_review").select("*").eq("company_id", company_id).eq("family", "suspect_data").execute().data if r["state"] != "fixed"]
    if not rows:
        return 0
    repo = None
    n = 0
    for r in rows:
        m = re.match(r"SUSPECT (\S+) FY(\d+)$", r["item_key"] or "")
        if not m:
            continue
        item, fy = m.group(1), int(m.group(2))
        if held_now is not None:
            fixed = (item, fy) not in held_now
        else:
            if repo is None:
                from src.repositories.financial_repository import FinancialRepository
                repo = FinancialRepository(client)
            try:
                item_id = repo.item_id(item)
            except KeyError:
                continue
            fixed = bool(client.table("financial_facts").select("item_id").eq("company_id", company_id).eq("fiscal_year", fy).eq("item_id", item_id).limit(1).execute().data)
        if fixed:
            client.table("data_gap_review").update({"state": "fixed", "closed_at": now.isoformat(), "last_seen": now.isoformat()}).eq("company_id", company_id).eq("item_key", r["item_key"]).execute()
            n += 1
    return n


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
    existing = {r["item_key"]: r for r in client.table("data_gap_review").select("*").eq("company_id", company_id).execute().data if r["family"] not in SPECIAL_FAMILIES}      # core, suspect and conflict rows have their own lifecycle
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
    counts["suspects_closed"] = close_suspects(client, company_id, now=now)               # M10: a suspect figure that is stored now (entered by `gaps fill`) is not wrong any more
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

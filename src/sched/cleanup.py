"""The retention cleanup (K6 spec 3.3, decided 2026-10-26): the only code that deletes old data, apart from the single-run rule of a new score run (``ScoreRepository``).

What is kept and what goes (everything else - financial facts, filing periods, the current price - is never touched here):

  score_runs (+ score_details, valuations)   only the latest run of each company; the rest goes (a leftover from before the single-run rule)
  ai_assessments                             per company and question: the answers of the latest fiscal year, and of those the latest prompt version; older approved rows go
  ai_texts                                   every row with approval_status 'superseded' (the old D1 / T1 texts included); per company, kind and language only the newest text that
                                             is not 'failed' stays (a failed attempt newer than it stays: a retry waits there)
  company_business_profiles                  per company only the latest (fiscal year, then id)
  data_update_log                            rows older than 90 days
  work_queue                                 'done' / 'failed' tasks whose last change is older than 30 days (open tasks are never deleted)
  SEC filings cache on disk                  filing documents of a fiscal year older than the 10-year window of the company (outside the database)

``plan_cleanup`` only reads and returns the plan; ``apply_plan`` deletes exactly that plan. The scheduled job and ``vc.py cleanup`` default to the plan only (``--apply`` deletes).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from src.ai.db_stores import select_all

LOG_DAYS, QUEUE_DAYS, WINDOW_YEARS = 90, 30, 10
CHUNK = 100
DELETE_ORDER = ("ai_texts", "company_business_profiles", "ai_assessments", "score_runs", "data_update_log", "work_queue")


def version_key(v) -> tuple:
    """Prompt versions compare as numbers where they are numbers ("3.1" > "3", "10" > "9")."""
    return tuple(int(x) for x in re.findall(r"\d+", str(v))) or (0,)


def size_of(row: dict) -> int:
    return len(json.dumps(row, default=str, ensure_ascii=False))


@dataclass
class Planned:
    id: int
    company_id: Optional[int]
    why: str
    bytes: int = 0
    children: int = 0                               # rows that go with it (score_details + valuations of a run)


@dataclass
class CleanupPlan:
    now: datetime
    rows: dict = field(default_factory=lambda: {t: [] for t in DELETE_ORDER})
    files: list = field(default_factory=list)       # [{"path", "company_id", "fiscal_year", "bytes"}]

    def total_bytes(self) -> int:
        return sum(p.bytes for v in self.rows.values() for p in v) + sum(f["bytes"] for f in self.files)

    def counts(self) -> dict:
        return {**{t: len(v) for t, v in self.rows.items()}, "sec_cache_files": len(self.files)}


# ---------------------------------------------------------------- selection (pure on rows)
def old_runs(runs: list) -> list:
    """Run rows of ALL companies -> the runs that are not the latest of their company."""
    latest: dict = {}
    for r in runs:
        if r["company_id"] not in latest or r["id"] > latest[r["company_id"]]:
            latest[r["company_id"]] = r["id"]
    return [r for r in runs if r["id"] != latest[r["company_id"]]]


def old_assessments(rows: list) -> list:
    """Approved answers that are not the current version of their (company, question): not the latest fiscal year, or not the latest prompt version of it."""
    best: dict = {}
    for r in rows:
        if r.get("approval_status") != "approved":
            continue
        k = (r["company_id"], r["question_id"])
        cand = (r["fiscal_year"], version_key(r["prompt_version"]))
        if k not in best or cand > best[k]:
            best[k] = cand
    return [r for r in rows if r.get("approval_status") == "approved" and (r["fiscal_year"], version_key(r["prompt_version"])) != best[(r["company_id"], r["question_id"])]]


def old_texts(rows: list) -> list:
    """-> [(row, why)]: superseded texts, and the texts that an newer one replaced."""
    out = [(r, "superseded") for r in rows if r.get("approval_status") == "superseded"]
    live = [r for r in rows if r.get("approval_status") not in ("superseded",)]
    groups: dict = {}
    for r in live:
        groups.setdefault((r["company_id"], r["kind"], r["language"]), []).append(r)
    for g in groups.values():
        ok = [r for r in g if r.get("approval_status") != "failed"]
        if not ok:
            continue
        win = max(ok, key=lambda r: (r["fiscal_year"], str(r.get("created_at") or ""), r["id"]))
        wkey = (win["fiscal_year"], str(win.get("created_at") or ""), win["id"])
        for r in g:
            if r["id"] == win["id"]:
                continue
            if r.get("approval_status") == "failed" and (r["fiscal_year"], str(r.get("created_at") or ""), r["id"]) > wkey:
                continue                                    # a failed attempt newer than the current text waits for its retry
            out.append((r, "replaced by a newer text"))
    return out


def old_profiles(rows: list) -> list:
    latest: dict = {}
    for r in rows:
        k = (r["fiscal_year"], r["id"])
        if r["company_id"] not in latest or k > latest[r["company_id"]]:
            latest[r["company_id"]] = k
    return [r for r in rows if (r["fiscal_year"], r["id"]) != latest[r["company_id"]]]


def accession_dashed(file_name: str) -> Optional[str]:
    m = re.match(r"^(\d{10})(\d{2})(\d{6})_", file_name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def outside_window(files: list, periods: list, window: int = WINDOW_YEARS) -> list:
    """``files``: [Path]; ``periods``: filing_periods rows (company_id, fiscal_year, accession). -> [(path, company_id, fiscal_year)] of the filing documents that lie before the
    10-year window (latest fiscal year of the company - 9) of their company. A file whose accession is unknown is kept."""
    latest: dict = {}
    for p in periods:
        latest[p["company_id"]] = max(latest.get(p["company_id"], 0), p["fiscal_year"])
    by_acc = {p["accession"]: p for p in periods}
    out = []
    for f in files:
        acc = accession_dashed(f.name)
        p = by_acc.get(acc) if acc else None
        if p and p["fiscal_year"] < latest[p["company_id"]] - window + 1:
            out.append((f, p["company_id"], p["fiscal_year"]))
    return out


# ---------------------------------------------------------------- the plan
def plan_cleanup(client, now: Optional[datetime] = None, filings_dir: Optional[Path] = None) -> CleanupPlan:
    now = now or datetime.now(timezone.utc)
    plan = CleanupPlan(now)

    runs = select_all(client, "score_runs", order="id")
    for r in old_runs(runs):
        det = select_all(client, "score_details", {"run_id": r["id"]})
        val = select_all(client, "valuations", {"run_id": r["id"]})
        plan.rows["score_runs"].append(Planned(r["id"], r["company_id"], "not the latest run of the company", size_of(r) + sum(size_of(x) for x in det + val), len(det) + len(val)))

    for r in old_assessments(select_all(client, "ai_assessments")):
        plan.rows["ai_assessments"].append(Planned(r["id"], r["company_id"], f"{r['question_id']} FY{r['fiscal_year']} v{r['prompt_version']}: not the current version", size_of(r)))
    for r, why in old_texts(select_all(client, "ai_texts")):
        plan.rows["ai_texts"].append(Planned(r["id"], r["company_id"], f"{r['kind']}/{r['language']} FY{r['fiscal_year']}: {why}", size_of(r)))
    for r in old_profiles(select_all(client, "company_business_profiles")):
        plan.rows["company_business_profiles"].append(Planned(r["id"], r["company_id"], f"profile FY{r['fiscal_year']}: not the latest", size_of(r)))

    log_cut = (now - timedelta(days=LOG_DAYS)).isoformat()
    for r in client.table("data_update_log").select("*").lt("created_at", log_cut).execute().data:
        plan.rows["data_update_log"].append(Planned(r["id"], r.get("company_id"), f"older than {LOG_DAYS} days ({str(r['created_at'])[:10]})", size_of(r)))
    q_cut = (now - timedelta(days=QUEUE_DAYS)).isoformat()
    for r in client.table("work_queue").select("*").in_("state", ["done", "failed"]).lt("updated_at", q_cut).execute().data:
        plan.rows["work_queue"].append(Planned(r["id"], r.get("company_id"), f"{r['state']} task older than {QUEUE_DAYS} days", size_of(r)))

    if filings_dir is not None and Path(filings_dir).exists():
        periods = select_all(client, "filing_periods", order="company_id")
        for f, cid, fy in outside_window([p for p in Path(filings_dir).iterdir() if p.is_file()], periods):
            plan.files.append({"path": str(f), "company_id": cid, "fiscal_year": fy, "bytes": f.stat().st_size})
    return plan


def apply_plan(client, plan: CleanupPlan) -> dict:
    """Delete exactly what the plan lists. -> {table: rows deleted, "sec_cache_files": n}."""
    done = {}
    for table in DELETE_ORDER:
        ids = [p.id for p in plan.rows[table]]
        n = 0
        for i in range(0, len(ids), CHUNK):
            n += len(client.table(table).delete().in_("id", ids[i:i + CHUNK]).execute().data)
        done[table] = n
    removed = 0
    for f in plan.files:
        try:
            Path(f["path"]).unlink()
            removed += 1
        except FileNotFoundError:
            pass
    done["sec_cache_files"] = removed
    return done


def render_plan(plan: CleanupPlan, tickers: Optional[dict] = None) -> str:
    """The "will be deleted" list: per table and per company, and the space it frees."""
    tickers = tickers or {}
    lines = [f"Retention cleanup plan ({plan.now.isoformat(timespec='seconds')}): " + ", ".join(f"{k} {v}" for k, v in plan.counts().items()),
             f"space freed (rows as JSON text + files): {plan.total_bytes() / 1024:,.1f} KB"]
    for table in DELETE_ORDER:
        rows = plan.rows[table]
        if not rows:
            continue
        by_co: dict = {}
        for p in rows:
            by_co.setdefault(p.company_id, []).append(p)
        lines.append(f"- {table}: {len(rows)} row(s), {sum(p.bytes for p in rows) / 1024:,.1f} KB" + (f" (+ {sum(p.children for p in rows)} detail rows inside)" if table == "score_runs" else ""))
        for cid, ps in sorted(by_co.items(), key=lambda kv: (kv[0] is None, kv[0])):
            lines.append(f"    {tickers.get(cid, cid if cid is not None else '(no company)')}: {len(ps)}  e.g. #{ps[0].id} {ps[0].why}")
    if plan.files:
        lines.append(f"- SEC cache files: {len(plan.files)}, {sum(f['bytes'] for f in plan.files) / 1024 / 1024:,.1f} MB")
        by_co = {}
        for f in plan.files:
            by_co.setdefault(f["company_id"], []).append(f)
        for cid, fs in sorted(by_co.items()):
            lines.append(f"    {tickers.get(cid, cid)}: {len(fs)} file(s), FY{min(f['fiscal_year'] for f in fs)}-FY{max(f['fiscal_year'] for f in fs)}")
    return "\n".join(lines)

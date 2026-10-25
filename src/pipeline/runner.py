"""The pipeline for one company (K6 spec 2.1-2.6, 2.7 step 1, section 3): RESOLVE -> AUDIT -> ROUTE -> SRC/COLLECT -> DQ -> WRITE, with a job log.

``Pipeline.load`` runs a job; ``Pipeline.audit`` prints the plan and writes nothing; ``Pipeline.status`` reads. ``dry_run=True`` computes and reports, and writes nothing
(not even a new tag text). Scoring and the AI queue are not here (K6c); a new annual report only records "AI required" in the job log.

Job types (spec section 3), no schedule (K6d):
  initial_import   the full pipeline, 10 years                         (the ``load`` command; idempotent: a second run writes nothing)
  backfill         only the years the audit finds missing
  new_report       the year(s) newer than the newest loaded one + the router; "AI required" in the log
  amendment        years superseded by a 10-K/A or a newer filing: rewrite those years, flag ``restated``
  repair           recompute from the local cache, no download (a missing file is an error)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable, Optional

from src.etl.db_io import PLACEHOLDER_ACCESSION
from src.etl.extraction_store import reg_from_rows
from src.etl.facts import FactSet
from src.pipeline import audit as A
from src.pipeline import collect as C
from src.pipeline import dq as D
from src.pipeline import prices as P
from src.pipeline import resolve as R
from src.pipeline.route import ENGINE_OF_PROFILE, route
from src.providers.bank_facts import BANK_FIELDS
from src.providers.insurance_facts import INS_FIELDS
from src.providers.realestate_facts import RE_FIELDS
from src.repositories.company_repository import CompanyRepository
from src.repositories.extraction_repository import ExtractionRepository
from src.repositories.financial_repository import FinancialRepository

CALCULATION_VERSION = "k6b-sec-1"
JOBS = ("initial_import", "backfill", "new_report", "amendment", "repair")
LOG_OPERATION = {"initial_import": "import_company", "backfill": "refresh_financials", "new_report": "refresh_financials", "amendment": "refresh_financials", "repair": "full_refresh"}
DATA_SOURCE = "sec_edgar"


@dataclass
class JobResult:
    ticker: str
    job: str
    status: str                       # success | partial_success | no_change | failed
    dry_run: bool = False
    state: Optional[str] = None
    profile: Optional[str] = None
    engine: Optional[str] = None
    years: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    periods: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
    dq: list = field(default_factory=list)
    missing_series: list = field(default_factory=list)
    missing_years: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    requests: int = 0
    seconds: float = 0.0
    ai_required: list = field(default_factory=list)
    restated: list = field(default_factory=list)
    price: Optional[dict] = None
    error: Optional[str] = None
    plan: list = field(default_factory=list)

    @property
    def rows_written(self) -> int:
        return sum(s.get("inserted", 0) + s.get("updated", 0) for s in (self.facts, self.periods))


class Pipeline:
    def __init__(self, sec, client=None, dry_run: bool = False, splits_fn: Optional[Callable] = None, industry_fn: Optional[Callable] = None,
                 price_fn: Optional[Callable] = None, clock: Callable = time.monotonic, today: Optional[date] = None):
        from src.db import get_supabase_client
        self.sec, self.dry_run, self.clock = sec, dry_run, clock
        self.client = client or get_supabase_client()
        self.companies, self.financial, self.extraction = CompanyRepository(self.client), FinancialRepository(self.client), ExtractionRepository(self.client)
        from src.providers import industry_provider, prices as price_provider
        self.splits_fn = splits_fn or price_provider.get_splits
        self.industry_fn = industry_fn or industry_provider.get_industry
        self.price_fn = price_fn or P.fetch_last_price
        self.today = today or date.today()

    # ------------------------------------------------------------ read-only steps
    def _company(self, ticker: str, resolved=None):
        row = (self.companies.get_by_cik(resolved.cik) if resolved else None) or self.companies.get_by_symbol(ticker, "US")
        return row

    def _plan(self, resolved, company, facts_json=None) -> list:
        periods = self.financial.get_filing_periods(company["id"]) if company else []
        amend = {f.accession for f in resolved.annual if f.form.endswith("/A")}
        xbrl = _accessions_in(facts_json, amend) if (facts_json and amend) else None
        return A.plan(resolved, periods, xbrl_accessions=xbrl)

    def audit(self, ticker: str) -> tuple:
        """-> (Resolved, [YearPlan]). Writes nothing."""
        resolved = R.resolve(self.sec, ticker)
        company = self._company(ticker, resolved)
        if resolved.unsupported_reason:
            return resolved, []
        cf = self.sec.companyfacts(resolved.cik)
        return resolved, self._plan(resolved, company, cf)

    # ------------------------------------------------------------ the job
    def load(self, ticker: str, job: str = "initial_import") -> JobResult:
        if job not in JOBS:
            raise ValueError(f"unknown job {job!r}; one of {', '.join(JOBS)}")
        t0, req0 = self.clock(), self.sec.requests_made
        res = JobResult(ticker=ticker.upper(), job=job, status="success", dry_run=self.dry_run)
        company_id = None
        try:
            self._run(res, job)
        except R.ResolveError as e:
            res.status, res.error = "failed", f"{e.kind}: {e}"
        except Exception as e:   # noqa: BLE001 - a failed job is logged, never silently dropped
            res.status, res.error = "failed", f"{type(e).__name__}: {e}"
        res.requests = self.sec.requests_made - req0
        res.seconds = round(self.clock() - t0, 2)
        company = self.companies.get_by_symbol(res.ticker, "US")
        company_id = company["id"] if company else None
        if res.status == "failed" and company_id and not self.dry_run and res.state != "unsupported":
            self.companies.set_processing_state(company_id, "failed")
        if not self.dry_run:
            self._log(res, company_id)
        return res

    def _run(self, res: JobResult, job: str) -> None:
        resolved = R.resolve(self.sec, res.ticker)
        res.warnings += resolved.warnings
        company = self._company(res.ticker, resolved)
        if not self.dry_run:
            company = R.persist(resolved, self.companies, self.client, state="resolved")
        if resolved.unsupported_reason:
            res.status, res.state = "no_change", "unsupported"
            res.warnings.append(f"unsupported: {resolved.unsupported_reason}")
            return
        cf = self.sec.companyfacts(resolved.cik)
        plans = self._plan(resolved, company, cf)
        res.plan = [(p.fiscal_year, p.status) for p in plans]
        res.missing_years = [p.fiscal_year for p in plans if p.status == "not_available"]
        years = self._years_for(job, plans, company)
        res.years = years
        if not years:
            res.status = "no_change"
            res.state = company.get("processing_state") if company else None
            res.warnings.append(f"{job}: nothing to load for this company")
            return

        # ROUTE (pre): the profile decides the engine
        previous = company.get("profile") if company else None
        rr = route(self.sec, res.ticker, previous_profile=previous, industry_fn=self.industry_fn)
        engine = ENGINE_OF_PROFILE.get(rr.profile)
        if engine is None:
            res.status, res.state = "no_change", "unsupported"
            res.warnings.append(f"router profile {rr.profile}: no engine")
            if company and not self.dry_run:
                self.companies.set_processing_state(company["id"], "unsupported", f"profile router result {rr.profile}")
            return
        res.engine = engine

        # SRC + COLLECT, final router run with the engine's own series (and its approved extraction rows) - E10. The first pass has no series, so a REIT or a bank can come out
        # as STANDARD; the engines hinted by the SIC code are tried too, and the first whose own series gives a profile of that engine wins.
        extraction_rows = self._extraction_rows(company)
        decoded = self.extraction.get_rows(company["id"], res.ticker) if company else []
        self.financial._load_items()
        chosen = None
        for eng in _candidates(resolved.sic, engine, cf):
            try:
                kw, raw = C.provider_kwargs(eng, self.sec, res.ticker, rr.profile if eng == "general" else "STANDARD", self.splits_fn)
            except Exception as e:   # noqa: BLE001 - a provider that does not fit this company is not an error of the job
                if eng == engine:
                    raise
                res.warnings.append(f"{eng} provider skipped: {type(e).__name__}: {e}")
                continue
            reg = reg_from_rows(eng, decoded) if eng != "general" else None
            final = route(self.sec, res.ticker, f=raw["f"], labels=raw["labels"], ends=raw["ends"], reg=reg, reg_engine=eng if eng != "general" else None,
                          previous_profile=previous, industry_fn=self.industry_fn)
            if chosen is None or eng == engine:
                chosen = (eng, kw, raw, final)                     # fallback: the first-pass engine
            if ENGINE_OF_PROFILE.get(final.profile) == eng:
                chosen = (eng, kw, raw, final)
                break
        engine, kw, raw, final = chosen
        if engine != res.engine:
            res.warnings.append(f"engine {engine} chosen after the series check (first pass: {res.engine}, profile {rr.profile})")
        elif ENGINE_OF_PROFILE.get(final.profile) != engine:
            res.warnings.append(f"router with the series says {final.profile}, the first pass gave {rr.profile}: the facts were collected with the {engine} provider")
        res.engine, res.profile = engine, final.profile
        fs: FactSet = C.facts_from_provider(engine, kw)
        rep = C.select_sources(fs, cf, extraction_rows, set(self.financial._ids))
        res.missing_series = rep.missing_series
        res.warnings += rep.skipped + list(kw.get("data_problems") or [])[:20]

        # DQ
        want = set(years)
        facts = [f for f in fs.facts if f.fiscal_year in want]
        previous_facts = {(d["fiscal_year"], d["item_key"]): d for d in (self.financial.get_history(company["id"]) if company else [])}
        facts, dq_results = D.run_checks(facts, previous_facts, _currency(cf), engine)
        res.dq = [(r.check, r.outcome, r.fiscal_year, r.item_key, r.detail) for r in dq_results]
        res.restated = sorted({(r.fiscal_year, r.item_key) for r in dq_results if r.check == "restatement"})
        res.sources = _count_kinds(facts)

        # WRITE
        period_rows = _period_rows(fs, plans, want)
        cid = company["id"] if company else None
        if cid is None:                                  # dry run on a company that is not in the DB
            res.facts = {"inserted": len(facts), "updated": 0, "unchanged": 0}
            res.periods = {"inserted": len(period_rows), "updated": 0, "unchanged": 0}
        else:
            res.periods = self.financial.upsert_filing_periods(cid, period_rows, dry_run=self.dry_run)
            res.facts = self.financial.upsert_facts(cid, facts, dry_run=self.dry_run)
        if not self.dry_run:
            self._write_profile(cid, final, rr, fs, resolved)
            before = (self.companies.get_by_id(cid) or {}).get("processing_state")
            if res.rows_written or R._rank(before) < R._rank("data_loaded"):          # a repeated load that changes nothing leaves the state (and updated_at) alone
                self.companies.set_processing_state(cid, "data_loaded")
                res.state = "data_loaded"
            else:
                res.state = before
            res.price = P.refresh_snapshot(self.client, cid, res.ticker, self.price_fn)
        if job == "new_report":
            res.ai_required = [{"fiscal_year": y, "reason": "new annual report: judgment questions A1-A14, D1, D2 and missing extraction"} for y in years]
        held = any(x[1] == "held" for x in res.dq)
        res.status = "no_change" if res.rows_written == 0 else ("partial_success" if held else "success")

    def _years_for(self, job: str, plans: list, company) -> list:
        loadable = [p for p in plans if p.status != "not_available"]
        if job in ("initial_import", "repair"):
            return [p.fiscal_year for p in loadable]
        if job == "backfill":
            return [p.fiscal_year for p in plans if p.status == "missing"]
        if job == "amendment":
            return [p.fiscal_year for p in plans if p.status == "superseded"]
        have = [p.fiscal_year for p in plans if p.status in ("present", "superseded")]                  # new_report
        newest = max(have) if have else -1
        return [p.fiscal_year for p in plans if p.status == "missing" and p.fiscal_year > newest]

    def _extraction_rows(self, company) -> list:
        if not company:
            return []
        return self.extraction._all(company["id"])

    def _write_profile(self, cid: int, final, first, fs: FactSet, resolved) -> None:
        reason = "; ".join(str(x) for x in final.reason)[:500]
        want = {"profile": final.profile, "profile_reason": reason, "profile_since": int(str(final.since)[2:]) if final.since and str(final.since).startswith("FY") else None}
        row = self.companies.get_by_id(cid)
        if any(row.get(k) != v for k, v in want.items()):
            self.companies.update(cid, want)
        latest = max(y for y, _l, _e in fs.periods)
        hist = self.client.table("company_profile_history").select("*").eq("company_id", cid).eq("fiscal_year", latest).limit(1).execute().data
        h = {"company_id": cid, "fiscal_year": latest, "profile": final.profile, "reason": reason, "borderline": bool(final.borderline)}
        if not hist or any(hist[0].get(k) != v for k, v in h.items()):
            self.client.table("company_profile_history").upsert(h, on_conflict="company_id,fiscal_year").execute()

    def _log(self, res: JobResult, company_id: Optional[int]) -> None:
        detail = {"job": res.job, "engine": res.engine, "profile": res.profile, "sources": res.sources, "plan": [list(p) for p in res.plan], "dq": [list(x) for x in res.dq][:60],
                  "sec_requests": res.requests, "seconds": res.seconds, "ai_required": res.ai_required, "restated": [list(x) for x in res.restated], "price": res.price,
                  "calculation_version": CALCULATION_VERSION}
        row = {"company_id": company_id, "symbol": res.ticker, "exchange": "US", "operation_type": LOG_OPERATION[res.job], "target_table": "financial_facts", "update_scope": res.job,
               "data_source": DATA_SOURCE, "status": res.status, "records_inserted": res.facts.get("inserted", 0) + res.periods.get("inserted", 0),
               "records_updated": res.facts.get("updated", 0) + res.periods.get("updated", 0), "records_deleted": 0, "years_requested": sorted(res.years)[-20:] or None,
               "years_imported": sorted(res.years)[-20:] if res.rows_written else [], "missing_fields": sorted(res.missing_series), "missing_years": sorted(res.missing_years),
               "error_message": res.error, "warning_message": "; ".join(res.warnings)[:2000] or None, "source_details": [detail]}
        self.client.table("data_update_log").insert(row).execute()

    # ------------------------------------------------------------ status
    def status(self, ticker: str) -> dict:
        ticker = ticker.upper()
        company = self.companies.get_by_symbol(ticker, "US")
        if not company:
            return {"ticker": ticker, "in_db": False}
        facts = self.financial.get_history(company["id"])
        kinds, flags = {}, {}
        for d in facts:
            kinds[d["source_kind"]] = kinds.get(d["source_kind"], 0) + 1
            for fl in d["flags"]:
                flags[fl] = flags.get(fl, 0) + 1
        log = self.client.table("data_update_log").select("created_at,status,update_scope").eq("company_id", company["id"]).order("created_at", desc=True).limit(1).execute().data
        snap = self.client.table("market_snapshot").select("market_date,current_price,is_stale").eq("company_id", company["id"]).limit(1).execute().data
        periods = self.financial.get_filing_periods(company["id"])
        return {"ticker": ticker, "in_db": True, "name": company["company_name"], "cik": company.get("cik"), "state": company.get("processing_state"), "unsupported_reason": company.get("unsupported_reason"),
                "profile": company.get("profile"), "years": sorted({d["fiscal_year"] for d in facts}), "facts": len(facts), "sources": kinds, "flags": flags,
                "accessions": {p["fiscal_year"]: p["accession"] for p in periods}, "last_job": log[0] if log else None, "price": snap[0] if snap else None, "updated_at": company.get("updated_at")}


# ---------------------------------------------------------------- helpers
def _candidates(sic: str, first: str, facts_json: Optional[dict] = None) -> list:
    """The engine of the first router pass, then the engines the SIC code or the company's own XBRL tags point at (the first pass has no series, so a REIT whose SIC is
    not 6798, e.g. a tower company, comes out as STANDARD until its real-estate series is tried)."""
    hint = []
    if sic in ("6798", "6795", "6500", "6510", "6512", "6513"):
        hint.append("realestate")
    elif sic[:2] in ("60", "61") or sic in ("6199",):
        hint.append("bank")
    elif sic[:2] == "63" or sic == "6411":
        hint.append("insurance")
    if facts_json:
        have = facts_json.get("facts", {}).get("us-gaap", {})
        for engine, spec in (("realestate", RE_FIELDS["re_net"]), ("bank", BANK_FIELDS["deposits"]), ("insurance", INS_FIELDS["claims_gross"])):
            if any(t in have for t in spec[2]):
                hint.append(engine)
    order = list(dict.fromkeys([first] + hint))
    return [e for e in order if e != "general"] + (["general"] if "general" in order else [])      # a specialised engine that the router confirms beats the general one


def _accessions_in(facts_json: dict, wanted: set) -> set:
    found: set = set()
    for taxo in facts_json.get("facts", {}).values():
        for node in taxo.values():
            for entries in node.get("units", {}).values():
                for e in entries:
                    if e.get("accn") in wanted:
                        found.add(e["accn"])
                        if found == wanted:
                            return found
    return found


def _currency(facts_json: dict) -> Optional[str]:
    units = facts_json.get("facts", {}).get("us-gaap", {}).get("Assets", {}).get("units", {})
    return next(iter(units)) if len(units) == 1 else ("USD" if "USD" in units else None)


def _count_kinds(facts: list) -> dict:
    out: dict = {}
    for f in facts:
        out[f.source_kind] = out.get(f.source_kind, 0) + 1
    return out


def _period_rows(fs: FactSet, plans: list, want: set) -> list:
    by = {p.fiscal_year: p for p in plans}
    rows = []
    for year, _label, end in fs.periods:
        if year not in want:
            continue
        p = by.get(year)
        rows.append({"fiscal_year": year, "accession": p.accession if p and p.accession else PLACEHOLDER_ACCESSION, "form": p.form if p and p.form else "10-K",
                     "filed_at": p.filed.isoformat() if p and p.filed else None, "fiscal_year_end": end.isoformat() if end else None, "reporting_currency": "USD",
                     "calculation_version": CALCULATION_VERSION})
    return rows

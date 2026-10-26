"""Profile router call for the pipeline (K6 spec 2.7, step 1; Part B): like scripts/router_runner.route_company, but from the pipeline SEC client and without the scripts folder."""
from __future__ import annotations

from src.etl.router_inputs import router_factset
from src.providers import industry_provider
from src.providers.realestate_facts import CIK_OVERRIDE
from src.scoring import router as R

ENGINE_OF_PROFILE = {"STANDARD": "general", "TECH_ASSET_LIGHT": "general", "BANK": "bank", "INSURANCE": "insurance", "INCOME_REAL_ESTATE": "realestate"}


def route(sec, ticker: str, f=None, labels=None, ends=None, reg=None, reg_engine=None, previous_profile=None, industry_fn=industry_provider.get_industry, override=None):
    cik, title = CIK_OVERRIDE.get(ticker) or sec.cik_for(ticker)
    facts = sec.companyfacts(cik)
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    fs = router_factset(ticker, title, facts, sub, industry_fn(ticker), f=f, labels=labels, ends=ends, reg=reg, reg_engine=reg_engine)
    return R.route(R.router_data_from_factset(fs), previous_profile=previous_profile, override=override)


def industry_override_of(company):
    """The router Override of a company row that has ``industry_override`` (a vocabulary code) and its reason; None otherwise. It beats the router's own classification and, being on the row, every load applies it."""
    if not company or not company.get("industry_override"):
        return None
    from src.bp.vocab import industry_name
    name = industry_name(company["industry_override"])
    if name is None:
        raise ValueError(f"industry_override {company['industry_override']!r} is not an industry code")
    return R.Override(reason=company.get("industry_override_reason") or "", set_by="owner", industry=name)

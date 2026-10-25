"""Profile router call for the pipeline (K6 spec 2.7, step 1; Part B): like scripts/router_runner.route_company, but from the pipeline SEC client and without the scripts folder."""
from __future__ import annotations

from src.etl.router_inputs import router_factset
from src.providers import industry_provider
from src.providers.realestate_facts import CIK_OVERRIDE
from src.scoring import router as R

ENGINE_OF_PROFILE = {"STANDARD": "general", "TECH_ASSET_LIGHT": "general", "BANK": "bank", "INSURANCE": "insurance", "INCOME_REAL_ESTATE": "realestate"}


def route(sec, ticker: str, f=None, labels=None, ends=None, reg=None, reg_engine=None, previous_profile=None, industry_fn=industry_provider.get_industry):
    cik, title = CIK_OVERRIDE.get(ticker) or sec.cik_for(ticker)
    facts = sec.companyfacts(cik)
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    fs = router_factset(ticker, title, facts, sub, industry_fn(ticker), f=f, labels=labels, ends=ends, reg=reg, reg_engine=reg_engine)
    return R.route(R.router_data_from_factset(fs), previous_profile=previous_profile)

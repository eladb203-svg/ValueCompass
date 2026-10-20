"""Runner helper (code stage K4b): the profile of a company comes from the router (src/scoring/router.py), not from a list.

``route_company`` builds the router's FactSet from the cached SEC data (+ the series the engine already built, when given), the SIC from the cached submissions and the
provider industry (src/providers/industry_provider.py), and returns the RouterResult. Manual overrides (P1) and stored history arrive as arguments; there is no company list.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.etl.router_inputs import router_factset  # noqa: E402
from src.providers import industry_provider  # noqa: E402
from src.providers.realestate_facts import CIK_OVERRIDE  # noqa: E402
from src.scoring import router as R  # noqa: E402


def route_company(sec, ticker, f=None, labels=None, ends=None, reg=None, reg_engine=None, override=None, previous_profile=None, ai=None):
    cik, title = CIK_OVERRIDE.get(ticker) or sec.cik_for(ticker)
    facts = sec.companyfacts(cik)
    sub = sec.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json", f"sub_{cik}.json")
    fs = router_factset(ticker, title, facts, sub, industry_provider.get_industry(ticker), f=f, labels=labels, ends=ends, reg=reg, reg_engine=reg_engine)
    return R.route(R.router_data_from_factset(fs), override=override, previous_profile=previous_profile, ai=ai)

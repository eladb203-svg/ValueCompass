"""Profile guard and the scoring entry point (pure; no I/O)."""
from __future__ import annotations

from .buffett import buffett_price, buffett_quality
from .c16 import apply_c16
from .graham import graham_price, graham_quality
from .metrics import derive

SUPPORTED_PROFILES = ("STANDARD", "TECH_ASSET_LIGHT")
UNSUPPORTED_PROFILES = ("BANK", "INSURANCE", "INCOME_REAL_ESTATE")
STATE_UNSUPPORTED = "sector_not_supported_v1"
STATE_UNKNOWN_PROFILE = "profile_unknown"
STATE_SCORED = "scored"


def profile_state(profile: str) -> str:
    if profile in UNSUPPORTED_PROFILES:
        return STATE_UNSUPPORTED
    if profile in SUPPORTED_PROFILES:
        return STATE_SCORED
    return STATE_UNKNOWN_PROFILE


def score_company(inp) -> dict:
    """Score a company, or return a non-scored state for sectors the v1 model does not cover."""
    st = profile_state(inp.profile)
    if st != STATE_SCORED:
        return {"state": st, "profile": inp.profile,
                "reason": f"methodology_profile {inp.profile} is not scored by the general model (v1)"}
    d = derive(inp)
    bq = buffett_quality(inp, d)
    bp = buffett_price(inp, d, bq)
    gq = graham_quality(inp, d)
    gp = graham_price(inp, d, gq)
    return apply_c16({"state": STATE_SCORED, "profile": inp.profile, "derived": d, "buffett_quality": bq,
                      "buffett_price": bp, "graham_quality": gq, "graham_price": gp}, getattr(inp, "price_entity_issue", None))

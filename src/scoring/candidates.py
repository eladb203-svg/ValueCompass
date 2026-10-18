"""v1.1 clarifications.

C13  APPROVED for v1.1 (default ON): when a benefits/claims expense tag is reported (PolicyholderBenefitsAndClaimsIncurredNet) it is included
     in the cost of revenue used for gross margin, for years where gross profit is derived or missing (a company-reported GrossProfit is
     kept). Can be switched off with ``candidates(c13=False)`` for comparisons.
C12  REJECTED (2026-10-13): non-current marketable debt is NOT added to current assets in any scored liquidity test. The alternative
     current ratio (``current_ratio_alt`` etc. in ``derive``) remains a display-only diagnostic.
C14  ETL share-count scale guard (``guard_share_scale``): always on.
G3-C APPROVED 2026-10-14 (general model v1.2, production, no flag): the Buffett base, growth and the growth-gate owner-earnings input use unlevered owner earnings = OE + interest expense x (1 - tax rate)
     (tax rate = effective rate clipped to 0-40%, otherwise 25%); value = (PV + discounted terminal + cash and short-term investments - financial debt) / diluted shares.
     The no-debt variant (G3) was rejected and removed; scripts/output_v12_g3/ and output_v12_g3c/ keep the regression outputs as history.
G1   APPROVED 2026-10-14 (production, no flag): Buffett owner-earnings base is rolled forward only when the latest owner earnings >= the 5-year median.
G2   APPROVED 2026-10-14 (production, no flag): Graham Number normalized EPS = 7-10 year average diluted EPS (>= 7 years, loss years included).
     The regression variants (G1 A/C, G2 A/B) were removed from the production path; scripts/output_v11_g/ keeps their outputs as history.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass


@dataclass
class Candidates:
    c13: bool = True


CANDIDATES = Candidates()


@contextmanager
def candidates(c13: bool = True):
    saved = CANDIDATES.c13
    CANDIDATES.c13 = c13
    try:
        yield CANDIDATES
    finally:
        CANDIDATES.c13 = saved

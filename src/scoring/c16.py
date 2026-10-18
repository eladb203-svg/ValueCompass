"""C16 (general model v1.3, all profiles): price and financials must belong to the same listed entity.

When the listed security changed (merger, spin-off, reorganization) and the price belongs to a successor while the financials belong to the predecessor (or the reverse), the price score and the
buy price are "cannot be priced (price and financials of different entities)"; quality is still shown. No exchange-ratio conversion. The issue text is carried on the inputs
(``price_entity_issue``) by whoever assembles them (price provider / runner); with no issue nothing changes.
"""
from __future__ import annotations

from typing import Optional

C16_TEXT = "cannot be priced (price and financials of different entities)"


def apply_c16(result: dict, issue: Optional[str]) -> dict:
    if not issue:
        return result
    for key in ("buffett_price", "graham_price"):
        p = result.get(key)
        if isinstance(p, dict):
            p.setdefault("flags", []).append("C16_" + C16_TEXT.replace(" ", "_"))
            p["c16_issue"] = issue
            p["price_score_before_c16"] = p.get("price_score")
            p["price_score"] = {"state": "cannot_be_priced", "points": None, "reason": f"C16: {C16_TEXT}: {issue}"}
            p["buy_price"] = {"state": "cannot_be_priced", "reason": f"C16: {C16_TEXT}: {issue}"}
    result["c16_issue"] = issue
    return result

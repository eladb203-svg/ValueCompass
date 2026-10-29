"""B14 (EXT-GENERAL) item selection from the Rulebook Part E dictionary (decision 2026-10-22): per profile, the dictionary items that the engine of the profile reads, that sit on a
financial statement we can send (income statement, balance sheet, cash-flow statement), that are extracted by code from a tag (not 'absent = 0' items, C5), that are not supplied by
B1-B13, and that have no tag value in the year. All missing items of a report go into one call. Pure over the dictionary text and the tag series.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
PREFIX = {"general": "G", "managed_care": "G", "bank": "BK", "insurance": "IN", "realestate": "RE"}
SECTION_OF = {"income statement": "X-IS", "balance sheet": "X-BS", "cash-flow statement": "X-CF"}
# engine fields that B1-B13 supply (so B14 does not ask for them), per prefix
COVERED = {"RE": {"maint_capex", "straight_line", "ti_lc_total", "mat_year1", "mat_year2", "nci_op", "nci_lp", "nci_redeemable", "fx_unrealized", "gains_sale", "gains_re_entities", "impairment",
                  "debt_extinguishment"}}
COUNT_FIELDS = re.compile(r"^shares")


def dictionary_path() -> Path:
    return sorted((ROOT / "docs" / "scoring").glob("ValueCompass_Rulebook_*_EN.md"))[-1]


def parse_dictionary(text: str) -> list:
    """Part E.1 rows -> [{id, item, definition, statement, fields: {prefix: [field, ...]}, extracts}]."""
    out = []
    for ln in text.splitlines():
        if not ln.startswith("| FIN-"):
            continue
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) < 6:
            continue
        fields: dict = {}
        for pre, f in re.findall(r"\b(G|BK|IN|RE)\.([a-z0-9_]+)\b", c[4]):
            fields.setdefault(pre, []).append(f)
        out.append({"id": c[0], "item": c[1], "definition": c[2], "statement": c[3], "fields": fields, "extracts": c[5]})
    return out


# Approval rule 2 (AI skills 2026-10-27, 2.3): an item that does not belong to the profile is never asked. The dictionary lists some insurance concepts under the general prefix because the
# managed-care engine (rule C13) reads them: "claims and benefits incurred" (FIN-061 / FIN-111, G.claims_expense) is a managed-care item; a company with another general profile
# (MSFT, INTC) has no claims, and the model took "cost of sales" for it. field -> the engine kinds that may be asked for it.
PROFILE_ONLY = {"claims_expense": ("managed_care",)}


def eligible(row: dict, prefix: str, kind: Optional[str] = None) -> list:
    """Engine fields of this profile that B14 may ask for, from one dictionary row (``kind``: the engine kind, to apply PROFILE_ONLY)."""
    st = next((v for k, v in SECTION_OF.items() if row["statement"].lower().startswith(k)), None)
    ex = row["extracts"]
    if st is None or "Code" not in ex or "C5" in ex:
        return []
    return [f for f in row["fields"].get(prefix, []) if f not in COVERED.get(prefix, set()) and (kind is None or f not in PROFILE_ONLY or kind in PROFILE_ONLY[f])]


def removed_by_profile(rows: list) -> dict:
    """{engine kind: [items that the dictionary lists under the profile's prefix but B14 no longer asks for]} - for the report."""
    out = {}
    for kind, pre in PREFIX.items():
        all_f = {f for r in rows for f in eligible(r, pre)}
        ok = {f for r in rows for f in eligible(r, pre, kind)}
        out[kind] = sorted(all_f - ok)
    return out


def b14_items(rows: list, kind: str, series: dict, labels: list) -> tuple:
    """-> (items, sections, counts). ``series`` = {field: {label: value}}; ``labels`` = the fiscal years of the report window (balance-sheet items: the last two).
    counts = {needed, covered_by_tags, asked} in item-years."""
    prefix = PREFIX[kind]
    items, secs, needed, asked = [], [], 0, 0
    for row in rows:
        st = next(v for k, v in SECTION_OF.items() if row["statement"].lower().startswith(k)) if any(row["statement"].lower().startswith(k) for k in SECTION_OF) else None
        for f in eligible(row, prefix, kind):
            if f not in series or any(i['key'] == f for i in items):
                continue                                        # the profile's data has no such series (not read by this company's engine)
            yrs = labels[-2:] if st == "X-BS" else labels
            miss = [y for y in yrs if (series[f] or {}).get(y) is None]
            needed += len(yrs)
            asked += len(miss)
            if miss:
                unit = "count" if COUNT_FIELDS.match(f) else "USD"
                items.append({"key": f, "def": f"{row['item']}: {row['definition']} ({row['statement']}) - needed for {', '.join(miss)}", "unit": unit, "section": st})
                if st not in secs:
                    secs.append(st)
    return items, secs, {"needed": needed, "covered_by_tags": needed - asked, "asked": asked}

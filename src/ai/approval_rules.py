"""Approval rules for the AI extraction (AI skills 2026-10-27_09-10, section 2.3). The gate rejects as well as approves.

  1  the same row assigned to 2+ different items (same company and period)      -> rejected, reason ``dup_row``
  2  an item that is not in the profile's list is never asked                    -> a B14 list fix (``src/ai/b14.py``: PROFILE_ONLY), not a check
  3  the quoted row label is not one of the item's allowed labels                -> rejected, reason ``label_mismatch`` (``config/extraction_labels.yaml``)
  4  B10 NAV classification: the lines sum to total assets within 1%             -> approved (``ai_controls``)
  5  B11 operating-partnership units consistent with XBRL                        -> approved (``ai_controls``)
  6  all checks pass; an item that feeds value / buy price / profile is also consistent with the neighbouring years (no 3x jump) or with an XBRL value -> approved (``ai_controls``)
  7  a reconciliation control fails (E11 / Q6 / RE29b, balance), or rule 4-6 is not met -> approval queue (``pending``, with the reason)

``evaluate`` is pure over the rows of one company. A row a person decided (``human_review``) is never touched; a row that is not a figure (NA / not disclosed / already rejected by the item
checks) keeps its state. The reason of every rule decision is kept with the row (``note`` and ``control.approval_rule``); rejected rows stay for audit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]
LABELS_PATH = ROOT / "config" / "extraction_labels.yaml"
HUMAN_SOURCES = ("human_review", "legacy_verified", "k5b_confirmed")       # decided outside these rules: kept as they are
B10_TOLERANCE, B10_UNIDENTIFIED = 0.01, 0.10
B14 = "EXT-GENERAL"
NEIGHBOUR_FACTOR = 3.0
# B14 items that feed a single sub-item (no value / buy price / profile): approved without a neighbour check when nothing else objects
SUB_ITEM_ONLY = ("acquisitions", "goodwill_acquired", "goodwill_impairment", "impairments", "buybacks", "dividends", "pref_div", "separate_accounts", "policy_fees", "interest_credited",
                 "interest_capitalized", "re_tax", "cip", "equity_method_income", "equity_method_inv")


@dataclass
class Decision:
    row_id: int
    ticker: str
    skill: str
    item_key: str
    period: str
    before: str
    after: str
    rule: str                 # dup_row | label_mismatch | b10_nav_sum | b11_xbrl | b14_neighbours | control:<name> | unchanged
    reason: str
    source: Optional[str]     # approval_source for an approved row

    @property
    def changed(self) -> bool:
        return self.before != self.after


def load_labels(path: Path = LABELS_PATH) -> dict:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {k: [norm(x) for x in v] for k, v in raw.items()}


def norm(s: str) -> str:
    s = str(s or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def row_label(quote: Optional[str]) -> str:
    """The row label of a quote: the text before the first table separator, number or currency sign ("Interest expense | (1,359.4) | ..." -> "interest expense")."""
    q = str(quote or "").strip()
    q = q.split("\n")[0] if "|" not in q.split("\n")[0] and len(q.split("\n")) > 1 and re.search(r"\d", q.split("\n")[1]) else q
    m = re.search(r"[|$—]|\(?\d", q)
    label = q[:m.start()] if m else q
    return norm(label.strip(" :-—"))


def label_ok(item_key: str, quote: Optional[str], labels: dict) -> Optional[bool]:
    """True / False, or None when the item has no label list or the quote has no label to compare."""
    allowed = labels.get(item_key)
    lab = row_label(quote)
    if not allowed or not lab:
        return None
    return any(a in lab for a in allowed)


def k5b(db_row: dict) -> dict:
    return ((db_row.get("control") or {}).get("k5b_row")) or {}


def _is_figure(db_row: dict) -> bool:
    r = k5b(db_row)
    return db_row.get("value_state") == "value" and r.get("state") == "value" and r.get("value_full") is not None


def _val(r: dict) -> float:
    return float(r["value_full"])


def dup_groups(figures: list) -> dict:
    """{db id: reason} for the B14 rows of two or more different items that carry the same row: the same quote with the same value, or the same non-zero value in the same period
    (B14 reads one statement line per item). Per company and year."""
    out: dict = {}
    by_q: dict = {}
    by_v: dict = {}
    for d in figures:
        r = k5b(d)
        v = _val(r)
        if v == 0 or r.get("skill_id") != B14:        # the structured blocks (B1-B13) read one line per item and legitimately repeat a total (FFO, total assets); the defect is B14's
            continue
        by_q.setdefault((r["year"], norm(r.get("quote")), round(v, 2)), []).append(d)
        by_v.setdefault((r["year"], round(v, 2)), []).append(d)
    for grp in list(by_q.values()) + list(by_v.values()):
        if len({k5b(d)["item_key"] for d in grp}) >= 2:
            for d in grp:
                out[d["id"]] = "dup_row"
    return out


def b10_year_check(figures: list, facts: dict) -> dict:
    """{year: (ok, detail)} for the B10 rows: classified lines vs total assets (the fact; the extracted total assets row when the fact is missing)."""
    by_year: dict = {}
    total_row: dict = {}
    for d in figures:
        r = k5b(d)
        if r.get("skill_id") != "EXT-RE-NAV":
            continue
        if r["item_key"] == "total_assets":
            total_row[r["year"]] = _val(r)
        elif r["item_key"].startswith("bsa_"):
            by_year.setdefault(r["year"], []).append(r)
    out = {}
    for y, rs in by_year.items():
        tot = (facts.get("total_assets") or {}).get(y) or total_row.get(y)
        if not tot:
            out[y] = (False, f"{y}: total assets not available to compare")
            continue
        s = sum(_val(r) for r in rs)
        other = sum(_val(r) for r in rs if r["item_key"] == "bsa_other")
        diff = abs(s - tot) / abs(tot)
        if other / abs(tot) > B10_UNIDENTIFIED:
            out[y] = (False, f"{y}: unidentified lines {other / abs(tot):.0%} of total assets > 10% (RP2a)")
        else:
            out[y] = (diff <= B10_TOLERANCE, f"{y}: classified lines {s:,.0f} vs total assets {tot:,.0f} ({diff:.2%}, limit 1%)")
    return out


def b11_check(r: dict, facts: dict) -> tuple:
    """Rule 5. -> (ok, detail). Consistent with XBRL: the carrying value of the OP units cannot exceed the XBRL noncontrolling interest of the year; a count needs a carrying value or a share
    of the partnership in range; a share of the partnership is a percentage."""
    y, k, v = r["year"], r["item_key"], _val(r)
    nci = (facts.get("nci_total") or {}).get(y)
    if k == "op_units_book_value":
        if nci is None:
            return False, f"{y}: no XBRL noncontrolling interest to compare"
        return v <= nci * 1.001, f"{y}: OP units carrying value {v:,.0f} vs XBRL noncontrolling interest {nci:,.0f}"
    if k == "op_units_count":
        return v > 0, f"{y}: OP units {v:,.0f}" + ("" if v > 0 else " not positive")
    if k == "inc_share_of_bplp":
        return 0 < v <= 100, f"{y}: share of the partnership {v}%"
    return False, f"{k}: no XBRL counterpart"


def neighbours_ok(d: dict, figures: list, facts: dict, field_fact_key: Optional[str]) -> tuple:
    """Rule 6 for a B14 value. -> (ok, detail): at least one neighbouring year (extracted or XBRL) and the value is not beyond 3x of all of them."""
    r = k5b(d)
    y, v = r["year"], _val(r)
    nb = {}
    for x in figures:
        q = k5b(x)
        if q["item_key"] == r["item_key"] and q["year"] in (y - 1, y + 1) and x["id"] != d["id"]:
            nb[q["year"]] = _val(q)
    if field_fact_key:
        for z in (y - 1, y + 1):
            if (facts.get(field_fact_key) or {}).get(z) is not None:
                nb.setdefault(z, float(facts[field_fact_key][z]))
    vals = [n for n in nb.values() if n]
    if not vals:
        return False, f"{y}: no neighbouring year to compare"
    far = [n for n in vals if abs(v) > NEIGHBOUR_FACTOR * abs(n) or abs(v) < abs(n) / NEIGHBOUR_FACTOR]
    ok = len(far) < len(vals)
    return ok, f"{y}: {v:,.0f} vs neighbours " + ", ".join(f"{n:,.0f}" for n in vals) + ("" if ok else " (beyond 3x of all)")


def evaluate(db_rows: list, facts: dict, labels: dict, fact_key_of: Optional[dict] = None, ticker: str = "") -> list:
    """The decision for every figure row of one company. ``facts`` = {fact item_key: {fiscal_year: value}}; ``fact_key_of`` = {B14 engine field: fact item_key}."""
    fact_key_of = fact_key_of or {}
    figures = [d for d in db_rows if _is_figure(d) and d.get("approval_source") not in HUMAN_SOURCES]
    dups = dup_groups(figures)
    b10 = b10_year_check(figures, facts)
    out = []
    for d in figures:
        r = k5b(d)
        key, skill, before = r["item_key"], r.get("skill_id"), d["approval_status"]
        mk = lambda after, rule, reason, src=None: Decision(d["id"], ticker, skill, key, str(d.get("period")), before, after, rule, reason, src)   # noqa: E731
        if d["id"] in dups:
            out.append(mk("rejected", "dup_row", "dup_row: the same row is assigned to more than one item"))
            continue
        if label_ok(key, r.get("quote"), labels) is False:
            out.append(mk("rejected", "label_mismatch", f"label_mismatch: row label '{row_label(r.get('quote'))}' is not a label of {key}"))
            continue
        if skill == "EXT-RE-NAV":
            ok, detail = b10.get(r["year"], (False, "no classified lines"))
            out.append(mk("approved", "b10_nav_sum", detail, "ai_controls") if ok else mk("pending", "control:assets_sum", "assets_sum: " + detail))
            continue
        if skill == "EXT-RE-OPU":
            ok, detail = b11_check(r, facts)
            out.append(mk("approved", "b11_xbrl", detail, "ai_controls") if ok else mk("pending", "control:b11_xbrl", "b11_xbrl: " + detail))
            continue
        if skill == B14:
            ok, detail = neighbours_ok(d, figures, facts, fact_key_of.get(key))
            if key in SUB_ITEM_ONLY and (ok or "no neighbouring" in detail):         # one sub-item only: approved unless a neighbouring year contradicts it
                out.append(mk("approved", "b14_neighbours", "feeds one sub-item; " + detail, "ai_controls"))
                continue
            out.append(mk("approved", "b14_neighbours", detail, "ai_controls") if ok else mk("pending", "control:neighbours_3x", "neighbours_3x: " + detail))
            continue
        out.append(mk(before, "unchanged", d.get("note") or "decided by the block control at extraction", d.get("approval_source")))
    return out

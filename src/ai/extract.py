"""AI extraction B1-B14 (code stage K5b): one call per skill per report, code checks per item, the block control, the approval status, the file store and the approval queue.

Flow per company: sections by title (``sections.ext_section``) -> prompt (``prompt.build_extraction_prompt``) -> reply -> ``ext_checks.check_reply`` -> rows -> block controls ->
approvals (AI spec section 7: ``approved`` automatic per block rule, ``pending`` otherwise) -> ``items.jsonl`` and ``approval_queue.md``. A stored call is never asked again.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import ext_checks as X
from .prompt import build_extraction_prompt, extraction_blocks, extraction_signs
from .sections import ext_section, Filing

PROMPT_VERSION = "1"
# what an item feeds (for the approval queue); default: a sub-item
FEEDS = {
    "cet1_ratio_standardized": "capital buffer (Graham quality D10)", "cet1_ratio_advanced": "capital buffer (D10)", "cet1_required_standardized": "capital buffer (D10)",
    "cet1_required_advanced": "capital buffer (D10)", "cet1_capital": "control only", "total_capital_standardized": "leverage / capital quality", "total_capital_advanced": "leverage / capital quality",
    "rwa_standardized": "capital quality", "rwa_advanced": "capital quality", "lcr_q4_average": "liquidity quality (V10)", "scb": "required CET1 (V9)", "gsib_surcharge": "required CET1 (V9)",
    "uninsured_deposits": "display only", "loan_line": "loan mix (Graham quality)", "total_loans": "control only", "reg_capital_ratio": "capital quality (INS)", "prior_year_dev": "reserve quality (INS)",
    "ldti_remeasurement": "earnings quality (INS)", "inv_ig_fixed": "investment quality (INS)", "inv_ig_share": "investment quality (INS)", "cat_loss_latest": "catastrophe sub-item",
    "alm_disclosed": "ALM flag", "occupancy": "operating quality (RE)", "largest_tenant_share": "tenant concentration (RE)", "same_property_noi_growth": "growth sub-item (RE)",
    "maint_capex": "owner earnings -> VALUE and buy price (Buffett)", "ti_lc": "owner earnings -> VALUE and buy price (Buffett)", "straight_line_rent_affo": "owner earnings -> VALUE and buy price",
    "fair_value_real_estate": "NAV -> Graham price", "stabilized_value": "NAV -> Graham price", "other_property_value": "NAV -> Graham price", "stabilized_noi": "NAV -> Graham price",
    "committed_undrawn_facilities": "liquidity block RP1a -> Buffett price score", "debt_maturity_year1": "liquidity block RP1a -> Buffett price score",
    "debt_maturity_year2": "liquidity (24 months)", "unencumbered_noi_share": "financing quality", "unencumbered_assets_share": "financing quality",
    "op_units_count": "share basis -> VALUE per share", "op_units_book_value": "NAV -> Graham price", "diluted_includes_op": "share basis -> VALUE per share",
    "partnership_units_weighted": "share basis -> VALUE per share", "shares_basis_override": "share basis -> VALUE per share", "inc_share_of_bplp": "share basis -> VALUE per share",
    "recon_net_income": "normalized FFO -> VALUE", "recon_re_da": "normalized FFO -> VALUE", "recon_nci_jv": "normalized FFO -> VALUE", "recon_gi_net": "normalized FFO -> VALUE",
    "reported_ffo": "normalized FFO control (E11)", "reported_core_ffo": "RE29b control", "reported_affo": "owner earnings control (Q6)", "reported_ebitdare": "EBITDAre control",
    "core_ffo_ps_reported": "RE29b control", "re29_re_sale_gains": "normalized FFO -> VALUE", "re29_nonre_impairments": "normalized FFO -> VALUE", "re29a_nonre_inv": "normalized FFO -> VALUE",
    "re29b_fx_net": "normalized FFO -> VALUE", "debt_extinguishment": "normalized FFO -> VALUE", "transaction_costs": "normalized FFO -> VALUE",
    "profile_total_assets": "PROFILE (S3 real-estate test)", "profile_property_value": "PROFILE (S3 real-estate test)", "profile_rental_revenue": "PROFILE (S3 real-estate test)",
    "profile_total_revenue": "PROFILE (S3 real-estate test)", "mortgage_loans_mbs": "PROFILE (mortgage REIT test)",
}
# B14 engine fields that feed a single sub-item (approval automatic when the control passes); every other B14 item feeds value, buy price or profile
SUB_ITEM_ONLY = ("acquisitions", "goodwill_acquired", "goodwill_impairment", "impairments", "buybacks", "dividends", "pref_div", "separate_accounts", "policy_fees", "interest_credited",
                 "interest_capitalized", "re_tax", "cip", "equity_method_income", "equity_method_inv")
BLOCK_ID = {b["skill_id"]: b["block"] for b in extraction_blocks().values()}


@dataclass
class Report:
    ticker: str
    name: str
    profile: str
    fiscal_year: int
    filing: Filing
    _text_cache: dict = field(default_factory=dict)

    def section(self, sid: str):
        if sid not in self._text_cache:
            self._text_cache[sid] = ext_section(self.filing.text, sid)
        return self._text_cache[sid]


class CallStore:
    """calls.jsonl: one record per skill call (raw reply kept, so checks and controls can be re-run without a call)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._rows: dict = {}
        if self.path.exists():
            for ln in self.path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    r = json.loads(ln)
                    self._rows[(r["ticker"], r["fiscal_year"], r["skill_id"], r["prompt_version"])] = r

    def get(self, ticker, fy, skill_id, pv=PROMPT_VERSION):
        return self._rows.get((ticker, int(fy), skill_id, pv))

    def put(self, rec: dict) -> dict:
        rec = {**rec, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self._rows[(rec["ticker"], rec["fiscal_year"], rec["skill_id"], rec["prompt_version"])] = rec
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        return rec

    def rows(self) -> list:
        return list(self._rows.values())


def ask_block(rep: Report, block: dict, client, calls: CallStore, items: Optional[list] = None, force: bool = False, part: int = 1) -> dict:
    """One extraction call (one retry on invalid JSON with another seed). Returns the stored call record; a stored record is returned without a call."""
    key_id = block["skill_id"] if part == 1 else f"{block['skill_id']}#{part}"          # B14 is asked in groups of at most 15 items: one stored call per group
    ex = None if force else calls.get(rep.ticker, rep.fiscal_year, key_id)
    if ex is not None:
        ex["_cached"] = True
        return ex
    sections = {sid: rep.section(sid).text for sid in block["sections"] if rep.section(sid).found}
    flags = [f"section_not_found:{sid}" for sid in block["sections"] if sid not in sections]
    flags += [f"{sid}:{f}" for sid in block["sections"] if sid in sections for f in rep.section(sid).flags]
    base = {"ticker": rep.ticker, "fiscal_year": rep.fiscal_year, "skill_id": key_id, "version": block["version"], "prompt_version": PROMPT_VERSION,
            "accession": rep.filing.accession, "items_asked": [i["key"] for i in (items if items is not None else block["items"])], "section_flags": flags}
    if not sections:
        return calls.put({**base, "model": "", "raw": None, "usage": {}, "sections_sent": [], "no_call": "sections_not_found"})
    ctx = {"company_name": rep.name, "ticker": rep.ticker, "fiscal_year": f"FY{rep.fiscal_year}", "profile": rep.profile, "accession": rep.filing.accession}
    prompt, text_sent, sent = build_extraction_prompt(block, ctx, sections, items)
    attempts, last = [], None
    for attempt in (1, 2):
        t0 = time.monotonic()
        r = client.generate(prompt, seed_offset=attempt - 1)
        res, reasons = X.check_reply(r.text, block, text_sent, rep.fiscal_year, items)
        attempts.append({"attempt": attempt, "finish": r.finish_reason, "seconds": round(time.monotonic() - t0, 1), "reasons": reasons})
        last = r
        if "invalid_json" not in reasons:
            break
    return calls.put({**base, "model": last.model, "raw": last.text, "sections_sent": sent, "text_chars_sent": len(text_sent),
                      "usage": {"prompt_tokens": last.prompt_tokens, "output_tokens": last.output_tokens, "thought_tokens": last.thought_tokens, "latency_s": round(last.latency, 2),
                                "attempts": last.attempts, "finish_reason": last.finish_reason, "attempt_log": last.attempt_log, "tries": attempts}})


def _aggregate(rows: list, keys: set) -> list:
    """Table lines that together make one engine item (``aggregate_sum`` in extraction.yaml) are summed into one row per year; the quotes of the lines are kept."""
    out, groups = [], {}
    for r in rows:
        if r["item_key"] in keys and r["state"] == "value":
            groups.setdefault((r["item_key"], r["year"]), []).append(r)
        else:
            out.append(r)
    for (_k, _y), rs in groups.items():
        uniq = list({r["quote"]: r for r in rs}.values())
        first = dict(uniq[0])
        if len(uniq) > 1:
            first.update({"value_full": sum(r["value_full"] for r in uniq), "quote": " || ".join(r["quote"] for r in uniq), "basis": " + ".join(str(r["basis"]) for r in uniq),
                          "flags": sorted(set(first["flags"]) | {f"summed_lines ({len(uniq)})"}), "value": None})
        out.append(first)
    return out


def rows_from_call(rep: Report, block: dict, rec: dict, items: Optional[list] = None) -> tuple:
    """Re-run the item checks on a stored call -> (rows, call_reasons). Every item the model returned becomes a row: state value / NA / not_disclosed, or rejected with the reasons."""
    if rec.get("raw") is None:
        return [], [rec.get("no_call", "no_reply")]
    sections = {sid: rep.section(sid).text for sid in block["sections"] if rep.section(sid).found}
    ctx = {"company_name": rep.name, "ticker": rep.ticker, "fiscal_year": f"FY{rep.fiscal_year}", "profile": rep.profile, "accession": rep.filing.accession}
    _, text_sent, _ = build_extraction_prompt(block, ctx, sections, items)
    results, creasons = X.check_reply(rec["raw"], block, text_sent, rep.fiscal_year, items)
    rows = []
    for r in results:
        it = r.item if isinstance(r.item, dict) else {}
        q = it.get("quote") if isinstance(it.get("quote"), dict) else {}
        state = it.get("value_state") if r.ok else "rejected"
        rows.append({
            "ticker": rep.ticker, "fiscal_year": rep.fiscal_year, "item_key": it.get("item_key"), "year": r.year, "value": it.get("value"), "unit": it.get("unit"), "scale": it.get("scale"),
            "value_full": r.value_full, "basis": it.get("basis"), "period": it.get("period"), "state": state, "stated_state": it.get("value_state"), "quote": q.get("text"),
            "section": q.get("section"), "accession": rep.filing.accession, "skill_id": block["skill_id"], "block": block["block"], "version": block["version"], "model": rec.get("model"),
            "prompt_version": PROMPT_VERSION, "flags": list(r.flags), "reasons": list(r.reasons), "control": None, "control_result": None, "control_detail": None,
            "approval_status": "rejected" if not r.ok else ("n/a" if state != "value" else None), "approval_reason": None})
    return _aggregate(rows, extraction_signs()[1]), creasons


def decide(block: dict, row: dict, ctrl: Optional[dict], key_in_control: bool = True) -> tuple:
    """-> (approval_status, reason). AI spec section 7."""
    if row["approval_status"] in ("rejected", "n/a"):
        return row["approval_status"], row.get("approval_reason")
    rule = block["approval"]
    res = ctrl["result"] if ctrl else "pass"
    if rule == "always":
        return "pending", "always reviewed (block " + block["block"] + ")"
    if rule == "by_control":
        return ("approved", None) if res == "pass" else ("pending", f"control {ctrl['name']} {res}: {ctrl['detail'][:160]}" if ctrl else "control missing")
    if rule == "by_feed":
        if row["item_key"] not in SUB_ITEM_ONLY:               # an engine input that is not known to feed only one sub-item: it may feed value / buy price / profile
            return "pending", "feeds value / buy price / profile"
        return ("approved", None) if res == "pass" else ("pending", f"control {ctrl['name']} flagged this item")
    if ctrl and res == "fail" and (not ctrl["items"] or row["item_key"] in ctrl["items"]):
        return "pending", f"control {ctrl['name']} failed: {ctrl['detail'][:160]}"
    return "approved", None


def apply_controls(block: dict, rows: list, engine_ctl: Optional[dict] = None) -> Optional[dict]:
    """Run the block's control on its accepted rows and stamp every row with the control and the approval status. ``engine_ctl`` = results of the engine-based controls (real estate)."""
    name = block["control"]
    ok_rows = [r for r in rows if r["state"] == "value"]
    ctrl = None
    if name in X.BLOCK_CONTROLS:
        ctrl = X.BLOCK_CONTROLS[name](ok_rows)
    elif name == "neighbours_3x":
        ctrl = X.control_neighbours(ok_rows)
    elif engine_ctl and name in engine_ctl:
        ctrl = {**engine_ctl[name], "items": [], "years": {}}
    elif name == "none":
        ctrl = None
    else:
        ctrl = {"name": name, "result": "na", "detail": "engine control not available", "items": [], "years": {}}
    for r in rows:
        r["control"] = ctrl["name"] if ctrl else "none"
        r["control_result"] = ctrl["result"] if ctrl else "n/a"
        r["control_detail"] = ctrl["detail"] if ctrl else ""
        r["approval_status"], r["approval_reason"] = decide(block, r, ctrl)
        if name == "neighbours_3x" and ctrl and r["item_key"] in ctrl.get("years", {}) and r["year"] in ctrl["years"][r["item_key"]] and r["approval_status"] == "approved":
            r["approval_status"], r["approval_reason"] = "pending", "value beyond 3x of both neighbouring years"
    return ctrl


def write_items(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def _fmt(r: dict) -> str:
    if r["value"] is None:
        return "-"
    u = {"USD": "USD", "percent": "%"}.get(r["unit"], r["unit"])
    sc = {1: "", 1000: " thousand", 1000000: " million", 1000000000: " billion"}.get(r["scale"], f" x{r['scale']}")
    return f"{r['value']:,}{sc} {u}" if u != "%" else f"{r['value']}%"


def write_queue(path: Path, rows: list) -> int:
    pend = [r for r in rows if r["approval_status"] == "pending"]
    lines = ["# Approval queue - AI extraction (code stage K5b)", "",
             f"{len(pend)} pending items. Each item: company, year, item, value, quote, the control and its result, what it feeds. Approve or reject in the admin screen (K6); nothing here is applied without approval.", ""]
    for t in sorted({r["ticker"] for r in pend}):
        lines += [f"## {t}", "", "| year | item | value | quote | control (result) | feeds | why pending |", "|---|---|---|---|---|---|---|"]
        for r in sorted((x for x in pend if x["ticker"] == t), key=lambda x: (x["block"], str(x["item_key"]), x["year"] or 0)):
            q = (r["quote"] or "").replace("|", "/").replace("\n", " ")
            q = q if len(q) <= 260 else q[:257] + "..."
            nm = r["item_key"] + (f" [{r['basis']}]" if r.get("basis") and r["item_key"].startswith(("loan_line", "bsa_")) else "")
            lines.append(f"| {r['year']} | {nm} ({r['block']}) | {_fmt(r)} | {q} | {r['control']} ({r['control_result']}) | {FEEDS.get(r['item_key'], 'sub-item')} | {(r['approval_reason'] or '')[:120].replace('|', '/')} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(pend)

"""K6d-2: the extraction approval rules (AI skills 2026-10-27, 2.3) - one test per rule, the label reader, B14 profile lists, the recheck on the database. Fake database, no network."""
import pytest

from fakedb import FakeClient
from src.ai import approval_rules as AR
from src.ai import b14 as B14
from src.ai import recheck as RC

LABELS = AR.load_labels()


def row(i, item, year, value, quote, skill="EXT-GENERAL", status="pending", source=None, state="value"):
    k = {"ticker": "ACM", "item_key": item, "year": year, "value_full": value, "quote": quote, "skill_id": skill, "state": state, "approval_status": status}
    return {"id": i, "company_id": 1, "item_key": item, "period": f"FY{year}", "value_state": state, "value": value, "approval_status": status, "approval_source": source, "note": None,
            "skill_id": skill, "control": {"k5b_row": k}}


def decide(rows, facts=None, fact_key=None):
    return {d.row_id: d for d in AR.evaluate(rows, facts or {}, LABELS, fact_key or {}, "ACM")}


# ---------------------------------------------------------------- the label reader
def test_the_row_label_is_the_text_before_the_first_separator_or_number():
    assert AR.row_label("Interest expense | (1,359.4) | | | (1,404.5)") == "interest expense"
    assert AR.row_label("Property (including reimbursements) | | | 428,800 | 377,675") == "property (including reimbursements)"
    assert AR.row_label("Total cost of revenue\n106,374\n87,831\n74,114") == "total cost of revenue"
    assert AR.row_label("Cost of sales | | 34,478 | | | 65.2 | %") == "cost of sales"
    assert AR.row_label("CONSOLIDATED STATEMENTS OF OPERATIONS") == "consolidated statements of operations"
    assert AR.row_label("") == "" and AR.row_label(None) == ""


def test_label_ok_true_false_and_none_for_no_list_or_no_label():
    assert AR.label_ok("interest_capitalized", "Interest | 1,134,879", LABELS) is False
    assert AR.label_ok("interest_capitalized", "Interest costs capitalized | 12", LABELS) is True
    assert AR.label_ok("claims_expense", "Cost of sales | 34,478", LABELS) is False
    assert AR.label_ok("sale_proceeds", "Proceeds from sales of real estate | 744,014", LABELS) is True
    assert AR.label_ok("no_such_item", "Anything | 1", LABELS) is None and AR.label_ok("cfo", "", LABELS) is None


# ---------------------------------------------------------------- rule 1
def test_rule_1_the_same_row_for_several_items_rejects_all_of_them_even_an_approved_one():
    q = "Property (including reimbursements) | 428,800 | 377,675 | 316,964"
    rows = [row(1, "cost_of_revenue", 2025, 428.8e6, q), row(2, "re_tax", 2025, 428.8e6, q, status="approved", source="ai_controls"), row(3, "repairs", 2025, 428.8e6, q),
            row(4, "cost_of_revenue", 2024, 377.7e6, q)]
    d = decide(rows)
    assert [d[i].after for i in (1, 2, 3)] == ["rejected"] * 3 and {d[i].rule for i in (1, 2, 3)} == {"dup_row"} and d[2].before == "approved"
    assert "dup_row" in d[1].reason and d[4].rule != "dup_row"                              # one item for FY2024 alone is not a duplicate


def test_rule_1_the_same_value_from_two_items_in_one_period_is_a_duplicate_but_zero_and_other_years_are_not():
    rows = [row(1, "net_income", 2025, 5e9, "Net income | 5,000"), row(2, "ebit", 2025, 5e9, "Operating income | 5,000"), row(3, "cash", 2025, 0, "Cash and cash equivalents | 0"),
            row(4, "sti", 2025, 0, "Short-term investments | 0"), row(5, "tax", 2024, 5e9, "Income tax | 5,000")]
    d = decide(rows)
    assert d[1].rule == d[2].rule == "dup_row" and d[3].rule != "dup_row" and d[5].rule != "dup_row"


def test_rule_1_does_not_apply_to_the_structured_blocks():
    rows = [row(1, "reported_ffo", 2025, 7e8, "FFO | 700", skill="EXT-RE-FFO", status="approved", source="ai_controls"),
            row(2, "recon_net_income", 2025, 7e8, "FFO | 700", skill="EXT-RE-FFO", status="approved", source="ai_controls")]
    assert {d.rule for d in decide(rows).values()} == {"unchanged"}


# ---------------------------------------------------------------- rule 3
def test_rule_3_a_label_that_does_not_fit_the_item_is_rejected_with_the_reason():
    rows = [row(1, "claims_expense", 2025, 87e9, "Total cost of revenue\n106,374\n87,831\n74,114"), row(2, "interest_capitalized", 2025, 1.1e9, "Interest expense | (1,359.4)", status="approved", source="ai_controls")]
    d = decide(rows)
    assert d[1].after == "rejected" and d[1].rule == "label_mismatch" and "total cost of revenue" in d[1].reason
    assert d[2].after == "rejected" and d[2].before == "approved"


# ---------------------------------------------------------------- rule 6 and 7 (B14)
def test_rule_6_a_b14_value_near_its_neighbours_is_approved_a_jump_goes_to_the_queue():
    facts = {"cost_of_revenue": {2024: 100.0, 2026: 120.0}}
    ok = decide([row(1, "cost_of_revenue", 2025, 110.0, "Cost of revenue | 110")], facts, {"cost_of_revenue": "cost_of_revenue"})[1]
    assert ok.after == "approved" and ok.source == "ai_controls" and ok.rule == "b14_neighbours"
    jump = decide([row(1, "cost_of_revenue", 2025, 5000.0, "Cost of revenue | 5,000")], facts, {"cost_of_revenue": "cost_of_revenue"})[1]
    assert jump.after == "pending" and jump.rule == "control:neighbours_3x" and "beyond 3x" in jump.reason
    alone = decide([row(1, "cost_of_revenue", 2025, 110.0, "Cost of revenue | 110")])[1]
    assert alone.after == "pending" and "no neighbouring year" in alone.reason


def test_rule_6_neighbours_come_from_other_extracted_years_too_and_a_sub_item_needs_no_neighbour():
    rows = [row(1, "sale_proceeds", 2024, 589e6, "Proceeds from sales of real estate | 589"), row(2, "sale_proceeds", 2025, 744e6, "Proceeds from sales of real estate | 744")]
    assert {d.after for d in decide(rows).values()} == {"approved"}
    sub = decide([row(1, "acquisitions", 2025, 61e6, "Acquisitions of businesses | (61)")])[1]
    assert sub.after == "approved" and "feeds one sub-item" in sub.reason


# ---------------------------------------------------------------- rule 4 (B10)
def nav(i, key, year, value, status="pending"):
    return row(i, key, year, value, f"{key} | {value:,.0f}", skill="EXT-RE-NAV", status=status)


def test_rule_4_classified_lines_that_sum_to_total_assets_within_1_percent_are_approved():
    rows = [nav(1, "bsa_noi", 2025, 700.0), nav(2, "bsa_inre", 2025, 200.0), nav(3, "bsa_wc", 2025, 95.0)]
    d = decide(rows, {"total_assets": {2025: 1000.0}})
    assert {x.after for x in d.values()} == {"approved"} and {x.rule for x in d.values()} == {"b10_nav_sum"}
    off = decide(rows, {"total_assets": {2025: 1100.0}})
    assert {x.after for x in off.values()} == {"pending"} and "assets_sum" in off[1].reason
    other = decide([nav(1, "bsa_noi", 2025, 800.0), nav(2, "bsa_other", 2025, 200.0)], {"total_assets": {2025: 1000.0}})
    assert {x.after for x in other.values()} == {"pending"} and "unidentified" in other[1].reason
    nothing = decide(rows)
    assert {x.after for x in nothing.values()} == {"pending"}                                  # no total assets to compare


def test_rule_4_uses_the_extracted_total_assets_row_when_the_fact_is_missing():
    rows = [nav(1, "bsa_noi", 2025, 900.0), nav(2, "bsa_wc", 2025, 100.0), nav(3, "total_assets", 2025, 1000.0)]
    assert {x.after for x in decide(rows).values()} == {"approved"}


# ---------------------------------------------------------------- rule 5 (B11)
def opu(i, key, year, value):
    return row(i, key, year, value, f"{key} {value}", skill="EXT-RE-OPU")


def test_rule_5_op_units_consistent_with_the_xbrl_noncontrolling_interest_are_approved():
    facts = {"nci_total": {2025: 685e6}}
    d = decide([opu(1, "op_units_book_value", 2025, 165e6), opu(2, "op_units_count", 2025, 2.68e6), opu(3, "inc_share_of_bplp", 2025, 90.05)], facts)
    assert {x.after for x in d.values()} == {"approved"} and {x.rule for x in d.values()} == {"b11_xbrl"}
    bad = decide([opu(1, "op_units_book_value", 2025, 900e6)], facts)[1]
    assert bad.after == "pending"
    assert decide([opu(1, "op_units_book_value", 2024, 100e6)], facts)[1].after == "pending"       # no XBRL value for that year


# ---------------------------------------------------------------- rule 7 and the rows nobody judges
def test_other_blocks_keep_the_decision_of_their_control_and_figures_only_are_judged():
    rows = [row(1, "maint_capex", 2025, 1e8, "Maintenance capex | 100", skill="EXT-RE-MAINT", status="approved", source="ai_controls"),
            row(2, "reported_ffo", 2025, 7e8, "FFO | 700", skill="EXT-RE-FFO", status="pending"),
            row(3, "occupancy", 2025, None, "", skill="EXT-RE-OPS", status="approved", source="ai_controls", state="not_disclosed")]
    d = decide(rows)
    assert d[1].after == "approved" and d[2].after == "pending" and 3 not in d and not any(x.changed for x in d.values())


def test_a_row_a_person_decided_is_never_touched():
    q = "Property | 1"
    rows = [row(1, "re_tax", 2025, 5.0, q, status="approved", source="human_review"), row(2, "repairs", 2025, 5.0, q)]
    d = decide(rows)
    assert 1 not in d and d[2].rule != "dup_row"


# ---------------------------------------------------------------- rule 2 (the B14 list per profile)
def test_b14_does_not_ask_an_insurance_item_of_a_company_that_is_not_managed_care():
    rows = B14.parse_dictionary(B14.dictionary_path().read_text(encoding="utf-8"))
    series = {"claims_expense": {}, "cost_of_revenue": {}}
    general, _, _ = B14.b14_items(rows, "general", series, ["FY2024", "FY2025"])
    managed, _, _ = B14.b14_items(rows, "managed_care", series, ["FY2024", "FY2025"])
    assert [i["key"] for i in general] == ["cost_of_revenue"] and [i["key"] for i in managed] == ["claims_expense", "cost_of_revenue"] or {i["key"] for i in managed} == {"claims_expense", "cost_of_revenue"}
    removed = B14.removed_by_profile(rows)
    assert "claims_expense" in removed["general"] and "claims_expense" not in removed["managed_care"]


# ---------------------------------------------------------------- the recheck on the database
def test_recheck_writes_status_source_reason_and_rule_and_a_second_run_changes_nothing():
    c = FakeClient()
    c.tables["companies"] = [{"id": 1, "symbol": "ACM", "profile": None}]
    q = "Property (including reimbursements) | 428,800"
    for i, (item, st) in enumerate([("cost_of_revenue", "pending"), ("re_tax", "approved"), ("repairs", "pending")], 1):
        r = row(i, item, 2025, 428.8e6, q, status=st, source="ai_controls" if st == "approved" else None)
        r.update({"company_id": 1, "document_ref": "a-1", "approved_at": "2026-10-27" if st == "approved" else None})
        c.tables.setdefault("extraction_items", []).append(r)
    res = RC.recheck(c, "ACM", apply=False)
    assert res["changed"] == 3 and res["applied"] == 0 and {r["approval_status"] for r in c.tables["extraction_items"]} == {"pending", "approved"}
    res = RC.recheck(c, "ACM", apply=True)
    rows = c.tables["extraction_items"]
    assert res["applied"] == 3 and {r["approval_status"] for r in rows} == {"rejected"} and all(r["approval_source"] is None for r in rows)
    assert all(r["note"].startswith("dup_row") and r["control"]["approval_rule"]["rule"] == "dup_row" and r["control"]["k5b_row"] for r in rows)
    assert {r["control"]["approval_rule"]["previous_status"] for r in rows} == {"pending", "approved"}
    assert RC.recheck(c, "ACM", apply=True)["changed"] == 0


def test_rows_with_a_legacy_source_are_never_rejected_or_sent_back_to_the_queue():
    """The rules judge the AI extraction only: a row from the verified CSV (legacy_verified) or confirmed by K5b (k5b_confirmed) keeps its status, even when it would break a rule."""
    q = "Property | 2,574.1"
    rows = [row(1, "re_tax", 2025, 2574.1e6, q, status="approved", source="legacy_verified"), row(2, "repairs", 2025, 2574.1e6, q, status="approved", source="k5b_confirmed"),
            row(3, "interest_capitalized", 2025, 1.4e9, "Interest expense | (1,404.5)", status="approved", source="legacy_verified"), row(4, "cost_of_revenue", 2025, 2574.1e6, q)]
    d = decide(rows)
    assert set(d) == {4} and d[4].rule != "dup_row"                                                  # only the AI row is judged; the CSV rows do not even count as its duplicates


def test_the_cash_line_for_acquisitions_is_not_a_label_of_goodwill_acquired():
    q = "Acquisitions of businesses, equity method investments and nonmarketable securities | (461) | | (315) | | (62)"
    assert AR.label_ok("goodwill_acquired", q, LABELS) is False and AR.label_ok("acquisitions", q, LABELS) is True
    assert AR.label_ok("goodwill_acquired", "Goodwill acquired | 120", LABELS) is True


def test_an_approved_b14_value_becomes_a_fact_of_the_engine_field_it_fills():
    from datetime import date as D
    from src.etl.facts import FactSet
    from src.pipeline import collect as CO
    fs = FactSet("ACM", "Acme", "insurance", [(2024, "FY2024", D(2024, 12, 31)), (2025, "FY2025", D(2025, 12, 31))])
    rep = CO.SourceReport()
    rows = [{"id": 1, "skill_id": "EXT-GENERAL", "item_key": "gains_realized", "period": "FY2025", "value": 464e6, "value_state": "value", "approval_status": "approved"},
            {"id": 2, "skill_id": "EXT-GENERAL", "item_key": "gains_realized", "period": "FY2024", "value": 197e6, "value_state": "value", "approval_status": "pending"},
            {"id": 3, "skill_id": "EXT-GENERAL", "item_key": "no_such_field", "period": "FY2025", "value": 1.0, "value_state": "value", "approval_status": "approved"}]
    CO.fill_from_extraction(fs, rows, rep)
    assert [(f.fiscal_year, f.item_key, f.value, f.source_kind) for f in fs.facts] == [(2025, "investment_gains", 464e6, "extraction")]      # approved only; unknown fields are not facts

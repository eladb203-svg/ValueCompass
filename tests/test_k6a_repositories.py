"""K6a: DB target and credentials, the financial_facts / extraction repositories (idempotent writes), the FactSet <-> DB round trip, company repository additions (fake client, no network)."""
import pytest

from fakedb import FakeClient
from src import config, db
from src.etl import field_map as fm
from src.etl.db_io import FactSetDb, approval_for, differences, equal_values
from src.etl.extraction_store import value_state
from src.etl.facts import ExtractionRow, Fact
from src.etl.from_providers import facts_from_kwargs
from src.etl.to_inputs import kwargs_from_facts, via_db
from src.repositories.company_repository import CompanyRepository
from src.repositories.extraction_repository import ExtractionRepository, decode, encode
from src.repositories.financial_repository import FinancialRepository

KEYS = sorted({v for e in fm.FIELDS.values() for v in e.values()})


def client():
    return FakeClient(KEYS)


def kw(**over):
    base = dict(ticker="ACM", name="Acme", fy=["FY2024", "FY2025"], end=["2024-12-31", "2025-12-31"], f={"revenue": [1.0, 2.5], "net_income": [None, 5], "sbc": [0.0, 3.0]},
                tag_log={"revenue": {"FY2024": {"tag": "Revenues"}, "FY2025": {"tag": "Revenues"}}, "net_income": {"FY2025": {"tag": "NetIncomeLoss"}}, "sbc": {}},
                sbc_state=["reported_none", "found"], assumed_zero={}, price_current=10.0)
    base.update(over)
    return base


# ---------------------------------------------------------------- target and credentials
def test_target_defaults_to_test_refuses_the_wrong_project_and_never_names_a_value(monkeypatch):
    monkeypatch.delenv("VC_DB_TARGET", raising=False)
    assert db.db_target() == "test"
    monkeypatch.setattr(config, "SUPABASE_TEST_URL", None)
    monkeypatch.setattr(config, "SUPABASE_TEST_SECRET_KEY", "sb_secret_TESTKEY")
    with pytest.raises(ValueError, match="SUPABASE_TEST_URL is missing"):
        db.credentials()
    monkeypatch.setattr(config, "SUPABASE_TEST_URL", "https://zwpftrjryxyymrxsprqh.supabase.co")          # a production URL used as the test URL
    with pytest.raises(ValueError, match="not the test project") as e:
        db.credentials()
    assert "sb_secret_TESTKEY" not in str(e.value)
    monkeypatch.setattr(config, "SUPABASE_TEST_URL", "https://wbhxjcegoobkbnjnuise.supabase.co")
    assert db.credentials() == ("https://wbhxjcegoobkbnjnuise.supabase.co", "sb_secret_TESTKEY")
    monkeypatch.setenv("VC_DB_TARGET", "prod")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://wbhxjcegoobkbnjnuise.supabase.co")               # a test URL used as the production URL
    monkeypatch.setattr(config, "SUPABASE_SECRET_KEY", "k")
    with pytest.raises(ValueError, match="not the prod project"):
        db.credentials()
    monkeypatch.setenv("VC_DB_TARGET", "staging")
    with pytest.raises(ValueError):
        db.db_target()


# ---------------------------------------------------------------- financial_facts
def facts():
    return [Fact("ACM", 2024, "revenue", 1.0, "found", "xbrl", tag="Revenues"), Fact("ACM", 2025, "revenue", 2.5, "found", "xbrl", tag="Revenues"),
            Fact("ACM", 2025, "net_income", 5, "found", "xbrl", tag="NetIncomeLoss", flags=("share_scale_guard",)), Fact("ACM", 2024, "sbc", 0.0, "reported_none", "derived")]


def test_upsert_is_idempotent_and_writes_only_changes():
    c = client()
    repo = FinancialRepository(c)
    assert repo.upsert_facts(1, facts()) == {"inserted": 4, "updated": 0, "unchanged": 0}
    w = c.writes
    assert repo.upsert_facts(1, facts()) == {"inserted": 0, "updated": 0, "unchanged": 4} and c.writes == w            # a second load writes nothing
    changed = facts()
    changed[1] = Fact("ACM", 2025, "revenue", 2.6, "found", "xbrl", tag="Revenues")
    assert repo.upsert_facts(1, changed) == {"inserted": 0, "updated": 1, "unchanged": 3}
    assert [t["tag"] for t in c.tables["fact_tags"]] == ["Revenues", "NetIncomeLoss"]                                 # a tag is created once


def test_history_year_coverage_and_wide_history_decode_keys_tags_and_flags():
    repo = FinancialRepository(client())
    repo.upsert_facts(1, facts())
    h = repo.get_history(1)
    assert [(d["fiscal_year"], d["item_key"]) for d in h] == [(2024, "revenue"), (2024, "sbc"), (2025, "net_income"), (2025, "revenue")]
    ni = repo.get_year(1, 2025)["net_income"]
    assert ni["tag"] == "NetIncomeLoss" and ni["flags"] == ("share_scale_guard",) and ni["value"] == 5
    assert repo.get_coverage_years(1) == [2024, 2025]
    assert repo.get_wide_history(1) == [{"fiscal_year": 2024, "revenue": 1.0, "sbc": 0.0}, {"fiscal_year": 2025, "net_income": 5, "revenue": 2.5}]
    assert repo.get_history(2) == []
    with pytest.raises(KeyError):
        repo.upsert_facts(1, [Fact("ACM", 2025, "not_in_dictionary", 1.0, "found", "xbrl")])


def test_filing_periods_are_idempotent():
    repo = FinancialRepository(client())
    p = [{"fiscal_year": 2025, "accession": "a", "form": "10-K", "fiscal_year_end": "2025-12-31", "reporting_currency": "USD", "calculation_version": "v"}]
    assert repo.upsert_filing_periods(1, p) == {"inserted": 1, "updated": 0, "unchanged": 0}
    assert repo.upsert_filing_periods(1, p) == {"inserted": 0, "updated": 0, "unchanged": 1}
    p[0]["accession"] = "b"
    assert repo.upsert_filing_periods(1, p)["updated"] == 1 and repo.get_filing_periods(1)[0]["accession"] == "b"


# ---------------------------------------------------------------- extraction_items
def test_text_values_survive_the_numeric_column():
    rows = [ExtractionRow("ACM", "a", "", 12.5, "value", "USD mm"), ExtractionRow("ACM", "b", "", "NA", "NA"), ExtractionRow("ACM", "c", "", "MISSING", "MISSING"),
            ExtractionRow("ACM", "d", "FY2025", "not disclosed", "not_disclosed"), ExtractionRow("ACM", "alm_disclosed", "FY2025", "YES", "value", "text"),
            ExtractionRow("ACM", "e", "FY2025", "not extracted", "value")]
    for r in rows:
        e = encode(1, r)
        assert e["value"] is None or isinstance(e["value"], (int, float))
        assert e["value_state"] in ("value", "NA", "MISSING", "not_disclosed") and (e["value_state"] != "value" or e["value"] is not None)
        d = decode("ACM", {**e, "id": 1})
        assert d.value == r.value and d.unit == r.unit and d.period == r.period
    assert value_state("YES") == "value"                                     # the in-memory state of the text YES stays 'value'; the table stores it as MISSING + basis "text:YES"


def test_extraction_rows_keep_their_order_and_upsert_is_idempotent():
    c = client()
    repo = ExtractionRepository(c)
    rows = [ExtractionRow("ACM", f"loan:{n}", "", float(i), "value", "USD mm", "", "sec", "quote", True, "", "note") for i, n in enumerate("zyx")]
    assert repo.upsert_rows(1, rows)["inserted"] == 3
    assert [r.item_key for r in repo.get_rows(1, "ACM")] == ["loan:z", "loan:y", "loan:x"]
    w = c.writes
    assert repo.upsert_rows(1, rows) == {"inserted": 0, "updated": 0, "unchanged": 3} and c.writes == w
    rows[0] = ExtractionRow("ACM", "loan:z", "", 9.0, "value", "USD mm", "", "sec", "quote", True, "", "note")
    assert repo.upsert_rows(1, rows)["updated"] == 1 and repo.get_rows(1)[0].value == 9.0


# ---------------------------------------------------------------- FactSet <-> database
def test_factset_round_trip_gives_the_same_engine_inputs_and_a_second_write_changes_nothing():
    c = client()
    sink = FactSetDb(c)
    fs = facts_from_kwargs("general", kw())
    s1 = sink.write(fs)
    assert s1["facts"]["inserted"] == len(fs.facts) and s1["periods"]["inserted"] == 2
    w = c.writes
    fs2 = sink.read(fs)
    assert differences(kwargs_from_facts("general", fs), kwargs_from_facts("general", fs2)) == []
    assert sink.write(fs)["facts"] == {"inserted": 0, "updated": 0, "unchanged": len(fs.facts)} and c.writes == w
    assert [p[:2] for p in fs2.periods] == [(2024, "FY2024"), (2025, "FY2025")] and str(fs2.periods[1][2]) == "2025-12-31"


def test_via_db_wraps_an_inputs_class_and_reports_zero_differences():
    sink, report = FactSetDb(client()), []

    class Inputs:
        def __init__(self, **k):
            self.k = k
    built = via_db("general", Inputs, sink, report)(**kw())
    assert report[0]["ticker"] == "ACM" and report[0]["differences"] == [] and built.k["f"]["revenue"] == [1.0, 2.5] and built.k["price_current"] == 10.0
    assert built.k["sbc_state"] == ["reported_none", "found"]


def test_comparison_helpers_treat_int_and_float_alike_and_name_the_path():
    assert equal_values({"a": [1, 2.0, None]}, {"a": [1.0, 2, None]}) and equal_values(float("nan"), float("nan")) and not equal_values(1, 2)
    assert differences({"f": {"x": [1, 2]}}, {"f": {"x": [1, 3]}}) == ["/f/x[1]: cache='2' db='3'"] or differences({"f": {"x": [1, 2]}}, {"f": {"x": [1, 3]}})[0].startswith("/f/x[1]")
    assert differences({"a": 1}, {"b": 1}) == ["/a: only in cache", "/b: only in db"]


# ---------------------------------------------------------------- companies
def test_company_repository_new_columns_ensure_and_processing_state():
    repo = CompanyRepository(client())
    row = repo.ensure("ACM", "Acme")
    assert row["symbol"] == "ACM" and repo.ensure("ACM", "Acme")["id"] == row["id"] and len(repo.client.tables["companies"]) == 1
    repo.set_classification(row["id"], sic="3559", vc_industry="Machinery", tier="sic", status="decided")
    assert repo.get_by_symbol("ACM")["vc_industry"] == "Machinery"
    with pytest.raises(ValueError):
        repo.set_processing_state(row["id"], "unsupported")                                    # a reason is required
    with pytest.raises(ValueError):
        repo.set_processing_state(row["id"], "nonsense")
    repo.set_processing_state(row["id"], "unsupported", "files 20-F")
    assert repo.get_by_symbol("ACM")["unsupported_reason"] == "files 20-F"
    repo.set_processing_state(row["id"], "complete")
    assert repo.get_by_symbol("ACM")["processing_state"] == "complete" and repo.get_by_symbol("ACM")["unsupported_reason"] is None


# ---------------------------------------------------------------- approval of extraction rows
def reg_rows():
    return [ExtractionRow("ACM", "a", "", 1.0, "value", "USD", quote_verified=True), ExtractionRow("ACM", "b", "", 2.0, "value", "USD", quote_verified=False),
            ExtractionRow("ACM", "c", "", "NA", "NA", quote_verified=False)]


def test_default_rule_legacy_verified_then_k5b_match_then_pending():
    r = reg_rows()
    assert [approval_for(x) for x in r] == [("approved", "legacy_verified"), ("pending", ""), ("pending", "")]
    assert [approval_for(x, k5b_matched=True) for x in r] == [("approved", "legacy_verified"), ("approved", "k5b_confirmed"), ("approved", "k5b_confirmed")]
    assert approval_for(r[1], approve_all=True) == ("approved", "human_review")


def test_csv_rows_load_pending_unless_verified_and_the_table_rules_hold():
    c = client()
    fs = facts_from_kwargs("general", kw())
    fs.extraction = reg_rows()
    fs.has_reg = True
    sink = FactSetDb(c)
    st = sink.write(fs)["extraction"]
    assert (st["rule_legacy_verified"], st["rule_k5b_confirmed"], st["rule_pending"], st["inserted"]) == (1, 0, 2, 3)
    rows = {r["item_key"]: r for r in c.tables["extraction_items"]}
    assert (rows["a"]["approval_status"], rows["a"]["approval_source"], rows["a"]["approved_at"] is not None) == ("approved", "legacy_verified", True)
    for k in ("b", "c"):
        assert (rows[k]["approval_status"], rows[k]["approval_source"], rows[k]["approved_at"]) == ("pending", None, None)
    for r in rows.values():                                                       # the table's CHECK: approved needs source and time
        assert r["approval_status"] != "approved" or (r["approval_source"] and r["approved_at"])
    assert sink.write(fs)["extraction"]["unchanged"] == 3
    st = FactSetDb(c, k5b_matched={("ACM", "b", "")}).write(fs)["extraction"]                  # a K5b match approves only the row that was not legacy-verified
    assert (st["rule_k5b_confirmed"], st["rule_pending"], st["updated"]) == (1, 1, 1)
    assert {r["item_key"]: r["approval_source"] for r in c.tables["extraction_items"]} == {"a": "legacy_verified", "b": "k5b_confirmed", "c": None}


def test_approve_all_flag_works_on_test_and_is_refused_on_prod(monkeypatch):
    fs = facts_from_kwargs("general", kw())
    fs.extraction = reg_rows()
    monkeypatch.setenv("VC_DB_TARGET", "test")
    c = client()
    FactSetDb(c, approve_all=True).write(fs)
    assert {r["approval_status"] for r in c.tables["extraction_items"]} == {"approved"} and {r["approval_source"] for r in c.tables["extraction_items"]} == {"human_review"}
    monkeypatch.setenv("VC_DB_TARGET", "prod")
    with pytest.raises(ValueError, match="refused when VC_DB_TARGET=prod"):
        FactSetDb(client(), approve_all=True)
    sink = FactSetDb(client())                                                    # without the flag, prod is fine...
    sink.approve_all = True                                                       # ...and a flag set afterwards is still caught at write time
    with pytest.raises(ValueError, match="refused when VC_DB_TARGET=prod"):
        sink.write(fs)
    monkeypatch.setenv("VC_DB_TARGET", "test")
    sink2 = FactSetDb(client(), approve_all=True)
    monkeypatch.setenv("VC_DB_TARGET", "prod")
    with pytest.raises(ValueError):
        sink2.write(fs)

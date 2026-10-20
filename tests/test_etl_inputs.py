"""Code stage K2: facts -> inputs behaviour (missing vs zero, states, wrapper)."""
from dataclasses import replace
from pathlib import Path

import pytest

from src.etl.from_providers import classify, facts_from_kwargs
from src.etl.to_inputs import kwargs_from_facts, via_facts
from tests.test_etl_roundtrip import GOLDEN, load_kwargs

pytestmark = pytest.mark.skipif(not Path(GOLDEN).exists(), reason="tests/golden/2026-10-20 not present")


@pytest.mark.parametrize("field,tag,sbc,expect", [
    ("revenue", "Revenues", None, ("found", "xbrl")),
    ("capex", "ixbrl:ci:PaymentsForProceedsFromPropertyPlantAndEquipment", None, ("found", "ixbrl")),
    ("aoci_afs", None, None, ("found", "ixbrl")),
    ("cash", None, None, ("found", "xbrl")),
    ("buybacks", "assumed_zero (line item absent while statement retrieved)", None, ("assumed_zero", "derived")),
    ("debt_current", "ASSUMED_ZERO (no current-debt tag)", None, ("assumed_zero", "derived")),
    ("sbc", "ASSUMED reported_none (cash-flow retrieved, no SBC tag in any year)", "reported_none", ("reported_none", "derived")),
    ("ebit", "DERIVED: pretax + interest_expense", None, ("found", "derived")),
    ("acquisitions", "PROXY: GoodwillAcquiredDuringPeriod (lower bound)", None, ("found", "derived")),
    ("debt_total", "SUM: NotesPayable + SecuredDebt", None, ("found", "derived")),
    ("debt_lt", "LongTermDebt - LongTermDebtCurrent", None, ("found", "derived")),
    ("shares_out", "dei:EntityCommonStockSharesOutstanding (cover page)", None, ("found", "xbrl")),
])
def test_classify(field, tag, sbc, expect):
    assert classify(field, tag, sbc) == expect


def _kw(directory, ticker):
    engine, kw = load_kwargs(directory, ticker)
    if engine == "general" and kw.get("sbc_state") is None:
        kw["sbc_state"] = ["found" if v is not None else "not_found" for v in kw["f"]["sbc"]]
    return engine, kw


@pytest.mark.parametrize("directory,ticker", [("general", "KO"), ("bank", "JPM"), ("insurance", "CB"), ("realestate", "O")])
def test_a_missing_row_is_none_never_zero(directory, ticker):
    engine, kw = _kw(directory, ticker)
    fs = facts_from_kwargs(engine, kw)
    victim = next(f for f in reversed(fs.facts) if f.fiscal_year == fs.periods[-1][0] and f.status == "found" and f.value not in (None, 0))
    fs.facts = [f for f in fs.facts if f is not victim]
    back = kwargs_from_facts(engine, fs)
    field = next(k for k, v in __import__("src.etl.field_map", fromlist=["x"]).FIELDS[engine].items() if v == victim.item_key)
    assert back["f"][field][-1] is None


@pytest.mark.parametrize("directory,ticker", [("general", "KO"), ("general", "MSFT"), ("bank", "JPM"), ("realestate", "O")])
def test_assumed_zero_reads_as_zero_and_keeps_its_state(directory, ticker):
    engine, kw = _kw(directory, ticker)
    fs = facts_from_kwargs(engine, kw)
    az = [f for f in fs.facts if f.status == "assumed_zero"]
    assert az, "expected an assumed_zero fact in this company"
    back = kwargs_from_facts(engine, fs)
    from src.etl.field_map import FIELDS
    inv = {v: k for k, v in FIELDS[engine].items()}
    for f in az[:20]:
        i = [y for y, _, _ in fs.periods].index(f.fiscal_year)
        assert back["f"][inv[f.item_key]][i] == 0.0
    # the same row dropped is a missing value, not a zero
    fs.facts = [f for f in fs.facts if f is not az[0]]
    back2 = kwargs_from_facts(engine, fs)
    i0 = [y for y, _, _ in fs.periods].index(az[0].fiscal_year)
    assert back2["f"][inv[az[0].item_key]][i0] is None


def test_general_states_and_runner_side_assumed_zero_map():
    engine, kw = _kw("general", "MSFT")
    fs = facts_from_kwargs(engine, kw)
    back = kwargs_from_facts(engine, fs)
    assert back["sbc_state"] == kw["sbc_state"]
    assert set(back["assumed_zero"]) <= {"acquisitions", "buybacks", "dividends", "impairments", "sti", "goodwill", "intangibles",
                                         "acquisitions_proxy_goodwill", "dps_derived", "shares_out_cover_page", "customer_funds_excluded"}
    for labs in back["assumed_zero"].values():
        assert set(labs) <= set(kw["fy"])


def test_reported_none_sbc_state():
    engine, kw = _kw("general", "KO")
    kw["f"]["sbc"] = [0.0] * len(kw["fy"])
    kw["sbc_state"] = ["reported_none"] * len(kw["fy"])
    kw["tag_log"]["sbc"] = {l: {"tag": "ASSUMED reported_none (cash-flow retrieved, no SBC tag in any year)"} for l in kw["fy"]}
    fs = facts_from_kwargs(engine, kw)
    assert {f.status for f in fs.facts if f.item_key == "sbc"} == {"reported_none"}
    assert kwargs_from_facts(engine, fs)["sbc_state"] == ["reported_none"] * len(kw["fy"])


def test_via_facts_builds_an_equal_inputs_object():
    from datetime import date
    from src.scoring.inputs import CompanyInputs
    engine, kw = _kw("general", "KO")
    kw = dict(kw, profile="STANDARD", end=[date.fromisoformat(e) for e in kw["end"]], as_of=date(2026, 10, 20), flags=["x"], data_problems=["y"],
              price_current=60.0, price_avg=[None] * len(kw["fy"]), assumed_zero={})
    direct = CompanyInputs(**kw)
    wrapped = via_facts("general", CompanyInputs)(**kw)
    for attr in ("ticker", "name", "profile", "fy", "end", "f", "sbc_state", "price_current", "price_avg", "as_of", "flags", "data_problems"):
        assert getattr(wrapped, attr) == getattr(direct, attr), attr
    with pytest.raises(AssertionError):
        via_facts("general", CompanyInputs)(direct)        # positional use is refused

"""Code stage K2, step 2: the engine-series <-> item_key map is complete, injective and consistent with the dictionary migrations."""
import csv
import json
import re
from pathlib import Path

import pytest

from src.etl import field_map as fm
from src.etl.facts import Fact, label_to_year, year_to_label

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "2026-10-20"
ROW = re.compile(r"\(\s*(\d+),\s*'((?:FIN|DRV|PRC|TXT)-\d{3})',\s*'([a-z][a-z0-9_]*)'")


def dictionary_keys() -> dict:
    out = {}
    for p in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
        text = p.read_text(encoding="utf-8")
        if "insert into public.dictionary_items" not in text:
            continue
        for i, dict_id, key in ROW.findall(text):
            assert key not in out, f"duplicate item_key {key}"
            out[key] = (int(i), dict_id)
    return out


KEYS = dictionary_keys()


def test_dictionary_parsed():
    assert len(KEYS) >= 252
    assert len({v[0] for v in KEYS.values()}) == len(KEYS)  # ids unique


@pytest.mark.parametrize("engine", list(fm.FIELDS))
def test_every_mapped_key_exists_and_map_is_injective(engine):
    m = fm.FIELDS[engine]
    assert all(k in KEYS for k in m.values()), [k for k in m.values() if k not in KEYS]
    assert len(set(m.values())) == len(m), "two series of one engine feed the same item_key"


def test_extraction_targets_exist():
    seen = set()
    for table in (fm._BANK_EXT, fm._INS_EXT, fm._RE_EXT):
        seen |= set(table.values())
    seen |= {k for _, k in fm._INS_EXT_PATTERNS} | {k for _, k in fm._RE_FAMILIES}
    assert [k for k in seen if k not in KEYS] == []


def _golden_series(engine):
    """series names present in the golden inputs of an engine"""
    if not GOLDEN.exists():
        pytest.skip("tests/golden/2026-10-20 not present")
    names = set()
    sub = {"general": ["general", "managed_care"], "bank": ["bank"], "insurance": ["insurance"], "realestate": ["realestate"]}[engine]
    for d in sub:
        for p in (GOLDEN / d).glob("*.json"):
            j = json.loads(p.read_text(encoding="utf-8"))
            fin = j.get("financials") or (j.get("inputs") or {}).get("f") or {}
            names |= set(fin)
    return names


@pytest.mark.parametrize("engine", list(fm.FIELDS))
def test_every_series_of_the_baseline_is_mapped_or_carried_through(engine):
    names = _golden_series(engine)
    assert names, engine
    unknown = names - set(fm.FIELDS[engine]) - fm.EXTRAS[engine]
    assert not unknown, f"{engine}: series without item_key and not in EXTRAS: {sorted(unknown)}"
    assert not (set(fm.FIELDS[engine]) & fm.EXTRAS[engine])


def test_extraction_items_are_all_classified():
    csvs = {"bank": "bank_regulatory.csv", "insurance": "insurance_regulatory.csv", "realestate": "realestate_extracted.csv"}
    for engine, name in csvs.items():
        p = ROOT / "scripts" / name
        if not p.exists():
            pytest.skip(f"{name} not present")
        items = {r["item"] for r in csv.DictReader(p.open(encoding="utf-8")) if r.get("ticker") and not r["ticker"].startswith("#")}
        modes = {i: fm.extraction_key(engine, i)[1] for i in items}
        assert "unmapped" not in modes.values(), {i: m for i, m in modes.items() if m == "unmapped"}


def test_extraction_key_modes():
    assert fm.extraction_key("bank", "loan:Auto") == (None, "rows")
    assert fm.extraction_key("bank", "past_due_90_accruing:total")[0] == "past_due_90_accruing_extracted"
    assert fm.extraction_key("bank", "past_due_90_accruing:consumer") == (None, "rows")
    assert fm.extraction_key("insurance", "adverse_prior_year_dev:FY2024") == ("prior_year_dev_extracted", "single")
    assert fm.extraction_key("insurance", "structural_event:FY2023") == (None, "rows")
    assert fm.extraction_key("realestate", "bsa_wc__prepaid") == ("bsa_wc", "sum")
    assert fm.extraction_key("realestate", "mat_year1_x__senior_notes") == ("debt_maturity_year1_extracted", "sum")
    assert fm.extraction_key("realestate", "recon_nci_adjust") == ("recon_nci_adjust", "single")
    assert fm.extraction_key("realestate", "brand_new_item")[1] == "unmapped"


def test_fact_rules_mirror_the_table_checks():
    Fact("T", 2024, "revenue", 1.0, "found", "xbrl")
    Fact("T", 2024, "sbc", 0.0, "reported_none", "derived")
    Fact("T", 2024, "capex", 0.0, "assumed_zero", "derived")
    Fact("T", 2024, "sbc", None, "not_applicable", "xbrl")
    for bad in (dict(value=None, status="found"), dict(value=5.0, status="assumed_zero"), dict(value=1.0, status="reported_none"),
                dict(value=1.0, status="weird")):
        with pytest.raises(ValueError):
            Fact("T", 2024, "x", source_kind="xbrl", **bad)
    with pytest.raises(ValueError):
        Fact("T", 2024, "x", 1.0, "found", "bogus")


def test_year_label_roundtrip():
    assert label_to_year("FY2024") == 2024 and year_to_label(2024) == "FY2024"
    with pytest.raises(ValueError):
        label_to_year("2024")

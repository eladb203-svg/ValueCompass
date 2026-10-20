"""Code stage K2, steps 3-4: provider output -> facts -> engine inputs is the identity on the 54 baseline companies (no providers run:
the inputs are read back from tests/golden/2026-10-20)."""
import json
from pathlib import Path

import pytest

from src.etl import field_map as fm
from src.etl.facts import label_to_year, parse_date
from src.etl.from_providers import facts_from_kwargs
from src.etl.to_inputs import kwargs_from_facts

GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "golden" / "2026-10-20"
ENGINE_OF = {"general": "general", "managed_care": "general", "bank": "bank", "insurance": "insurance", "realestate": "realestate"}


def companies():
    if not GOLDEN.exists():
        return []
    return [(d, p.stem) for d in ENGINE_OF for p in sorted((GOLDEN / d).glob("*.json"))]


def load_kwargs(directory, ticker):
    j = json.loads((GOLDEN / directory / f"{ticker}.json").read_text(encoding="utf-8"))
    engine = ENGINE_OF[directory]
    if engine == "realestate":
        i = j["inputs"]
        kw = dict(ticker=ticker, name=j["name"], fy=i["fy"], end=i["end"], f=i["f"], tag_log=i["tag_log"], reg=i["reg"])
        return engine, kw
    labels = list(j["fiscal_years"])
    kw = dict(ticker=ticker, name=j["name"], fy=labels, end=[j["fiscal_years"][l] for l in labels],
              f={fld: [vals.get(l) for l in labels] for fld, vals in j["financials"].items()},
              tag_log=(j.get("data_source") or {}).get("tag_log_per_field_per_year") or j.get("tag_log_per_field_per_year") or j.get("tag_log") or {})
    if engine == "general":
        kw["sbc_state"] = [j["sbc_state"][l] for l in labels] if "sbc_state" in j else None
    if engine == "bank":
        kw["reg"] = j["data_source"]["regulatory_csv_rows"]
    if engine == "insurance":
        kw["reg"] = j["extraction_rows"]
    return engine, kw


pytestmark = pytest.mark.skipif(not companies(), reason="tests/golden/2026-10-20 not present")


@pytest.mark.parametrize("directory,ticker", companies())
def test_roundtrip_is_identity(directory, ticker):
    engine, kw = load_kwargs(directory, ticker)
    if engine == "general" and kw.get("sbc_state") is None:   # managed-care JSON has no sbc_state: derive "found" where a value exists
        kw["sbc_state"] = ["found" if v is not None else "not_found" for v in kw["f"]["sbc"]]
    fs = facts_from_kwargs(engine, kw)
    back = kwargs_from_facts(engine, fs)
    assert back["fy"] == kw["fy"]
    assert [d.isoformat() for d in back["end"]] == [parse_date(e).isoformat() for e in kw["end"]]
    # L1: every series equal (None stays None, 0.0 stays 0.0, ints stay ints)
    for fld, vals in kw["f"].items():
        assert back["f"][fld] == vals, f"{ticker} {fld}"
        assert [type(a) is type(b) for a, b in zip(back["f"][fld], vals)] == [True] * len(vals), f"{ticker} {fld} type"
    for fld, vals in back["f"].items():
        if fld not in kw["f"]:
            assert all(v is None for v in vals), f"{ticker}: series {fld} appeared"
    # tag text equal where the provider logged one; none invented
    for fld, yrs in kw["tag_log"].items():
        if fld not in kw["f"]:
            continue                                           # provider-side logs of non-series names (e.g. insurance 'aoci'): metadata, not facts
        for lab, ent in yrs.items():
            t = (ent or {}).get("tag")
            if kw["f"].get(fld) is not None and kw["f"][fld][kw["fy"].index(lab)] is None:
                continue                                       # no value -> no fact -> no tag (the provider logs {"tag": None})
            assert back["tag_log"][fld][lab]["tag"] == t, f"{ticker} {fld} {lab}"
    for fld, yrs in back["tag_log"].items():
        for lab, ent in yrs.items():
            if ent["tag"] is not None:
                assert (kw["tag_log"].get(fld, {}).get(lab) or {}).get("tag") == ent["tag"]
    if engine == "general":
        assert back["sbc_state"] == kw["sbc_state"]
    if "reg" in kw:
        assert back["reg"] == kw["reg"]
        assert list(back["reg"]) == list(kw["reg"])           # insertion order (the engines sum extracted lines in this order)
        if engine == "realestate":
            assert all(list(back["reg"][k]) == list(kw["reg"][k]) for k in kw["reg"])
    # every fact is a legal financial_facts row and maps to a dictionary key
    assert all(f.item_key in set(fm.FIELDS[engine].values()) for f in fs.facts)
    assert all(label_to_year(l) == y for y, l, _ in fs.periods)


def test_status_counts_match_the_tag_logs():
    """assumed_zero facts = cells whose tag says assumed_zero and that carry a value (independent count)."""
    per_engine = {}
    for d, t in companies():
        engine, kw = load_kwargs(d, t)
        if engine == "general" and kw.get("sbc_state") is None:
            kw["sbc_state"] = ["found" if v is not None else "not_found" for v in kw["f"]["sbc"]]
        fs = facts_from_kwargs(engine, kw)
        want = sum(1 for fld, yrs in kw["tag_log"].items() for lab, ent in yrs.items()
                   if str((ent or {}).get("tag") or "").lower().startswith("assumed_zero")
                   and kw["f"].get(fld) and kw["f"][fld][kw["fy"].index(lab)] is not None)
        got = sum(1 for f in fs.facts if f.status == "assumed_zero")
        per_engine.setdefault(d, [0, 0])
        per_engine[d][0] += want
        per_engine[d][1] += got
    assert all(w == g for w, g in per_engine.values()), per_engine
    assert sum(w for w, _ in per_engine.values()) > 1000     # 171 + 47 + 313 + 337 + 442 cells in the baseline

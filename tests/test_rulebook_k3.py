"""Code stage K3 - rulebook corrections (Part H.1 of ValueCompass_Rulebook_2026-10-20_10-33). One section per fix; each test fails on the pre-K3 code."""
import pytest

from src.scoring import bank as BK
from src.scoring import insurance as I
from src.scoring.insurance import derive_insurance, insurance_buffett_price, score_insurance
from test_bank import _gq, synth
from test_insurance import N, ins


# ---------------------------------------------------------------- H-01 (C-11, C-12; A.5, D.3 6.3, D.4 P3): Graham price score below quality 55
def test_h01_bank_graham_score_shown_with_label_buy_price_not_suitable():
    bi = synth()
    q = _gq(bi)
    q.score = 40.0
    gp = BK.bank_graham_price(bi, BK.derive_bank(bi), q)
    assert gp["price_score"]["state"] == "score" and gp["price_score"]["label"]
    assert gp["buy_price"]["state"] == "not_suitable"


def test_h01_insurance_graham_score_shown_with_label_buy_price_not_suitable():
    ii = ins()
    q = score_insurance(ii)["graham_quality"]
    q.score, q.status = 40.0, "full"
    gp = I.insurance_graham_price(ii, derive_insurance(ii), q)
    assert gp["price_score"]["state"] == "score" and gp["price_score"]["label"]
    assert gp["buy_price"]["state"] == "not_suitable"


def test_h01_no_label_at_or_above_55():
    ii = ins()
    q = score_insurance(ii)["graham_quality"]
    q.score = 60.0
    gp = I.insurance_graham_price(ii, derive_insurance(ii), q)
    assert gp["price_score"]["state"] == "score" and "label" not in gp["price_score"]


# ---------------------------------------------------------------- H-02 (C-16; C.B3.4-INS): goodwill impairment is added back to operating profit
def test_h02_insurance_goodwill_impairment_added_back():
    base = derive_insurance(ins())
    imp = derive_insurance(ins(goodwill_impairment=[1.0e9] * N))
    for a, b in zip(base["nop_pretax"], imp["nop_pretax"]):
        assert b - a == pytest.approx(1.0e9)


# ---------------------------------------------------------------- H-07 (C-14; C15, D.3, D.4): value <= 0 -> price score 0, no buy price
def test_h07_bank_value_nonpositive_price_score_zero(monkeypatch):
    bi = synth()
    monkeypatch.setattr(BK, "two_stage_value", lambda *a, **k: {"total": -1.0e9, "pv_ri": 0, "pv_terminal_value": 0, "tce10": 0, "years": [], "pv_ri_sum": 0})
    bp = BK.bank_buffett_price(bi, BK.derive_bank(bi), BK.score_bank(bi)["buffett_quality"])
    assert bp["state"] == "cannot_be_valued" and bp["fair_value"] is None and bp["buy_price"] is None
    assert bp["price_score"]["state"] == "score" and bp["price_score"]["points"] == 0.0


def test_h07_insurance_value_nonpositive_price_score_zero(monkeypatch):
    ii = ins()
    monkeypatch.setattr(I.BK, "two_stage_value", lambda *a, **k: {"total": -1.0e9, "pv_ri": 0, "pv_terminal_value": 0, "tce10": 0, "years": []})
    bp = insurance_buffett_price(ii, derive_insurance(ii), score_insurance(ii)["buffett_quality"])
    assert bp["state"] == "cannot_be_valued" and bp["fair_value"] is None and bp["buy_price"] is None
    assert bp["price_score"]["state"] == "score" and bp["price_score"]["points"] == 0.0


# ================================================================ real estate
from src.scoring import buffett as B  # noqa: E402
from src.scoring import realestate as RE  # noqa: E402
from src.scoring.realestate import derive_re, nav_components, re_buffett_price, re_graham_nav, score_realestate  # noqa: E402
from test_realestate import _yrs, reit  # noqa: E402
from test_realestate_pricing import OE_REG, nav_reit  # noqa: E402
from test_realestate_pricing2 import oe_reg, r  # noqa: E402


# ---------------------------------------------------------------- H-03 (C-18b; RP1a, M7): quality coverage below 80% removes only the buy price
def test_h03_low_quality_coverage_removes_only_the_buy_price():
    ri = reit(reg=oe_reg(committed_undrawn_facilities=r(500e6)))  # 12-month liquidity coverage computable and >= 1
    sc = score_realestate(ri)
    sc["buffett_quality"].status, sc["buffett_quality"].coverage = "partial", 0.6  # coverage below 80%
    bp = re_buffett_price(ri, sc["derived"], sc["buffett_quality"])
    assert bp["state"] == "valued" and not bp["guard"]["blocked"]
    assert bp["price_score"]["state"] == "score"
    assert bp["buy_price"]["state"] == "not_computed"


def test_h03_uncomputable_12_month_coverage_still_blocks():  # C-18a
    ri = reit(reg=OE_REG, mat_year1=[None] * N, mat_year2=[None] * N)
    sc = score_realestate(ri)
    bp = re_buffett_price(ri, sc["derived"], sc["buffett_quality"])
    assert bp["guard"]["blocked"] and bp["price_score"]["state"] == "blocked"


# ---------------------------------------------------------------- H-04 (C-19; C.B3.7 variants / CL5): 3.7.3 denominator is always the normalized FFO
def test_h04_b37_acquisition_gate_divides_by_normalized_ffo_even_when_oe_exists():
    ri = reit(reg=OE_REG, acq_business=[10e6] * N)
    d = derive_re(ri)
    assert all(x is not None for x in d["oe"][-5:])
    item = next(i for i in RE.b37(ri, d) if i.id == "3")
    assert item.inputs["sum_fcf"] == pytest.approx(sum(d["norm_ffo"][-5:]))
    assert item.inputs["sum_fcf"] != pytest.approx(sum(d["oe"][-5:]))


# ---------------------------------------------------------------- H-05 (C-24; RP1 / CL6): previous-5 median <= 0 -> stage-1 growth 0%, flagged
def test_h05_previous5_median_nonpositive_gives_zero_growth_with_flag():
    ri = reit(reg=OE_REG)
    d = derive_re(ri)
    series = [-1.0] * 5 + [1.0, 2.0, 3.0, 4.0, 5.0]
    bg = RE._buffett_base_growth(ri, d, series)
    assert bg["ok"] and bg["growth_before_gate"] == 0.0
    assert any("previous-5 median <= 0" in f for f in bg["flags"]) and "growth_fallback_r14" not in bg["flags"]


# ---------------------------------------------------------------- H-06 (C-23; RP2 / M6 / CL7): no yield at all -> cannot be valued (no 6% floor)
def test_h06_no_yield_means_no_cap_rate_and_nav_cannot_be_valued(tmp_path, monkeypatch):
    p = tmp_path / "y.csv"
    p.write_text("currency,year,yield_pct\nUSD,2025,4.0\n", encoding="utf-8")
    cr = RE.conservative_cap_rate("EUR", p)
    assert cr["value"] is None and "gov_yield_missing_cannot_be_valued" in cr["flags"]
    monkeypatch.setattr(RE, "conservative_cap_rate", lambda *a, **k: cr)
    ri = nav_reit()
    sc = score_realestate(ri)
    c = nav_components(ri, sc["derived"])
    assert c["ok"] is False and "government yield" in c["reason"]
    gp = re_graham_nav(ri, sc["derived"], sc["graham_quality"])
    assert gp["state"] == "cannot_be_valued" and gp["buy_price"] is None


def test_h06_annual_fallback_stays_flagged(tmp_path):
    p = tmp_path / "y.csv"
    p.write_text("currency,year,yield_pct\nUSD,2025,4.0\n", encoding="utf-8")
    cr = RE.conservative_cap_rate("USD", p)
    assert cr["value"] == pytest.approx(0.07) and any("annual_average" in f for f in cr["flags"])


# ---------------------------------------------------------------- H-08 (C-26; C.B3.1 / CL9): the five general AI questions
def test_h08_b31_uses_the_five_general_questions():
    ri = reit()
    items = RE.b31(ri, derive_re(ri))
    assert [(i.id, i.name) for i in items] == list(B.Q31)


# ---------------------------------------------------------------- H-19 (E11): the Q6 test (OE vs AFFO less SBC, > 15%) lives in the engine, flag only
def _q6_ri(gap):
    base = reit(reg=OE_REG, sbc=[12e6] * N)
    d = derive_re(base)
    affo = {f"FY{2016 + i}": d["oe"][i] / (1 + gap) + 12e6 for i in range(N)}
    from test_realestate import _row
    return reit(reg={**OE_REG, "reported_affo": {k: _row(v) for k, v in affo.items()}}, sbc=[12e6] * N)


def test_h19_q6_gap_above_15pct_is_flagged_in_the_pricing_result():
    ri = _q6_ri(0.20)
    res = RE.score_realestate_pricing(ri, score_realestate(ri))
    assert res["reconciliation_q6"] and all(x["flag"] for x in res["reconciliation_q6"])
    assert any(f.startswith("E11_Q6") for f in res["buffett_price"]["flags"])


def test_h19_q6_gap_within_15pct_is_not_flagged_and_changes_nothing():
    ri = _q6_ri(0.10)
    sc = score_realestate(ri)
    res = RE.score_realestate_pricing(ri, sc)
    assert res["reconciliation_q6"] and not any(x["flag"] for x in res["reconciliation_q6"])
    assert not any(f.startswith("E11_Q6") for f in res["buffett_price"]["flags"])
    assert res["buffett_price"]["fair_value"] == re_buffett_price(ri, sc["derived"], sc["buffett_quality"])["fair_value"]


# ================================================================ C5 / CL12: preferred stock and preferred dividends absent from a retrieved statement = 0, flagged
class _FakeSec:
    requests_made = 0

    def __init__(self, tags):
        self.tags = tags

    def cik_for(self, ticker):
        return "0000000001", "Fake Co"

    def get_json(self, url, name, refresh=False):
        return {}

    def first_annual_report(self, cik):
        from datetime import date
        return date(2000, 3, 1)

    def companyfacts(self, cik):
        us = {}
        for tag, (unit, flow) in self.tags.items():
            ents = []
            for y in range(2021, 2026):
                e = {"end": f"{y}-12-31", "val": 100.0, "form": "10-K", "fp": "FY", "fy": y, "filed": f"{y + 1}-02-20", "accn": f"a{y}"}
                if flow:
                    e["start"] = f"{y}-01-01"
                ents.append(e)
            us[tag] = {"units": {unit: ents}}
        return {"facts": {"us-gaap": us, "dei": {}}}


def test_c5_realestate_preferred_equity_absent_is_zero_with_assumed_zero_flag():
    from src.etl.from_providers import facts_from_kwargs
    from src.providers.realestate_facts import build_realestate_series
    sec = _FakeSec({"NetIncomeLoss": ("USD", True), "Assets": ("USD", False)})
    out = build_realestate_series(sec, "TST", [], n_years=5)
    assert out["f"]["pref_equity"] == [0.0] * 5
    assert out["tag_log"]["pref_equity"]["FY2025"]["tag"] == "assumed_zero" and "pref_equity" in out["assumed"]
    fs = facts_from_kwargs("realestate", {"ticker": "TST", "fy": out["labels"], "end": [e.isoformat() for e in out["ends"]], "f": out["f"], "tag_log": out["tag_log"]})
    from src.etl import field_map as fm
    rows = [x for x in fs.facts if x.item_key == fm.FIELDS["realestate"]["pref_equity"]]
    assert len(rows) == 5 and all(x.status == "assumed_zero" and x.value == 0.0 for x in rows)


def test_c5_realestate_reported_preferred_equity_is_kept():
    from src.providers.realestate_facts import build_realestate_series
    sec = _FakeSec({"NetIncomeLoss": ("USD", True), "Assets": ("USD", False), "PreferredStockValue": ("USD", False)})
    out = build_realestate_series(sec, "TST", [], n_years=5)
    assert out["f"]["pref_equity"] == [100.0] * 5 and "pref_equity" not in out["assumed"]


def test_c5_bank_preferred_dividends_absent_is_zero_with_assumed_zero_flag():
    from src.providers.bank_facts import build_bank_series
    sec = _FakeSec({"NetIncomeLoss": ("USD", True), "Assets": ("USD", False)})
    out = build_bank_series(sec, "TST", [], n_years=5)
    assert out["f"]["pref_div"] == [0.0] * 5 and out["tag_log"]["pref_div"]["FY2025"]["tag"] == "assumed_zero" and "pref_div" in out["assumed"]

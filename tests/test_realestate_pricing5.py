"""INCOME_REAL_ESTATE final check (rules 2026-10-15_10-35): RE29a - no unrealized FX remeasurement and no non-real-estate investment results in normalized FFO, in both directions."""
import pytest

from src.providers.realestate_facts import load_realestate_extracted
from src.scoring.realestate import derive_re
from test_realestate import N, _yrs, reit
from test_realestate_pricing2 import oe_reg


def test_re29a_fx_remeasurement_gain_is_deducted_and_loss_is_added_back():
    base = derive_re(reit(reg=oe_reg()))
    gain = derive_re(reit(reg=oe_reg(), fx_unrealized=[40e6] * N))
    loss = derive_re(reit(reg=oe_reg(), fx_unrealized=[-90e6] * N))
    assert gain["ffo"][-1] == base["ffo"][-1] and loss["ffo"][-1] == base["ffo"][-1]  # FFO itself is unchanged
    assert gain["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] - 40e6)
    assert loss["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] + 90e6)
    assert gain["re29a_fx_result"][-1] == 40e6 and loss["oe"][-1] == pytest.approx(base["oe"][-1] + 90e6)


def test_re29a_non_real_estate_investment_results_both_directions_and_components_are_summed():
    base = derive_re(reit(reg=oe_reg()))
    d = derive_re(reit(reg=oe_reg(re29a_nonre_inv__realized=_yrs(30e6), re29a_nonre_inv__unrealized=_yrs(-50e6))))
    assert d["re29a_investment_result"][-1] == pytest.approx(-20e6)  # net loss of 20m
    assert d["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] + 20e6)
    g = derive_re(reit(reg=oe_reg(re29a_nonre_inv__realized=_yrs(30e6))))
    assert g["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] - 30e6)


def test_re29a_combines_with_re29_without_double_counting_and_is_neutral_when_nothing_is_extracted():
    base = derive_re(reit(reg=oe_reg()))
    d = derive_re(reit(reg=oe_reg(dev_gains_reported=_yrs(10e6), re29_nonre_impairments__x=_yrs(4e6), re29a_nonre_inv__y=_yrs(7e6)), fx_unrealized=[-3e6] * N))
    assert d["norm_ffo"][-1] == pytest.approx(base["norm_ffo"][-1] - 10e6 + 4e6 - 7e6 + 3e6)
    assert derive_re(reit(reg=oe_reg()))["norm_ffo"][-1] == base["norm_ffo"][-1] and base["re29a_fx_result"][-1] is None and base["re29a_investment_result"][-1] is None


def test_re29a_fx_series_is_read_by_the_provider_from_the_unrealized_tag_first():
    from src.providers.realestate_facts import RE_FIELDS
    kind, unit, tags = RE_FIELDS["fx_unrealized"]
    assert kind == "flow" and tags[0] == "ForeignCurrencyTransactionGainLossUnrealized" and "ForeignCurrencyTransactionGainLossBeforeTax" in tags


def test_re29a_shipped_csv_amounts_signs_and_sources():
    reg = load_realestate_extracted()
    assert reg["ARE"]["re29a_nonre_inv__investment_income"]["FY2022"]["value"] == pytest.approx(-331.758e6)  # a loss
    assert reg["ARE"]["re29a_nonre_inv__investment_income"]["FY2021"]["value"] == pytest.approx(259.477e6)  # a gain
    assert reg["SPG"]["re29a_nonre_inv__equity_interests"]["FY2025"]["value"] == pytest.approx(-66.981e6)  # the company adds a 67.0m loss back
    assert reg["SPG"]["re29a_nonre_inv__equity_interests"]["FY2024"]["value"] == pytest.approx(386.417e6)
    assert reg["AMT"]["re29a_nonre_inv__equity_securities"]["FY2025"]["value"] == pytest.approx(232.6e6) and reg["AMT"]["re29a_nonre_inv__vil_sale"]["FY2024"]["value"] == pytest.approx(46.4e6)
    for t, item, y in (("ARE", "re29a_nonre_inv__investment_income", "FY2025"), ("SPG", "re29a_nonre_inv__platform", "FY2024"), ("AMT", "re29a_nonre_inv__equity_securities", "FY2025"), ("EQR", "re29a_nonre_inv__unrealized_securities", "FY2025")):
        row = reg[t][item][y]
        assert row["quote"] and row["verified"] and "[source:" in row["source"]

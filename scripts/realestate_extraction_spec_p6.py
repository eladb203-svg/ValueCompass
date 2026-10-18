"""Extraction spec, RE29b (2026-10-15; rules 2026-10-15_10-50): the foreign-exchange amount removed from normalized FFO is the NET result including the hedging derivatives.
Priority 1: the net line of the income statement (O: 'foreign currency and derivative (loss) gain, net'); priority 2: the amount the company itself adds back in its FFO / AFFO reconciliation
(PLD, PSA, AMT). Sign: positive = gain (deducted), negative = loss (added back). Item read by src/scoring/realestate.py: re29b_fx_net (replaces the gross XBRL tag for the years where present).
"""
from realestate_extraction_spec import USD, X, R
from realestate_extraction_spec_p2 import _D, _gr

ROWS_P6 = []
ROWS_P6 += [
    X("O", "re29b_fx_net", 2025, r"Foreign currency and derivative \(loss\) gain, net " + _gr(3), ["FY2025", "FY2024", "FY2023"], USD, "Item 8 - consolidated statements of income: foreign currency and derivative (loss) gain, net", 1e3,
      note="NET of the hedging derivatives (cross-currency swaps / forwards): priority 1 (income-statement net line, equal to the company's AFFO adjustment); hedged: yes"),
    X("O", "re29b_fx_net", 2023, r"Foreign currency and derivative \(loss\) gain, net " + _gr(3), [None, "FY2022", "FY2021"], USD, "Item 8 - consolidated statements of income: foreign currency and derivative (loss) gain, net", 1e3,
      note="NET of the hedging derivatives: priority 1; hedged: yes"),
    X("PLD", "re29b_fx_net", 2025, r"Unrealized foreign currency and derivative losses \(gains\), net " + _gr(3), ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - FFO reconciliation: unrealized foreign currency and derivative losses (gains), net", -1e3,
      note="priority 2: the amount Prologis adds back in 'FFO, as modified by Prologis' (already net of the derivatives: 'foreign currency and derivative'); printed as a loss (gain), sign reversed; hedged: yes (derivatives and foreign-currency debt), net = the XBRL unrealized tag"),
    X("PLD", "re29b_fx_net", 2023, r"Unrealized foreign currency and derivative losses \(gains\), net " + _gr(3), [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - FFO reconciliation: unrealized foreign currency and derivative losses (gains), net", -1e3,
      note="as above (USD thousand in this filing)"),
    X("PSA", "re29b_fx_net", 2025, r"Foreign currency exchange gain \(loss\) " + _gr(3), ["FY2025", "FY2024", "FY2023"], USD, "Item 8 - consolidated statements of income: foreign currency exchange gain (loss)", 1e3,
      note="remeasurement of the euro-denominated notes; no hedging derivative: net = gross"),
    R("AMT", "re29b_fx_net", "FY2025", 2025, -809.4e6, USD, "Item 7 MD&A - AFFO reconciliation footnote (6): other expense (income)", ("losses (gains) on foreign currency exchange rate fluctuations of $809.4 million and $(308.3) million, respectively",), "$809.4 million", pre=40, post=40,
      note="company add-back in AFFO; unrealized remeasurement of intercompany / unaffiliated balances, no hedging derivative: net = gross; loss"),
    R("AMT", "re29b_fx_net", "FY2024", 2025, 308.3e6, USD, "Item 7 MD&A - AFFO reconciliation footnote (6): other expense (income)", ("losses (gains) on foreign currency exchange rate fluctuations of $809.4 million and $(308.3) million, respectively",), "$(308.3) million", pre=40, post=40,
      note="company add-back in AFFO; gain; no hedging derivative: net = gross"),
    R("AMT", "re29b_fx_net", "FY2023", 2023, -330.8e6, USD, "Item 7 MD&A - AFFO reconciliation footnote (4): other expense (income)", ("(losses) gains on foreign currency exchange rate fluctuations of $(330.8) million and $449.4 million, respectively",), "$(330.8) million", pre=40, post=40,
      note="company add-back in AFFO; loss; no hedging derivative: net = gross"),
    R("AMT", "re29b_fx_net", "FY2022", 2023, 449.4e6, USD, "Item 7 MD&A - AFFO reconciliation footnote (4): other expense (income)", ("(losses) gains on foreign currency exchange rate fluctuations of $(330.8) million and $449.4 million, respectively",), "$449.4 million", pre=40, post=40,
      note="company add-back in AFFO; gain; no hedging derivative: net = gross"),
    R("AMT", "re29b_fx_net", "FY2021", 2021, 557.9e6, USD, "Item 7 MD&A - AFFO reconciliation footnote (3): other expense (income)", ("(gains) losses on foreign currency exchange rate fluctuations of $(557.9) million and $216.4 million, respectively",), "$(557.9) million", pre=40, post=40,
      note="company add-back in AFFO; gain; no hedging derivative: net = gross"),
]

ROWS_P6.append(X("PSA", "re29b_fx_net", 2023, r"Foreign currency exchange \(loss\) gain " + _gr(3), [None, "FY2022", "FY2021"], USD, "Item 8 - consolidated statements of income: foreign currency exchange (loss) gain", 1e3,
                 note="remeasurement of the euro-denominated notes; no hedging derivative: net = gross"))

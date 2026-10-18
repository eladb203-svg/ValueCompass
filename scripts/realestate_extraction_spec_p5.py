"""Extraction spec, final check (2026-10-15; rules 2026-10-15_10-35): RE29a - results of non-real-estate investments (realized and unrealized, both directions) that stay in normalized FFO otherwise.
Foreign-currency remeasurement comes from XBRL (ForeignCurrencyTransactionGainLossUnrealized / BeforeTax). Sign convention of every row: positive = gain (deducted from normalized FFO), negative = loss (added back).

Item names read by src/scoring/realestate.py: re29a_nonre_inv__* (summed per year).
"""
from realestate_extraction_spec import USD, X, R
from realestate_extraction_spec_p2 import _D, _gr

ROWS_P5 = []
_NUM = r"(\(\d[\d,]*\)|\d[\d,]*)"

# ARE: investment income (loss) = realized and unrealized results and impairments of non-real-estate investments (USD thousand)
ROWS_P5 += [
    X("ARE", "re29a_nonre_inv__investment_income", 2025, r"Investment loss \$ ?" + _NUM + r" \$ ?" + _NUM, ["FY2025", "FY2024"], USD, "Item 7 MD&A - investments: investment (loss) income (realized, unrealized and impairments)", 1e3,
      note="all results of non-real-estate investments (realized gains, unrealized changes in fair value, impairments); loss printed in parentheses"),
    X("ARE", "re29a_nonre_inv__investment_income", 2024, r"Investment loss \$ ?" + _NUM + r" \$ ?" + _NUM + r" \$ ?" + _NUM, [None, "FY2024", "FY2023"], USD, "Item 7 MD&A - investments: investment (loss) income", 1e3, note="as above (columns: Q4, year, prior year)"),
    X("ARE", "re29a_nonre_inv__investment_income", 2022, r"Investment \(loss\) income \$ ?" + _NUM + r" \$ ?" + _NUM + r" \$ ?" + _NUM, [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - investments: investment (loss) income", 1e3, note="as above (columns: Q4, year, prior year)"),
]
# SPG: the company's own FFO adjustments for platform investments and equity instruments (positive in the table = loss added back -> sign reversed)
_SPG = [("equity_interests", r"Loss \(gain\) due to disposal, exchange, or revaluation of equity interests, net of tax"), ("platform", r"Other platform investments, net of tax"),
        ("unrealized_equity", r"Unrealized losses \(gains\) in fair value of publicly traded equity instruments and derivative instrument, net")]
for slug, lab in _SPG:
    ROWS_P5.append(X("SPG", f"re29a_nonre_inv__{slug}", 2025, lab + " " + " ".join([_D] * 3), ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - Real Estate FFO bridge: " + lab, -1e3,
                     note="company adjustment to reach Real Estate FFO (positive = loss added back); sign reversed so that a gain is positive; not available for FY2021-FY2022 (not shown in those reconciliations)"))
# AMT: gains on equity securities and the VIL investment (in 'other expense (income)')
ROWS_P5 += [
    R("AMT", "re29a_nonre_inv__equity_securities", "FY2025", 2025, 232.6e6, USD, "Item 7 MD&A - other expense (income)", ("gains from equity securities in the United States of $232.6 million and $70.4 million, respectively",), "$232.6 million", pre=160, post=60,
      note="gain; first amount = 2025"),
    R("AMT", "re29a_nonre_inv__equity_securities", "FY2024", 2025, 70.4e6, USD, "Item 7 MD&A - other expense (income)", ("gains from equity securities in the United States of $232.6 million and $70.4 million, respectively",), "$70.4 million", pre=160, post=60,
      note="gain; second amount = 2024"),
    R("AMT", "re29a_nonre_inv__vil_sale", "FY2024", 2025, 46.4e6, USD, "Item 7 - VIL Shares and VIL OCDs", ("we recognized a gain of $46.4 million on the sale of the VIL Shares and the VIL OCDs",), "$46.4 million", pre=160, post=60,
      note="realized gain on the sale of the VIL investment"),
    R("AMT", "re29a_nonre_inv__vil_ocd_unrealized", "FY2023", 2023, 76.7e6, USD, "Item 7 - other expense (income)", ("unrealized gains of $76.7 million related to the VIL OCDs held as of December 31, 2023",), "$76.7 million", pre=160, post=60,
      note="unrealized gain on the VIL OCDs"),
]
# EQR: realized / unrealized (gain) loss on investment securities in the Normalized FFO bridge of the earnings release (USD thousand, trailing twelve months at year end; printed adjustment, positive = loss)
for _frag, _fy in [("SUP2025:eqr-ex99_1", "FY2025"), ("SUP2024:17025012330", "FY2024"), ("SUP2023:7024008861", "FY2023"), ("SUP2022:eqr-ex99_1", "FY2022"), ("SUP2021:eqr-ex991", "FY2021")]:
    ROWS_P5.append(X("EQR", "re29a_nonre_inv__realized_securities", _frag, r"Realized \(gain\) loss on investment securities \(interest and other income\) " + _D, [_fy], USD, "Earnings release - Normalized FFO bridge", -1e3,
                     note="printed adjustment, sign reversed so that a gain is positive"))
for _frag, _fy in [("SUP2025:eqr-ex99_1", "FY2025"), ("SUP2024:17025012330", "FY2024"), ("SUP2023:7024008861", "FY2023")]:
    ROWS_P5.append(X("EQR", "re29a_nonre_inv__unrealized_securities", _frag, r"Unrealized \(gain\) loss on investment securities \(interest and other income\) " + _D, [_fy], USD, "Earnings release - Normalized FFO bridge", -1e3,
                     note="printed adjustment, sign reversed so that a gain is positive"))

"""Extraction spec, pricing round 3 (2026-10-14; rules 2026-10-14_23-25): single basis for OE (RE28: BXP Inc. share of the partnership, SPG operating-partnership basis), reported AFFO / FAD for the Q6
check, PLD Core FFO and development gains for the Q1 definition check. Same row machinery as the earlier spec files (exact quote, source document, section, verification).

Item names read by src/scoring/realestate.py:
  inc_share_of_bplp (fraction: BXP, Inc. share of Boston Properties Limited Partnership FFO), partnership_units_weighted (BXP: weighted shares + OP units, basic), straight_line_x_q / reported_affo_q
  (BXP quarter rows summed by the loader), recon_net_income / shares_basis_override (SPG: consolidated net income and weighted shares + units), reported_affo (O, EQIX, AMT),
  core_ffo_reported and dev_gains_reported (PLD).
"""
from realestate_extraction_spec import USD, X
from realestate_extraction_spec_p2 import _D, _gr

ROWS_P3 = []

# ================================================================== BXP: single basis (RE28)
_PCT = r"Our percentage share of Funds from Operations.basic ([\d.]+) ?% ([\d.]+) ?% ([\d.]+) ?%"
ROWS_P3 += [
    X("BXP", "inc_share_of_bplp", 2025, _PCT, ["FY2025", "FY2024", "FY2023"], "fraction", "Item 7 MD&A - FFO: BXP, Inc.'s percentage share of the partnership FFO", 0.01,
      note="BXP, Inc.'s share of Boston Properties Limited Partnership FFO (basic); FFO attributable to BXP, Inc. = this share x partnership FFO"),
    X("BXP", "inc_share_of_bplp", 2023, _PCT, ["FY2023", "FY2022", "FY2021"], "fraction", "Item 7 MD&A - FFO: BXP, Inc.'s percentage share of the partnership FFO", 0.01, note="as above"),
]
_BXP_UNITS = r"Funds from Operations attributable to Boston Properties Limited Partnership(?: common unitholders)? \(\d\) \$ [\d,]+ \$ [\d,]+ \$ [\d,]+ Weighted average shares outstanding.basic (\d[\d,]*) (\d[\d,]*) (\d[\d,]*)"
ROWS_P3 += [
    X("BXP", "partnership_units_weighted", 2025, _BXP_UNITS, ["FY2025", "FY2024", "FY2023"], "shares", "Item 7 MD&A - FFO of the partnership: weighted average shares and units, basic", 1e3, note="shares + OP units (thousand x 1e3)"),
    X("BXP", "partnership_units_weighted", 2023, _BXP_UNITS, ["FY2023", "FY2022", "FY2021"], "shares", "Item 7 MD&A - FFO of the partnership: weighted average shares and units, basic", 1e3, note="shares + OP units (thousand x 1e3)"),
]
_FAD = r"Funds available for distribution to common shareholders and common unitholders \(FAD\) (?:\(A\)|\d) \$ (\d[\d,]*) \$ (\d[\d,]*)"
_SLQ = r"BXP.{1,3}s Share of straight-line rent \d(?:, ?\d)? (\d[\d,]*) (\d[\d,]*)"
_BXP_NOTE = "BXP's share (partnership basis, incl. unconsolidated JVs, net of partners' share), FAD table of the supplemental, quarter column; the loader sums four quarters"
for _tag, _fy, _q1, _q2, _frag in [("SUP2025", "FY2025", "Q4", "Q3", "q42025supplemental"), ("SUP2025Q2", "FY2025", "Q2", "Q1", "q22025supplemental"),
                                  ("SUP2024Q4", "FY2024", "Q4", "Q3", "q42024supplemental"), ("SUP2024Q2", "FY2024", "Q2", "Q1", "q22024supplemental"),
                                  ("SUP2023Q4", "FY2023", "Q4", "Q3", "q42023supplemental"), ("SUP2023Q2", "FY2023", "Q2", "Q1", "q22023supplemental"),
                                  ("SUP2022Q4", "FY2022", "Q4", "Q3", "q42022supplemental"), ("SUP2022Q2", "FY2022", "Q2", "Q1", "q22022supplemental"),
                                  ("SUP2021Q4", "FY2021", "Q4", "Q3", "q42021supplemental"), ("SUP2021Q2", "FY2021", "Q2", "Q1", "q22021supplemental")]:
    _f = f"{_tag}:{_frag}"
    ROWS_P3 += [
        X("BXP", "straight_line_x_q", _f, _SLQ, [f"{_fy}{_q1}", f"{_fy}{_q2}"], USD, "Supplemental - Funds Available for Distribution: BXP's share of straight-line rent", 1e3, note=_BXP_NOTE),
        X("BXP", "reported_affo_q", _f, _FAD, [f"{_fy}{_q1}", f"{_fy}{_q2}"], USD, "Supplemental - Funds Available for Distribution (FAD) to common shareholders and unitholders", 1e3,
          note="BXP's FAD (partnership basis; per unit on shares + OP units); the loader sums four quarters"),
    ]

# ================================================================== SPG: operating-partnership basis (RE28)
_SPG_NI = r"Consolidated Net Income \$ " + r" \$ ".join([_D] * 3) + r" Adjustments to Arrive at FFO"
_SPG_UNITS = r"Basic and Diluted weighted average shares and units outstanding " + _gr(3)
ROWS_P3 += [
    X("SPG", "recon_net_income", 2025, _SPG_NI, ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - FFO reconciliation: consolidated net income (start of the OP's FFO)", 1e3,
      note="consolidated net income (before the limited partners' share): the FFO reconciliation of the Operating Partnership starts here"),
    X("SPG", "recon_net_income", 2023, _SPG_NI, [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - FFO reconciliation: consolidated net income", 1e3, note="as above"),
    X("SPG", "shares_basis_override", 2025, _SPG_UNITS, ["FY2025", "FY2024", "FY2023"], "shares", "Item 7 MD&A - basic and diluted weighted average shares and units", 1e3,
      note="shares + limited partnership units (OP basis, RE28); thousand x 1e3"),
    X("SPG", "shares_basis_override", 2023, _SPG_UNITS, [None, "FY2022", "FY2021"], "shares", "Item 7 MD&A - basic and diluted weighted average shares and units", 1e3, note="as above"),
]

# ================================================================== reported AFFO (Q6)
ROWS_P3 += [
    X("O", "reported_affo", 2025, r"AFFO available to common stockholders \$ " + _gr(1) + r" \$ " + _gr(1), ["FY2025", "FY2024"], USD, "Item 7 MD&A - AFFO available to common stockholders (USD million)", 1e6, note="company AFFO"),
    X("O", "reported_affo", 2023, r"AFFO available to common stockholders \$ " + _gr(1) + r" \$ " + _gr(1), ["FY2023", "FY2022"], USD, "Item 7 MD&A - AFFO available to common stockholders (USD million)", 1e6, note="company AFFO"),
    X("O", "reported_affo", 2021, r"AFFO available to common stockholders \$ " + _gr(1) + r" \$ ", ["FY2021"], USD, "Item 7 MD&A - AFFO available to common stockholders (USD million)", 1e6, note="company AFFO"),
    X("EQIX", "reported_affo", 2025, r"AFFO attributable to common stockholders \$ " + _gr(1) + r" \$ " + _gr(1) + r" \$ " + _gr(1), ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - AFFO attributable to common stockholders (USD million)", 1e6,
      note="company AFFO (adds back stock-based compensation 498m, non-real-estate depreciation 568m and amortization 200m, deducts recurring capex)"),
    X("EQIX", "reported_affo", 2023, r"AFFO attributable to common shareholders \$ " + _gr(1) + r" \$ " + _gr(1) + r" \$ " + _gr(1), [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - AFFO attributable to common shareholders (USD thousand)", 1e3, note="company AFFO"),
    X("AMT", "reported_affo", 2025, r"AFFO attributable to American Tower Corporation common stockholders \$ " + _gr(1) + r" \$ " + _gr(1), ["FY2025", "FY2024"], USD, "Item 7 MD&A - AFFO attributable to AMT common stockholders (USD million)", 1e6, note="company AFFO"),
    X("AMT", "reported_affo", 2023, r"AFFO attributable to American Tower Corporation common stockholders \$ " + _gr(1) + r" \$ " + _gr(1), ["FY2023", "FY2022"], USD, "Item 7 MD&A - AFFO attributable to AMT common stockholders (USD million)", 1e6, note="company AFFO"),
    X("AMT", "reported_affo", 2021, r"AFFO attributable to American Tower Corporation common stockholders \$ " + _gr(1) + r" \$ ", ["FY2021"], USD, "Item 7 MD&A - AFFO attributable to AMT common stockholders (USD million)", 1e6, note="company AFFO"),
]

# ================================================================== PLD: Core FFO and development gains (Q1)
_PLD_DEV = r"Adjustments to arrive at Core FFO: Gains on dispositions of development properties and land, net " + _gr(2)
_PLD_CORE = r"Core FFO attributable to common stockholders/unitholders \$ " + _D + r" \$ " + _D
for _filing, _years in ((2025, ["FY2025", "FY2024"]), (2023, ["FY2023", "FY2022"]), (2021, ["FY2021", "FY2020"])):
    ROWS_P3.append(X("PLD", "core_ffo_reported", _filing, _PLD_CORE, _years, USD, "Item 7 MD&A - FFO reconciliation: Core FFO attributable to common stockholders/unitholders", 1e6,
                     note="company Core FFO (excludes gains on development properties and land); USD million"))
    ROWS_P3.append(X("PLD", "dev_gains_reported", _filing, _PLD_DEV, _years, USD,
                     "Item 7 MD&A - FFO reconciliation: gains on dispositions of development properties and land, net (deducted to reach Core FFO)", -1e6,
                     note="gains included in NAREIT FFO and excluded from Core FFO (the table prints them as a deduction); USD million"))

# ================================================================== EQIX: AFFO add-backs (Q6 bridge) and balance-sheet debt composition (finance-lease check)
from realestate_extraction_spec_p2 import L as _L  # noqa: E402

_EQIX_ADD = r"Non-real estate depreciation expense " + _gr(3) + r".{0,120}?Amortization expense " + _gr(3)
ROWS_P3 += [
    X("EQIX", "affo_addback_non_re_depr", 2025, _EQIX_ADD, ["FY2025", "FY2024", "FY2023", None, None, None], USD, "Item 7 MD&A - AFFO reconciliation: non-real estate depreciation expense", 1e6,
      note="added back in the company's AFFO (a real cost of servers / equipment that the recurring-capex deduction only partly replaces); USD million"),
    X("EQIX", "affo_addback_amortization", 2025, _EQIX_ADD, [None, None, None, "FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - AFFO reconciliation: amortization expense", 1e6, note="added back in the company's AFFO; USD million"),
    X("EQIX", "affo_addback_non_re_depr", 2023, _EQIX_ADD, [None, "FY2022", "FY2021", None, None, None], USD, "Item 7 MD&A - AFFO reconciliation: non-real estate depreciation expense", 1e3, note="USD thousand"),
    X("EQIX", "affo_addback_amortization", 2023, _EQIX_ADD, [None, None, None, None, "FY2022", "FY2021"], USD, "Item 7 MD&A - AFFO reconciliation: amortization expense", 1e3, note="USD thousand"),
]
_EQIX_LIAB = r"Liabilities, Redeemable Non-Controlling Interest and Stockholders' Equity Current liabilities:"
for _slug, _label in [("finance_lease_current", r"Current portion of finance lease liabilities"), ("finance_lease_noncurrent", r"Finance lease liabilities, less current portion"),
                      ("mortgage_current", r"Current portion of mortgage and loans payable"), ("senior_notes_current", r"Current portion of senior notes"),
                      ("mortgage_noncurrent", r"Mortgage and loans payable, less current portion"), ("senior_notes_noncurrent", r"Senior notes, less current portion")]:
    ROWS_P3.append(_L("EQIX", f"bs_check__{_slug}", "FY2025", 2025, _EQIX_LIAB, _label, 0, 1e6, section="Item 8 - balance sheet liabilities (finance-lease check, RP2 other claims)",
                      note="used to test whether the debt tag includes finance-lease liabilities", within=3000))

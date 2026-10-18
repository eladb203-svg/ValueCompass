"""Extraction spec, confirmation round (2026-10-15; rules 2026-10-15_09-30): RE29 (normalized FFO without real-estate sale gains and without non-real-estate impairments), the companies' own
Core / normalized / adjusted FFO for the Q1 comparison, and the AMT AFFO reconciliation lines for the Q6 bridge (FY2023 and FY2025). Same row machinery as the earlier spec files.

Item names read by src/scoring/realestate.py:
  recon_gi_net (AMT: the company's 'losses from sale or disposal of real estate and real estate related impairment charges' line, positive = add-back),
  re29_nonre_impairments (additional non-real-estate impairments added back to normalized FFO), core_ffo_reported (USD, the company's Core / normalized FFO to common),
  core_ffo_ps_reported (USD per share, where only per-share figures are published), affo_br__* (AMT AFFO reconciliation lines).
"""
from realestate_extraction_spec import USD, X, R
from realestate_extraction_spec_p2 import _D, _gr

ROWS_P4 = []
PS = "USD/share"

# ================================================================== company Core / normalized / adjusted FFO (Q1)
ROWS_P4 += [
    X("O", "core_ffo_reported", 2025, r"Normalized FFO available to common stockholders \$ " + _D + r" \$ " + _D, ["FY2025", "FY2024"], USD, "Item 7 MD&A - Normalized FFO available to common stockholders (USD million)", 1e6,
      note="company 'Normalized FFO' (adds back merger / integration costs, loss on extinguishment and other items)"),
    X("O", "core_ffo_reported", 2023, r"Normalized FFO available to common stockholders \$ " + _D + r" \$ " + _D, ["FY2023", "FY2022"], USD, "Item 7 MD&A - Normalized FFO available to common stockholders (USD million)", 1e6, note="company Normalized FFO"),
    X("O", "core_ffo_reported", 2021, r"Normalized FFO available to common stockholders \$ " + _D + r" \$ ", ["FY2021"], USD, "Item 7 MD&A - Normalized FFO available to common stockholders (USD million)", 1e6, note="company Normalized FFO"),
    X("SPG", "core_ffo_reported", 2025, r"Real Estate FFO \$ " + _D + r" \$ " + _D + r" \$ " + _D, ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - Real Estate FFO (Operating Partnership)", 1e3,
      note="company 'Real Estate FFO' (FFO of the Operating Partnership adjusted for equity-interest revaluations, platform investments and unrealized securities items)"),
    X("ARE", "core_ffo_ps_reported", 2025, r"Funds from operations per share attributable to Alexandria Real Estate Equities, Inc..s common stockholders - diluted, as adjusted \$ ?" + _D + r" \$ ?" + _D + r" \$ ?" + _D,
      ["FY2025", "FY2024", "FY2023"], PS, "Item 7 MD&A - FFO per share, diluted, as adjusted", 1.0, note="company 'FFO per share - diluted, as adjusted' (excludes unrealized investment results, impairments, extinguishment losses and other items)"),
    X("ARE", "core_ffo_ps_reported", 2023, r"Funds from operations per share attributable to Alexandria Real Estate Equities, Inc..s common stockholders - diluted, as adjusted \$ ?" + _D + r" \$ ?" + _D + r" \$ ?" + _D,
      [None, "FY2022", "FY2021"], PS, "Item 7 MD&A - FFO per share, diluted, as adjusted", 1.0, note="company FFO per share, diluted, as adjusted"),
    X("PSA", "core_ffo_ps_reported", 2025, r"Core FFO per share \$ " + _D + r" \$ " + _D + r" [\d.]+ ?\(?[\d.]*\)? ?% \$ " + _D + r" \$ " + _D, ["FY2025", "FY2024", None, "FY2023"], PS, "Item 7 MD&A - Core FFO per share", 1.0,
      note="company Core FFO per share (FY2025 vs FY2024; the second pair is FY2024 vs FY2023)"),
    X("FRT", "core_ffo_ps_reported", "SUP2025:frt-12312025", r"Core FFO \$ ?" + _D + r" \$ ?" + _D + r" \$ ?7\.42", ["FY2024", "FY2025"], PS, "Earnings release - Core FFO per share (new measure introduced in 2025)", 1.0,
      note="company Core FFO per share; introduced in the 2025 release, no earlier years published"),
]
for _frag, _fy in [("SUP2025:eqr-ex99_1", "FY2025"), ("SUP2024:17025012330", "FY2024"), ("SUP2023:7024008861", "FY2023"), ("SUP2022:eqr-ex99_1", "FY2022"), ("SUP2021:eqr-ex991", "FY2021")]:
    ROWS_P4.append(X("EQR", "core_ffo_reported", _frag, r"Normalized FFO available to Common Shares and Units \$ " + _D, [_fy], USD, "Earnings release - Normalized FFO available to common shares and units", 1e3,
                     note="company Normalized FFO (after preferred distributions; common shares and OP units)"))

# ================================================================== AMT: AFFO reconciliation lines (Q6 bridge) and the Nareit line that carries impairments and goodwill (RE29)
_a = lambda label, n=2: label + " " + " ".join([_D] * n)  # noqa: E731
AMT25 = [("recon_gi_net", r"Losses from sale or disposal of real estate and real estate related impairment charges \(2\)"), ("straight_line_revenue", r"Straight-line revenue"), ("straight_line_expense", r"Straight-line expense"),
         ("deferred_tax", r"Deferred portion of income tax and other income tax adjustments \(5\)"), ("non_re_da", r"Non-real estate related depreciation, amortization and accretion"),
         ("amort_financing", r"Amortization of deferred financing costs, capitalized interest, debt discounts and premiums and long-term deferred interest charges"), ("other_expense", r"Other expense \(income\) \(6\)"),
         ("other_operating", r"Other operating income \(7\)"), ("capital_improvement", r"Capital improvement capital expenditures"), ("corporate_capex", r"Corporate capital expenditures"),
         ("unconsolidated_nci", r"Adjustments and distributions for unconsolidated affiliates and noncontrolling interests \(8\)"), ("discontinued", r"Adjustments for discontinued operations \(9\)"),
         ("sbc_affo", r"Straight-line expense [\d.()]+ [\d.()]+ [\d.()]+ Stock-based compensation expense")]
AMT23 = [("recon_gi_net", r"Losses from sale or disposal of real estate and real estate related impairment charges \(1\)"), ("nci_dividends", r"Dividends to noncontrolling interests \(2\)"),
         ("straight_line_revenue", r"Straight-line revenue"), ("straight_line_expense", r"Straight-line expense"), ("deferred_tax", r"Deferred portion of income tax and other income tax adjustments"),
         ("non_re_da", r"Non-real estate related depreciation, amortization and accretion"),
         ("amort_financing", r"Amortization of deferred financing costs, debt discounts and premiums and long-term deferred interest charges"), ("other_expense", r"Other expense \(income\) \(4\)"),
         ("retirement_loss", r"Loss on retirement of long-term obligations"), ("other_operating", r"Other operating expenses \(5\)"), ("capital_improvement", r"Capital improvement capital expenditures"),
         ("corporate_capex", r"Corporate capital expenditures"), ("unconsolidated_nci", r"Adjustments for unconsolidated affiliates and noncontrolling interests \d{2,3}\.\d \d{2,3}\.\d Consolidated AFFO")]
for slug, lab in AMT25:
    if slug == "sbc_affo":
        continue
    ROWS_P4.append(X("AMT", f"affo_br__{slug}" if slug != "recon_gi_net" else "recon_gi_net", 2025, lab + " " + " ".join([_D] * 2), ["FY2025", "FY2024"], USD, "Item 7 MD&A - Nareit FFO / AFFO reconciliation", 1e6,
                     note="AMT reconciliation line, USD million; positive = added to FFO / AFFO"))
for slug, lab in AMT23:
    if slug == "unconsolidated_nci":
        ROWS_P4.append(X("AMT", "affo_br__unconsolidated_nci", 2023, r"Adjustments for unconsolidated affiliates and noncontrolling interests " + " ".join([_D] * 2) + r" \(?\d+\)? Consolidated AFFO", ["FY2023", "FY2022"], USD,
                         "Item 7 MD&A - AFFO reconciliation", 1e6, note="AMT reconciliation line, USD million"))
        continue
    ROWS_P4.append(X("AMT", f"affo_br__{slug}" if slug != "recon_gi_net" else "recon_gi_net", 2023, lab + " " + " ".join([_D] * 2), ["FY2023", "FY2022"], USD, "Item 7 MD&A - Nareit FFO / AFFO reconciliation", 1e6,
                     note="AMT reconciliation line, USD million; positive = added to FFO / AFFO"))
ROWS_P4 += [
    X("AMT", "affo_br__consolidated_to_attributable", 2023, r"Consolidated AFFO \$ [\d.,]+ \$ [\d.,]+ \(?\d+\.?\d*\)? ?% Adjustments for unconsolidated affiliates and noncontrolling interests \(6\) " + " ".join([_D] * 2), ["FY2023", "FY2022"], USD,
      "Item 7 MD&A - AFFO reconciliation: consolidated to attributable", 1e6, note="AMT line, USD million"),
    # non-real-estate impairments that are NOT in the Nareit line (RE29, added back to normalized FFO): FY2025 goodwill impairment Spain 80.0 (own line) and Bangladesh 6.5 (other operating expense)
    R("AMT", "re29_nonre_impairments__spain_goodwill", "FY2025", 2025, 80.0e6, USD, "Item 7 - critical accounting estimates: goodwill (Spain reporting unit)", ("we recorded a goodwill impairment charge of $80.0 million",), "$80.0 million", pre=200, post=120,
      note="goodwill impairment recorded in 'Goodwill impairment'; not part of AMT's Nareit FFO line in FY2025 (the line's footnote lists impairment charges of $100.7m and a South Africa Fiber gain only)"),
    R("AMT", "re29_nonre_impairments__bangladesh_goodwill", "FY2025", 2025, 6.5e6, USD, "Item 7 - critical accounting estimates: goodwill (Bangladesh reporting unit)", ("we recorded a goodwill impairment charge of $6.5 million",), "$6.5 million", pre=200, post=160,
      note="goodwill impairment recorded in other operating expense"),
]

ROWS_P4.append(X("AMT", "recon_gi_net", 2021, r"Losses from sale or disposal of real estate and real estate related impairment charges \(1\) " + " ".join([_D] * 2), ["FY2021", None], USD,
                 "Item 7 MD&A - Nareit FFO reconciliation", 1e6, note="AMT reconciliation line, USD million; positive = added to FFO"))

# ARE: impairments of non-real-estate investments (FFO 'as adjusted' reconciliation); information only since round 5 - they are inside the total non-real-estate investment income (loss) that RE29a neutralizes (no double count)
_ARE_NRI = r"Impairment of non-real estate investments (\d[\d,]*|—)(?: \(\d\))? (\d[\d,]*|—)(?: \(\d\))? (\d[\d,]*|—)(?: \(\d\))? Impairment of real estate"
ROWS_P4 += [
    X("ARE", "info_nonre_impairments_in_investment_income", 2025, _ARE_NRI, ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - FFO as adjusted: impairment of non-real estate investments", 1e3,
      note="non-real-estate investments (private equity / equity securities of life-science companies); not in NAREIT FFO, added back in the company's FFO as adjusted; USD thousand"),
    X("ARE", "info_nonre_impairments_in_investment_income", 2023, _ARE_NRI, [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - FFO as adjusted: impairment of non-real estate investments", 1e3, note="as above"),
]

"""Extraction spec additions for the bank regression round (spec 2026-10-12_21-05).

Rows here are appended to ``bank_extraction_spec.S``; a row with the same (ticker, item) overrides the earlier one.
  D10  cet1_required_standardized / cet1_required_advanced   requirement as reported by the bank (fallback: Fed table)
  D12  lcr_q4_average from the bank's separate public LCR disclosure (``file`` = text under scripts/cache/)
  D15  funding:<role>:<label>   balance-sheet funding lines used for deposit funding (roles: deposits, repo, short_term, long_term)
"""
MM = "USD mm"
PCT = "%"


def r(t, item, value, unit, section, tokens, verify=None, pre=40, post=300, note="", file=None):
    return dict(t=t, item=item, value=value, unit=unit, section=section, tokens=tokens, verify=verify,
                pre=pre, post=post, note=note, file=file)


S2 = []

# ------------------------------------------------------------------ D12: LCR from public disclosures / missing
S2 += [
    r("PNC", "lcr_q4_average", 108, PCT,
      "Public LCR disclosure - PNC Q4 2025 LCR & NSFR Disclosures (investor.pnc.com, filed 2026-02-23)",
      ("average LCR for the three months ended December 31, 2025 was",), "108%", pre=40, post=20,
      file="public_lcr/PNC_Q4_2025_LCR_NSFR_Disclosure.txt",
      note="Not in the 10-K (only 'exceeded the 100% minimum'); found in PNC's separate public LCR disclosure (D12)"),
    r("FITB", "lcr_q4_average", 123, PCT, "Public disclosure - Fifth Third Q4 2025 earnings presentation (8-K filed 2026-01-20)",
      ("Maintained full Category 1 LCR compliance during the quarter, ending at",), "123%", pre=20, post=20,
      file="public_lcr/FITB_4Q25_presentation.txt",
      note="QUARTER-END figure, not a Q4 average; no LCR in the 10-K; FITB is a Category IV bank whose LCR exemption is not stated (D12)"),
    r("FLG", "lcr_q4_average", "NA", PCT, "Balance sheet (V11 evidence: total assets < $100bn)", ("Total assets", "87,512", "100,160"), "87,512",
      pre=0, post=40, note="V11: not applicable by regulatory category - evidence: total assets < $100bn (10-K balance sheet: $87,512mm at "
                           "2025-12-31; $100,160mm at 2024-12-31). The 10-K does not mention the LCR."),
]

# ------------------------------------------------------------------ D10: required CET1 per approach
S2 += [
    r("JPM", "cet1_required_standardized", 11.5, PCT, "MD&A - Selected capital and RWA data (Capital ratio requirements)",
      ("CET1 capital ratio", "14.6"), "11.5", post=140),
    r("JPM", "cet1_required_advanced", 11.5, PCT, "MD&A - Selected capital and RWA data (Capital ratio requirements)",
      ("CET1 capital ratio", "14.6"), "14.1", post=200, note="the second 11.5% in the quote is the Advanced requirement"),
    r("BAC", "cet1_required_standardized", 10.0, PCT, "MD&A - Table 10 (Regulatory Minimum; footnote 3: 4.5% + G-SIB 3.0% + SCB 2.5%)",
      ("Common equity tier 1 capital ratio", "11.4"), "10.0", post=120),
    r("BAC", "cet1_required_advanced", 10.0, PCT, "MD&A - Table 10 (one Regulatory Minimum column shown for both approaches)",
      ("Common equity tier 1 capital ratio", "11.4"), "10.0", post=120,
      note="BAC reports a single regulatory-minimum column (10.0%) next to both the Standardized and the Advanced column"),
    r("C", "cet1_required_standardized", 11.6, PCT, "MD&A - Citigroup's required risk-based capital ratios",
      ("CET1 Capital ratio requirement", "11.6"), "11.6", post=80),
    r("C", "cet1_required_advanced", 10.5, PCT, "MD&A - Citigroup's required risk-based capital ratios",
      ("CET1 Capital ratio requirement", "11.6"), "10.5", post=80),
    r("WFC", "cet1_required_standardized", 8.5, PCT, "MD&A - Table 35 (Required Capital Ratios)",
      ("Common Equity Tier 1 capital ratio", "(A)/(D)"), "8.50", post=100),
    r("WFC", "cet1_required_advanced", 8.5, PCT, "MD&A - Table 35 (Required Capital Ratios)",
      ("Common Equity Tier 1 capital ratio", "(A)/(D)"), "12.35", post=140, note="the second 8.50% in the quote is the Advanced requirement"),
    r("GS", "cet1_required_standardized", 10.9, PCT, "Note 20 - Consolidated Regulatory Capital Requirements (total risk-based requirements)",
      ("CET1 capital ratio", "10.9", "13.7", "10.0"), "10.9", post=100),
    r("GS", "cet1_required_advanced", 10.0, PCT, "Note 20 - Consolidated Regulatory Capital Requirements (total risk-based requirements)",
      ("CET1 capital ratio", "10.9", "13.7", "10.0"), "10.0", post=100),
    r("PNC", "cet1_required_standardized", 7.0, PCT, "Item 1 - Supervision and Regulation (capital)",
      ("must maintain a CET1 capital ratio of at least", "7.0%"), "7.0%", post=100),
    r("MTB", "cet1_required_standardized", 7.2, PCT, "Item 1 - Supervision and Regulation (capital)",
      ("subject to a CET1 capital requirement of", "7.2%"), "7.2%", post=100),
    r("FLG", "cet1_required_standardized", 7.0, PCT, "Item 1 - Supervision and Regulation (capital schedule with capital conservation buffer)",
      ("Common Equity Tier 1", "4.50%", "7.00%"), "7.00%", post=60),
]

# ------------------------------------------------------------------ D15: funding lines at December 31, 2025
FS = "Consolidated balance sheet (December 31, 2025)"


def F(t, role, label, value, tokens, verify, note="", post=200):
    return r(t, f"funding:{role}:{label}", value, MM, FS, tokens, verify, post=post, note=note)


S2 += [
    F("JPM", "deposits", "Deposits", 2559320, ("Deposits", "2,559,320"), "2,559,320"),
    F("JPM", "repo", "Federal funds purchased and securities loaned or sold under repurchase agreements", 442396,
      ("Federal funds purchased and securities loaned or sold under repurchase agreements", "442,396"), "442,396"),
    F("JPM", "short_term", "Short-term borrowings", 64776, ("Short-term borrowings", "64,776"), "64,776"),
    F("JPM", "long_term", "Long-term debt", 435206, ("Long-term debt", "435,206"), "435,206"),
    F("BAC", "deposits", "Total deposits", 2018729, ("Total deposits", "2,018,729"), "2,018,729"),
    F("BAC", "repo", "Federal funds purchased and securities loaned or sold under agreements to repurchase", 344716,
      ("(includes $223,067 and $192,859 measured at fair value)", "344,716"), "344,716"),
    F("BAC", "short_term", "Short-term borrowings", 48088,
      ("Short-term borrowings (includes $8,051 and $6,245 measured at fair value)", "48,088"), "48,088"),
    F("BAC", "long_term", "Long-term debt", 317816,
      ("Long-term debt (includes $72,591 and $50,005 measured at fair value)", "317,816"), "317,816"),
    F("WFC", "deposits", "Total deposits", 1426207, ("Total deposits", "1,426,207"), "1,426,207"),
    F("WFC", "repo", "Federal funds purchased and securities loaned or sold under repurchase agreements", 232687,
      ("Federal funds purchased and securities loaned or sold under repurchase agreements (1)", "232,687"), "232,687"),
    F("WFC", "short_term", "Short-term borrowings", 18323, ("Short-term borrowings (1)", "18,323"), "18,323"),
    F("WFC", "long_term", "Long-term debt", 174712,
      ("Long-term debt (includes $7,082 and $3,495 carried at fair value)", "174,712"), "174,712"),
    F("USB", "deposits", "Total deposits", 522216, ("Total deposits", "522,216"), "522,216"),
    F("USB", "short_term", "Short-term borrowings", 17162, ("Short-term borrowings", "17,162"), "17,162",
      note="includes federal funds purchased and securities sold under repurchase agreements (no separate balance-sheet line)"),
    F("USB", "long_term", "Long-term debt", 60764,
      ("Long-term debt (including $1,414 and $391 of long-term debt carried at fair value, respectively)", "60,764"), "60,764"),
    F("PNC", "deposits", "Total deposits", 440866, ("Total deposits", "440,866"), "440,866"),
    F("PNC", "long_term", "Total borrowed funds", 57101, ("Total borrowed funds", "57,101"), "57,101",
      note="includes FHLB advances $13,000mm, senior debt $38,642mm, subordinated debt $3,016mm and other $2,443mm - counted once "
           "as the total; PNC has no separate repo line"),
    F("TFC", "deposits", "Noninterest-bearing deposits", 105092, ("Noninterest-bearing deposits", "105,092"), "105,092"),
    F("TFC", "deposits", "Interest-bearing deposits", 295306,
      ("Interest-bearing deposits (including $639 and $192 at fair value, respectively)", "295,306"), "295,306"),
    F("TFC", "short_term", "Short-term borrowings", 27839,
      ("Short-term borrowings (including $2,394 and $1,896 at fair value, respectively)", "27,839"), "27,839",
      note="includes securities sold under repurchase agreements and short-term FHLB advances (no separate repo line)"),
    F("TFC", "long_term", "Long-term debt", 41963, ("Long-term debt", "41,963"), "41,963"),
    F("MTB", "deposits", "Total deposits", 166909, ("Total deposits", "166,909"), "166,909"),
    F("MTB", "short_term", "Short-term borrowings", 2149, ("Short-term borrowings", "2,149"), "2,149"),
    F("MTB", "long_term", "Long-term borrowings", 10911, ("Long-term borrowings (a)", "10,911"), "10,911"),
    F("FITB", "deposits", "Total deposits", 171819, ("Total deposits", "171,819"), "171,819"),
    F("FITB", "short_term", "Short-term borrowings", 926, ("Short-term borrowings", "926"), "926"),
    F("FITB", "long_term", "Long-term debt", 13589, ("Long-term debt(a)", "13,589"), "13,589"),
    F("KEY", "deposits", "Total deposits", 148713, ("Total deposits", "148,713"), "148,713"),
    F("KEY", "repo", "Federal funds purchased and securities sold under repurchase agreements", 13,
      ("Federal funds purchased and securities sold under repurchase agreements", "13"), "13"),
    F("KEY", "short_term", "Bank notes and other short-term borrowings", 1071,
      ("Bank notes and other short-term borrowings", "1,071"), "1,071"),
    F("KEY", "long_term", "Long-term debt", 9917, ("Long-term debt", "9,917"), "9,917"),
    F("FLG", "deposits", "Total deposits", 66000, ("Total deposits", "66,000"), "66,000"),
    F("FLG", "long_term", "Borrowed funds", 12184, ("Borrowed funds", "12,184"), "12,184",
      note="includes FHLB advances (counted once as the total); no separate repo line"),
]


# ------------------------------------------------------------------ V9: SCB and stated total CET1 requirement
S2 += [
    r("USB", "scb", 2.6, PCT, "Item 1 - Supervision and Regulation (SCB)", ("the SCB applicable to the Company is", "2.6 percent"), "2.6 percent", post=60),
    r("TFC", "scb", 2.5, PCT, "Item 1 - Supervision and Regulation (SCB)", ("The FRB has assigned Truist an SCB of", "2.5%"), "2.5%", post=60),
    r("FITB", "scb", 3.2, PCT, "Item 1 - Supervision and Regulation (SCB)",
      ("stress capital buffer under the FRB severely adverse scenario was", "3.2%"), "3.2%", post=60),
    r("KEY", "scb", 3.2, PCT, "Item 1 - Supervision and Regulation (SCB)", ("updated stress capital buffer is", "3.2%"), "3.2%", post=60),
    r("PNC", "scb", 2.5, PCT, "Item 15 - Parent company capital note", ("regulatory minimum required CET1 ratio of 4.5% plus SCB of", "2.5%"), "2.5%", post=60),
    r("MTB", "scb", 2.7, PCT, "Item 1 - Supervision and Regulation (capital)", ("M&T's SCB of", "2.7%"), "2.7%", post=100),
    r("TFC", "cet1_required_standardized", 7.0, PCT, "MD&A - Table 35 Capital Requirements (Minimum Capital Plus Stress Capital Buffer)",
      ("CET1", "4.5", "NA", "6.5", "7.0"), "7.0", post=30),
    r("KEY", "cet1_required_standardized", 7.7, PCT, "MD&A - Minimum Capital Ratios (including stress capital buffer)",
      ("Common Equity Tier 1", "4.50", "3.20", "7.70"), "7.70", post=30),
]

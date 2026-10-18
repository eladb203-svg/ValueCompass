"""Extraction spec for the BANK test round (FY2025 10-K text).

Each row: bank, item, value, unit, 10-K section, anchor tokens, verify string. ``build_bank_regulatory.py`` finds the
anchor in the converted 10-K text, takes the surrounding text as the exact quote, and checks that the verify string
(the extracted number) occurs inside the quote. Rows that fail verification are reported and not written as verified.

Amounts are USD millions unless the unit says otherwise. Percent values are percentage points.
Items:
  cet1_ratio_standardized / cet1_ratio_advanced   reported CET1 ratios (binding = lower, chosen in code)
  cet1_capital, rwa_standardized, rwa_advanced, total_capital_standardized, total_capital_advanced, total_capital_ratio
  lcr_q4_average                                   LCR, Q4 average ("NA" = not subject / not reported, D9)
  loan:<label>                                     loan line as reported (mapped to 5 categories in code)
  nonaccrual_loans, past_due_90_accruing:<label>   components of NPL
  nco_2025, avg_loans_2025, acl_loans_2025, loans_2025   latest-year credit items where XBRL is missing
  uninsured_deposits                               display only
"""


def r(t, item, value, unit, section, tokens, verify=None, pre=40, post=300, note=""):
    return dict(t=t, item=item, value=value, unit=unit, section=section, tokens=tokens,
                verify=verify if verify is not None else None, pre=pre, post=post, note=note)


MM = "USD mm"
PCT = "%"
S = []

# ------------------------------------------------------------------ JPM
CAP = "MD&A - Capital Risk Management - Selected capital and RWA data"
S += [
    r("JPM", "cet1_ratio_standardized", 14.6, PCT, CAP, ("CET1 capital ratio", "14.6"), "14.6", post=160),
    r("JPM", "cet1_ratio_advanced", 14.1, PCT, CAP, ("CET1 capital ratio", "14.6"), "14.1", post=160,
      note="Advanced is lower and binding; footnote (d) of the selected-data table says Advanced ratios became more binding"),
    r("JPM", "cet1_capital", 288469, MM, CAP, ("CET1 capital", "288,469"), "288,469"),
    r("JPM", "rwa_standardized", 1981692, MM, CAP, ("Risk-weighted assets", "1,981,692"), "1,981,692"),
    r("JPM", "rwa_advanced", 2045249, MM, CAP, ("Risk-weighted assets", "1,981,692"), "2,045,249", post=200),
    r("JPM", "total_capital_standardized", 343843, MM, CAP, ("Total capital", "343,843"), "343,843"),
    r("JPM", "total_capital_advanced", 328962, MM, CAP, ("Total capital", "343,843"), "328,962", post=200),
    r("JPM", "lcr_q4_average", 111, PCT, "MD&A - Selected financial data / Liquidity Risk Management",
      ("Firm Liquidity coverage ratio",), "111", post=120),
    r("JPM", "loan:Residential real estate", 303531, MM, "MD&A - Consumer credit portfolio",
      ("Residential real estate(a)", "303,531"), "303,531"),
    r("JPM", "loan:Auto and other", 65210, MM, "MD&A - Consumer credit portfolio", ("Auto and other(b)(c)", "65,210"), "65,210"),
    r("JPM", "loan:Credit card", 247797, MM, "MD&A - Consumer credit portfolio", ("Loans retained(f)", "247,797"), "247,797"),
    r("JPM", "loan:Wholesale - secured by real estate", 165545, MM, "Note 12 - Loans (wholesale loans by risk rating)",
      ("Total retained loans", "165,545"), "165,545", post=260),
    r("JPM", "loan:Wholesale - commercial and industrial", 174403, MM, "Note 12 - Loans (wholesale loans by risk rating)",
      ("Total retained loans", "165,545"), "174,403", post=260),
    r("JPM", "loan:Wholesale - other", 452419, MM, "Note 12 - Loans (wholesale loans by risk rating)",
      ("Total retained loans", "165,545"), "452,419", post=300),
    r("JPM", "nonaccrual_loans", 9857, MM, "MD&A - Allowance for credit losses / Firmwide nonaccrual loans",
      ("Total nonaccrual loans", "9,857"), "9,857"),
    r("JPM", "past_due_90_accruing:credit card", 2732, MM, "Note 12 - Loans (credit card delinquency)",
      ("90 or more days past due and still accruing", "2,619"), "2,732", post=120),
    r("JPM", "past_due_90_accruing:wholesale", 58, MM, "Note 12 - Loans (wholesale delinquency)",
      ("90 or more days past due and still accruing(b)", "42"), "58", post=200),
    r("JPM", "past_due_90_accruing:government-insured mortgage", 70, MM, "MD&A - Consumer credit portfolio (footnote)",
      ("mortgage loans 90 or more days past due and insured by U.S. government agencies were", "$70 million"), "$70 million"),
    r("JPM", "avg_loans_2025", 1335675, MM, "MD&A - Allowance for credit losses (net charge-off table)",
      ("Average retained loans", "1,335,675"), "1,335,675"),
    r("JPM", "nco_2025", 9849, MM, "MD&A - Allowance for credit losses (net charge-off table)", ("Net charge-offs", "9,849"), "9,849"),
    r("JPM", "uninsured_deposits", 1558600, MM, "MD&A - Liquidity Risk Management - Deposits",
      ("Firmwide estimated uninsured deposits were", "$1,558.6 billion"), "$1,558.6 billion",
      note="reported in USD billions: 1,558.6"),
]

# ------------------------------------------------------------------ BAC
CAP = "MD&A - Table 10 Bank of America Corporation Regulatory Capital under Basel 3"
S += [
    r("BAC", "cet1_ratio_standardized", 11.4, PCT, CAP, ("Common equity tier 1 capital ratio", "11.4"), "11.4", post=120),
    r("BAC", "cet1_ratio_advanced", 12.8, PCT, CAP, ("Common equity tier 1 capital ratio", "11.4"), "12.8", post=120),
    r("BAC", "cet1_capital", 201410, MM, CAP, ("Common equity tier 1 capital", "201,410"), "201,410"),
    r("BAC", "rwa_standardized", 1773000, MM, CAP, ("Risk-weighted assets (in billions)", "1,773"), "1,773",
      note="reported in USD billions: 1,773"),
    r("BAC", "rwa_advanced", 1570000, MM, CAP, ("Risk-weighted assets (in billions)", "1,773"), "1,570",
      note="reported in USD billions: 1,570"),
    r("BAC", "total_capital_standardized", 261232, MM, CAP, ("Total capital (4)", "261,232"), "261,232"),
    r("BAC", "total_capital_advanced", 250347, MM, CAP, ("Total capital (4)", "261,232"), "250,347"),
    r("BAC", "lcr_q4_average", 112, PCT, "MD&A - Liquidity Risk", ("Our average consolidated HQLA",), "112", post=260),
    r("BAC", "loan:Residential mortgage", 236360, MM, "MD&A - Loans maturity table (December 31, 2025)",
      ("Residential mortgage", "6,043"), "236,360"),
    r("BAC", "loan:Home equity", 26930, MM, "MD&A - Loans maturity table", ("Home equity", "574"), "26,930"),
    r("BAC", "loan:Credit card", 106027, MM, "MD&A - Loans maturity table", ("Credit card", "106,027"), "106,027"),
    r("BAC", "loan:Direct/Indirect consumer", 114130, MM, "MD&A - Loans maturity table",
      ("Direct/Indirect consumer", "72,094"), "114,130"),
    r("BAC", "loan:Other consumer", 144, MM, "MD&A - Loans maturity table", ("Other consumer", "144"), "144"),
    r("BAC", "loan:U.S. commercial", 438388, MM, "MD&A - Loans maturity table", ("U.S. commercial", "133,448"), "438,388"),
    r("BAC", "loan:Non-U.S. commercial", 156232, MM, "MD&A - Loans maturity table", ("Non-U.S. commercial", "51,894"), "156,232"),
    r("BAC", "loan:Commercial real estate", 68748, MM, "MD&A - Loans maturity table", ("Commercial real estate", "27,454"), "68,748"),
    r("BAC", "loan:Commercial lease financing", 16241, MM, "MD&A - Loans maturity table", ("Commercial lease financing", "3,970"), "16,241"),
    r("BAC", "loan:U.S. small business commercial", 22500, MM, "MD&A - Loans maturity table",
      ("U.S. small business commercial", "13,067"), "22,500"),
    r("BAC", "uninsured_deposits", 857900, MM, "MD&A - Deposits",
      ("total estimated uninsured U.S. and non-U.S. deposits were",), "$723.0 billion", post=100,
      note="US $723.0bn + non-US $134.9bn = $857.9bn"),
]

# ------------------------------------------------------------------ C
CAP = "MD&A - Capital Resources"
S += [
    r("C", "cet1_ratio_standardized", 13.18, PCT, "MD&A - Citigroup's Capital Resources (capital components and ratios, December 31, 2025)",
      ("CET1 Capital ratio(2)", "13.18"), "13.18", post=140),
    r("C", "cet1_ratio_advanced", 11.93, PCT, "MD&A - Citigroup's Capital Resources (capital components and ratios, December 31, 2025)",
      ("CET1 Capital ratio(2)", "13.18"), "11.93", post=140,
      note="Citi calls the Standardized ratio its binding CET1 ratio (headroom vs. its own requirement); the lower of the two ratios (Advanced) is used per the spec. Citi requirements: Standardized 11.6%, Advanced 10.5%"),
    r("C", "cet1_capital", 157099, MM, "MD&A - Citigroup's Capital Resources", ("CET1 Capital(1)", "157,099"), "157,099"),
    r("C", "rwa_standardized", 1192174, MM, "MD&A - Citigroup's Capital Resources", ("Total Risk-Weighted Assets", "1,192,174"), "1,192,174"),
    r("C", "rwa_advanced", 1316371, MM, "MD&A - Citigroup's Capital Resources", ("Total Risk-Weighted Assets", "1,192,174"), "1,316,371", post=160),
    r("C", "total_capital_standardized", 216468, MM, "MD&A - Citigroup's Capital Resources",
      ("Total Capital (Tier 1 Capital + Tier 2 Capital)(1)", "216,468"), "216,468"),
    r("C", "total_capital_advanced", 206170, MM, "MD&A - Citigroup's Capital Resources",
      ("Total Capital (Tier 1 Capital + Tier 2 Capital)(1)", "216,468"), "206,170", post=160),
    r("C", "lcr_q4_average", 115, PCT, "MD&A - Liquidity - LCR table", ("LCR", "115"), "115", post=100),
    r("C", "loan:Wealth - mortgages", 86400, MM, "MD&A - Consumer loans (4Q25, USD bn)", ("Mortgages(4)", "89.0"), "86.4", note="reported in USD billions"),
    r("C", "loan:Wealth - margin lending", 33400, MM, "MD&A - Consumer loans (4Q25, USD bn)", ("Margin lending", "29.4"), "33.4", note="USD bn"),
    r("C", "loan:Wealth - personal, small business and other", 25300, MM, "MD&A - Consumer loans (4Q25, USD bn)",
      ("Personal, small business and other", "24.1"), "25.3", note="USD bn"),
    r("C", "loan:Wealth - cards", 4900, MM, "MD&A - Consumer loans (4Q25, USD bn)", ("Cards", "5.0"), "4.9", note="USD bn"),
    r("C", "loan:USPB - Branded Cards", 125300, MM, "MD&A - Consumer loans (4Q25, USD bn)", ("Branded Cards(5)", "121.1"), "125.3", note="USD bn"),
    r("C", "loan:USPB - Retail Services", 52200, MM, "MD&A - Consumer loans (4Q25, USD bn)", ("Retail Services", "53.8"), "52.2", note="USD bn"),
    r("C", "loan:USPB - Retail Banking mortgages", 53100, MM, "MD&A - Consumer loans (4Q25, USD bn)", ("Mortgages", "45.5"), "53.1", note="USD bn"),
    r("C", "loan:USPB - Retail Banking personal, small business and other", 1200, MM, "MD&A - Consumer loans (4Q25, USD bn)",
      ("Personal, small business and other", "1.3"), "1.2", note="USD bn"),
    r("C", "loan:Mexico Consumer", 22500, MM, "MD&A - Consumer loans (4Q25, USD bn)", ("Mexico Consumer", "17.2"), "22.5", note="USD bn"),
    r("C", "loan:Asia Consumer", 2500, MM, "MD&A - Consumer loans (4Q25, USD bn)", ("Asia Consumer(6)", "4.7"), "2.5", note="USD bn"),
    r("C", "loan:Legacy Holdings Assets (consumer)", 1700, MM, "MD&A - Consumer loans (4Q25, USD bn)",
      ("Legacy Holdings Assets(7)", "2.0"), "1.7", note="USD bn"),
    r("C", "loan:Corporate N.A. - commercial and industrial", 57406, MM, "Note 14 - Loans (corporate loans, December 31, 2025)",
      ("Commercial and industrial", "57,406"), "57,406"),
    r("C", "loan:Corporate N.A. - financial institutions", 72154, MM, "Note 14 - Loans", ("Financial institutions", "72,154"), "72,154"),
    r("C", "loan:Corporate N.A. - mortgage and real estate", 17931, MM, "Note 14 - Loans", ("Mortgage and real estate(2)", "17,931"), "17,931"),
    r("C", "loan:Corporate N.A. - installment and other", 23104, MM, "Note 14 - Loans", ("Installment and other(4)", "23,104"), "23,104"),
    r("C", "loan:Corporate N.A. - lease financing", 72, MM, "Note 14 - Loans", ("Lease financing", "72"), "72"),
    r("C", "loan:Corporate intl - commercial and industrial", 96886, MM, "Note 14 - Loans", ("Commercial and industrial", "96,886"), "96,886"),
    r("C", "loan:Corporate intl - financial institutions", 27054, MM, "Note 14 - Loans", ("Financial institutions", "27,054"), "27,054"),
    r("C", "loan:Corporate intl - mortgage and real estate", 9856, MM, "Note 14 - Loans", ("Mortgage and real estate(2)", "9,856"), "9,856"),
    r("C", "loan:Corporate intl - installment and other", 34100, MM, "Note 14 - Loans", ("Installment and other(4)", "34,100"), "34,100"),
    r("C", "loan:Corporate intl - lease financing", 47, MM, "Note 14 - Loans", ("Lease financing", "47"), "47"),
    r("C", "loan:Corporate - governments and official institutions", 5070, MM, "Note 14 - Loans",
      ("Governments and official institutions", "5,070"), "5,070"),
    r("C", "nonaccrual_loans", 3619, MM, "MD&A - Credit Risk - Non-Accrual Loans", ("Total non-accrual loans", "3,619"), "3,619"),
    r("C", "past_due_90_accruing:consumer", 2760, MM, "Note 14 - Consumer loans delinquencies and non-accrual status (December 31, 2025)",
      ("Total excluding portfolio-layer hedges cumulative basis adjustments", "401,095"), "2,760", post=260,
      note="consumer only (cards 90+ days accruing); corporate loans 90+ days accruing not shown as a total"),
    r("C", "uninsured_deposits", 1110000, MM, "Supervision and Regulation / Deposits",
      ("Total uninsured deposits as of December 31, 2025 were",), "$1.11 trillion", post=60, note="USD 1.11 trillion"),
]

# ------------------------------------------------------------------ WFC
CAP = "MD&A - Capital Management - Table 35: Capital Components and Ratios"
S += [
    r("WFC", "cet1_ratio_standardized", 10.61, PCT, CAP, ("Common Equity Tier 1 capital ratio", "(A)/(D)"), "10.61", post=140,
      note="Standardized is the binding framework (asterisk) at December 31, 2025"),
    r("WFC", "cet1_ratio_advanced", 12.35, PCT, CAP, ("Common Equity Tier 1 capital ratio", "(A)/(D)"), "12.35", post=140),
    r("WFC", "cet1_capital", 137346, MM, CAP, ("Common Equity Tier 1", "(A)"), "137,346"),
    r("WFC", "rwa_standardized", 1294609, MM, CAP, ("Risk-weighted assets", "(D)"), "1,294,609"),
    r("WFC", "rwa_advanced", 1112533, MM, CAP, ("Risk-weighted assets", "(D)"), "1,112,533", post=200),
    r("WFC", "total_capital_standardized", 184682, MM, CAP, ("Total capital", "(C)"), "184,682"),
    r("WFC", "total_capital_advanced", 174617, MM, CAP, ("Total capital", "(C)"), "174,617", post=200),
    r("WFC", "lcr_q4_average", 119, PCT, "MD&A - Financial Summary / Table 1",
      ("Liquidity Coverage Ratio (LCR) (7)",), "119", post=60),
    r("WFC", "loan:Commercial and industrial", 452068, MM, "MD&A - Loans maturity table",
      ("Commercial and industrial", "162,370"), "452,068", post=160),
    r("WFC", "loan:Commercial real estate", 132284, MM, "MD&A - Loans maturity table", ("Commercial real estate", "59,616"), "132,284"),
    r("WFC", "loan:Lease financing", 15543, MM, "MD&A - Loans maturity table", ("Lease financing", "3,332"), "15,543"),
    r("WFC", "loan:Residential mortgage", 242190, MM, "MD&A - Loans maturity table", ("Residential mortgage", "9,790"), "242,190"),
    r("WFC", "loan:Credit card", 59540, MM, "MD&A - Loans maturity table", ("Credit card", "59,540"), "59,540"),
    r("WFC", "loan:Auto", 50487, MM, "MD&A - Loans maturity table", ("Auto", "12,283"), "50,487"),
    r("WFC", "loan:Other consumer", 34055, MM, "MD&A - Loans maturity table", ("Other consumer", "27,951"), "34,055"),
    r("WFC", "loans_2025", 986167, MM, "MD&A - Loans maturity table", ("Total loans", "334,882"), "986,167"),
    r("WFC", "avg_loans_2025", 927491, MM, "MD&A - Average balances and interest rates", ("Total loans", "927,491"), "927,491"),
    r("WFC", "nonaccrual_loans", 8201, MM, "MD&A - Risk Management - Credit Risk", ("Total nonaccrual loans", "8,201"), "8,201"),
    r("WFC", "past_due_90_accruing:total", 3000, MM, "Note 3 - Table 3.14 Loans 90 Days or More Past Due and Still Accruing",
      ("Table 3.14: Loans 90 Days or More Past Due and Still Accruing",), "3,000", post=300,
      note="includes $1,688mm government insured/guaranteed (not government insured: $1,312mm)"),
    r("WFC", "acl_loans_2025", 14337, MM, "Note 3 - Allowance for credit losses", ("Net loan charge-offs", "(3,994)"), "14,337", post=140),
    r("WFC", "nco_2025", 3994, MM, "Note 3 - Allowance for credit losses", ("Net loan charge-offs", "(3,994)"), "3,994"),
    r("WFC", "uninsured_deposits", 600000, MM, "MD&A - Deposits",
      ("total deposits that exceed FDIC insurance limits, or are otherwise uninsured, were estimated to be",), "$600 billion", post=80),
]

# ------------------------------------------------------------------ USB
CAP = "Annual Report - Capital Management / Regulatory capital"
S += [
    r("USB", "cet1_ratio_standardized", 10.8, PCT, CAP, ("Common equity tier 1 capital as a percent of risk-weighted assets", "10.8"), "10.8"),
    r("USB", "cet1_capital", 51665, MM, CAP, ("Common equity tier 1 capital", "51,665"), "51,665"),
    r("USB", "rwa_standardized", 480382, MM, CAP, ("Risk-weighted assets", "480,382"), "480,382"),
    r("USB", "total_capital_standardized", 68087, MM, CAP, ("Total risk-based capital", "68,087"), "68,087"),
    r("USB", "lcr_q4_average", 106.5, PCT, "Annual Report - Liquidity (LCR)", ("average daily LCR was", "106.5 percent"), "106.5 percent", post=120),
    r("USB", "loan:Commercial", 149522, MM, "Annual Report - Table 6 Loan Portfolio Distribution", ("Commercial", "149,522"), "149,522"),
    r("USB", "loan:Lease financing", 4436, MM, "Annual Report - Table 6", ("Lease financing", "4,436"), "4,436"),
    r("USB", "loan:Total commercial real estate", 48920, MM, "Annual Report - Table 6", ("Total commercial real estate", "48,920"), "48,920"),
    r("USB", "loan:Total residential mortgages", 115885, MM, "Annual Report - Table 6", ("Total residential mortgages", "115,885"), "115,885"),
    r("USB", "loan:Credit Card", 32234, MM, "Annual Report - Table 6", ("Credit Card", "32,234"), "32,234"),
    r("USB", "loan:Total other retail", 40338, MM, "Annual Report - Table 6", ("Total other retail", "40,338"), "40,338"),
    r("USB", "nonaccrual_loans", 1547, MM, "Annual Report - Table 11 Nonperforming Assets", ("Total nonperforming loans(1)", "1,547"), "1,547"),
    r("USB", "past_due_90_accruing:total", 853, MM, "Annual Report - Table 11", ("Accruing loans 90 days or more past due(b)", "853"), "853"),
]

# ------------------------------------------------------------------ PNC
CAP = "MD&A - Liquidity and Capital Management / Table - Basel III capital"
S += [
    r("PNC", "cet1_ratio_standardized", 10.6, PCT, CAP, ("Basel III risk-based capital and leverage ratios (d)", "Common equity tier 1", "10.6"), "10.6", post=120),
    r("PNC", "cet1_capital", 47259, MM, CAP, ("Common equity tier 1 capital (a)", "47,259"), "47,259"),
    r("PNC", "preferred_stock_2025", 5757, MM, CAP, ("Preferred stock plus related surplus", "5,757"), "5,757",
      note="PNC's XBRL PreferredStockValue is 0 (par value); preferred stock incl. surplus used for TCE in FY2025 only"),
    r("PNC", "rwa_standardized", 444438, MM, CAP, ("Basel III standardized approach risk-weighted assets (b)", "444,438"), "444,438"),
    r("PNC", "total_capital_standardized", 60032, MM, CAP, ("Total Basel III capital", "60,032"), "60,032"),
    r("PNC", "lcr_q4_average", "NA", PCT, "MD&A - Liquidity and Capital Management",
      ("PNC and PNC Bank calculate the LCR daily",), "required to maintain a regulatory minimum of 100%", post=240,
      note="PNC discloses only that the LCR exceeded the 100% minimum; no numeric LCR in the 10-K -> not reported (D9)"),
    r("PNC", "loan:Commercial and industrial", 195723, MM, "MD&A - Table 8: Loans", ("Commercial and industrial", "195,723"), "195,723"),
    r("PNC", "loan:Commercial real estate", 29565, MM, "MD&A - Table 8: Loans", ("Commercial real estate", "29,565"), "29,565"),
    r("PNC", "loan:Equipment lease financing", 7175, MM, "MD&A - Table 8: Loans", ("Equipment lease financing", "7,175"), "7,175"),
    r("PNC", "loan:Residential real estate", 43760, MM, "MD&A - Table 8: Loans", ("Residential real estate", "43,760"), "43,760"),
    r("PNC", "loan:Home equity", 25941, MM, "MD&A - Table 8: Loans", ("Home equity", "25,941"), "25,941"),
    r("PNC", "loan:Automobile", 16591, MM, "MD&A - Table 8: Loans", ("Automobile", "16,591"), "16,591"),
    r("PNC", "loan:Credit card", 7014, MM, "MD&A - Table 8: Loans", ("Credit card", "7,014"), "7,014"),
    r("PNC", "loan:Education", 1468, MM, "MD&A - Table 8: Loans", ("Education", "1,468"), "1,468"),
    r("PNC", "loan:Other consumer", 4244, MM, "MD&A - Table 8: Loans", ("Other consumer", "4,244"), "4,244"),
    r("PNC", "nonaccrual_loans", 2218, MM, "MD&A - Credit Risk Management - Nonperforming assets", ("Total nonperforming loans", "2,218"), "2,218"),
    r("PNC", "past_due_90_accruing:total", 380, MM, "MD&A - Loan Delinquencies", ("Accruing loans past due 90 days or more", "380"), "380"),
    r("PNC", "uninsured_deposits", 209300, MM, "MD&A - Deposits",
      ("The aggregate amount of uninsured deposits",), "$209.3 billion", post=240),
]

# ------------------------------------------------------------------ TFC
CAP = "MD&A - Capital / Note - Regulatory capital"
S += [
    r("TFC", "cet1_ratio_standardized", 10.8, PCT, "MD&A - Table 37: Capital Ratios - Truist Financial Corporation",
      ("Table 37: Capital Ratios - Truist Financial Corporation",), "10.8", post=220),
    r("TFC", "cet1_capital", 48027, MM, "Note - Regulatory capital (Truist Financial Corporation)", ("CET1(1)", "4.5"), "48,027", post=140),
    r("TFC", "rwa_standardized", 443257, MM, "MD&A - Table 37", ("Table 37: Capital Ratios - Truist Financial Corporation",), "443,257", post=520),
    r("TFC", "total_capital_standardized", 61255, MM, "Note - Regulatory capital (Truist Financial Corporation)", ("Total capital(1)", "8.0"), "61,255", post=140),
    r("TFC", "lcr_q4_average", 111, PCT, "MD&A - Liquidity", ("average consolidated LCR was 111%",), "111%", pre=60, post=100),
    r("TFC", "loan:Commercial and industrial", 167808, MM, "MD&A - Table 13: Loans and Leases as of Period End", ("Commercial and industrial", "167,808"), "167,808"),
    r("TFC", "loan:CRE", 23720, MM, "MD&A - Table 13", ("CRE", "23,720"), "23,720"),
    r("TFC", "loan:Commercial construction", 7783, MM, "MD&A - Table 13", ("Commercial construction", "7,783"), "7,783"),
    r("TFC", "loan:Residential mortgage", 56807, MM, "MD&A - Table 13", ("Residential mortgage", "56,807"), "56,807"),
    r("TFC", "loan:Home equity", 9719, MM, "MD&A - Table 13", ("Home equity", "9,719"), "9,719"),
    r("TFC", "loan:Indirect auto", 25659, MM, "MD&A - Table 13", ("Indirect auto", "25,659"), "25,659"),
    r("TFC", "loan:Other consumer", 32181, MM, "MD&A - Table 13", ("Other consumer", "32,181"), "32,181"),
    r("TFC", "loan:Credit card", 4918, MM, "MD&A - Table 13", ("Credit card", "4,918"), "4,918"),
    r("TFC", "nonaccrual_loans", 1577, MM, "MD&A - Nonperforming assets", ("Total nonperforming loans and leases", "1,577"), "1,577"),
    r("TFC", "past_due_90_accruing:total", 684, MM, "MD&A - Nonperforming assets",
      ("Total loans 90 days or more past due and still accruing", "684"), "684",
      note="includes government-guaranteed residential mortgage loans"),
    r("TFC", "nco_2025", 1705, MM, "Note 5 - Allowance rollforward", ("Net charge-offs", "(1,705)"), "(1,705)"),
]

# ------------------------------------------------------------------ MTB
CAP = "Note 22 - Regulatory capital (capital ratios and amounts as of December 31, 2025)"
S += [
    r("MTB", "cet1_ratio_standardized", 10.84, PCT, CAP, ("CET1 capital", "Amount", "17,551"), "10.84", post=140),
    r("MTB", "cet1_capital", 17551, MM, CAP, ("CET1 capital", "Amount", "17,551"), "17,551"),
    r("MTB", "rwa_standardized", 161892, MM, CAP, ("RWA", "161,892"), "161,892"),
    r("MTB", "total_capital_standardized", 23371, MM, CAP, ("Total capital", "Amount", "23,371"), "23,371"),
    r("MTB", "lcr_q4_average", "NA", PCT, "MD&A - Liquidity", ("M&T is not subject to the LCR",), "M&T is not subject to the LCR", post=240,
      note="M&T is not subject to the LCR (voluntary estimate 109%) -> not applicable (D9)"),
    r("MTB", "loan:Commercial and industrial", 63548, MM, "MD&A - Table 9 Loans", ("Commercial and industrial", "63,548"), "63,548"),
    r("MTB", "loan:Real estate - commercial", 23819, MM, "MD&A - Table 9 Loans", ("Real estate - commercial", "23,819"), "23,819"),
    r("MTB", "loan:Real estate - residential", 24874, MM, "MD&A - Table 9 Loans", ("Real estate - residential", "24,874"), "24,874"),
    r("MTB", "loan:Home equity lines and loans", 4807, MM, "MD&A - Table 9 Loans", ("Home equity lines and loans", "4,807"), "4,807"),
    r("MTB", "loan:Recreational finance", 14092, MM, "MD&A - Table 9 Loans", ("Recreational finance", "14,092"), "14,092"),
    r("MTB", "loan:Automobile", 5167, MM, "MD&A - Table 9 Loans", ("Automobile", "5,167"), "5,167"),
    r("MTB", "loan:Other secured", 810, MM, "MD&A - Table 9 Loans", ("Other secured", "810"), "810"),
    r("MTB", "loan:Other unsecured", 1585, MM, "MD&A - Table 9 Loans", ("Other unsecured", "1,585"), "1,585"),
    r("MTB", "past_due_90_accruing:total", 561, MM, "MD&A - Table - Nonperforming assets",
      ("Accruing loans past due 90 days or more (a)", "561"), "561", note="predominantly government-guaranteed ($543mm)"),
    r("MTB", "uninsured_deposits", 78900, MM, "MD&A - Liquidity", ("Total uninsured deposits were estimated to be",), "$78.9 billion", post=100),
]

# ------------------------------------------------------------------ FITB
CAP = "Regulatory capital table (Fifth Third Bancorp)"
S += [
    r("FITB", "cet1_ratio_standardized", 10.81, PCT, CAP, ("Fifth Third Bancorp", "10.81"), "10.81", post=120),
    r("FITB", "cet1_capital", 18099, MM, CAP, ("Fifth Third Bancorp", "10.81"), "18,099", post=120),
    r("FITB", "rwa_standardized", 167431, MM, CAP, ("Total risk-weighted assets:",), "167,431", post=160),
    r("FITB", "total_capital_standardized", 23066, MM, CAP, ("Total risk-based capital:",), "23,066", post=120),
    r("FITB", "lcr_q4_average", "NA", PCT, "Item 1 - Supervision and Regulation", ("calibrated liquidity coverage ratio and net stable funding ratio requirements",),
      "calibrated liquidity coverage ratio", pre=300, post=120,
      note="Category IV: LCR requirement not applicable / no LCR disclosed in the 10-K -> not applicable (D9)"),
    r("FITB", "loan:Commercial and industrial loans", 52749, MM, "MD&A - Table 53 portfolio loans and leases", ("Commercial and industrial loans", "52,749"), "52,749"),
    r("FITB", "loan:Commercial mortgage loans", 12228, MM, "MD&A - Table 53", ("Commercial mortgage loans", "12,228"), "12,228"),
    r("FITB", "loan:Commercial construction loans", 5316, MM, "MD&A - Table 53", ("Commercial construction loans", "5,316"), "5,316"),
    r("FITB", "loan:Commercial leases", 3269, MM, "MD&A - Table 53", ("Commercial leases", "3,269"), "3,269"),
    r("FITB", "loan:Residential mortgage loans", 17652, MM, "MD&A - Table 53", ("Residential mortgage loans(a)", "17,652"), "17,652"),
    r("FITB", "loan:Home equity", 4846, MM, "MD&A - Table 53", ("Home equity", "4,846"), "4,846"),
    r("FITB", "loan:Indirect secured consumer loans", 17964, MM, "MD&A - Table 53", ("Indirect secured consumer loans", "17,964"), "17,964"),
    r("FITB", "loan:Credit card", 1747, MM, "MD&A - Table 53", ("Credit card", "1,747"), "1,747"),
    r("FITB", "loan:Solar energy installation loans", 4560, MM, "MD&A - Table 53", ("Solar energy installation loans", "4,560"), "4,560"),
    r("FITB", "loan:Other consumer loans", 2320, MM, "MD&A - Table 53", ("Other consumer loans", "2,320"), "2,320"),
    r("FITB", "past_due_90_accruing:total", 30, MM, "MD&A - Nonperforming assets table",
      ("Total portfolio loans and leases 90 days past due and still accruing", "30"), "30", post=40),
]

# ------------------------------------------------------------------ KEY
CAP = "MD&A - Figure 22. Capital Components and Risk-Weighted Assets"
S += [
    r("KEY", "cet1_ratio_standardized", 11.78, PCT, CAP, ("Common Equity Tier 1", "11.78"), "11.78", post=60),
    r("KEY", "cet1_capital", 17195, MM, CAP, ("Total Common Equity Tier 1 capital", "17,195"), "17,195"),
    r("KEY", "rwa_standardized", 145933, MM, CAP, ("RISK-WEIGHTED ASSETS (a)",), "145,933", post=80),
    r("KEY", "total_capital_standardized", 22910, MM, CAP, ("Total risk-based capital", "22,910"), "22,910"),
    r("KEY", "lcr_q4_average", "NA", PCT, "Item 1 - Supervision and Regulation (liquidity)",
      ("KeyCorp and KeyBank are not subject to an LCR requirement",), "not subject to an LCR requirement", post=200,
      note="Category IV: not subject to the LCR -> not applicable (D9)"),
    r("KEY", "loan:Commercial and industrial", 57688, MM, "MD&A - Loans maturity table", ("Commercial and industrial", "14,655"), "57,688"),
    r("KEY", "loan:Commercial mortgage", 13707, MM, "MD&A - Loans maturity table", ("Commercial mortgage", "5,227"), "13,707"),
    r("KEY", "loan:Real estate - construction", 2844, MM, "MD&A - Loans maturity table", ("Real estate — construction", "1,285"), "2,844"),
    r("KEY", "loan:Commercial lease financing", 2270, MM, "MD&A - Loans maturity table", ("Commercial lease financing", "191"), "2,270"),
    r("KEY", "loan:Real estate - residential mortgage", 18732, MM, "MD&A - Loans maturity table", ("Real estate - residential mortgage", "167"), "18,732"),
    r("KEY", "loan:Home equity loans", 5703, MM, "MD&A - Loans maturity table", ("Home equity loans", "103"), "5,703"),
    r("KEY", "loan:Other consumer loans", 4644, MM, "MD&A - Loans maturity table", ("Other consumer loans", "569"), "4,644"),
    r("KEY", "loan:Credit Cards", 953, MM, "MD&A - Loans maturity table", ("Credit Cards", "953"), "953"),
    r("KEY", "nonaccrual_loans", 615, MM, "MD&A - Nonperforming assets", ("Total nonperforming loans", "615"), "615"),
    r("KEY", "past_due_90_accruing:total", 99, MM, "MD&A - Nonperforming assets", ("Accruing loans past due 90 days or more", "99"), "99"),
    r("KEY", "uninsured_deposits", 66200, MM, "MD&A - Liquidity", ("Uninsured deposits totaled",), "$66.2 billion", post=80),
]

# ------------------------------------------------------------------ FLG
CAP = "Item 1 / Note - Regulatory capital"
S += [
    r("FLG", "cet1_ratio_standardized", 12.83, PCT, "Item 1 - Supervision and Regulation (capital schedule)",
      ("Common Equity Tier 1", "4.50%"), "12.83%", post=160),
    r("FLG", "cet1_capital", 7845, MM, "Note - Regulatory capital", ("Actual capital", "7,845"), "7,845", post=100),
    r("FLG", "total_capital_standardized", 9921, MM, "Note - Regulatory capital", ("Actual capital", "7,845"), "9,921", post=260),
    r("FLG", "lcr_q4_average", "NA", PCT, "10-K text search",
      ("liquidity",), "liquidity", post=0,
      note="No mention of the liquidity coverage ratio anywhere in the 10-K text -> not reported (D9)"),
    r("FLG", "loan:Multi-family", 28983, MM, "MD&A - Loans and Leases composition", ("Multi-family", "28,983"), "28,983"),
    r("FLG", "loan:Commercial real estate", 9314, MM, "MD&A - Loans and Leases composition", ("Commercial real estate(1)", "9,314"), "9,314"),
    r("FLG", "loan:One-to-four family first mortgage", 5630, MM, "MD&A - Loans and Leases composition", ("One-to-four family first mortgage", "5,630"), "5,630"),
    r("FLG", "loan:Commercial and industrial", 15217, MM, "MD&A - Loans and Leases composition", ("Commercial and industrial", "15,217"), "15,217"),
    r("FLG", "loan:Other loans", 1588, MM, "MD&A - Loans and Leases composition", ("Other loans", "1,588"), "1,588"),
]

# ------------------------------------------------------------------ GS
CAP = "MD&A - Capital Management / Risk-Based Capital"
S += [
    r("GS", "cet1_ratio_standardized", 14.3, PCT, "MD&A - Executive Overview",
      ("our CET1 capital ratio was 14.3% under the Standardized Capital Rules",), "14.3%", post=120),
    r("GS", "cet1_ratio_advanced", 15.1, PCT, "MD&A - Executive Overview",
      ("our CET1 capital ratio was 14.3% under the Standardized Capital Rules",), "15.1%", post=120),
    r("GS", "cet1_capital", 104297, MM, CAP, ("CET1 capital", "104,297"), "104,297"),
    r("GS", "rwa_standardized", 727338, MM, "MD&A - RWAs table (December 2025)", ("Total RWAs", "727,338"), "727,338"),
    r("GS", "rwa_advanced", 691470, MM, "MD&A - RWAs table (December 2025)", ("Total RWAs", "727,338"), "691,470"),
    r("GS", "total_capital_standardized", 130665, MM, CAP, ("Standardized Total capital", "130,665"), "130,665"),
    r("GS", "total_capital_advanced", 128470, MM, "MD&A - changes in capital", ("Total capital", "128,470"), "128,470", pre=120),
    r("GS", "lcr_q4_average", 123, PCT, "MD&A - Liquidity Risk Management - average daily LCR",
      ("Net cash outflows", "322,793"), "123", post=120),
    r("GS", "loan:Corporate", 30676, MM, "Note 9 - Loans receivable (December 2025)", ("Corporate", "30,676"), "30,676"),
    r("GS", "loan:Commercial real estate", 37409, MM, "Note 9 - Loans receivable", ("Commercial real estate", "37,409"), "37,409"),
    r("GS", "loan:Residential real estate", 31957, MM, "Note 9 - Loans receivable", ("Residential real estate", "31,957"), "31,957"),
    r("GS", "loan:Securities-based", 18079, MM, "Note 9 - Loans receivable", ("Securities-based", "18,079"), "18,079", post=120),
    r("GS", "loan:Other collateralized", 98999, MM, "Note 9 - Loans receivable", ("Other collateralized", "98,999"), "98,999", post=120),
    r("GS", "loan:Credit cards", 19742, MM, "Note 9 - Loans receivable", ("Credit cards", "19,742"), "19,742"),
    r("GS", "loan:Other", 3020, MM, "Note 9 - Loans receivable", ("Other", "3,020"), "3,020"),
    r("GS", "nonaccrual_loans", 3387, MM, "Note 9 - Nonaccrual loans accounted for at amortized cost",
      ("The table below presents information about nonaccrual loans accounted for at amortized cost.",), "3,387", post=520),
]

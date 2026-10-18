"""Extraction spec, pricing round 2 (2026-10-14; rules 2026-10-14_22-35): OE components, debt maturities and facilities, reported EBITDAre, balance-sheet classification for RP2a, noncontrolling
interests / operating-partnership units for RP2b. Same row machinery as ``realestate_extraction_spec`` (exact quote, source document, section, verification).

Item names read by src/scoring/realestate.py:
  straight_line_x (USD; positive = GAAP rent above cash rent, i.e. deducted from FFO), maintenance_capex_q / ti_lc_income_preserving_q (quarter rows 'FY2024Q3', summed to the fiscal year by the loader),
  mat_year1_x__* / mat_year2_x__* (debt maturing in the next 12 / second 12 months, components summed), committed_undrawn_facilities, ebitdare_reported,
  bsa_<class>__<slug> (FY2025 asset lines; class: noi | carry | carryfin | inre | wc | excl | other), nci_op_units, nci_op_book__*, diluted_includes_op.
"""
from realestate_extraction_spec import FR, USD, A, L, R, X, Z

_D = r"(\(?[\d,]+(?:\.\d+)?(?: ?\))?%?|—|�)"  # number with optional decimals / parentheses / percent


def _gr(k):
    return " ".join([_D] * k)


ROWS_P2 = []
CAP = "Item 8 - consolidated balance sheet"

# ================================================================== (a) OE components
# O: straight-line rent and expenses, net (AFFO reconciliation; negative in the table = GAAP rent above cash rent -> positive adjustment)
ROWS_P2 += [
    X("O", "straight_line_x", 2021, r"Straight-line rent and expenses " + _gr(1), ["FY2021"], USD, "Item 7 MD&A - AFFO reconciliation", -1e3, note="AFFO reconciliation line; sign reversed (deduction in the table = positive adjustment)"),
    X("O", "straight_line_x", 2023, r"Straight-line rent and expenses, net " + _gr(2), ["FY2023", "FY2022"], USD, "Item 7 MD&A - AFFO reconciliation", -1e3, note="AFFO reconciliation line; sign reversed"),
    X("O", "straight_line_x", 2025, r"Straight-line rent and expenses, net " + _gr(2), ["FY2025", "FY2024"], USD, "Item 7 MD&A - AFFO reconciliation", -1e3, note="AFFO reconciliation line; sign reversed"),
]

# BXP: BXP's share of 2nd generation TI/LC and of maintenance capital expenditures, quarterly columns of the FAD table of the supplemental (current quarter, prior quarter)
_BXP_RX = (r"2nd generation tenant improvements and leasing commissions \d(?:, ?\d)? (\d[\d,]*) (\d[\d,]*) BXP.{1,3}s Share of maintenance capital expenditures \d(?:, ?\d)? (\d[\d,]*) (\d[\d,]*)")
_BXP_NOTE = "BXP's share (incl. unconsolidated JVs, net of partners' share), FAD table of the supplemental, quarter column; the loader sums four quarters"
for _tag, _fy, _q1, _q2, _frag in [("SUP2025", "FY2025", "Q4", "Q3", "q42025supplemental"), ("SUP2025Q2", "FY2025", "Q2", "Q1", "q22025supplemental"),
                                  ("SUP2024Q4", "FY2024", "Q4", "Q3", "q42024supplemental"), ("SUP2024Q2", "FY2024", "Q2", "Q1", "q22024supplemental"),
                                  ("SUP2023Q4", "FY2023", "Q4", "Q3", "q42023supplemental"), ("SUP2023Q2", "FY2023", "Q2", "Q1", "q22023supplemental"),
                                  ("SUP2022Q4", "FY2022", "Q4", "Q3", "q42022supplemental"), ("SUP2022Q2", "FY2022", "Q2", "Q1", "q22022supplemental"),
                                  ("SUP2021Q4", "FY2021", "Q4", "Q3", "q42021supplemental"), ("SUP2021Q2", "FY2021", "Q2", "Q1", "q22021supplemental")]:
    _f = f"{_tag}:{_frag}"
    ROWS_P2 += [
        X("BXP", "ti_lc_income_preserving_q", _f, _BXP_RX, [f"{_fy}{_q1}", f"{_fy}{_q2}", None, None], USD, "Supplemental - Funds Available for Distribution: 2nd generation TI and leasing commissions", 1e3, note=_BXP_NOTE),
        X("BXP", "maintenance_capex_q", _f, _BXP_RX, [None, None, f"{_fy}{_q1}", f"{_fy}{_q2}"], USD, "Supplemental - Funds Available for Distribution: maintenance capital expenditures", 1e3, note=_BXP_NOTE),
    ]

# EQIX: the AFFO reconciliation has no lessor straight-line revenue line (only "Straight-line rent expense adjustment", the lessee side)
ROWS_P2 += [
    A("EQIX", "straight_line_x", "FY2025", 2025, "Item 7 MD&A - AFFO reconciliation", r"Straight-line rent (revenue )?adjustment|Straight-line revenue",
      "10-K FY2025 full text: the AFFO reconciliation lists installation revenue adjustment and straight-line rent EXPENSE adjustment only; no lessor straight-line revenue adjustment"),
]

# AMT: AFFO deductions "Capital improvement capital expenditures" + "Corporate capital expenditures" (recurring / sustaining capex)
_AMT_CAPEX = rf"Capital improvement capital expenditures {_gr(3)} Corporate capital expenditures {_gr(3)}"
for _filing, _years in [(2025, ("FY2025", "FY2024")), (2023, ("FY2023", "FY2022")), (2021, ("FY2021", "FY2020"))]:
    for _i, _y in enumerate(_years):
        if _y == "FY2020":
            continue
        ROWS_P2.append(X("AMT", "maintenance_capex", _filing, _AMT_CAPEX, [_y], USD, "Item 7 MD&A - AFFO reconciliation: capital improvement + corporate capital expenditures", -1e6, agg=(_y, [_i, 3 + _i]),
                         note="sum of the two AFFO capex deductions (towers: sustaining capex; no separate TI/LC line); USD million x 1e6, sign reversed"))

# EQR FY2025: recurring capital expenditures (company's relabelled measure in the Q4 2025 earnings release; FY2021-FY2024 rows = building improvements + replacements)
ROWS_P2.append(R("EQR", "maintenance_capex", "FY2025", "SUP2025:eqr-ex99_1", 193831e3, USD, "Q4 2025 earnings release - Residential Capital Expenditures to Real Estate (Recurring Capital Expenditures)",
                 ("Recurring Capital Expenditures", "168,828", "25,003", "193,831"), "193,831", pre=60, post=60,
                 note="total consolidated 'Recurring Capital Expenditures' (earnings release); FY2021-FY2024 rows are building improvements + replacements (same intent)"))

# ================================================================== (b) debt maturing (next 12 / second 12 months) and committed facilities
SEC = "Item 7 - contractual obligations / debt maturity table"
ROWS_P2 += [
    # O (USD million; columns 2026, 2027)
    L("O", "mat_year1_x__credit_facilities", "FY2025", 2025, r"each of our obligations as of December 31, 2025 \(in millions\)", r"Credit Facilities \(1\)", 0, 1e6, section=SEC, note="2026 column"),
    L("O", "mat_year2_x__credit_facilities", "FY2025", 2025, r"each of our obligations as of December 31, 2025 \(in millions\)", r"Credit Facilities \(1\)", 1, 1e6, section=SEC, note="2027 column"),
    L("O", "mat_year1_x__commercial_paper", "FY2025", 2025, r"each of our obligations as of December 31, 2025 \(in millions\)", r"Commercial Paper \(2\)", 0, 1e6, section=SEC, note="2026 column"),
    L("O", "mat_year1_x__term_loans", "FY2025", 2025, r"each of our obligations as of December 31, 2025 \(in millions\)", r"Unsecured Term Loans", 0, 1e6, section=SEC, note="2026 column (dash = 0)"),
    L("O", "mat_year2_x__term_loans", "FY2025", 2025, r"each of our obligations as of December 31, 2025 \(in millions\)", r"Unsecured Term Loans", 1, 1e6, section=SEC, note="2027 column"),
    L("O", "mat_year1_x__mortgages", "FY2025", 2025, r"each of our obligations as of December 31, 2025 \(in millions\)", r"Mortgages Payable", 0, 1e6, section=SEC, note="2026 column"),
    L("O", "mat_year2_x__mortgages", "FY2025", 2025, r"each of our obligations as of December 31, 2025 \(in millions\)", r"Mortgages Payable", 1, 1e6, section=SEC, note="2027 column"),
    L("O", "mat_year1_x__senior_notes", "FY2025", 2025, r"each of our obligations as of December 31, 2025 \(in millions\)", r"Senior Unsecured Notes and Bonds", 0, 1e6, section=SEC, note="2026 column"),
    L("O", "mat_year2_x__senior_notes", "FY2025", 2025, r"each of our obligations as of December 31, 2025 \(in millions\)", r"Senior Unsecured Notes and Bonds", 1, 1e6, section=SEC, note="2027 column"),
    # BXP (USD thousand)
    L("BXP", "mat_year1_x__senior_notes_feb2026", "FY2025", 2025, r"Maturity Date 12/31/2025 12/31/2024 Unsecured Senior Notes", r"3\.650 % 3\.766 % February 1, 2026", 0, 1e3, section="Note 7 - unsecured senior notes table", note="principal at 12/31/2025"),
    L("BXP", "mat_year1_x__senior_notes_oct2026", "FY2025", 2025, r"Maturity Date 12/31/2025 12/31/2024 Unsecured Senior Notes", r"2\.750 % 3\.495 % October 1, 2026", 0, 1e3, section="Note 7 - unsecured senior notes table", note="principal at 12/31/2025"),
    L("BXP", "mat_year2_x__senior_notes_dec2027", "FY2025", 2025, r"Maturity Date 12/31/2025 12/31/2024 Unsecured Senior Notes", r"6\.750 % 6\.924 % December 1, 2027", 0, 1e3, section="Note 7 - unsecured senior notes table", note="principal at 12/31/2025"),
    L("BXP", "mat_year1_x__mortgage_notes", "FY2025", 2025, r"contractual aggregate principal payments of mortgage notes payable at December 31, 2025", r"Principal Payments Year \(in thousands\) 2026", 0, 1e3, section="Note 7 - mortgage notes principal payments", note="2026"),
    L("BXP", "mat_year2_x__mortgage_notes", "FY2025", 2025, r"contractual aggregate principal payments of mortgage notes payable at December 31, 2025", r"Principal Payments Year \(in thousands\) 2026 \$ [\d,]+ 2027", 0, 1e3, section="Note 7 - mortgage notes principal payments", note="2027"),
    R("BXP", "mat_year1_x__term_loan", "FY2025", 2025, 100e6, USD, "Item 7 - liquidity: principal due", ("$100.0 million of principal outstanding on the 2024 Unsecured Term Loan due September 26, 2026",), "$100.0 million", post=60,
      note="contractual maturity 2026 (two one-year extension options at the company's option are not assumed)"),
    # ARE (USD thousand; total row of the principal-payments table)
    L("ARE", "mat_year1_x__total_unsecured", "FY2025", 2025, r"Principal Payments Remaining for the Periods Ending December 31", r"Unsecured debt weighted-average interest rate/total [\d.]+%", 0, 1e3, section="Note 10 - debt principal payments (total row)", note="2026"),
    L("ARE", "mat_year2_x__total_unsecured", "FY2025", 2025, r"Principal Payments Remaining for the Periods Ending December 31", r"Unsecured debt weighted-average interest rate/total [\d.]+%", 1, 1e3, section="Note 10 - debt principal payments (total row)", note="2027"),
    # AMT (USD million; includes finance leases)
    L("AMT", "mat_year1_x__debt_obligations", "FY2025", 2025, r"Material Cash Requirements", r"Debt obligations \(1\)", 0, 1e6, section="Item 7 - material cash requirements", note="2026; principal maturities incl. finance leases"),
    L("AMT", "mat_year2_x__debt_obligations", "FY2025", 2025, r"Material Cash Requirements", r"Debt obligations \(1\)", 1, 1e6, section="Item 7 - material cash requirements", note="2027"),
    L("AMT", "committed_undrawn_facilities", "FY2025", 2025, r"The following table summarizes our liquidity as of December 31, 2025", r"Total available under credit facilities, net", 0, 1e6, section="Item 7 - liquidity", note="available under the 2021 Multicurrency Credit Facility and the 2021 Credit Facility, net of letters of credit"),
]

# ================================================================== (c) reported EBITDAre (company-reported, annual / trailing twelve months)
_FRT_RX = r"EBITDAre \$ [\d,]+ \$ [\d,]+ \$ ([\d,]+) \$ ([\d,]+) (?:Ratio of EBITDAre|Funds From Operations)"
ROWS_P2 += [
    X("FRT", "ebitdare_reported", "SUP2025:frt-12312025", _FRT_RX, ["FY2025", "FY2024"], USD, "Earnings release - EBITDAre reconciliation (year ended)", 1e3, note="company EBITDAre; consolidated plus adjustments of unconsolidated affiliates"),
    X("FRT", "ebitdare_reported", "SUP2023:frt-12312023", _FRT_RX, ["FY2023", "FY2022"], USD, "Earnings release - EBITDAre reconciliation (year ended)", 1e3, note="company EBITDAre"),
    X("FRT", "ebitdare_reported", "SUP2021:frt-12312021", _FRT_RX, ["FY2021", None], USD, "Earnings release - EBITDAre reconciliation (year ended)", 1e3, note="company EBITDAre"),
]
_EQR_RX = r"(?<!Normalized )EBITDAre ([\d,]+) [\d,]+ "
for _frag, _fy in [("SUP2025:eqr-ex99_1", "FY2025"), ("SUP2024:17025012330", "FY2024"), ("SUP2023:7024008861", "FY2023"), ("SUP2022:eqr-ex99_1", "FY2022"), ("SUP2021:eqr-ex991", "FY2021")]:
    ROWS_P2.append(X("EQR", "ebitdare_reported", _frag, _EQR_RX, [_fy], USD, "Earnings release - Normalized EBITDAre reconciliations (trailing twelve months at December 31)", 1e3,
                     note="EBITDAre line (before the normalizing items), trailing twelve months at the fiscal year end"))

# ================================================================== (d) RP2a: balance-sheet classification, FY2025 (face and notes)
def bs(t, filing, anchor, scale, lines, sec, year="FY2025"):
    """lines: (class, slug, label regex[, col]) -> rows bsa_<class>__<slug>."""
    rows = []
    for ln in lines:
        cls, slug, label = ln[0], ln[1], ln[2]
        col = ln[3] if len(ln) > 3 else 0
        anc = ln[4] if len(ln) > 4 else anchor
        rows.append(L(t, f"bsa_{cls}__{slug}", year, filing, anc, label, col, scale, section=sec, note=f"RP2a class {cls}"))
    return rows


_O_BS = r"Real estate held for investment, at cost:"
_O_AR = r"Accounts receivable, net, consist of the following at:"
_O_OA = r"Other assets, net, consist of the following at:"
ROWS_P2 += bs("O", 2025, _O_BS, 1e3, [
    ("noi", "real_estate_net", r"Real estate held for investment, net"), ("noi", "held_for_sale", r"Real estate and lease intangibles held for sale, net"),
    ("noi", "lease_intangibles", r"Lease intangible assets, net"), ("excl", "cash", r"Cash and cash equivalents"), ("excl", "goodwill", r"Goodwill"),
    ("carry", "unconsolidated", r"Investment in unconsolidated entities"),
    ("noi", "straight_line_receivable", r"Straight-line rent receivables, net", 0, _O_AR), ("wc", "client_receivables", r"Client receivables, net", 0, _O_AR),
    ("carry", "loans_receivable", r"Loans receivable, net", 0, _O_OA), ("carry", "financing_receivables", r"Financing receivables, net", 0, _O_OA),
    ("noi", "rou_financing", r"Right of use asset - financing leases, net", 0, _O_OA), ("carryfin", "preferred_equity", r"Investment in preferred equity", 0, _O_OA),
    ("noi", "rou_operating", r"Right of use asset - operating leases, net", 0, _O_OA), ("wc", "restricted_escrow", r"Restricted escrow deposits", 0, _O_OA),
    ("wc", "prepaid", r"Prepaid expenses", 0, _O_OA), ("wc", "vat", r"Value-added tax receivable", 0, _O_OA), ("wc", "interest_receivable", r"Interest receivable", 0, _O_OA),
    ("wc", "revolver_costs", r"Revolving credit facilities origination costs, net", 0, _O_OA), ("wc", "corporate_assets", r"Corporate assets, net", 0, _O_OA),
    ("wc", "derivatives", r"Derivative assets and receivables - at fair value", 0, _O_OA), ("carry", "sales_type_lease", r"Investment in sales type lease", 0, _O_OA),
    ("wc", "nonrefundable_escrow", r"Non-refundable escrow deposits", 0, _O_OA), ("wc", "impounds", r"Impounds related to mortgages payable", 0, _O_OA), ("wc", "other_items", r"Other items", 0, _O_OA),
], "Item 8 - balance sheet and Note 5 (components of consolidated balance sheets)")

_PLD_BS = r"ASSETS Investments in real estate properties"
_PLD_N3 = r"NOTE 3\. REAL ESTATE Investments in real estate properties consisted of the following"
_PLD_N6 = r"NOTE 6\. OTHER ASSETS AND OTHER LIABILITIES"
ROWS_P2 += bs("PLD", 2025, _PLD_BS, 1e3, [
    ("noi", "real_estate_net", r"Net investments in real estate properties"), ("carry", "unconsolidated", r"Investments in and advances to unconsolidated entities"),
    ("noi", "held_for_sale", r"Assets held for sale or contribution"), ("excl", "cash", r"Cash and cash equivalents"),
    ("inre", "properties_under_development", r"Properties under development [\d,]+ [\d,]+ [\d,]+ [\d,]+", 0, _PLD_N3), ("inre", "land", r"Land \(1\)", 0, _PLD_N3),
    ("noi", "rent_leveling", r"Rent leveling", 0, _PLD_N6), ("noi", "leasing_commissions", r"Leasing commissions, net of \$[\d.]+ billion and \$[\d.]+ billion of accumulated amortization", 0, _PLD_N6),
    ("noi", "lease_rou", r"Lease right-of-use assets \(1\)", 0, _PLD_N6), ("wc", "accounts_receivable", r"Accounts receivable", 0, _PLD_N6),
    ("noi", "acquired_lease_intangibles", r"Acquired lease intangibles, net of \$[\d.]+ billion and \$[\d.]+ billion of accumulated amortization", 0, _PLD_N6),
    ("wc", "prepaid", r"Prepaid assets", 0, _PLD_N6), ("other", "fixed_assets", r"Fixed assets", 0, _PLD_N6), ("wc", "vat", r"Value added taxes receivable", 0, _PLD_N6),
    ("wc", "derivatives", r"Derivative assets", 0, _PLD_N6), ("carry", "other_notes_receivable", r"Other notes receivable", 0, _PLD_N6),
    ("other", "deferred_taxes", r"Deferred income taxes", 0, _PLD_N6), ("other", "management_contracts", r"Management contracts", 0, _PLD_N6), ("other", "other", r"Management contracts [\d,]+ [\d,]+ Other", 0, _PLD_N6),
], "Item 8 - balance sheet, Note 3 (real estate) and Note 6 (other assets)")

_SPG_BS = r"ASSETS: Investment properties, at cost"
_SPG_DC = r"Deferred costs and other assets include the following as of December 31:"
ROWS_P2 += bs("SPG", 2025, _SPG_BS, 1e3, [
    ("noi", "investment_properties_net", r"Investment properties at cost, net", 0, r"Investment properties consist of the following as of December 31:"),
    ("inre", "construction_in_progress", r"Construction in progress included above", 0, r"Investment properties consist of the following as of December 31:"),
    ("excl", "cash", r"Cash and cash equivalents"), ("wc", "tenant_receivables_accrued_revenue", r"Tenant receivables and accrued revenue, net"),
    ("carry", "other_unconsolidated", r"Investment in other unconsolidated entities, at equity"), ("carry", "klepierre", r"Investment in Kl.pierre, at equity"),
    ("noi", "rou", r"Right-of-use assets, net"),
    ("noi", "deferred_lease_costs", r"Deferred lease costs, net", 0, _SPG_DC), ("noi", "in_place_intangibles", r"In-place lease intangibles, net", 0, _SPG_DC),
    ("noi", "above_market_intangibles", r"Acquired above market lease intangibles, net", 0, _SPG_DC),
    ("carryfin", "captive_securities", r"Marketable securities of our captive insurance companies", 0, _SPG_DC), ("excl", "goodwill", r"Goodwill", 0, _SPG_DC),
    ("carryfin", "other_securities", r"Other marketable and non-marketable securities", 0, _SPG_DC),
    ("other", "trg_provisional_fair_value", r"Provisional fair value - TRG Acquisition, net \(Note 4\)", 0, _SPG_DC),
    ("wc", "prepaids_notes_other", r"Prepaids, notes receivable and other assets, net", 0, _SPG_DC),
], "Item 8 - balance sheet and notes (investment properties; deferred costs and other assets)")

_FRT_BS = r"ASSETS Real estate, at cost"
ROWS_P2 += bs("FRT", 2025, _FRT_BS, 1e3, [
    ("noi", "net_real_estate", r"Net real estate"), ("inre", "construction_in_progress", r"Construction-in-progress \(including \$[\d,]+ and \$[\d,]+ of consolidated variable interest entities, respectively\)"),
    ("excl", "cash", r"Cash and cash equivalents"), ("wc", "accounts_notes_receivable", r"Accounts and notes receivable, net"), ("carry", "mortgage_notes_receivable", r"Mortgage notes receivable, net"),
    ("carry", "partnerships", r"Investment in partnerships"), ("noi", "rou_operating", r"Operating lease right of use assets, net"), ("noi", "rou_finance", r"Finance lease right of use assets, net"),
    ("wc", "prepaid_other", r"Prepaid expenses and other assets"),
], "Item 8 - balance sheet (prepaid and other assets: lease costs, prepaid property taxes, acquired above-market leases per the accounting policy note; not split numerically)")

_BXP_BS = r"ASSETS Real estate, at cost \(amounts related to variable interest entities"
_BXP_RE = r"Right of use assets - operating leases 325,841 334,767 325,841 334,767"
ROWS_P2 += bs("BXP", 2025, _BXP_BS, 1e3, [
    ("noi", "total_real_estate", r"Total real estate"), ("excl", "cash", r"Cash and cash equivalents \([^)]*\)"), ("wc", "escrows", r"Cash held in escrows \([^)]*\)"),
    ("carryfin", "securities", r"Investments in securities"), ("wc", "tenant_other_receivables", r"Tenant and other receivables, net \([^)]*\)"),
    ("carry", "note_receivable", r"Note receivable, net"), ("carry", "related_party_notes", r"Related party notes receivable, net"), ("carry", "sales_type_lease", r"Sales-type lease receivable, net"),
    ("noi", "accrued_rental_income", r"Accrued rental income, net \([^)]*\)"), ("noi", "deferred_charges", r"Deferred charges, net \([^)]*\)"),
    ("wc", "prepaid_other", r"Prepaid expenses and other assets \([^)]*\)"), ("carry", "unconsolidated_jvs", r"Investments in unconsolidated joint ventures"), ("noi", "held_for_sale", r"Assets held for sale"),
    ("inre", "land_held_for_future_development", r"Land held for future development \(1\)", 0, _BXP_RE), ("inre", "construction_in_progress", r"Construction in progress", 0, _BXP_RE),
], "Item 8 - balance sheet and Note 3 (real estate)")

_ARE_BS = r"Consolidated Balance Sheets \(In thousands, except share and per share amounts\) December 31, 2025 2024 Assets"
_ARE_OA = r"OTHER ASSETS The following table summarizes the components of other assets"
ROWS_P2 += bs("ARE", 2025, _ARE_BS, 1e3, [
    ("noi", "investments_in_real_estate", r"Investments in real estate"), ("carry", "unconsolidated_jvs", r"Investments in unconsolidated real estate joint ventures"),
    ("excl", "cash", r"Cash and cash equivalents"), ("wc", "restricted_cash", r"Restricted cash"), ("wc", "tenant_receivables", r"Tenant receivables"), ("noi", "deferred_rent", r"Deferred rent"),
    ("noi", "deferred_leasing_costs", r"Deferred leasing costs"), ("carryfin", "investments", r"Deferred leasing costs [\d,]+ [\d,]+ Investments"),
    ("inre", "development_and_redevelopment_projects", r"Current and future development and redevelopment projects", 0, r"3\.INVESTMENTS IN REAL ESTATE Our consolidated investments in real estate consisted"),
    ("noi", "acquired_in_place_leases", r"Acquired in-place leases", 0, _ARE_OA), ("other", "deferred_compensation_plan", r"Deferred compensation plan", 0, _ARE_OA),
    ("other", "deferred_financing_costs", r"Deferred financing costs - unsecured senior line of credit", 0, _ARE_OA), ("wc", "deposits", r"Deposits", 0, _ARE_OA),
    ("other", "fixtures_equipment_software", r"Furniture, fixtures, equipment, and software", 0, _ARE_OA), ("carry", "net_investment_in_leases", r"Net investment in leases", 0, _ARE_OA),
    ("carry", "notes_receivable", r"Notes receivable", 0, _ARE_OA), ("noi", "rou_operating", r"Operating lease right-of-use assets", 0, _ARE_OA),
    ("other", "other_assets", r"Operating lease right-of-use assets [\d,]+ [\d,]+ Other assets", 0, _ARE_OA), ("wc", "prepaid", r"Prepaid expenses", 0, _ARE_OA),
    ("other", "property_plant_equipment", r"Property, plant, and equipment", 0, _ARE_OA),
], "Item 15 - balance sheet, Note 3 (investments in real estate) and Note 8 (other assets)")

_EQR_BS = r"ASSETS Land \$ 5,563,407"
ROWS_P2 += bs("EQR", 2025, _EQR_BS, 1e3, [
    ("noi", "investment_in_real_estate_net", r"Investment in real estate, net"), ("inre", "projects_under_development", r"Projects under development"), ("inre", "land_held_for_development", r"Land held for development"),
    ("carry", "unconsolidated", r"Investments in unconsolidated entities"), ("excl", "cash", r"Cash and cash equivalents"), ("wc", "restricted_deposits", r"Restricted deposits"),
    ("noi", "rou", r"Right-of-use assets"), ("other", "other_assets", r"Other assets"),
], "Item 8 - balance sheet (other assets are not broken down in the 10-K)")

_PSA_BS = r"CONSOLIDATED BALANCE SHEETS \(Amounts in thousands, except share data\) December 31, 2025 December 31, 2024"
ROWS_P2 += bs("PSA", 2025, _PSA_BS, 1e3, [
    ("excl", "cash", r"Cash and equivalents"), ("noi", "land_and_buildings_net", r"Total land and buildings, net"), ("carry", "construction_in_process", r"Construction in process"),
    ("carry", "unconsolidated_real_estate_entity", r"Investment in unconsolidated real estate entity"), ("excl", "goodwill_and_intangibles", r"Goodwill and other intangible assets, net"),
    ("carry", "notes_receivable", r"Notes receivable"), ("other", "other_assets", r"Notes receivable [\d,]+ [\d,]+ Other assets"),
], "Item 8 - balance sheet (other assets are not broken down in the 10-K)")

_EQIX_BS = r"Consolidated Balance Sheets \(in millions, except share and per share data\) December 31, 2025 2024 Assets"
_EQIX_OCA = r"Other Current Assets Other current assets consisted of the following as of December 31"
_EQIX_PPE = r"Property, Plant and Equipment, Net Property, plant and equipment, net consisted of the following as of December 31"
_EQIX_OA = r"Other Assets Other assets consisted of the following as of December 31"
ROWS_P2 += bs("EQIX", 2025, _EQIX_BS, 1e6, [
    ("excl", "cash", r"Cash and cash equivalents"), ("excl", "short_term_investments", r"Short-term investments"), ("wc", "accounts_receivable", r"Accounts receivable, net of allowance of \$\d+ and \$\d+"),
    ("wc", "other_current_assets", r"Other current assets"), ("noi", "ppe_net", r"Property, plant and equipment, net"), ("noi", "rou_operating", r"Operating lease right-of-use assets"),
    ("excl", "goodwill", r"Goodwill"), ("noi", "intangibles", r"Intangible assets, net"),
    ("inre", "construction_in_progress", r"Construction in progress", 0, _EQIX_PPE),
    ("wc", "prepaid_noncurrent", r"Prepaid assets, non-current", 0, _EQIX_OA), ("carry", "equity_method_investments", r"Equity method investments", 0, _EQIX_OA), ("other", "contract_costs", r"Contract costs", 0, _EQIX_OA),
    ("carry", "loan_receivable", r"Loan receivable", 0, _EQIX_OA), ("other", "deferred_cca", r"Deferred CCA implementation costs", 0, _EQIX_OA), ("wc", "contract_assets_noncurrent", r"Contract assets, non-current", 0, _EQIX_OA),
    ("wc", "prepaid_expenses_noncurrent", r"Prepaid expenses, non-current", 0, _EQIX_OA), ("other", "deferred_tax_assets", r"Deferred tax assets, net", 0, _EQIX_OA), ("wc", "deposits", r"Deposits", 0, _EQIX_OA),
    ("wc", "derivatives_noncurrent", r"Derivative assets, non-current", 0, _EQIX_OA), ("other", "debt_issuance_costs", r"Debt issuance costs, net", 0, _EQIX_OA), ("other", "other", r"Other \(1\)", 0, _EQIX_OA),
], "Item 8 - balance sheet and notes (PP&E; other assets)")

_AMT_BS = r"CURRENT ASSETS:"
_AMT_PPE = r"3\. PROPERTY AND EQUIPMENT Property and equipment \(including assets held under finance leases\) consisted of the following"
ROWS_P2 += bs("AMT", 2025, _AMT_BS, 1e6, [
    ("excl", "cash", r"Cash and cash equivalents"), ("wc", "restricted_cash", r"Restricted cash"), ("wc", "accounts_receivable", r"Accounts receivable, net"), ("wc", "prepaid_other_current", r"Prepaid and other current assets"),
    ("noi", "property_and_equipment_net", r"PROPERTY AND EQUIPMENT, net"), ("excl", "goodwill", r"GOODWILL"), ("noi", "other_intangibles", r"OTHER INTANGIBLE ASSETS, net"), ("other", "deferred_tax_asset", r"DEFERRED TAX ASSET"),
    ("noi", "deferred_rent_asset", r"DEFERRED RENT ASSET"), ("noi", "rou", r"RIGHT-OF-USE ASSET"), ("wc", "notes_receivable_other_noncurrent", r"NOTES RECEIVABLE AND OTHER NON-CURRENT ASSETS"),
    ("inre", "construction_in_progress", r"Construction-in-progress", 0, _AMT_PPE),
], "Item 8 - balance sheet and Note 3 (property and equipment)")

# ================================================================== (e) RP2b: noncontrolling interests, operating-partnership units, share basis
_NOTE_OP = "RP2b"
ROWS_P2 += [
    # O
    R("O", "nci_op_units", "FY2025", 2025, 2681808 * 1.02934, "units", "Note 12 - noncontrolling interests: Realty Income, L.P. units (x conversion ratio 1.02934)", ("2,681,808 units were outstanding as of both December 31, 2025 and 2024",), "2,681,808", pre=120, post=80,
      note="OP units outstanding 2,681,808 x conversion ratio 1.02934 into common shares"),
    L("O", "nci_op_book__units", "FY2025", 2025, r"The following table represents the change in the carrying value of all noncontrolling interests through December 31, 2025", r"Carrying value as of December 31, 2025", 1, 1e3,
      section="Note 12 - noncontrolling interests (Realty Income, L.P. units column)", note="carrying value of the OP-unit column at 12/31/2025", ),
    # PLD
    R("PLD", "nci_op_units", "FY2025", 2025, 21758e3, "units", "Item 5 - common limited partnership units outstanding (OP)", ("Common limited partnership units outstanding", "21,758"), "21,758", post=60, note="thousand units x 1e3; exchangeable 1:1"),
    R("PLD", "nci_op_book__limited_partners_common", "FY2025", 2025, 1244117e3, USD, "Prologis, L.P. balance sheet: Limited partners - common", ("Limited partners - common", "1,244,117"), "1,244,117", pre=200, post=60,
      note="OP-unit holders' capital at book value"),
    R("PLD", "diluted_includes_op", "FY2025", 2025, 1.0, FR, "Note - earnings per share: incremental weighted average effect on exchange of limited partnership units", ("Incremental weighted average effect on exchange of limited partnership units", "(1)", "23,034"), "23,034", pre=120, post=120,
      note="1 = diluted shares include OP units"),
    # SPG
    R("SPG", "nci_op_units", "FY2025", 2025, 55689714.0, "units", "Operating Partnership balance sheet: limited partners units outstanding", ("Limited Partners, 55,689,714 and 50,759,627 units outstanding",), "55,689,714", pre=60, post=60, note="limited partner units at 12/31/2025"),
    R("SPG", "diluted_includes_op", "FY2025", 2025, 0.0, FR, "Item 7 - FFO: basic and diluted weighted average shares exclude limited partnership units",
      ("Basic and Diluted weighted average shares outstanding", "326,367"), "326,367", post=200, note="0 = diluted shares exclude OP units (they are shown separately)"),
    # BXP
    R("BXP", "nci_op_units", "FY2025", 2025, 18252e3, "units", "Item 7 - consolidated market capitalization at December 31, 2025: common operating partnership units", ("Common Operating Partnership Units", "18,252"), "18,252", pre=120, post=60, note="thousand units x 1e3"),
    R("BXP", "diluted_includes_op", "FY2025", 2025, 0.0, FR, "Note - earnings per share: diluted shares = basic + stock-based compensation only", ("Effect of Dilutive Securities:", "Stock Based Compensation", "(1)", "539"), "158,869", pre=60, post=140,
      note="0 = diluted shares exclude common OP units; BXP's reported FFO is the BXP, Inc. share (90.03% of BPLP FFO)"),
    # EQR
    R("EQR", "nci_op_units", "FY2025", 2025, 9325363.0, "units", "Q4 2025 earnings release - period-ending units (OP units and restricted units)", ("Units (includes OP Units and Restricted Units)", "9,325,363"), "9,325,363", post=60, note="units at 12/31/2025"),
    R("EQR", "diluted_includes_op", "FY2025", "SUP2025:eqr-ex99_1", 1.0, FR, "Q4 2025 earnings release - weighted average amounts: total common shares and units - diluted", ("Shares issuable from assumed conversion/vesting of:", "- OP Units", "9,491,664"), "9,491,664", pre=120, post=120,
      note="1 = diluted shares include OP units"),
    L("EQR", "nci_op_book__equity", "FY2025", 2025, r"Retained earnings 1,193,931", r"Noncontrolling Interests: Operating Partnership", 0, 1e3, section="Item 8 - balance sheet: noncontrolling interests - Operating Partnership", note="OP-unit holders' interest (equity)"),
    L("EQR", "nci_op_book__redeemable", "FY2025", 2025, r"Total liabilities 9,336,889", r"Redeemable Noncontrolling Interests - Operating Partnership", 0, 1e3, section="Item 8 - balance sheet: redeemable noncontrolling interests - Operating Partnership",
      note="OP-unit holders' redeemable interest (temporary equity) at redemption value"),
    # no operating-partnership units outstanding (verified absence)
    Z("ARE", "nci_op_units", "FY2025", 2025, "Item 1 / Note - noncontrolling interests", r"OP [Uu]nits|operating partnership units|limited partnership units|common units",
      "10-K FY2025 full text: no operating-partnership, OP or common units are mentioned; noncontrolling interests are partners in consolidated real estate joint ventures"),
    Z("EQIX", "nci_op_units", "FY2025", 2025, "Item 1 / Note - noncontrolling interests", r"OP [Uu]nits|operating partnership units|limited partnership units|common units", "10-K FY2025 full text: no OP units"),
    Z("AMT", "nci_op_units", "FY2025", 2025, "Item 1 / Note - noncontrolling interests", r"OP [Uu]nits|operating partnership units|limited partnership units|common units", "10-K FY2025 full text: no OP units (noncontrolling interests are partners in consolidated subsidiaries)"),
]

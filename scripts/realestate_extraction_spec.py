"""Extraction spec for INCOME_REAL_ESTATE round 2 (items found only in text; AI extraction with exact quotes, as for BANK / INSURANCE).

``R`` = a value found in the 10-K text of fiscal year ``filing`` (tokens anchor the quote, ``verify`` is the number string that must be inside it).
``A`` = "not disclosed": an absence regex that must have NO match in the filing text, with the search scope written in the row.
Units: USD in full dollars, fractions (0.989 = 98.9%).  Item names read by src/scoring/realestate.py:
  reported_ffo, maintenance_capex, ti_lc_income_preserving, same_property_noi_growth, occupancy, largest_tenant_share, committed_undrawn_facilities, unencumbered_noi_share,
  unencumbered_assets_share, secured_debt, acquisition_yield, development_yield, fair_value_real_estate, debt_total_bs, jv_noi_share;
  display only: same_store_revenue_growth, acquisition_invested, development_invested, profile_* (RE11).
"""
USD, FR = "USD", "fraction"


def R(t, item, year, filing, value, unit, section, tokens, verify, pre=40, post=160, note=""):
    return dict(t=t, item=item, year=year, filing=filing, value=value, unit=unit, section=section, tokens=tokens, verify=verify, pre=pre, post=post, note=note)


def A(t, item, year, filing, section, regex, scope, note="", unit=USD):
    return dict(t=t, item=item, year=year, filing=filing, value="not disclosed", unit=unit, section=section, absence=regex, scope=scope, note=note)


def X(t, item, filing, regex, cols, unit, section, scale=1.0, pre=0, post=0, note="", agg=None):
    """Series row: the regex groups (numbers) map to the fiscal-year columns ``cols`` (None = skip a group); value = number * scale."""
    return dict(t=t, item=item, filing=filing, regex=regex, cols=cols, unit=unit, section=section, scale=scale, pre=pre, post=post, note=note, agg=agg)


ROWS = []

# ================================================================== O (Realty Income, net lease)
ROWS += [
    R("O", "occupancy", "FY2021", 2021, 0.985, FR, "Item 7 MD&A - portfolio occupancy", ("portfolio of 11,136 properties was", "98.5% leased"), "98.5%", post=120, note="leased %, December 31"),
    R("O", "occupancy", "FY2022", 2023, 0.990, FR, "Item 7 MD&A - portfolio occupancy (prior-year comparison)", ("as compared to 99.0% leased",), "99.0%", pre=120, post=80, note="leased %, December 31, 2022"),
    R("O", "occupancy", "FY2023", 2023, 0.986, FR, "Item 7 MD&A - portfolio occupancy", ("portfolio of 13,458 properties was", "98.6% leased"), "98.6%", post=120),
    R("O", "occupancy", "FY2024", 2025, 0.987, FR, "Item 7 MD&A - portfolio occupancy (prior-year comparison)", ("as compared to 98.7% leased",), "98.7%", pre=120, post=80),
    R("O", "occupancy", "FY2025", 2025, 0.989, FR, "Item 7 MD&A - portfolio occupancy", ("portfolio of 15,511 properties was", "98.9% leased"), "98.9%", post=120),
    R("O", "reported_ffo", "FY2021", 2021, 1240.6e6, USD, "Item 7 MD&A - FFO table", ("FFO available to common stockholders", "1,240.6"), "1,240.6", post=60, note="USD m x 1e6"),
    R("O", "reported_ffo", "FY2022", 2023, 2471.9e6, USD, "Item 7 MD&A - FFO table", ("FFO available to common stockholders", "2,822.1", "2,471.9"), "2,471.9", post=40),
    R("O", "reported_ffo", "FY2023", 2023, 2822.1e6, USD, "Item 7 MD&A - FFO table", ("FFO available to common stockholders", "2,822.1"), "2,822.1", post=40),
    R("O", "reported_ffo", "FY2024", 2025, 3467.7e6, USD, "Item 7 MD&A - FFO table", ("FFO available to common stockholders", "3,860.3", "3,467.7"), "3,467.7", post=40),
    R("O", "reported_ffo", "FY2025", 2025, 3860.3e6, USD, "Item 7 MD&A - FFO table", ("FFO available to common stockholders", "3,860.3"), "3,860.3", post=40),
    R("O", "acquisition_yield", "FY2025", 2025, 0.073, FR, "Item 7 MD&A - Investments", ("we invested $6.3 billion at an initial weighted average cash yield of 7.3%",), "7.3%", post=100, note="all investments (acquisitions, development, JV, preferred equity, loans)"),
    R("O", "acquisition_invested", "FY2025", 2025, 6.3e9, USD, "Item 7 MD&A - Investments", ("we invested $6.3 billion at an initial weighted average cash yield of 7.3%",), "$6.3 billion", post=100),
    R("O", "acquisition_yield", "FY2023", 2023, 0.071, FR, "Item 7 MD&A - Investments During 2023", ("we invested $9.5 billion at an initial weighted average cash yield of 7.1%",), "7.1%", post=100),
    R("O", "acquisition_invested", "FY2023", 2023, 9.5e9, USD, "Item 7 MD&A - Investments During 2023", ("we invested $9.5 billion at an initial weighted average cash yield of 7.1%",), "$9.5 billion", post=100),
    R("O", "same_store_revenue_growth", "FY2025", 2025, 0.013, FR, "Item 7 MD&A - rental revenue", ("The same store rental revenue percentage increased by 1.3%",), "1.3%", post=100, note="same-store RENTAL REVENUE (NOI not disclosed)"),
    R("O", "largest_tenant_share", "FY2025", 2025, 0.033, FR, "Item 1 - Client Diversification (percentage of annualized base rent)", ("7-Eleven", "812", "3.3"), "3.3", pre=120, post=60, note="7-Eleven, % of portfolio annualized base rent"),
    R("O", "committed_undrawn_facilities", "FY2025", 2025, 2.7e9, USD, "Item 7 - Liquidity: RI Credit Facilities", ("we had a borrowing capacity of $2.7 billion available on our RI Credit Facilities",), "$2.7 billion", post=120, note="RI Credit Facilities only; the consolidated Fund's own facility has a further $1.2 billion available and is excluded"),
    R("O", "unencumbered_assets_share", "FY2025", 2025, 0.998, FR, "Item 7 - debt covenants: secured debt / adjusted assets", ("Limitation on incurrence of secured debt", "40", "of adjusted assets", "0.2"), "0.2", post=40, note="derived: 1 - 0.2% (secured debt as % of adjusted assets, covenant table); unencumbered share of assets"),
    A("O", "same_property_noi_growth", "FY2025", 2025, "Item 7 MD&A", r"same[- ](store|property) (NOI|net operating income)", "10-K FY2025 full text; the company reports same-store rental revenue only", unit=FR),
    R("O", "maintenance_capex", "FY2025", 2025, 0.335e6, USD, "Note 5 / MD&A - capitalized costs on existing properties (recurring capital expenditures)", ("$0.3 million for recurring capital expenditures",), "$0.3 million", pre=200, post=20, note="table: recurring capital expenditures (335) thousand"),
    R("O", "ti_lc_income_preserving", "FY2025", 2025, 9.481e6, USD, "Cash-flow reconciliation of FFO - capital expenditures from operating properties", ("Leasing costs and commissions", "(9,481)"), "9,481", pre=60, post=120, note="re-leasing costs (leasing costs and commissions), USD thousand x 1e3"),
    R("O", "maintenance_capex", "FY2024", 2025, 0.402e6, USD, "Note 5 - capitalized costs", ("$0.4 million for recurring capital expenditures",), "$0.4 million", pre=200, post=20, note="table: recurring capital expenditures (402) thousand"),
    R("O", "ti_lc_income_preserving", "FY2024", 2025, 8.558e6, USD, "Cash-flow reconciliation of FFO", ("Leasing costs and commissions", "(9,481)", "(8,558)"), "8,558", pre=60, post=60),
    R("O", "maintenance_capex", "FY2023", 2023, 0.3e6, USD, "Note 5 - capitalized costs", ("$9.9 million for re-leasing costs, and $0.3 million for recurring capital expenditures",), "$0.3 million", pre=120, post=20),
    R("O", "ti_lc_income_preserving", "FY2023", 2023, 9.9e6, USD, "Note 5 - capitalized costs", ("$9.9 million for re-leasing costs, and $0.3 million for recurring capital expenditures",), "$9.9 million", pre=120, post=20),
    R("O", "maintenance_capex", "FY2022", 2023, 3.2e6, USD, "Note 5 - capitalized costs (prior year)", ("$5.2 million for re-leasing costs, and $3.2 million for recurring capital expenditures",), "$3.2 million", pre=160, post=20),
    R("O", "ti_lc_income_preserving", "FY2022", 2023, 5.2e6, USD, "Note 5 - capitalized costs (prior year)", ("$5.2 million for re-leasing costs, and $3.2 million for recurring capital expenditures",), "$5.2 million", pre=160, post=20),
    R("O", "maintenance_capex", "FY2021", 2021, 0.978e6, USD, "Note 5 - capitalized costs", ("$6.3 million for re-leasing costs, $978,000 for recurring capital expenditures",), "$978,000", pre=120, post=20),
    R("O", "ti_lc_income_preserving", "FY2021", 2021, 6.3e6, USD, "Note 5 - capitalized costs", ("$6.3 million for re-leasing costs, $978,000 for recurring capital expenditures",), "$6.3 million", pre=120, post=20),
    A("O", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio)", "10-K FY2025 full text; only acquisition-date fair value allocations are disclosed"),
]

# ================================================================== PLD (Prologis, industrial)
ROWS += [
    X("PLD", "reported_ffo", 2025, r"NAREIT defined FFO attributable to common stockholders/unitholders\s*\$?\s*([\d,]+)\s*\$?\s*([\d,]+)", ["FY2025", "FY2024"], USD, "Item 7 MD&A - FFO reconciliation (NAREIT defined, proportionate incl. unconsolidated entities)", 1e6, note="USD m x 1e6; includes the proportionate share of unconsolidated co-investment ventures"),
    X("PLD", "reported_ffo", 2023, r"NAREIT defined FFO attributable to common stockholders/unitholders\s*\$?\s*([\d,]+)\s*\$?\s*([\d,]+)", ["FY2023", "FY2022"], USD, "Item 7 MD&A - FFO reconciliation", 1e6),
    X("PLD", "reported_ffo", 2021, r"NAREIT defined FFO attributable to common stockholders/unitholders\s*\$?\s*([\d,]+)\s*\$?\s*([\d,]+)", ["FY2021", None], USD, "Item 7 MD&A - FFO reconciliation", 1e6),
    X("PLD", "same_property_noi_growth", 2025, r"Prologis Share of Same Store Property NOI - Net Effective[^$]{0,6}\$\s*([\d,]+)\s*\$\s*([\d,]+)\s*([\d.]+)\s*%", [None, None, "FY2025"], FR, "Item 7 MD&A - Same Store Analysis (three months ended December 31)", 0.01, note="BASIS: Prologis share, net effective, fourth quarter vs prior-year fourth quarter (annual not disclosed)"),
    X("PLD", "same_property_noi_growth", 2023, r"Prologis Share of Same Store Property NOI - Net Effective[^$]{0,6}\$\s*([\d,]+)\s*\$\s*([\d,]+)\s*([\d.]+)\s*%", [None, None, "FY2023"], FR, "Item 7 MD&A - Same Store Analysis (three months ended December 31)", 0.01, note="BASIS: Q4 vs Q4, net effective, Prologis share"),
    X("PLD", "same_property_noi_growth", 2021, r"Prologis Share of Same Store Property NOI - Net Effective[^$]{0,6}\$\s*([\d,]+)\s*\$\s*([\d,]+)\s*([\d.]+)\s*%", [None, None, "FY2021"], FR, "Item 7 MD&A - Same Store Analysis (three months ended December 31)", 0.01, note="BASIS: Q4 vs Q4, net effective, Prologis share"),
    X("PLD", "ti_lc_income_preserving", 2025, r"Tenant improvements and lease commissions on previously leased space\s*\(([\d,]+)\s*\)\s*\(([\d,]+)\s*\)\s*\(([\d,]+)\s*\)", ["FY2025", "FY2024", "FY2023"], USD, "Consolidated statements of cash flows - investing", 1e3, note="USD thousand x 1e3; 'previously leased space' = income-preserving"),
    X("PLD", "ti_lc_income_preserving", 2023, r"Tenant improvements and lease commissions on previously leased space\s*\(([\d,]+)\s*\)\s*\(([\d,]+)\s*\)\s*\(([\d,]+)\s*\)", [None, "FY2022", "FY2021"], USD, "Consolidated statements of cash flows - investing", 1e3),
    X("PLD", "maintenance_capex", 2025, r"Property improvements\s*\(([\d,]+)\s*\)\s*\(([\d,]+)\s*\)\s*\(([\d,]+)\s*\)", ["FY2025", "FY2024", "FY2023"], USD, "Consolidated statements of cash flows - investing", 1e3, note="company line 'Property improvements' (capex on existing properties); the split recurring vs value-add is not stated in the 10-K"),
    X("PLD", "maintenance_capex", 2023, r"Property improvements\s*\(([\d,]+)\s*\)\s*\(([\d,]+)\s*\)\s*\(([\d,]+)\s*\)", [None, "FY2022", "FY2021"], USD, "Consolidated statements of cash flows - investing", 1e3, note="company line 'Property improvements'"),
    X("PLD", "occupancy", 2025, r"occupancy in our operating portfolio of ([\d.]+)%", ["FY2025"], FR, "Item 7 MD&A - overview (operating portfolio)", 0.01, pre=40, post=80),
    X("PLD", "occupancy", 2023, r"O&M operating portfolio occupancy was ([\d.]+)%", ["FY2023"], FR, "Item 7 MD&A - overview (owned and managed operating portfolio)", 0.01, pre=40, post=80),
    A("PLD", "occupancy", "FY2021", 2021, "Item 7 MD&A", r"operating portfolio[^.]{0,40}\d\d\.\d%", "10-K FY2021 full text; the operating-portfolio occupancy sentence is not in this filing", unit=FR),
    X("PLD", "development_yield", 2025, r"Stabilizations:.{0,300}?Weighted average stabilized yield \(1\)\s*([\d.]+)\s*%\s*([\d.]+)\s*%", ["FY2025", "FY2024"], FR, "Item 7 MD&A - development stabilizations", 0.01, note="weighted average stabilized yield on stabilized development buildings"),
    X("PLD", "development_invested", 2025, r"Stabilizations:.{0,300}?TEI\s*\$\s*([\d,]+)\s*\$\s*([\d,]+)\s*Percentage of build-to-suits", ["FY2025", "FY2024"], USD, "Item 7 MD&A - development stabilizations (TEI)", 1e6, note="total expected investment of stabilized buildings"),
    X("PLD", "development_yield", 2023, r"Stabilizations:.{0,300}?Weighted average stabilized yield \(2\)\s*([\d.]+)\s*%\s*([\d.]+)\s*%", ["FY2023", "FY2022"], FR, "Item 7 MD&A - development stabilizations", 0.01),
    X("PLD", "development_invested", 2023, r"Stabilizations:.{0,300}?TEI\s*\$\s*([\d,]+)\s*\$\s*([\d,]+)\s*Percentage of build-to-suits", ["FY2023", "FY2022"], USD, "Item 7 MD&A - development stabilizations (TEI)", 1e6),
    X("PLD", "development_yield", 2021, r"Stabilizations:.{0,300}?Weighted average stabilized yield \(1\)\s*([\d.]+)\s*%\s*([\d.]+)\s*%", ["FY2021", None], FR, "Item 7 MD&A - development stabilizations", 0.01),
    X("PLD", "development_invested", 2021, r"Stabilizations:.{0,300}?TEI\s*\$\s*([\d,]+)\s*\$\s*([\d,]+)\s*Percentage of build-to-suits", ["FY2021", None], USD, "Item 7 MD&A - development stabilizations (TEI)", 1e6),
    X("PLD", "largest_tenant_share", 2025, r"Top Customers\s*%\s*of\s+NER\s+Total Occupied Square Feet\s+Top Customers\s*%\s*of\s+NER\s+Total Occupied Square Feet\s+1\.\s*Amazon\s+([\d.]+)", ["FY2025"], FR, "Item 1 - top 25 customers (consolidated, % of net effective rent)", 0.01, note="Amazon, consolidated real estate segment (owned and managed: 5.3%)"),
    X("PLD", "committed_undrawn_facilities", 2025, r"available capacity on our credit facilities of \$([\d.]+) billion", ["FY2025"], USD, "Item 7 - liquidity", 1e9, note="credit facilities incl. commercial-paper backstop"),
    X("PLD", "debt_total_bs", 2021, r"Total debt\s*\(1\)\s*[\d.]+\s*%\s*\$\s*([\d,]+)\s*100\.0", ["FY2021"], USD, "Item 7A - debt by currency, total debt at December 31, 2021 (principal)", 1e6, note="round 1 set FY2021 debt missing (tag implausible)"),
    A("PLD", "unencumbered_noi_share", "FY2025", 2025, "Item 7 / debt note", r"unencumbered (NOI|net operating income|assets|properties) (of|represent|were|totaled)", "10-K FY2025 full text (only a generic mention of unencumbered properties in ventures)", unit=FR),
    A("PLD", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio|investments in real estate)", "10-K FY2025 full text"),
]

# ================================================================== SPG (Simon Property Group, retail malls)
_SPG_NOI = r"Results for the Year.{0,3500}?[Dd]omestic property NOI (?:increased|decreased) ([\d.]+)%"
ROWS += [
    X("SPG", "reported_ffo", 2025, r"FFO of the Operating Partnership\s*\$\s*([\d,]+)\s*\$\s*([\d,]+)\s*\$\s*([\d,]+)", ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - FFO of the Operating Partnership (reconciliation)", 1e3, note="USD thousand x 1e3; FFO of the Operating Partnership (all units), our-share basis incl. unconsolidated entities"),
    X("SPG", "reported_ffo", 2023, r"FFO of the Operating Partnership\s*\$\s*([\d,]+)\s*\$\s*([\d,]+)\s*\$\s*([\d,]+)", [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - FFO of the Operating Partnership (reconciliation)", 1e3),
    X("SPG", "occupancy", 2025, r"Total Portfolio\s*([\d.]+)%\s*-?\d+\s*bps\s*([\d.]+)%\s*-?\d+\s*bps\s*([\d.]+)%\s*Average Base Minimum Rent", ["FY2025", "FY2024", "FY2023"], FR, "Item 7 MD&A - United States portfolio data (U.S. Malls and Premium Outlets, total portfolio ending occupancy)", 0.01),
    X("SPG", "occupancy", 2023, r"Total Portfolio\s*([\d.]+)%\s*-?\d+\s*bps\s*([\d.]+)%\s*-?\d+\s*bps\s*([\d.]+)%\s*Average Base Minimum Rent", [None, "FY2022", "FY2021"], FR, "Item 7 MD&A - United States portfolio data", 0.01),
    X("SPG", "same_property_noi_growth", "SUP2025:tm263695d2", _SPG_NOI, ["FY2025"], FR, "8-K 2026-02-02 EX-99.1 earnings release, Results for the Year (domestic property NOI)", 0.01, note="domestic property NOI growth (company like-for-like measure)"),
    X("SPG", "same_property_noi_growth", "SUP2024:tm254065d2", _SPG_NOI, ["FY2024"], FR, "8-K 2025-02-04 EX-99.1 earnings release, Results for the Year", 0.01, note="domestic property NOI growth"),
    X("SPG", "same_property_noi_growth", "SUP2023:tm243752d2", _SPG_NOI, ["FY2023"], FR, "8-K 2024-02-05 EX-99.1 earnings release, Results for the Year", 0.01, note="domestic property NOI growth"),
    X("SPG", "same_property_noi_growth", "SUP2022:tm233979d2", _SPG_NOI, ["FY2022"], FR, "8-K 2023-02-06 EX-99.1 earnings release, Results for the Year", 0.01, note="domestic property NOI growth"),
    X("SPG", "ti_lc_income_preserving", 2025, r"Tenant Allowances\s*(\d+)\s*(\d+)\s*(\d+)\s*Operational Capital Expenditures\s*(\d+)\s*(\d+)\s*(\d+)", ["FY2025", "FY2024", "FY2023", None, None, None], USD, "Item 7 MD&A - capital expenditures on consolidated properties (cash basis)", 1e6, note="tenant allowances"),
    X("SPG", "maintenance_capex", 2025, r"Tenant Allowances\s*(\d+)\s*(\d+)\s*(\d+)\s*Operational Capital Expenditures\s*(\d+)\s*(\d+)\s*(\d+)", [None, None, None, "FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - capital expenditures on consolidated properties (cash basis)", 1e6, note="'Operational Capital Expenditures'"),
    X("SPG", "ti_lc_income_preserving", 2023, r"Tenant Allowances\s*(\d+)\s*(\d+)\s*(\d+)\s*Operational Capital Expenditures\s*(\d+)\s*(\d+)\s*(\d+)", [None, "FY2022", "FY2021", None, None, None], USD, "Item 7 MD&A - capital expenditures", 1e6, note="tenant allowances"),
    X("SPG", "maintenance_capex", 2023, r"Tenant Allowances\s*(\d+)\s*(\d+)\s*(\d+)\s*Operational Capital Expenditures\s*(\d+)\s*(\d+)\s*(\d+)", [None, None, None, None, "FY2022", "FY2021"], USD, "Item 7 MD&A - capital expenditures", 1e6, note="'Operational Capital Expenditures'"),
    X("SPG", "committed_undrawn_facilities", 2025, r"we had an aggregate available borrowing capacity of approximately \$([\d.]+) billion under the Credit Facilities", ["FY2025"], USD, "Item 7 - liquidity", 1e9, note="net of letters of credit"),
    A("SPG", "largest_tenant_share", "FY2025", 2025, "Item 1 / Item 2", r"(largest|top (five|ten|\d+)) tenants?|no (single )?tenant (accounted|represent)", "10-K FY2025 full text; the 4Q 2025 supplemental lists 'Top Tenants' (p.22) but the table is not in the converted exhibit text", unit=FR),
    A("SPG", "unencumbered_noi_share", "FY2025", 2025, "Item 7 / debt note", r"unencumbered (NOI|net operating income|assets|properties)[^.]{0,40}(\d+\.\d|\d\d)%", "10-K FY2025 full text (only single-property mentions of 'unencumbered')", unit=FR),
    A("SPG", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio|investment propert)", "10-K FY2025 full text"),
]

# ================================================================== FRT (Federal Realty, shopping centers)
_FRT_FFO = r"Funds from operations available for common shareholders[\s|$]*([\d,]+)[\s|$]*([\d,]+)[\s|$]*([\d,]+)"
_FRT_CAP = r"Tenant improvements and incentives[\s|$]*([\d,]+)[\s|$]*([\d,]+)[\s|$]*([\d,]+)[\s|$]*([\d,]+)[\s|$]*Total non-maintenance capital expenditures[\s|$]*[\d,]+[\s|$]*[\d,]+[\s|$]*[\d,]+[\s|$]*[\d,]+[\s|$]*Maintenance capital expenditures[\s|$]*([\d,]+)[\s|$]*([\d,]+)[\s|$]*([\d,]+)[\s|$]*([\d,]+)"
ROWS += [
    X("FRT", "reported_ffo", 2025, _FRT_FFO, ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - Funds from operations available for common shareholders (Nareit FFO)", 1e3, note="USD thousand x 1e3"),
    X("FRT", "reported_ffo", 2023, _FRT_FFO, [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - Funds from operations available for common shareholders", 1e3),
    X("FRT", "same_property_noi_growth", "SUP2025:xex991", r"comparable property operating income \(POI\) growth of ([\d.]+)% for the year", ["FY2025"], FR, "8-K 2026-02-12 EX-99.1 earnings release - comparable property POI", 0.01, note="comparable property POI growth excluding lease termination fees and prior-period rents"),
    X("FRT", "same_property_noi_growth", "SUP2024:xex991", r"comparable property operating income \(POI\) excluding lease termination fees and prior period rents collected growth of ([\d.]+)% for the year", ["FY2024"], FR, "8-K 2025-02-13 EX-99.1 earnings release - comparable property POI", 0.01, note="excluding lease termination fees and prior-period rents"),
    X("FRT", "same_property_noi_growth", "SUP2023:xex991", r"comparable property operating income \(POI\) excluding lease termination fees and prior period rents collected growth of ([\d.]+)% for the year", ["FY2023"], FR, "8-K 2024-02-12 EX-99.1 earnings release - comparable property POI", 0.01),
    X("FRT", "same_property_noi_growth", "SUP2022:xex991", r"comparable property operating income \(POI\) growth of [\d.]+% for the fourth quarter and ([\d.]+)% for the year", ["FY2022"], FR, "8-K 2023-02-08 EX-99.1 earnings release - comparable property POI", 0.01),
    X("FRT", "occupancy", 2025, r"real estate projects were [\d.]+% leased and ([\d.]+)% occupied at December 31, 2025", ["FY2025"], FR, "Item 1 - overview (portfolio occupied %)", 0.01, note="occupied (physical) %, all real estate projects"),
    X("FRT", "occupancy", "SUP2024:xex991", r"The portfolio was ([\d.]+)% occupied as of December 31, 2024", ["FY2024"], FR, "8-K 2025-02-13 EX-99.1 - Operational Update", 0.01, note="occupied %"),
    X("FRT", "occupancy", "SUP2023:xex991", r"The portfolio was ([\d.]+)% occupied", ["FY2023"], FR, "8-K 2024-02-12 EX-99.1 - Operational Update", 0.01, note="occupied %"),
    X("FRT", "occupancy", "SUP2022:xex991", r"The portfolio was ([\d.]+)% occupied as of December 31, 2022", ["FY2022"], FR, "8-K 2023-02-08 EX-99.1 - Operational Update", 0.01, note="occupied %"),
    X("FRT", "occupancy", "SUP2021:xex991", r"The portfolio was ([\d.]+)% occupied as of December 31, 2021", ["FY2021"], FR, "8-K 2022-02-10 EX-99.1 - Operational Update", 0.01, note="occupied %"),
    X("FRT", "ti_lc_income_preserving", "SUP2025:xex991", _FRT_CAP, [None, None, "FY2025", "FY2024", None, None, None, None], USD, "8-K 2026-02-12 EX-99.1 - Summary of Capital Expenditures", 1e3, note="'Tenant improvements and incentives' (company classes them as non-maintenance; the new / renewal split is not stated); leasing costs excluded"),
    X("FRT", "maintenance_capex", "SUP2025:xex991", _FRT_CAP, [None, None, None, None, None, None, "FY2025", "FY2024"], USD, "8-K 2026-02-12 EX-99.1 - Summary of Capital Expenditures", 1e3, note="'Maintenance capital expenditures'"),
    X("FRT", "ti_lc_income_preserving", "SUP2023:xex991", _FRT_CAP, [None, None, "FY2023", "FY2022", None, None, None, None], USD, "8-K 2024-02-12 EX-99.1 - Summary of Capital Expenditures", 1e3, note="'Tenant improvements and incentives'"),
    X("FRT", "maintenance_capex", "SUP2023:xex991", _FRT_CAP, [None, None, None, None, None, None, "FY2023", "FY2022"], USD, "8-K 2024-02-12 EX-99.1 - Summary of Capital Expenditures", 1e3, note="'Maintenance capital expenditures'"),
    X("FRT", "ti_lc_income_preserving", "SUP2021:xex991", _FRT_CAP, [None, None, "FY2021", None, None, None, None, None], USD, "8-K 2022-02-10 EX-99.1 - Summary of Capital Expenditures", 1e3, note="'Tenant improvements and incentives'"),
    X("FRT", "maintenance_capex", "SUP2021:xex991", _FRT_CAP, [None, None, None, None, None, None, "FY2021", None], USD, "8-K 2022-02-10 EX-99.1 - Summary of Capital Expenditures", 1e3, note="'Maintenance capital expenditures'"),
    X("FRT", "largest_tenant_share", 2025, r"no single tenant accounted for more than ([\d.]+)% of annualized base rent", ["FY2025"], FR, "Item 7 / Item 1 - tenant concentration", 0.01, note="upper bound: no single tenant above this share (largest tenant share)"),
    R("FRT", "committed_undrawn_facilities", "FY2025", 2025, 940.0e6, USD, "Item 7A / Item 7 - revolving credit facility", ("revolving credit facility, which bears interest at SOFR plus 77.5 basis points, of which $310.0 million was outstanding at December 31, 2025",), "$310.0 million", pre=40, post=20, note="derived: $1.25 billion commitment - $310.0 million outstanding = $940.0 million undrawn"),
    X("FRT", "secured_debt", 2025, r"Total mortgages payable, net[\s|$]*([\d,]+)", ["FY2025"], USD, "Item 8 - debt note, mortgages payable", 1e3, note="net of unamortized issuance costs"),
    R("FRT", "development_yield", "FY2025", "SUP2025:xex991", 0.07, FR, "8-K 2026-02-12 EX-99.1 - Willow Grove redevelopment (projected ROI)", ("projected return on investment (ROI) of 7%",), "7%", pre=160, post=20, note="PROJECTED ROI of one announced project, not a stabilized yield of completed projects"),
    A("FRT", "unencumbered_noi_share", "FY2025", 2025, "Item 7 / debt note", r"unencumbered (NOI|net operating income|POI|property operating income|assets)[^.]{0,40}\d+(\.\d)?%", "10-K FY2025 full text (only a generic financing-strategy mention of an unencumbered pool)", unit=FR),
    A("FRT", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio|investment propert)", "10-K FY2025 full text"),
]


def L(t, item, year, filing, anchor, label, col=0, scale=1e3, unit=USD, section="", note="", within=9000, pre=30, post=30):
    """Line item (balance-sheet face or note table): the first numbers after ``label`` in the ``within`` characters following ``anchor`` (both regexes on whitespace-collapsed text)."""
    return dict(t=t, item=item, year=year, filing=filing, anchor=anchor, label=label, col=col, scale=scale, unit=unit, section=section, note=note, within=within, pre=pre, post=post, value=None)


def Z(t, item, year, filing, section, absence, scope, note="", unit="units"):
    """Numeric zero backed by a verified absence regex (no match in the filing text)."""
    return dict(t=t, item=item, year=year, filing=filing, value="0.0", unit=unit, section=section, zero_absence=absence, scope=scope, note=note)


def N(t, item, year, filing, scope, unit=USD, note=""):
    """'not extracted': the item exists in a source that was not searched in this round (time-boxed); NOT the same as 'not disclosed'."""
    return dict(t=t, item=item, year=year, filing=filing, value="not extracted", unit=unit, section="-", scope=scope, note=note, nomatch=True)


# ================================================================== BXP (BXP, office)
_BXP_SP = r"Hotel Net Operating Income \(\d\).{0,500}?Net Operating Income \(Loss\) \$ [\d,]+ \$ [\d,]+ \$ \(?[\d,]+\)? (\(?[\d.]+\)?) %"
ROWS += [
    X("BXP", "reported_ffo", 2025, r"Diluted FFO attributable to (?:BXP|Boston Properties), Inc\.[^$]{0,14}\$ ([\d,]+) \$ ([\d,]+) \$ ([\d,]+)", ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - Diluted FFO attributable to BXP, Inc.", 1e3, note="USD thousand x 1e3"),
    X("BXP", "reported_ffo", 2023, r"Diluted FFO attributable to (?:BXP|Boston Properties), Inc\.[^$]{0,14}\$ ([\d,]+) \$ ([\d,]+) \$ ([\d,]+)", [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - Diluted FFO attributable to Boston Properties, Inc.", 1e3),
    X("BXP", "same_property_noi_growth", 2025, _BXP_SP, ["FY2025"], FR, "Item 7 MD&A - Same Property Portfolio net operating income (GAAP) % change", 0.01, note="same property NOI (GAAP basis, incl. residential and hotel)"),
    X("BXP", "same_property_noi_growth", 2023, _BXP_SP, ["FY2023"], FR, "Item 7 MD&A - Same Property Portfolio net operating income % change", 0.01),
    X("BXP", "occupancy", 2025, r"BXP.s total portfolio was ([\d.]+)% leased", ["FY2025"], FR, "Item 7 MD&A - portfolio overview (leased %, incl. signed leases not yet commenced)", 0.01, note="LEASED % (not physical occupancy)"),
    X("BXP", "occupancy", 2021, r"in-service portfolio was approximately ([\d.]+)% leased as of December 31, 2021", ["FY2021"], FR, "Item 7 MD&A - overview", 0.01, note="LEASED % (approximate)"),
    N("BXP", "occupancy", "FY2022-FY2024", 2025, "disclosed in the Q4 supplemental 'Occupancy by Location' tables; 10-K FY2023 / FY2025 do not state a comparable year-end percentage"),
    X("BXP", "largest_tenant_share", 2025, r"1\. (Salesforce) [\d,]+ ([\d.]+) %", [None, "FY2025"], FR, "Item 1 / Item 2 - Top 20 Clients by Square Feet (% of in-service portfolio)", 0.01, note="BASIS: share of in-service portfolio square feet (rent share not given)"),
    X("BXP", "committed_undrawn_facilities", 2025, r"Total Remaining Capacity \$ ([\d,]+) \$ [\d,]+", ["FY2025"], USD, "Item 7 - Liquidity: unsecured line of credit remaining capacity at December 31, 2025", 1e3, note="after $750.0 million commercial paper backstop and letters of credit"),
    A("BXP", "unencumbered_noi_share", "FY2025", 2025, "Item 7 / debt note", r"unencumbered (NOI|net operating income|properties)[^.]{0,60}\d+(\.\d+)?%", "10-K FY2025 full text (only covenant wording: unencumbered asset value not less than 150% of unsecured debt); the supplemental covenant table was not searched", unit=FR),
    A("BXP", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio|investment propert)", "10-K FY2025 full text"),
]

# ================================================================== ARE (Alexandria, life-science office)
_ARE_FFO = r"Funds from operations attributable to Alexandria Real Estate Equities, Inc\.[’'] ?s common stockholders - diluted\(\d\) ([\d,]+) ([\d,]+) ([\d,]+)"
ROWS += [
    X("ARE", "reported_ffo", 2025, _ARE_FFO, ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - FFO attributable to common stockholders - diluted (Nareit)", 1e3, note="USD thousand x 1e3"),
    X("ARE", "reported_ffo", 2023, _ARE_FFO, [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - FFO attributable to common stockholders - diluted", 1e3),
    X("ARE", "occupancy", 2025, r"occupancy percentage of our operating properties in North America was ([\d.]+)% as of December 31, 2025", ["FY2025"], FR, "Item 1 / Item 7 - operating properties in North America", 0.01),
    X("ARE", "occupancy", 2025, r"2023 \$[\d,]+ \$[\d.]+ [\d.]+ months [\d.]+% ([\d.]+)% 2024 \$[\d,]+ \$[\d.]+ [\d.]+ months [\d.]+% ([\d.]+)% 2025", ["FY2023", "FY2024"], FR, "Item 7 MD&A - capital expenditures / operating occupancy table (as of each period end)", 0.01),
    X("ARE", "occupancy", 2023, r"occupancy percentage of our operating properties in North America was ([\d.]+)% as of December 31, 2023", ["FY2023"], FR, "Item 1 / Item 7", 0.01),
    X("ARE", "occupancy", 2021, r"occupancy percentage of our operating properties in North America was ([\d.]+)% as of December 31, 2021", ["FY2021"], FR, "Item 1 / Item 7", 0.01),
    X("ARE", "same_property_noi_growth", 2025, r"Same property net operating income (?:decreased|increased) by ([\d.]+)% and (?:decreased|increased) by [\d.]+% \(cash basis\) for the year ended December 31, 2025", ["FY2025"], FR, "Item 7 MD&A - highlights (same property NOI, GAAP basis; sign: decrease)", -0.01, note="GAAP basis; the filing says DECREASED by 3.5% (cash basis +0.9%)"),
    X("ARE", "same_property_noi_growth", 2023, r"Same property net operating income growth of ([\d.]+)% and [\d.]+% \(cash basis\) for the year ended December 31, 2023", ["FY2023"], FR, "Item 7 MD&A - highlights (GAAP basis)", 0.01),
    X("ARE", "same_property_noi_growth", 2021, r"Same property net operating income growth of ([\d.]+)% and [\d.]+% \(cash basis\) for the year ended December 31, 2021", ["FY2021"], FR, "Item 7 MD&A - highlights (GAAP basis)", 0.01),
    X("ARE", "unencumbered_noi_share", 2025, r"Unencumbered net operating income as a percentage of total net operating income ([\d.]+)% ([\d.]+)% ([\d.]+)%", ["FY2025", "FY2024", "FY2023"], FR, "Item 7 - non-GAAP reconciliation (unencumbered NOI %)", 0.01),
    X("ARE", "largest_tenant_share", 2025, r"no individual tenant accounting for greater than ([\d.]+)% of our (?:aggregate )?annual rental revenue", ["FY2025"], FR, "Item 1 / Item 2 - top 20 tenants", 0.01, note="upper bound: no individual tenant above this share"),
    X("ARE", "committed_undrawn_facilities", 2025, r"Availability under our unsecured senior line of credit, net of amounts outstanding under our commercial paper program SOFR\+[\d.]+% \$[\d,]+ \$[\d,]+ \$([\d,]+)", ["FY2025"], USD, "Item 7 - Liquidity table (remaining commitments)", 1e3, note="net of commercial paper outstanding"),
    A("ARE", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio|investment propert)", "10-K FY2025 full text"),
]

# ================================================================== EQR (Equity Residential, residential)
_EQR_FFO = r"FFO available to Common Shares and Units / Units \(1\) \(3\) \(4\) \$? ?([\d,]+) \$? ?([\d,]+) \$? ?([\d,]+)"
_EQR_SP = r"NOI: Same store ([\d,]+) ([\d,]+) \(?[\d,]+ ?\)? (\(?[\d.]+ ?\)?) ?%"
ROWS += [
    X("EQR", "reported_ffo", 2025, _EQR_FFO, ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - FFO available to Common Shares and Units (Nareit)", 1e3, note="USD thousand x 1e3; includes OP units (about 4%)"),
    X("EQR", "reported_ffo", 2023, _EQR_FFO, [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - FFO available to Common Shares and Units", 1e3, note="includes OP units"),
    X("EQR", "same_property_noi_growth", 2025, _EQR_SP, [None, None, "FY2025"], FR, "Item 7 MD&A - results of operations, same store NOI", 0.01),
    X("EQR", "same_property_noi_growth", 2023, _EQR_SP, [None, None, "FY2023"], FR, "Item 7 MD&A - results of operations, same store NOI", 0.01),
    X("EQR", "same_property_noi_growth", 2021, _EQR_SP, [None, None, "FY2021"], FR, "Item 7 MD&A - results of operations, same store NOI", 0.01),
    X("EQR", "occupancy", 2025, r"For the year ended December 31, 2025, the Company.s same store Physical Occupancy was ([\d.]+)%", ["FY2025"], FR, "Item 7 MD&A - same store physical occupancy (year average)", 0.01, note="same-store physical occupancy, year average"),
    X("EQR", "occupancy", 2023, r"For the year ended December 31, 2023, the Company.s same store Physical Occupancy was ([\d.]+)%", ["FY2023"], FR, "Item 7 MD&A - same store physical occupancy", 0.01, note="same-store, year average"),
    X("EQR", "occupancy", 2021, r"As of December 31, 2021, the Company.s same store occupancy was ([\d.]+)%", ["FY2021"], FR, "Item 7 MD&A - same store occupancy at year end", 0.01, note="same-store, December 31"),
    X("EQR", "unencumbered_assets_share", 2025, r"or ([\d.]+)% was unencumbered", ["FY2025"], FR, "Item 7 - Liquidity and Capital Resources (unencumbered share of assets)", 0.01, note="share of total assets (balance sheet) unencumbered"),
    X("EQR", "unencumbered_assets_share", 2023, r"or ([\d.]+)% was unencumbered", ["FY2023"], FR, "Item 7 - Liquidity and Capital Resources", 0.01),
    X("EQR", "unencumbered_assets_share", 2021, r"or ([\d.]+)% was unencumbered", ["FY2021"], FR, "Item 7 - Liquidity and Capital Resources", 0.01),
    N("EQR", "ti_lc_income_preserving", "FY2021-FY2025", 2025, "residential: no TI/LC concept"),
    A("EQR", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio|investment propert)", "10-K FY2025 full text"),
]

# ================================================================== AVB (AvalonBay, residential)
ROWS += [
    X("AVB", "reported_ffo", 2025, r"Casualty loss and impairment on real estate [\d,]+ [\d,]+ FFO ([\d,]+) ([\d,]+) Adjusting items", ["FY2025", "FY2024"], USD, "Item 7 MD&A - FFO reconciliation (Nareit)", 1e3, note="USD thousand x 1e3"),
    X("AVB", "reported_ffo", 2023, r"FFO attributable to common stockholders \$ ([\d,]+) \$ ([\d,]+) Adjusting items", ["FY2023", "FY2022"], USD, "Item 7 MD&A - FFO attributable to common stockholders", 1e3),
    X("AVB", "reported_ffo", 2021, r"FFO attributable to common stockholders \$ ([\d,]+) \$ ([\d,]+) Adjusting items", ["FY2021", None], USD, "Item 7 MD&A - FFO attributable to common stockholders", 1e3),
    X("AVB", "same_property_noi_growth", 2025, r"The ([\d.]+)% increase in our Same Store Residential NOI in 2025", ["FY2025"], FR, "Item 7 MD&A - same store residential NOI", 0.01),
    X("AVB", "occupancy", "SUP2025:ex-992", r"Total Same Store [\d,]+ \$ [\d,]+ \$ [\d,]+ [\d.()-]+ % ([\d.]+) % ([\d.]+) %", ["FY2025", "FY2024"], FR, "8-K 2026-02-05 EX-99.2 earnings release attachment - same store economic occupancy", 0.01, note="ECONOMIC occupancy, same store"),
    X("AVB", "unencumbered_noi_share", "SUP2025:ex-992", r"Full Year 2025 Unencumbered NOI \(5\) ([\d.]+)%", ["FY2025"], FR, "8-K 2026-02-05 EX-99.2 - debt metrics", 0.01),
    X("AVB", "maintenance_capex", "SUP2025:ex-992", r"Total 95,416 \$ [\d,]+ \$ [\d,]+ \$ [\d,]+ \$ [\d,]+ \$ [\d,]+ \$ ([\d,]+) \$ [\d,]+", ["FY2025"], USD, "8-K 2026-02-05 EX-99.2 Attachment 8 - capitalized community expenditures, 'Asset Preservation' (total)", 1e3, note="company category 'Asset Preservation' (vs 'NOI Enhancing'); 2025 only, earlier years not extracted"),
    N("AVB", "committed_undrawn_facilities", "FY2025", 2025, "10-K text patterns for credit-facility availability returned nothing; the supplemental debt attachment was not read for it"),
    A("AVB", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio|investment propert)", "10-K FY2025 full text"),
]

# ================================================================== RE11 profile test inputs (EQR, EQIX, AMT): revenue breakdown and real estate leased to tenants (incl. PP&E)
ROWS += [
    X("EQR", "profile_rental_revenue", 2025, r"REVENUES Rental income \$ ([\d,]+) \$ [\d,]+ \$ [\d,]+ EXPENSES", ["FY2025"], USD, "Item 8 - consolidated statements of operations (rental income is the only revenue line)", 1e3),
    X("EQR", "profile_total_revenue", 2025, r"REVENUES Rental income \$ ([\d,]+) \$ [\d,]+ \$ [\d,]+ EXPENSES", ["FY2025"], USD, "Item 8 - statements of operations (rental income = total revenues)", 1e3, note="the statement has a single revenue line"),
    X("EQR", "profile_property_value", 2025, r"Investment in real estate, net ([\d,]+) [\d,]+ Investments in unconsolidated", ["FY2025"], USD, "Item 8 - balance sheet", 1e3),
    X("EQR", "profile_total_assets", 2025, r"Total assets \$ ([\d,]+) \$ [\d,]+ LIABILITIES AND EQUITY", ["FY2025"], USD, "Item 8 - balance sheet", 1e3),
    X("EQIX", "profile_rental_revenue", 2025, r"Colocation \(1\) \$ [\d,]+ \$ [\d,]+ \$ [\d,]+ \$ ([\d,]+) Interconnection", ["FY2025"], USD, "Note - segment / revenue disaggregation: colocation (space and power under lease; lease and non-lease components combined as one lease component under ASC 842)", 1e6, note="colocation counted as lease revenue; interconnection, managed infrastructure and other counted as services"),
    X("EQIX", "profile_total_revenue", 2025, r"Total revenues \(2\) [\d,]+ [\d,]+ [\d,]+ ([\d,]+) Less: Segment cost", ["FY2025"], USD, "Note - segment information", 1e6),
    X("EQIX", "profile_property_value", 2025, r"Property, plant and equipment, net ([\d,]+) [\d,]+ Operating lease right-of-use", ["FY2025"], USD, "Item 8 - balance sheet (data-center buildings, land and core systems leased to customers)", 1e6, note="PP&E net incl. core systems; the building / land part alone is smaller (gross buildings 11,170 + land 2,757)"),
    X("EQIX", "profile_total_assets", 2025, r"Total assets \$ ([\d,]+) \$ [\d,]+ Liabilities, Redeemable", ["FY2025"], USD, "Item 8 - balance sheet", 1e6),
    X("AMT", "profile_rental_revenue", 2025, r"Total property ([\d,.]+) [\d,.]+ [\d,.]+ Services [\d,.]+ [\d,.]+ [\d,.]+ Total revenues \$ [\d,.]+", ["FY2025"], USD, "Item 7 MD&A - property segment revenue (tenant leases on towers, small cells and data centers)", 1e6, note="'Total property' revenue"),
    X("AMT", "profile_total_revenue", 2025, r"Total property [\d,.]+ [\d,.]+ [\d,.]+ Services [\d,.]+ [\d,.]+ [\d,.]+ Total revenues \$ ([\d,.]+)", ["FY2025"], USD, "Item 7 MD&A - revenues", 1e6),
    X("AMT", "profile_property_value", 2025, r"Property and equipment, net \$ ([\d,.]+) \$ [\d,.]+ _", ["FY2025"], USD, "Note - property and equipment, net (towers, buildings, equipment)", 1e6, note="excludes goodwill and acquired tenant-related intangibles"),
    X("AMT", "profile_total_assets", 2025, r"Total assets \$ ([\d,.]+) \$ [\d,.]+ _", ["FY2025"], USD, "Note - segment assets / balance sheet", 1e6),
]

# ================================================================== EQIX (Equinix, data centers)
ROWS += [
    X("EQIX", "reported_ffo", 2025, r"FFO attributable to common stockholders \$ ([\d,]+) \$ ([\d,]+) \$ ([\d,]+)", ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - FFO reconciliation (Nareit)", 1e6, note="USD m x 1e6"),
    X("EQIX", "occupancy", 2025, r"cabinet utilization rates were approximately (\d+)% and (\d+)%", ["FY2025", "FY2024"], FR, "Item 7 MD&A - cabinet utilization (table A mapped metric: leased capacity / available capacity)", 0.01, note="cabinet utilization %"),
    X("EQIX", "occupancy", 2023, r"cabinet utilization rates were approximately (\d+)% and (\d+)%", ["FY2023", "FY2022"], FR, "Item 7 MD&A - cabinet utilization", 0.01, note="cabinet utilization %"),
    X("EQIX", "largest_tenant_share", 2025, r"largest customer accounted for approximately (\d+)% of our recurring revenues", ["FY2025"], FR, "Item 1 / Item 7 - customer concentration (share of recurring revenues)", 0.01, note="BASIS: recurring revenues"),
    X("EQIX", "committed_undrawn_facilities", 2025, r"approximately \$([\d.]+) billion of additional liquidity available to us from our \$[\d.]+ billion revolving", ["FY2025"], USD, "Item 7 - liquidity (revolving credit facility availability)", 1e9),
    N("EQIX", "same_property_noi_growth", "FY2021-FY2025", 2025, "the 10-K gives constant-currency revenue growth, not same-store NOI; the earnings release has 'same store' revenue growth; not extracted"),
    N("EQIX", "ti_lc_income_preserving", "FY2021-FY2025", 2025, "not a data-center concept (no TI/LC)"),
    A("EQIX", "unencumbered_noi_share", "FY2025", 2025, "10-K text", r"unencumbered[^.]{0,120}\d+(\.\d+)?%", "10-K FY2025 full text", unit=FR),
    A("EQIX", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio|investment propert|data center)", "10-K FY2025 full text"),
]

# ================================================================== PSA (Public Storage, self-storage)
_PSA_FFO = r"FFO allocable to common shares \$ ([\d,]+) \$ ([\d,]+) \(?[\d.]+\)? ?% \$ ([\d,]+) \$ ([\d,]+)"
_PSA_SP = r"Net operating income ([\d,]+) ([\d,]+) (\(?[\d.]+\)?) ?% ([\d,]+) ([\d,]+) (\(?[\d.]+\)?) ?% Depreciation and amortization expense"
_PSA_OCC = r"Weighted average for the period: Square foot occupancy ([\d.]+)% ([\d.]+)% \(?[\d.]+\)? ?% ([\d.]+)% ([\d.]+)%"
ROWS += [
    X("PSA", "reported_ffo", 2025, _PSA_FFO, ["FY2025", "FY2024", None, "FY2023"], USD, "Item 7 MD&A - reconciliation of net income to FFO (allocable to common shares)", 1e3, note="USD thousand x 1e3; excludes the FY2022 gain on the PS Business Parks interest"),
    X("PSA", "reported_ffo", 2023, _PSA_FFO, ["FY2023", "FY2022", None, "FY2021"], USD, "Item 7 MD&A - FFO allocable to common shares", 1e3),
    X("PSA", "same_property_noi_growth", 2025, _PSA_SP, [None, None, "FY2025", None, None, "FY2024"], FR, "Item 7 MD&A - Same Store Facilities net operating income % change", 0.01, note="Same Store Facilities NOI; the first row of the quoted table"),
    X("PSA", "same_property_noi_growth", 2023, _PSA_SP, [None, None, "FY2023", None, None, "FY2022"], FR, "Item 7 MD&A - Same Store Facilities net operating income % change", 0.01),
    X("PSA", "occupancy", 2025, _PSA_OCC, ["FY2025", "FY2024", None, "FY2023"], FR, "Item 7 MD&A - Same Store Facilities weighted average square foot occupancy", 0.01, note="weighted average for the year, same store"),
    X("PSA", "occupancy", 2023, _PSA_OCC, ["FY2023", "FY2022", None, "FY2021"], FR, "Item 7 MD&A - Same Store Facilities weighted average square foot occupancy", 0.01, note="weighted average for the year, same store"),
    X("PSA", "committed_undrawn_facilities", 2025, r"we have \$([\d.]+) billion available borrowing capacity on our revolving line of credit", ["FY2025"], USD, "Item 7 - liquidity", 1e9),
    N("PSA", "ti_lc_income_preserving", "FY2021-FY2025", 2025, "self-storage has no TI/LC concept"),
    A("PSA", "unencumbered_noi_share", "FY2025", 2025, "10-K text", r"unencumbered[^.]{0,120}\d+(\.\d+)?%", "10-K FY2025 full text", unit=FR),
    A("PSA", "fair_value_real_estate", "FY2025", 2025, "10-K text", r"estimated fair value of (our )?(real estate|properties|portfolio|investment propert|facilities)", "10-K FY2025 full text"),
]

# ================================================================== WELL (Welltower): STANDARD under RE10 - no extraction round-2 items (rental share 18%); AMT likewise after RE11

# PSA income-statement lines (no XBRL tag for property-level revenue / cost; used for NOI and for the profile test)
_PSA_IS = r"Revenues: Self-storage facilities \$ ([\d,]+) \$ ([\d,]+) \$ ([\d,]+) Ancillary operations [\d,]+ [\d,]+ [\d,]+ Total revenues ([\d,]+) ([\d,]+) ([\d,]+) Expenses: Self-storage cost of operations ([\d,]+) ([\d,]+) ([\d,]+)"
_PSA_IS23 = r"Revenues: Self-storage facilities \$ ([\d,]+) \$ ([\d,]+) \$? ?([\d,]+) Ancillary operations [\d,]+ [\d,]+ [\d,]+ [\d,]+ [\d,]+ [\d,]+ Expenses: Self-storage cost of operations ([\d,]+) ([\d,]+) ([\d,]+)"
ROWS += [
    X("PSA", "rental_revenue_extracted", 2025, _PSA_IS, ["FY2025", "FY2024", "FY2023", None, None, None, None, None, None], USD, "Item 8 - consolidated statements of income: self-storage facilities revenue", 1e3),
    X("PSA", "rental_revenue_extracted", 2023, _PSA_IS23, ["FY2023", "FY2022", "FY2021", None, None, None], USD, "Item 8 - consolidated statements of income: self-storage facilities revenue", 1e3),
    X("PSA", "property_opex_extracted", 2025, _PSA_IS, [None, None, None, None, None, None, "FY2025", "FY2024", "FY2023"], USD, "Item 8 - consolidated statements of income: self-storage cost of operations", 1e3),
    X("PSA", "property_opex_extracted", 2023, _PSA_IS23, [None, None, None, "FY2023", "FY2022", "FY2021"], USD, "Item 8 - consolidated statements of income: self-storage cost of operations", 1e3),
    X("PSA", "profile_rental_revenue", 2025, _PSA_IS, ["FY2025"] + [None] * 8, USD, "Item 8 - statements of income (self-storage facilities)", 1e3),
    X("PSA", "profile_total_revenue", 2025, _PSA_IS, [None, None, None, "FY2025"] + [None] * 5, USD, "Item 8 - statements of income (total revenues)", 1e3),
    X("BXP", "debt_total_bs", 2021, r"\$ ([\d,]+) \$ [\d,]+ December 31, 2021 2020 Consolidated Debt Financing Statistics", ["FY2021"], USD, "Item 7 - debt summary (consolidated debt carrying value at December 31, 2021)", 1e3, note="round 1 left BXP FY2016-FY2021 debt missing (tag implausible); FY2021 is the t-4 point"),
]


# ================================================================== ROUND 3 (2026-10-14_13-50: RE15-RE21, C15) - extraction completion
# ARE: non-revenue-enhancing capex from each fiscal year's Q4 supplemental (five quarterly columns; the fiscal year = the first four columns)
_ARE_CAP = (r"Non-revenue-enhancing capital expenditures: Building improvements \$ ?([\d,]+)(?: \(\d\))? \$ ?([\d,]+)(?: \(\d\))? \$ ?([\d,]+)(?: \(\d\))? \$ ?([\d,]+)(?: \(\d\))? \$ ?([\d,]+)(?: \(\d\))? "
            r"Tenant improvements and leasing commissions \$ ?([\d,]+)(?: \(\d\))? \$ ?([\d,]+)(?: \(\d\))? \$ ?([\d,]+)(?: \(\d\))? \$ ?([\d,]+)(?: \(\d\))? \$ ?([\d,]+)")
for _y, _frag in ((2025, "a4q25ex991supp"), (2024, "a4q24ex991supp"), (2023, "a4q23ex991supp"), (2022, "a4q22ex991supp"), (2021, "a4q21ex991supp")):
    ROWS += [
        X("ARE", "maintenance_capex", f"SUP{_y}:{_frag}", _ARE_CAP, [f"FY{_y}"], USD, f"Q4 {_y} supplemental - non-revenue-enhancing capital expenditures: building improvements (sum of the four quarters of {_y})", 1e3,
          agg=(f"FY{_y}", [0, 1, 2, 3]), note="non-revenue-enhancing building improvements = maintenance-type capex; USD thousand x 1e3"),
        X("ARE", "ti_lc_income_preserving", f"SUP{_y}:{_frag}", _ARE_CAP, [f"FY{_y}"], USD, f"Q4 {_y} supplemental - non-revenue-enhancing capital expenditures: tenant improvements and leasing commissions (sum of the four quarters of {_y})", 1e3,
          agg=(f"FY{_y}", [5, 6, 7, 8]), note="company classes these TI/LC as non-revenue-enhancing (income-preserving); USD thousand x 1e3"),
    ]

# EQR: capital expenditures to real estate by category (10-K FY2021-FY2024; FY2025 gives the total only)
_EQR_CAP = (r"Building Improvements \$ ([\d,]+) \$ ([\d,]+)(?: \(\d\))? \$ ([\d,]+) \$ ([\d,]+) Renovation Expenditures(?: \(\d\))? ([\d,]+)(?: \(\d\))? ([\d,]+)(?: \(\d\))? ([\d,]+) ([\d,]+) "
            r"Replacements ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)")
for _y in (2021, 2022, 2023, 2024):
    ROWS.append(X("EQR", "maintenance_capex", _y, _EQR_CAP, [f"FY{_y}"], USD, f"Item 7 MD&A - capital expenditures to real estate FY{_y}: building improvements + replacements (unit turnover)", 1e3, agg=(f"FY{_y}", [2, 10]),
                  note="recurring capex = building improvements + replacements (appliances, flooring); renovation expenditures (value-add) excluded; USD thousand x 1e3"))
ROWS.append(A("EQR", "maintenance_capex", "FY2025", 2025, "Item 7 MD&A - capital expenditures to real estate", r"Building Improvements \$ [\d,]+", "10-K FY2025 full text: the FY2025 filing gives total capital expenditures to real estate ($342.0 million) without the building-improvement / renovation / replacement split"))

# ------------------------------------------------------------------ RE17: FFO reconciliation lines (real-estate-related D&A incl. unconsolidated JV share; OP-unit / noncontrolling adjustments)
_N = r"(\(?[\d,]+ ?\)?|\u2014|\ufffd)"


def _gr(k):
    return " ".join([_N] * k)


def RC(t, filing, regex, years, da_groups, nci_groups=None, jv_groups=None, section="Item 7 MD&A - FFO reconciliation", scale=1e3, note=""):
    """Rows recon_re_da / recon_nci_adjust / recon_jv_other_adjust per fiscal year: the value is the signed sum of the selected regex groups (as printed in the company's reconciliation)."""
    rows = []
    for i, y in enumerate(years):
        if y is None:
            continue
        for item, grp in (("recon_re_da", da_groups), ("recon_nci_adjust", nci_groups), ("recon_jv_other_adjust", jv_groups)):
            if grp is None or grp[i] is None:
                continue
            rows.append(X(t, item, filing, regex, [y], USD, section, scale, agg=(y, grp[i]), note=note))
    return rows


def _O_re(k):
    return (rf"Depreciation and amortization {_gr(k)} Depreciation of furniture, fixtures and equipment {_gr(k)} Provisions for impairment(?: of real estate)? {_gr(k)} "
            rf"Gain on sales of real estate {_gr(k)} Proportionate share of adjustments for unconsolidated entities(?: \(\d\))? {_gr(k)} FFO adjustments allocable to noncontrolling interests {_gr(k)}")


_NOTE_O = "D&A + depreciation of furniture, fixtures and equipment (negative) + proportionate share of adjustments for unconsolidated entities; NCI = FFO adjustments allocable to noncontrolling interests"
ROWS += RC("O", 2025, _O_re(2), ["FY2025", "FY2024"], [[0, 2, 8], [1, 3, 9]], [[10], [11]], note=_NOTE_O)
ROWS += RC("O", 2023, _O_re(2), ["FY2023", "FY2022"], [[0, 2, 8], [1, 3, 9]], [[10], [11]], note=_NOTE_O)
ROWS += RC("O", 2021, _O_re(3), ["FY2021", None, None], [[0, 3, 12], None, None], [[15], None, None], note=_NOTE_O)

_PLD_re = (rf"Real estate related depreciation and amortization {_gr(2)} Gains on other dispositions of investments in real estate, net of taxes(?: \(excluding development properties and land\))? {_gr(2)} "
           rf"(?:Adjustments|Reconciling items) related to noncontrolling interests {_gr(2)} (?:Our proportionate share of adjustments related to|Our share of reconciling items included in earnings related to) unconsolidated entities {_gr(2)} NAREIT defined FFO")
_NOTE_PLD = "real estate related D&A + our (proportionate) share of reconciling items of unconsolidated entities; NCI = adjustments related to noncontrolling interests; USD million x 1e6"
ROWS += RC("PLD", 2025, _PLD_re, ["FY2025", "FY2024"], [[0, 6], [1, 7]], [[4], [5]], scale=1e6, note=_NOTE_PLD)
ROWS += RC("PLD", 2023, _PLD_re, ["FY2023", "FY2022"], [[0, 6], [1, 7]], [[4], [5]], scale=1e6, note=_NOTE_PLD)
ROWS += RC("PLD", 2021, _PLD_re, ["FY2021", None], [[0, 6], None], [[4], None], scale=1e6, note=_NOTE_PLD)

_SPG_re = (rf"Depreciation and amortization from consolidated properties {_gr(3)} Our share of depreciation and amortization from unconsolidated entities.{{0,160}}? {_gr(3)} "
           rf"\(Gain\) loss .{{0,200}}? {_gr(3)} Net \(gain\) loss attributable to noncontrolling interest holders in properties {_gr(3)} Noncontrolling interests portion of depreciation and amortization {_gr(3)}")
_NOTE_SPG = "D&A from consolidated properties + our share of D&A from unconsolidated entities (incl. Klepierre, TRG) + noncontrolling interests' portion of D&A (negative); NCI = net (gain) loss attributable to noncontrolling interest holders in properties"
ROWS += RC("SPG", 2025, _SPG_re, ["FY2025", "FY2024", "FY2023"], [[0, 3, 12], [1, 4, 13], [2, 5, 14]], [[9], [10], [11]], note=_NOTE_SPG)
_SPG_re_old = (rf"Depreciation and amortization from consolidated properties {_gr(3)} Our share of depreciation and amortization from unconsolidated entities.{{0,160}}? {_gr(3)} "
               rf"(?:Loss \(gain\)|\(Gain\) loss) .{{0,200}}? {_gr(3)} Unrealized losses in fair value of publicly traded equity instruments, net, excluded from FFO \(A\) {_gr(3)} "
               rf"Net (?:loss \(income\)|\(gain\) loss|income \(loss\)) attributable to noncontrolling interest holders in properties {_gr(3)} Noncontrolling interests portion of depreciation and amortization[^0-9(]{{0,100}} {_gr(3)}")
ROWS += RC("SPG", 2023, _SPG_re_old, [None, "FY2022", "FY2021"], [None, [1, 4, 16], [2, 5, 17]], [None, [13], [14]], note=_NOTE_SPG)

_FRT_re = (rf"Depreciation and amortization of real estate assets {_gr(3)} Amortization of initial direct costs of leases {_gr(3)} Funds from operations {_gr(3)} Dividends on preferred shares(?: \(\d\))? {_gr(3)} "
           rf"Income attributable to downREIT operating partnership units {_gr(3)} Income attributable to unvested shares {_gr(3)}")
_NOTE_FRT = "D&A of real estate assets + amortization of initial direct costs of leases; NCI/OP = income attributable to downREIT OP units + income attributable to unvested shares (negative)"
ROWS += RC("FRT", 2025, _FRT_re, ["FY2025", "FY2024", "FY2023"], [[0, 3], [1, 4], [2, 5]], [[12, 15], [13, 16], [14, 17]], note=_NOTE_FRT)
ROWS += RC("FRT", 2023, _FRT_re, [None, "FY2022", "FY2021"], [None, [1, 4], [2, 5]], [None, [13, 16], [14, 17]], note=_NOTE_FRT)

_BXP_re = (rf"Add: Noncontrolling interest.common units of the Operating Partnership {_gr(3)} Noncontrolling interests in property partnerships {_gr(3)} Net income {_gr(3)} "
           rf"Add: Depreciation and amortization {_gr(3)} Noncontrolling interests in property partnerships.? share of depreciation and amortization {_gr(3)} "
           rf"BXP.s share of depreciation and amortization from unconsolidated joint ventures {_gr(3)} Corporate-related depreciation and amortization {_gr(3)} Non-real estate depreciation and amortization {_gr(3)} "
           rf".{{0,140}}? Impairment losses {_gr(3)} Impairment losses included within [^0-9]{{0,80}}? {_gr(3)} Less: Gain on sale / consolidation included within [^0-9]{{0,80}}? {_gr(3)} "
           rf".{{0,900}}? Less: Noncontrolling interest.common units of the Operating Partnership.s share of funds from operations {_gr(3)}")
_NOTE_BXP = ("D&A - noncontrolling property partnerships' share + share of unconsolidated JV D&A + corporate-related and non-real-estate D&A (as printed); JV other = impairment losses included in loss from unconsolidated JVs - gains "
             "included there; NCI = net income of OP unitholders - their share of FFO (our net income is BXP Inc.'s)")
ROWS += RC("BXP", 2025, _BXP_re, ["FY2025", "FY2024", "FY2023"], [[9, 12, 15, 18, 21], [10, 13, 16, 19, 22], [11, 14, 17, 20, 23]], [[0, (33, -1)], [1, (34, -1)], [2, (35, -1)]],
           [[27, (30, -1)], [28, (31, -1)], [29, (32, -1)]], note=_NOTE_BXP)
_BXP_re23 = (rf"Add: Preferred stock redemption charge {_gr(3)} Preferred dividends {_gr(3)} Noncontrolling interest.common units of the Operating Partnership {_gr(3)} Noncontrolling interests in property partnerships {_gr(3)} "
             rf"Net income {_gr(3)} Add: Depreciation and amortization {_gr(3)} Noncontrolling interests in property partnerships.? share of depreciation and amortization {_gr(3)} "
             rf"BXP.s share of depreciation and amortization from unconsolidated joint ventures {_gr(3)} Corporate-related depreciation and amortization {_gr(3)} Non-real estate depreciation and amortization {_gr(3)} "
             rf"Impairment losses included within loss from unconsolidated joint ventures \(\d\) {_gr(3)} Less: Gain on sale of real estate included within loss from unconsolidated joint ventures \(\d\) {_gr(3)} "
             rf"Gain \(loss\) on sale / consolidation included within loss from unconsolidated joint ventures \(\d\) {_gr(3)} Gain on investment included within loss from unconsolidated joint ventures \(\d\) {_gr(3)} "
             rf".{{0,500}}? Funds from Operations \(FFO\) attributable to the Operating Partnership common unitholders \(including Boston Properties, Inc\.\) {_gr(3)} "
             rf"Less: Noncontrolling interest.common units of the Operating Partnership.s share of funds from operations {_gr(3)}")
ROWS += RC("BXP", 2023, _BXP_re23, [None, "FY2022", "FY2021"], [None, [16, 19, 22, 25, 28], [17, 20, 23, 26, 29]], [None, [7, (46, -1)], [8, (47, -1)]],
           [None, [31, (34, -1), (37, -1), (40, -1)], [32, (35, -1), (38, -1), (41, -1)]], note=_NOTE_BXP)

_ARE_re = (rf"Depreciation and amortization of real estate assets {_gr(3)} Noncontrolling share of depreciation and amortization from consolidated real estate JVs {_gr(3)} "
           rf"Our share of depreciation and amortization from unconsolidated real estate JVs {_gr(3)} .{{0,400}}? Allocation to unvested restricted stock awards {_gr(3)} Funds from operations attributable")
_NOTE_ARE = "D&A of real estate assets - noncontrolling share of D&A of consolidated real estate JVs + our share of D&A of unconsolidated real estate JVs; NCI = allocation to unvested restricted stock awards"
ROWS += RC("ARE", 2025, _ARE_re, ["FY2025", "FY2024", "FY2023"], [[0, 3, 6], [1, 4, 7], [2, 5, 8]], [[9], [10], [11]], note=_NOTE_ARE)
ROWS += RC("ARE", 2023, _ARE_re, [None, "FY2022", "FY2021"], [None, [1, 4, 7], [2, 5, 8]], [None, [10], [11]], note=_NOTE_ARE)

_EQR_re = (rf"Adjustments: Depreciation {_gr(3)} Depreciation - Non-real estate additions {_gr(3)} Depreciation - Partially Owned Properties {_gr(3)} Depreciation - Unconsolidated Properties {_gr(3)}")
_NOTE_EQR = "depreciation - non-real-estate additions - partially owned properties' share + unconsolidated properties' share (as printed in the Nareit FFO reconciliation)"
ROWS += RC("EQR", 2025, _EQR_re, ["FY2025", "FY2024", "FY2023"], [[0, 3, 6, 9], [1, 4, 7, 10], [2, 5, 8, 11]], note=_NOTE_EQR)
ROWS += RC("EQR", 2023, _EQR_re, [None, "FY2022", "FY2021"], [None, [1, 4, 7, 10], [2, 5, 8, 11]], note=_NOTE_EQR)

_AVB_re = rf"Depreciation - real estate assets, including joint venture adjustments {_gr(2)} (?:Income attributable to|Distributions to) noncontrolling interests {_gr(2)}"
_NOTE_AVB = "depreciation - real estate assets, including joint venture adjustments; NCI = income attributable to noncontrolling interests (added back in the company's FFO)"
ROWS += RC("AVB", 2025, _AVB_re, ["FY2025", "FY2024"], [[0], [1]], [[2], [3]], note=_NOTE_AVB)
ROWS += RC("AVB", 2023, _AVB_re, ["FY2023", "FY2022"], [[0], [1]], [[2], [3]], note=_NOTE_AVB)
ROWS += RC("AVB", 2021, _AVB_re, ["FY2021", None], [[0], None], [[2], None], note=_NOTE_AVB)

_PSA_re = (rf"Real estate-related depreciation and amortization {_gr(4)} Real estate-related depreciation from unconsolidated real estate investments? {_gr(4)} "
           rf"Real estate-related depreciation allocated to noncontrolling interests[^0-9(]{{0,100}} {_gr(4)}")
_NOTE_PSA = "real estate-related D&A + the share from unconsolidated real estate investments - the part allocated to noncontrolling interests and unvested units (as printed)"
ROWS += RC("PSA", 2025, _PSA_re, ["FY2025", "FY2024", None, "FY2023"], [[0, 4, 8], [1, 5, 9], None, [3, 7, 11]], note=_NOTE_PSA)
ROWS += RC("PSA", 2023, _PSA_re, [None, "FY2022", None, "FY2021"], [None, [1, 5, 9], None, [3, 7, 11]], note=_NOTE_PSA)

# ------------------------------------------------------------------ EQIX: real-estate depreciation (+ JV adjustment) and recurring capex from the FFO / AFFO reconciliation
_EQIX_re = rf"Real estate depreciation {_gr(3)} \(Gain\) loss on disposition of real estate (?:assets|property) {_gr(3)} Adjustments for FFO from unconsolidated joint ventures {_gr(3)}"
_NOTE_EQIX = "real estate depreciation + adjustments for FFO from unconsolidated joint ventures (company reconciliation)"
ROWS += RC("EQIX", 2025, _EQIX_re, ["FY2025", "FY2024", "FY2023"], [[0, 6], [1, 7], [2, 8]], scale=1e6, note=_NOTE_EQIX)
ROWS += RC("EQIX", 2023, _EQIX_re, [None, "FY2022", "FY2021"], [None, [1, 7], [2, 8]], scale=1e3, note=_NOTE_EQIX)
ROWS += [
    X("EQIX", "maintenance_capex", 2025, r"Recurring capital expenditures \(([\d,]+)\) \(([\d,]+)\) \(([\d,]+)\)", ["FY2025", "FY2024", "FY2023"], USD, "Item 7 MD&A - AFFO reconciliation: recurring capital expenditures", 1e6,
      note="company-defined recurring capex (expenditures to extend the useful life of data centers); USD million x 1e6"),
    X("EQIX", "maintenance_capex", 2023, r"Recurring capital expenditures \(([\d,]+)\) \(([\d,]+)\) \(([\d,]+)\)", [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - AFFO reconciliation: recurring capital expenditures", 1e3, note="USD thousand x 1e3"),
    X("EQIX", "reported_ffo", 2023, r"FFO attributable to common shareholders \$ ([\d,]+) \$ ([\d,]+) \$ ([\d,]+)", [None, "FY2022", "FY2021"], USD, "Item 7 MD&A - FFO reconciliation (Nareit)", 1e3, note="USD thousand x 1e3"),
    A("EQIX", "ti_lc_income_preserving", "FY2021-FY2025", 2025, "10-K text", r"tenant improvements and leasing commissions", "10-K FY2025 full text: data-center operator, no TI/LC concept (stored as not applicable, not 0)"),
]

# ------------------------------------------------------------------ EQR facilities; yields not disclosed in the 10-Ks; AMT essentials (RE15: now an INCOME_REAL_ESTATE candidate)
ROWS += [
    X("EQR", "committed_undrawn_facilities", 2025, r"Unsecured revolving credit facility availability \$ ([\d,]+) \$ [\d,]+", ["FY2025"], USD, "Item 7 - Liquidity: availability on the unsecured revolving credit facility at December 31, 2025", 1e3, note="$2.5 billion commitment less commercial paper outstanding and restricted amounts"),
]
for _t, _scope in (("ARE", "10-K FY2025: initial stabilized yields are defined but the numbers are not given in the filing ('we expect to provide ... over time'); supplemental not searched"),
                   ("AVB", "10-K FY2025 text: no stabilized / projected NOI yield; supplemental earnings release (attachment 9 development) not read for yields"),
                   ("EQR", "10-K FY2025 text: no stabilized yield"), ("PSA", "10-K FY2025 text: no stabilized yield on development"), ("EQIX", "10-K FY2025 text: no stabilization yield"),
                   ("BXP", "10-K FY2025 text: estimated stabilization dates and investment, no yield; supplemental not searched"),
                   ("SPG", "10-K FY2025: only a policy target ('stabilized return on invested capital in the range of 8-10%'), no yield on completed projects")):
    ROWS.append(A(_t, "development_yield", "FY2025", 2025, "Item 7 MD&A", r"(stabilized|initial stabilized|projected NOI|expected|untrended) (NOI )?(yield|return)[^.]{0,20}(of|was|were|at) \d+(\.\d+)? ?%", _scope, unit=FR))
ROWS += [
    X("AMT", "largest_tenant_share", 2025, r"T-Mobile ([\d]+) ?% ([\d]+) ?% ([\d]+) ?%", ["FY2025"], FR, "Item 1A / Note - customers above 10% of revenue (T-Mobile)", 0.01, note="share of total revenue"),
    A("AMT", "occupancy", "FY2025", 2025, "Table A", r"occupancy rate of [\d.]+%", "towers: no occupancy metric (table A: not applicable)", unit=FR),
]

# ================================================================== ROUND 4: AMT FFO reconciliation FY2021-FY2025 (consolidated net income start, as in the company's table)
_AMT_re = (r"Net income (?:\(1\) )?\$ ([\d,.]+) \$ ([\d,.]+) \(?\d+\)? ?% Real estate related depreciation, amortization and accretion ([\d,.]+) ([\d,.]+) \(?\d+\)? "
           r"Losses from sale or disposal of real estate and real estate related impairment charges \(\d\) ([\d,.]+) ([\d,.]+) \(?\d+\)? .{0,420}? "
           r"Nareit FFO attributable to American Tower Corporation common stockholders \$ ([\d,.]+) \$ ([\d,.]+)")
_NOTE_AMT = ("company reconciliation starts from consolidated net income (incl. noncontrolling interests); RE D&A = real estate related depreciation, amortization and accretion; "
             "NCI/other = residual of the middle lines (dividends to NCI, adjustments and distributions for unconsolidated affiliates and noncontrolling interests, discontinued operations) = FFO - net income - D&A - losses; USD million x 1e6")
for _doc, _yrs in ((2025, ("FY2025", "FY2024")), (2023, ("FY2023", "FY2022")), (2021, ("FY2021", None))):
    for _i, _y in enumerate(_yrs):
        if _y is None:
            continue
        ROWS += [
            X("AMT", "recon_net_income", _doc, _AMT_re, [_y], USD, "Item 7 MD&A - Net income / Nareit FFO reconciliation: consolidated net income", 1e6, agg=(_y, [_i]), note=_NOTE_AMT),
            X("AMT", "recon_re_da", _doc, _AMT_re, [_y], USD, "Item 7 MD&A - Nareit FFO reconciliation: real estate related D&A and accretion", 1e6, agg=(_y, [2 + _i]), note=_NOTE_AMT),
            X("AMT", "recon_nci_adjust", _doc, _AMT_re, [_y], USD, "Item 7 MD&A - Nareit FFO reconciliation: noncontrolling / unconsolidated / discontinued adjustments (residual)", 1e6,
              agg=(_y, [6 + _i, (_i, -1), (2 + _i, -1), (4 + _i, -1)]), note=_NOTE_AMT),
            X("AMT", "reported_ffo", _doc, _AMT_re, [_y], USD, "Item 7 MD&A - Nareit FFO attributable to AMT common stockholders", 1e6, agg=(_y, [6 + _i]), note=_NOTE_AMT),
        ]

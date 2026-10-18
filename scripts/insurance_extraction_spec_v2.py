"""Extraction spec additions for INSURANCE round 2 (spec 2026-10-13_11-45): balance-sheet categories (Q2) and changes in group structure (Q4).

Q2 items (USD mm, latest year): bs_short_term, bs_fixed_maturities, bs_equity, bs_illiquid_loans (mortgage / policy / private loans), bs_real_estate,
bs_other_invested (limited partnerships, funds, other invested assets), bs_total_investments (as reported; note INCLUDES_CASH when the reported total
contains cash). Cash comes from the cash tag (``bs_cash`` overrides it). Rows whose value is a sum say so in the note (DERIVED).
"""
from insurance_extraction_spec import MM, r

S2 = []


def bs(t, item, value, section, tokens, verify, pre=20, post=60, note=""):
    return r(t, item, value, MM, section, tokens, verify, pre=pre, post=post, note=note)


S2 += [
    # --- CB (MD&A invested assets, fair value)
    bs("CB", "bs_short_term", 4840, "MD&A - Invested assets (fair value)", ("Short-term investments", "$", "4,840", "$", "4,840", "$", "5,142"), "4,840"),
    bs("CB", "bs_fixed_maturities", 130771, "MD&A - Invested assets (fair value)",
       ("Other Investments - Fixed Maturities", "8,091", "8,091", "6,265", "6,265", "Fixed maturities available-for-sale", "122,680"), "122,680",
       note="DERIVED = other investments - fixed maturities 8,091 + fixed maturities available-for-sale 122,680"),
    bs("CB", "bs_equity", 10801, "MD&A - Invested assets (fair value)", ("Equity securities", "10,801", "10,801", "9,151"), "10,801"),
    bs("CB", "bs_other_invested", 22342, "MD&A - Invested assets (fair value)",
       ("Private debt held-for-investment", "2,445", "2,411", "2,680", "2,628", "Private equities and other", "19,897"), "19,897",
       note="DERIVED = private debt held-for-investment 2,445 + private equities and other 19,897"),
    bs("CB", "bs_total_investments", 168754, "MD&A - Invested assets (fair value)", ("Total investments", "$", "168,754"), "168,754"),
    # --- TRV (balance sheet)
    bs("TRV", "bs_fixed_maturities", 89833, "Balance sheet", ("allowance for expected credit losses of $3 and $2)", "$", "89,833"), "89,833", pre=60),
    bs("TRV", "bs_equity", 618, "Balance sheet", ("Equity securities, at fair value (cost $457 and $544)", "618"), "618"),
    bs("TRV", "bs_real_estate", 900, "Balance sheet", ("Real estate investments", "900", "902"), "900"),
    bs("TRV", "bs_short_term", 5716, "Balance sheet", ("Short-term securities", "5,716"), "5,716"),
    bs("TRV", "bs_other_invested", 4115, "Balance sheet", ("Other investments", "4,115", "4,202"), "4,115"),
    bs("TRV", "bs_total_investments", 101182, "Balance sheet", ("Total investments", "101,182"), "101,182"),
    # --- PGR (balance sheet, annual report exhibit)
    bs("PGR", "bs_fixed_maturities", 82866, "Balance sheet", ("Fixed maturities (amortized cost: $82,704 and $77,126)", "$", "82,866"), "82,866"),
    bs("PGR", "bs_short_term", 10005, "Balance sheet", ("Short-term investments (amortized cost: $10,005 and $615)", "10,005"), "10,005"),
    bs("PGR", "bs_equity", 4502, "Balance sheet", ("Total equity securities", "4,502", "4,303"), "4,502"),
    bs("PGR", "bs_total_investments", 97373, "Balance sheet", ("Total investments", "97,373", "80,250"), "97,373"),
    # --- ALL (statement of financial position)
    bs("ALL", "bs_fixed_maturities", 59115, "Statement of financial position",
       ("Fixed income securities, at fair value (amortized cost, net $58,730 and $53,616)", "$", "59,115"), "59,115"),
    bs("ALL", "bs_equity", 8398, "Statement of financial position", ("Equity securities, at fair value (cost $8,026 and $4,329)", "8,398"), "8,398"),
    bs("ALL", "bs_illiquid_loans", 879, "Statement of financial position", ("Mortgage loans, net", "879", "784"), "879"),
    bs("ALL", "bs_other_invested", 9958, "Statement of financial position", ("Limited partnership interests", "8,844", "9,255"), "8,844", post=260,
       note="DERIVED = limited partnership interests 8,844 + other investments, net 1,114"),
    bs("ALL", "bs_short_term", 4887, "Statement of financial position", ("Short-term, at fair value (amortized cost $4,888 and $4,539)", "4,887"), "4,887"),
    bs("ALL", "bs_total_investments", 83237, "Statement of financial position", ("Total investments", "83,237", "72,610"), "83,237"),
    # --- WRB (MD&A investment portfolio, USD thousands -> mm; the reported total includes cash)
    bs("WRB", "bs_fixed_maturities", 25047.662, "MD&A - Investment portfolio", ("Total fixed maturity securities", "25,047,662"), "25,047,662", note="USD thousands in the filing"),
    bs("WRB", "bs_equity", 2579.304, "MD&A - Investment portfolio", ("Total equity securities available for sale", "1,358,201"), "1,358,201", post=40,
       note="DERIVED (USD thousands) = equity securities available for sale 1,358,201 + arbitrage trading account 1,221,103 (merger-arbitrage equities)"),
    bs("WRB", "bs_other_invested", 1361.802, "MD&A - Investment portfolio", ("Investment funds", "1,361,802"), "1,361,802", note="USD thousands in the filing"),
    bs("WRB", "bs_real_estate", 1279.748, "MD&A - Investment portfolio", ("Real estate", "1,279,748"), "1,279,748", note="USD thousands in the filing"),
    bs("WRB", "bs_illiquid_loans", 418.913, "MD&A - Investment portfolio", ("Loans receivable", "418,913"), "418,913", note="USD thousands in the filing"),
    bs("WRB", "bs_cash", 2485.952, "MD&A - Investment portfolio", ("Cash and cash equivalents (2)", "2,485,952"), "2,485,952", note="USD thousands; included in the reported total"),
    bs("WRB", "bs_total_investments", 33173.381, "MD&A - Investment portfolio", ("Total investments", "$", "33,173,381"), "33,173,381",
       note="INCLUDES_CASH; USD thousands in the filing"),
    # --- CINF (balance sheet)
    bs("CINF", "bs_fixed_maturities", 18123, "Balance sheet", ("Fixed maturities, at fair value (amortized cost: 2025—$18,304; 2024—$16,735)", "$", "18,123"), "18,123"),
    bs("CINF", "bs_equity", 12694, "Balance sheet", ("Equity securities, at fair value (cost: 2025—$4,155; 2024—$3,953)", "12,694"), "12,694"),
    bs("CINF", "bs_short_term", 148, "Balance sheet", ("Short-term investments, at fair value (amortized cost: 2025—$148; 2024—$298)", "148"), "148"),
    bs("CINF", "bs_other_invested", 818, "Balance sheet", ("Other invested assets", "818", "713", "Total investments", "31,783"), "818"),
    bs("CINF", "bs_total_investments", 31783, "Balance sheet", ("Other invested assets", "818", "713", "Total investments", "31,783"), "31,783"),
    # --- RNR (MD&A investment portfolio, USD thousands -> mm)
    bs("RNR", "bs_fixed_maturities", 24884.323, "MD&A - Investments", ("Total fixed maturity investments trading, at fair value", "24,884,323", "69.1"), "24,884,323",
       note="USD thousands in the filing"),
    bs("RNR", "bs_short_term", 4759.811, "MD&A - Investments", ("Short term investments, at fair value", "4,759,811", "13.2"), "4,759,811", note="USD thousands in the filing"),
    bs("RNR", "bs_equity", 1732.990, "MD&A - Investments", ("Total equity investments, at fair value", "1,732,990"), "1,732,990",
       note="USD thousands; includes fixed income exchange traded funds 1,582,811 and common stock 150,179 (as classified by the company)"),
    bs("RNR", "bs_other_invested", 4696.085, "MD&A - Investments", ("Total other investments, at fair value", "4,574,214"), "4,574,214", post=330,
       note="DERIVED (USD thousands) = other investments at fair value 4,574,214 (fund investments, catastrophe bonds, private equity) + equity-method ventures 121,871"),
    bs("RNR", "bs_total_investments", 36073.209, "MD&A - Investments", ("Total investments", "$", "36,073,209"), "36,073,209", note="USD thousands in the filing"),
    # --- MET (balance sheet)
    bs("MET", "bs_fixed_maturities", 315931, "Balance sheet", ("and amortized cost: $337,201 and $307,421, respectively", "$", "315,931"), "315,931"),
    bs("MET", "bs_equity", 14817, "Balance sheet", ("Equity securities, at estimated fair value", "858", "712"), "858", post=380,
       note="DERIVED = equity securities 858 + contractholder-directed equity securities and fair value option securities 13,959"),
    bs("MET", "bs_illiquid_loans", 93140, "Balance sheet", ("includes $35 and $0, respectively, of mortgage loans held-for-sale)", "84,593"), "84,593", post=100,
       note="DERIVED = mortgage loans 84,593 + policy loans 8,547"),
    bs("MET", "bs_real_estate", 13440, "Balance sheet", ("$302 and $183, respectively, relating to variable interest entities)", "13,440"), "13,440"),
    bs("MET", "bs_other_invested", 31249, "Balance sheet", ("Other limited partnership interests", "14,917", "14,378"), "14,917", post=330,
       note="DERIVED = other limited partnership interests 14,917 + other invested assets 16,332"),
    bs("MET", "bs_short_term", 3601, "Balance sheet", ("Short-term investments, principally at estimated fair value", "3,601"), "3,601"),
    bs("MET", "bs_total_investments", 472178, "Balance sheet", ("Total investments", "472,178", "441,364"), "472,178"),
    # --- PRU (MD&A general account investments, total column)
    bs("PRU", "bs_fixed_maturities", 350395, "MD&A - Composition of investments (total column)",
       ("Public, available-for-sale, at fair value", "$", "214,796", "53.6", "$", "18,833", "$", "4,576", "$", "238,205"), "238,205", post=640,
       note="DERIVED = public AFS 238,205 + private AFS 92,900 + trading 14,448 + assets supporting experience-rated contractholder liabilities 4,842"),
    bs("PRU", "bs_equity", 10515, "MD&A - Composition of investments (total column)", ("Equity securities, at fair value", "8,922", "2.2", "1,593", "0", "10,515"), "10,515"),
    bs("PRU", "bs_illiquid_loans", 73879, "MD&A - Composition of investments (total column)",
       ("Commercial mortgage and other loans, at book value, net of allowance", "56,195"), "63,921", post=240,
       note="DERIVED = commercial mortgage and other loans 63,921 + policy loans 9,958"),
    bs("PRU", "bs_other_invested", 24066, "MD&A - Composition of investments (total column)",
       ("Other invested assets, net of allowance(1)", "17,684", "4.4", "4,532", "1,850", "24,066"), "24,066"),
    bs("PRU", "bs_short_term", 6404, "MD&A - Composition of investments (total column)", ("Short-term investments, net of allowance", "6,078", "1.5", "255", "71", "6,404"), "6,404"),
    bs("PRU", "bs_total_investments", 470519, "MD&A - Composition of investments (total column)", ("Total investments", "$", "405,970", "$", "46,523", "$", "18,026", "$", "470,519"), "470,519", post=20,
       note="total investments 470,519 includes invested assets of other entities and operations 5,260 that are not classified by category (residual)"),
    # --- AFL (MD&A investments by segment, total column)
    bs("AFL", "bs_fixed_maturities", 80241, "MD&A - Investments by segment (total column)",
       ("Fixed maturity securities available-for-sale, at", "fair value", "$", "44,782", "$", "12,426", "$", "6,913", "$", "64,121"), "16,120", post=200,
       note="DERIVED = available-for-sale 64,121 + held-to-maturity (amortized cost) 16,120"),
    bs("AFL", "bs_equity", 887, "MD&A - Investments by segment (total column)", ("Equity securities", "632", "2", "253", "887"), "887"),
    bs("AFL", "bs_illiquid_loans", 9975, "MD&A - Investments by segment (total column)", ("Transitional real estate loans", "2,818", "658", "135", "3,611"), "210", post=520,
       note="DERIVED = transitional real estate loans 3,611 + commercial mortgage loans 1,443 + middle market loans 4,266 + other loans 445 + policy loans 210"),
    bs("AFL", "bs_other_invested", 4137, "MD&A - Investments by segment (total column)", ("Limited partnerships", "3,273", "536", "300", "4,109"), "4,109", post=200,
       note="DERIVED = limited partnerships 4,109 + other 28"),
    bs("AFL", "bs_real_estate", 902, "MD&A - Investments by segment (total column)", ("Real estate owned", "777", "125", "0", "902"), "902"),
    bs("AFL", "bs_short_term", 1373, "MD&A - Investments by segment (total column)", ("Short-term investments (2)", "596", "223", "554", "1,373"), "1,373"),
    bs("AFL", "bs_total_investments", 97515, "MD&A - Investments by segment (total column)", ("Total investments", "74,248", "16,261", "7,006", "97,515"), "97,515"),
    # --- AIG (balance sheet)
    bs("AIG", "bs_fixed_maturities", 71773, "Balance sheet", ("(amortized cost: 2025 - $71,772; 2024 - $66,195)", "$", "71,032"), "71,032", post=140,
       note="DERIVED = bonds available for sale 71,032 + other bond securities 741"),
    bs("AIG", "bs_equity", 502, "Balance sheet", ("Equity securities, at fair value", "502", "704"), "502"),
    bs("AIG", "bs_illiquid_loans", 2887, "Balance sheet", ("in 2025 and $37,800 in 2024", "2,887"), "2,887", pre=80),
    bs("AIG", "bs_other_invested", 6696, "Balance sheet", ("Other invested assets (portion measured at fair value: 2025 - $5,011; 2024 - $7,384)", "6,696"), "6,696"),
    bs("AIG", "bs_short_term", 11141, "Balance sheet", ("(portion measured at fair value: 2025 - $5,909; 2024 - $9,789)", "11,141"), "11,141", pre=80),
    bs("AIG", "bs_total_investments", 92999, "Balance sheet", ("Total investments", "92,999", "93,613"), "92,999"),
    # --- HIG (MD&A composition of invested assets)
    bs("HIG", "bs_fixed_maturities", 46209, "MD&A - Composition of invested assets",
       ("Fixed maturities, AFS, at fair value", "$", "46,041", "72.0", "$", "42,567", "71.9", "Fixed maturities, at fair value using the fair value option", "168"), "168",
       note="DERIVED = AFS 46,041 + fair value option 168"),
    bs("HIG", "bs_equity", 492, "MD&A - Composition of invested assets", ("Equity securities, at fair value", "492", "0.8"), "492"),
    bs("HIG", "bs_illiquid_loans", 6837, "MD&A - Composition of invested assets", ("Mortgage loans (net of ACL of $49 and $44)", "6,837"), "6,837"),
    bs("HIG", "bs_other_invested", 6066, "MD&A - Composition of invested assets", ("Limited partnerships and other alternative investments", "5,804"), "5,804", post=140,
       note="DERIVED = limited partnerships and other alternative investments 5,804 + other investments 262"),
    bs("HIG", "bs_short_term", 4353, "MD&A - Composition of invested assets", ("Short-term investments", "4,353", "6.8"), "4,353"),
    bs("HIG", "bs_total_investments", 63957, "MD&A - Composition of invested assets", ("Total investments", "$", "63,957", "100.0"), "63,957"),
]

# Q4: changes in group structure (extracted events; the XBRL indicator proxy is applied in the code in addition)
S2 += [
    r("AIG", "structural_event:FY2024", "YES", "text", "Item 1A / Note 4 - Corebridge deconsolidation",
      ("At the time of deconsolidation on June 9, 2024",), "June 9, 2024", pre=300, post=200,
      note="deconsolidation of Corebridge (life and retirement business: most of AIG's future policy benefits and policyholder account balances left the balance sheet)",
      period="FY2024"),
    r("CB", "structural_event:FY2023", "YES", "text", "Note 1 - Basis of presentation (Huatai Group)",
      ("On July 1, 2023, Chubb discontinued equity method accounting for its investment in Huatai Group",), "July 1, 2023", pre=60, post=240,
      note="Huatai Group consolidated at 100% from July 1, 2023 (acquisition of control; adds life and P&C liabilities)", period="FY2023"),
]

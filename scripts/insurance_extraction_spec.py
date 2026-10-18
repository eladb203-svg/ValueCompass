"""Extraction spec for the INSURANCE test round (items found only in the FY2025 10-K text; AI-extraction pattern as for BANK).

Row types
  normal    tokens (anchor strings, joined by whitespace/|/$/% tolerant regex) + ``verify`` (the number string that must appear in the quote)
  absence   ``absence`` = regex; verified YES only when it has NO match in the 10-K text (a missing number is documented, not guessed)
  presence  ``presence`` = regex; value YES with the first match as the quote (ALM disclosure flag)
Units: "USD mm", "%" (reg_capital_ratio / ig_share_pct), "text".
Item names read by src/scoring/insurance.py:
  reg_capital_ratio  value in % with ``basis=ACL|CAL|SCR|SMR`` in the note; MISSING when the filing gives no number
  ig_fixed_income / total_fixed_income (USD mm)  or  ig_share_pct (%)
  cat_loss_latest (USD mm), alm_disclosed (YES/NO), debt_total (USD mm), adverse_prior_year_dev:<FY> (USD mm, adverse positive)
"""
MM = "USD mm"
PCT = "%"


def r(t, item, value, unit, section, tokens, verify=None, pre=40, post=300, note="", period="FY2025", **kw):
    return dict(t=t, item=item, value=value, unit=unit, section=section, tokens=tokens, verify=verify, pre=pre, post=post,
                note=note, period=period, **kw)


def absent(t, item, section, regex, note, period="FY2025"):
    return dict(t=t, item=item, value="MISSING", unit=PCT, section=section, tokens=None, verify=None, pre=0, post=0, note=note, period=period,
                absence=regex)


def present(t, item, section, regex, note=""):
    return dict(t=t, item=item, value="YES", unit="text", section=section, tokens=None, verify=None, pre=150, post=300, note=note, period="FY2025",
                presence=regex)


S = []

# ------------------------------------------------------------------ regulatory capital (I4 / I14): numeric where the filing gives one
S += [
    r("CINF", "reg_capital_ratio", 560, PCT, "Item 1 - Insurance regulation (statutory table, standard market P&C subsidiary)",
      ("Risk-based capital to authorized control level risk-based capital ratio", "5.6"), "5.6", post=60,
      note="basis=ACL; the table shows 5.6 (times ACL) = 560% of ACL; entity=lead subsidiary (standard market property casualty), not group; 2025-12-31"),
    r("WRB", "reg_capital_ratio", 397, PCT, "Note 17 - Statutory financial information (RBC)",
      ("Total Adjusted Capital of $9.7 billion was", "397%"), "397%", post=80,
      note="basis=ACL; entity=Berkley Insurance Company (BIC), the lead insurance subsidiary, not group; 2025-12-31"),
    r("ALL", "reg_capital_ratio", 490.5, PCT, "Note 17 - Statutory financial information (RBC)",
      ("authorized control level RBC of AIC were estimated to be", "$20.75 billion and $4.23 billion"), "$20.75 billion", post=60,
      note="basis=ACL; DERIVED = total adjusted capital 20.75bn / authorized control level RBC 4.23bn of Allstate Insurance Company (AIC), "
           "the lead subsidiary; the filing gives amounts, not a ratio; 2025-12-31"),
    r("MET", "reg_capital_ratio", 350, PCT, "MD&A - Liquidity and Capital Resources - Statutory Capital and Dividends",
      ("Statement-Based Combined RBC Ratio was in excess of", "350%"), "350%", post=120,
      note="basis=CAL; FLOOR ('in excess of 350%'); company-defined combined ratio of the principal US subsidiaries (excl. American Life) on company "
           "action level RBC; 2025-12-31"),
    r("PRU", "reg_capital_ratio", 409, PCT, "MD&A - Liquidity and Capital Resources (PICA)",
      ("RBC ratio as of December 31, 2024, its most recent statutory fiscal year-end and RBC reporting date, was", "409%"), "409%", post=120, period="FY2024",
      note="basis=CAL; PICA (lead US subsidiary) as of 2024-12-31, 'its most recent statutory fiscal year-end'; FY2025 not yet filed -> STALE by one year"),
    r("AFL", "reg_capital_ratio", 995, PCT, "MD&A - Capital and liquidity (Aflac Japan solvency margin ratio)",
      ("Aflac Japan's SMR was", "995%"), "995%", post=90,
      note="basis=SMR; Aflac Japan only (lead subsidiary, majority of earnings); Japanese solvency margin ratio, first regulatory intervention level 200% "
           "(not one of the regimes named in the spec); 2025-12-31"),
    r("RNR", "reg_capital_ratio", 242, PCT, "Note - Statutory requirements (Bermuda BSCR)",
      ("group BSCR was filed with the BMA on May 30, 2025 with a BSCR ratio of", "242%"), "242%", post=40, period="FY2024",
      note="basis=SCR; group BSCR ratio for the 2024 filing (FY2025 filing is made after the 10-K) -> STALE by one year; ECR = 100% intervention level"),
    r("PGR", "reg_capital_ratio", "MISSING", PCT, "Item 1 - Insurance regulation (RBC)",
      ("our RBC ratios were in excess of minimum requirements",), "in excess of minimum requirements", pre=120, post=60,
      note="No number: 'exceeds requirements' without a number = missing (as BANK D12)"),
    r("AIG", "reg_capital_ratio", "MISSING", PCT, "Item 1 - Regulation (RBC)",
      ("exceeded each of these specific thresholds as of December 31, 2025",), "exceeded each of these specific thresholds", pre=200, post=60,
      note="No number: 'exceeded thresholds' without a number = missing"),
    absent("CB", "reg_capital_ratio", "Item 1 / Note - Regulation (RBC / BSCR)",
           r"(?i)(RBC|risk-based capital|BSCR|solvency)[^.]{0,150}\b\d{3}(\.\d)?\s*(%|percent)",
           "No numeric group or lead-subsidiary capital ratio found in the 10-K (only descriptions of BSCR / RBC) -> missing"),
    absent("TRV", "reg_capital_ratio", "Item 1 / Note - Regulation (RBC)",
           r"(?i)(RBC|risk-based capital|solvency)[^.]{0,150}\b\d{3}(\.\d)?\s*(%|percent)",
           "No numeric RBC / Solvency ratio found in the 10-K (GCC has no ratio) -> missing"),
    absent("HIG", "reg_capital_ratio", "Item 1 / Note - Regulation (RBC)",
           r"(?i)(RBC|risk-based capital|solvency)[^.]{0,150}\b\d{3}(\.\d)?\s*(%|percent)",
           "No numeric RBC / Solvency ratio found in the 10-K -> missing"),
]

# ------------------------------------------------------------------ credit quality of fixed income (investment grade / total)
S += [
    r("TRV", "ig_fixed_income", 88783, MM, "MD&A - Investment portfolio (fixed maturities by quality rating)",
      ("Total investment grade", "88,783"), "88,783", post=120, note="carrying value; Baa or higher"),
    r("TRV", "total_fixed_income", 89833, MM, "MD&A - Investment portfolio (fixed maturities by quality rating)",
      ("Below investment grade", "1,050", "1.2", "Total fixed maturities", "89,833"), "89,833", pre=60, post=40),
    r("CB", "ig_fixed_income", 112801, MM, "MD&A - Credit risk (fixed income by S&P rating)",
      ("Total (1)", "$", "135,611"), "23,584", pre=20, post=560,
      note="DERIVED sum AAA 13,313 + AA 40,720 + A 35,184 + BBB 23,584; fair value, includes fixed maturities in Other investments"),
    r("CB", "total_fixed_income", 135611, MM, "MD&A - Credit risk (fixed income by S&P rating)", ("Total (1)", "$", "135,611"), "135,611", pre=20, post=60),
    r("HIG", "ig_fixed_income", 43740, MM, "MD&A - Investments (AFS fixed maturities by credit quality)",
      ("United States Government/Government agencies", "6,253"), "10,250", pre=20, post=700,
      note="DERIVED fair value: US government 5,929 + AAA 7,751 + AA 7,340 + A 12,470 + BBB 10,250; excludes FVO securities"),
    r("HIG", "total_fixed_income", 46041, MM, "MD&A - Investments (AFS fixed maturities by credit quality)",
      ("United States Government/Government agencies", "6,253"), "46,041", pre=20, post=700, note="fair value of AFS fixed maturities"),
    r("PRU", "ig_fixed_income", 276036, MM, "MD&A - Fixed maturity securities by NAIC designation (high or highest quality = NAIC 1-2)",
      ("Subtotal High or Highest Quality Securities(4)", "300,052"), "276,036", pre=20, post=120, note="fair value; NAIC 1 and 2 (investment grade)"),
    r("PRU", "total_fixed_income", 295430, MM, "MD&A - Fixed maturity securities by NAIC designation",
      ("Total fixed maturities, available-for-sale", "$", "319,725", "$", "6,252"), "295,430", pre=20, post=240, note="fair value"),
    r("MET", "ig_fixed_income", 285735, MM, "MD&A - Investments (fixed maturity securities AFS by rating)",
      ("Subtotal investment grade", "306,042", "(20,307)", "285,735"), "285,735", pre=20, post=60, note="estimated fair value, excluding reinsurance activity"),
    r("MET", "total_fixed_income", 297731, MM, "MD&A - Investments (fixed maturity securities AFS by rating)",
      ("Total fixed maturity securities AFS, excluding Reinsurance activity", "$", "318,108", "$", "(20,377)", "$", "297,731"), "297,731", pre=20, post=60,
      note="estimated fair value, excluding reinsurance activity"),
    r("AIG", "ig_fixed_income", 65807, MM, "MD&A - Investments (composite credit ratings of fixed maturity securities, total)",
      ("AAA", "$", "15,261", "$", "14,011"), "71,773", pre=20, post=900,
      note="DERIVED fair value total (AFS + other bond securities): AAA 15,377 + AA 16,260 + A 19,017 + BBB 15,153; below IG 5,872 and non-rated 94 excluded"),
    r("AIG", "total_fixed_income", 71773, MM, "MD&A - Investments (composite credit ratings of fixed maturity securities, total)",
      ("AAA", "$", "15,261", "$", "14,011"), "71,773", pre=20, post=900, note="fair value, AFS + other bond securities"),
    r("ALL", "ig_share_pct", 92.1, PCT, "MD&A - Investments (credit quality)",
      ("92.1% of the consolidated fixed income securities portfolio was rated investment grade",), "92.1%", pre=60, post=40, note="as stated by the company"),
    r("CINF", "ig_share_pct", 97.5, PCT, "Item 1 - Investments segment",
      ("investment-grade fixed-maturity securities represented 97.5% of the portfolio",), "97.5%", pre=60, post=120, note="as stated; NRSRO or NAIC SVO"),
    r("RNR", "ig_share_pct", 95.0, PCT, "MD&A - Investments (credit quality)",
      ("non-investment grade and not-rated fixed maturity investments totaled $1.2 billion or 5.0%",), "5.0%", pre=60, post=100,
      note="DERIVED = 100% - 5.0% (non-investment grade AND not rated, unrated = not investment grade as in the spec)"),
    r("AFL", "ig_share_pct", 98.4, PCT, "MD&A - Investments (fixed maturities by credit rating, fair value 2025)",
      ("BB or lower", "1.4", "1.6", "1.6", "1.7"), "1.6", pre=420, post=120,
      note="DERIVED = 100% - 1.6% (BB or lower, fair value column 2025); columns assumed amortized cost / fair value for 2025 then 2024"),
]

# ------------------------------------------------------------------ catastrophe losses (flag only, I19)
S += [
    r("TRV", "cat_loss_latest", 3690, MM, "MD&A - Overview", ("Catastrophe losses of $3.69 billion",), "$3.69 billion", pre=40, post=120, note="2025"),
    r("ALL", "cat_loss_latest", 4959, MM, "MD&A - Property-Liability",
      ("Catastrophe losses", "$", "4,959", "$", "4,964"), "4,959", pre=40, post=60, note="2025"),
    r("WRB", "cat_loss_latest", 336, MM, "MD&A - Consolidated results",
      ("Catastrophe losses, net of reinsurance recoveries, were $336 million in 2025",), "$336 million", pre=40, post=120, note="2025"),
    r("PGR", "cat_loss_latest", 1478, MM, "Note - Segment information (loss reconciliation)",
      ("Catastrophe losses", "1,437", "41", "0", "1,478"), "1,478", pre=40, post=60, note="2025 total across segments"),
    r("HIG", "cat_loss_latest", 748, MM, "MD&A - Catastrophe losses (P&C)", ("Total catastrophe losses", "$", "421", "$", "327", "$", "748"), "748",
      pre=300, post=60, note="2025 (first table; 2024 table total 768 follows later)"),
    r("AIG", "cat_loss_latest", 1098, MM, "MD&A - General Insurance (catastrophe-related charges)",
      ("Total catastrophe-related charges", "$", "612", "$", "309", "$", "177", "$", "1,098"), "1,098", pre=40, post=60,
      note="total catastrophe-related charges (natural + man-made, incl. reinstatement premiums) for 2025"),
    r("CB", "cat_loss_latest", 2805, MM, "MD&A - Overview (catastrophe losses by segment)",
      ("Total North America P&C Insurance catastrophe losses were $2.3 billion", "◦Total Overseas General catastrophe losses were $505 million"),
      "$505 million", pre=40, post=40, note="DERIVED sum North America P&C $2.3bn + Overseas General $505m (2025); life segment not included"),
]

# ------------------------------------------------------------------ ALM disclosure (flag only in v1)
_ALM = r"(?i)(asset[- ]liability (management|matching|duration)|asset/liability|ALM|duration of (our |its |the )?(insurance )?liabilities|(match|matching)[^.]{0,80}(duration|cash flows?)[^.]{0,80}(liabilit|asset)|liabilit[^.]{0,100}duration[^.]{0,100}(asset|portfolio))"
for _t in ("CB", "TRV", "PGR", "ALL", "WRB", "CINF", "RNR", "MET", "PRU", "AFL", "AIG", "HIG"):
    S.append(present(_t, "alm_disclosed", "Item 7 / 7A - Market risk and investments", _ALM, "first disclosure of asset-liability / duration management found by pattern"))


# ------------------------------------------------------------------ financial debt (latest year) where no total tag / chain exists
S += [
    r("MET", "debt_total", 18599, MM, "Note - Fair value (carrying amounts: long-term debt, subordinated debt securities) and Note - Debt (short-term debt)",
      ("Long-term debt", "$", "15,080", "$", "—", "$", "14,498"), "3,164", pre=20, post=330,
      note="DERIVED carrying amounts: long-term debt 15,080 + subordinated debt securities 3,164 + short-term debt 355; the collateral financing "
           "arrangement (476) is not included (funding arrangement, flagged)"),
    r("WRB", "debt_total", 2839.7, MM, "Balance sheet", ("Senior notes and other debt", "1,829,198", "1,831,158", "Subordinated debentures", "1,010,527"),
      "1,010,527", pre=20, post=60, note="DERIVED (USD thousands in the filing): senior notes and other debt 1,829,198 + subordinated debentures 1,010,527"),
]

# ------------------------------------------------------------------ prior-year reserve development not tagged (TRV): adverse positive = -(net favorable)
S += [
    r("TRV", "adverse_prior_year_dev:FY2025", -1036, MM, "Note 2 - Segment information (prior year reserve development by segment)",
      ("2025", "Net favorable prior year reserve development", "$", "233", "$", "221", "$", "582", "$", "1,036"), "1,036", pre=20, post=20,
      note="net FAVORABLE 1,036 -> adverse = -1,036", period="FY2025"),
    r("TRV", "adverse_prior_year_dev:FY2024", -709, MM, "Note 2 - Segment information (prior year reserve development by segment)",
      ("2024", "Net favorable prior year reserve development", "$", "90", "$", "129", "$", "490", "$", "709"), "709", pre=20, post=20,
      note="net FAVORABLE 709 -> adverse = -709", period="FY2024"),
    r("TRV", "adverse_prior_year_dev:FY2023", -143, MM, "Note 2 - Segment information (prior year reserve development by segment)",
      ("2023", "Net favorable (unfavorable) prior year reserve development", "$", "(289)", "$", "285", "$", "147", "$", "143"), "143", pre=20, post=20,
      note="net FAVORABLE 143 (segments: Business Insurance unfavorable 289) -> adverse = -143", period="FY2023"),
]

S += [
    r("HIG", "adverse_prior_year_dev:FY2025", -424, MM, "MD&A / Note - Liability for unpaid losses (reserve roll-forward, total P&C)",
      ("Prior accident year development", "(441)", "(179)", "196", "(424)"), "(424)", pre=20, post=10,
      note="prior accident year development (favorable) -424 -> adverse -424 (net of the deferred-gain effect shown separately)", period="FY2025"),
    r("HIG", "adverse_prior_year_dev:FY2024", -120, MM, "MD&A / Note - Liability for unpaid losses (reserve roll-forward, total P&C)",
      ("Prior accident year development", "(231)", "(108)", "219", "(120)"), "(120)", pre=20, post=10, note="favorable 120 -> adverse -120", period="FY2024"),
    r("HIG", "adverse_prior_year_dev:FY2023", 10, MM, "MD&A / Note - Liability for unpaid losses (reserve roll-forward, total P&C)",
      ("Prior accident year development", "(225)", "11", "224", "10"), "224", pre=20, post=20, note="unfavorable 10 -> adverse +10", period="FY2023"),
]

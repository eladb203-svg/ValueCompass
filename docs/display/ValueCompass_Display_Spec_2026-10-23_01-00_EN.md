---
title: "ValueCompass — Display Specification"
subtitle: "2026-10-23_01-00 · English (source of truth) · approved"
---

# ValueCompass — Display Specification

**Scope:** what the user sees, and how it is computed for display. This document is separate from the Rulebook: nothing here changes a score, a value or a buy price. The screen shows only what the engine stored, plus the display formulas listed here.

**Language:** English is the source of truth; the Hebrew version is a translation. The app itself is in Hebrew; on-screen texts are given in Hebrew.

**Basis:** Elad's design (2026-10-22/23), as reviewed on the design canvas "ValueCompass — דוגמת מסכים". This replaces the draft 2026-10-22_14-58 and the version 2026-10-19_13-31.

## 1. Sign-in

- The entry screen is a sign-in screen with these elements:
  - Email.
  - Password.
  - "שכחתי סיסמה" ("forgot password").
  - "הרשמה" ("sign up").
- **Users and passwords are managed by Supabase Auth.**
  - The password is stored hashed by Supabase, never in our tables.
  - `user_profiles` links to the user.
  - Each user sees only their own portfolio and watchlist (RLS).
- **Google sign-in:** decided later.

## 2. General layout

- **Top bar, on every screen:**
  - Menu button (☰).
  - Logo.
  - **The search bar**: name, ticker or a free-text request.
    - Free text goes to smart search: the AI turns the request into a filter, and code searches the DB.
    - A stock that is not found goes to the automatic add.
  - User name.
- **Side menu — closed by default, opened on click.** Items:
  - My portfolio.
  - Watchlist.
  - Top ranked.
  - How we score.
  - Account settings.
  - Admin (admin only: the approval queue).
  - **Screen colour:** light / warm / dark, saved in the user settings.
  - **Sign out**, at the bottom.
- **Score colour:**
  - A continuous scale from red (0) to green (maximum), by the score relative to its maximum.
  - The number is always written, so colour is never the only carrier of meaning.

## 3. User page — three tabs

### 3.1 My portfolio

- **One portfolio on screen.** The DB keeps the option of several.
- **Summary cards:** portfolio value, gain / loss, number of stocks.
- **Holdings table columns:**
  - Stock.
  - Quantity.
  - Average purchase price.
  - **Purchase date.**
  - Current price.
  - Value.
  - Gain / loss.
  - Weight.
  - The four scores: Buffett quality, Buffett price, Graham quality, Graham price.
- **Empty fields are allowed.**
  - A field the user did not enter, or the code could not extract, shows "—".
  - Values that depend on it (e.g., gain / loss) also show "—".
- **Adding stocks:**
  - "הוספת מניה" ("add stock"): manual entry.
  - "ייבוא מקובץ" ("import from file"):
    - The import recognises the columns in different brokers' files by itself: ticker, quantity, price, date.
    - It leaves blank what it cannot find.
    - A stock not in the DB goes to the automatic add ("מבצע עיבוד וניתוח של החברה", "processing and analysing the company").

### 3.2 Watchlist

Columns:

- Stock.
- Current price.
- Buy price (Buffett).
- Distance from the buy price.
- The four scores.
- Date added.

### 3.3 Top ranked

- **Filters:** sector (ValueCompass industries) and country (US for now).
- **Top 5 combined:**
  - The average of the four scores, with the price score (out of 10) multiplied by 10.
  - **Only stocks that have all four scores.**
- **Top 5 for each rating** (Buffett quality, Buffett price, Graham quality, Graham price):
  - A stock enters every rating where it has a score, even if another score is missing.
- **No extra filter for low quality or low coverage.** Such a stock does not reach the top because of its score.

## 4. Stock page

Order of sections:

### 4.1 Details and background

- **Details:**
  - Name, ticker, exchange.
  - Main country of operation, sector.
  - Market cap, current price.
  - Last update, with the fiscal year of the annual report.
- **Buttons:** "+ למעקב" ("add to watchlist"), "+ לתיק" ("add to portfolio").
- **על החברה ("about the company"):** background D1 — the five agreed parts, at most 120 words.

### 4.2 Key financials — six charts

- **One chart per metric**, each in its own colour. No combined chart, no trend line.
- **Bars for each of the last 10 fiscal years.** With fewer years: what exists, labelled "נתונים ל-X שנים" ("data for X years").
- **Under each chart, 3 / 5 / 7 / 10 years:**
  - CAGR for revenue, net income, EPS and free cash flow. When CAGR is not meaningful: the average, labelled.
  - The average for return on equity and debt / equity.
- **The metrics** (definitions per profile in Appendix A):

| Title | STANDARD / TECH metric |
|---|---|
| Revenue | Revenue |
| Net income | Net income to shareholders |
| EPS | Diluted EPS |
| Return on equity | ROE |
| Free cash flow | CFO − capex |
| Debt / equity | **Financial debt / equity**, the ratio that Graham 3.3 scores |

- **Banks, insurers and real estate:** the titles stay. The metric under each title follows the profile (Appendix A), with a short explanation line.

### 4.3 Score summary

- **Table, one row each for Buffett and Graham.** Columns:
  - **Quality score**, with label.
  - **Price score.**
  - **Fair value.**
  - **Buy price.**
  - **Margin of safety:** current, with the required one in brackets.
  - **Conclusion.**
- Scores are shown in the continuous colour scale.
- **"פירוט" ("details") per model** opens two parts:
  - **Criteria:** the eight criteria, each with its name and score only ("X/weight"), in the colour scale. No calculation detail.
  - **Price determination:** the method and its components as stored by the engine.
    - **Buffett:** fair value, current price, discount, upside, required margin of safety, buy price, price score.
    - **Graham:** Graham Number, normalized EPS × 15, BVPS × 1.5, the value (the minimum), current price, required margin, buy price, price score.
    - **Banks, insurers and real estate:** the profile's method.
- **Price states are shown as text instead of a number:**
  - "לא מתאים לרכישה" ("not suitable for purchase"), when quality is below 55.
  - "לא רלוונטי" ("not applicable").
  - "לא ניתן לתמחר כרגע" ("cannot be priced at the moment").
  - "חסום" ("blocked").
  - "המחיר לא עודכן" ("price not updated").
  - "מחיר קנייה לא מוצג — כיסוי נתונים נמוך" ("buy price not shown — low data coverage").

### 4.4 Summary and analysis

- **Analysis (D2):**
  - A quality paragraph and a value-and-price paragraph, each at most 60 words.
  - The peer comparison.
  - Generated once per run.
- **Disclaimer:** "ניתוח לימודי, לא ייעוץ השקעות. אין התחייבות לתשואה." ("Educational analysis, not investment advice. No guarantee of returns.")

### 4.5 Later

- A share-price and returns chart over the years.
- It comes from an embedded external component; price history is not stored in the DB.

## 5. Labels and conclusion

Approved in principle. These are display rules and will be added to the Rulebook.

**Quality labels — the same bands for both models:**

| Quality score | Graham (Rulebook A.6) | Buffett (decided 2026-10-23) |
|---|---|---|
| 85–100 | שמרנית וחזקה מאוד (very conservative and strong) | עסק מצוין (an excellent business) |
| 70–84 | טובה ויציבה (good and stable) | עסק טוב (a good business) |
| 55–69 | גבולית (borderline) | עסק בינוני (an average business) |
| Below 55 | לא מתאימה לגישה הדפנסיבית (not suitable for the defensive approach) | עסק חלש (a weak business) |

**Conclusion — per model:**

| Condition | Conclusion |
|---|---|
| Quality ≥ 70 and price ≤ buy price | קנייה אפשרית עכשיו (buy possible now) |
| Quality ≥ 70 and price > buy price | להמתין למחיר נמוך יותר (wait for a lower price) |
| Quality 55–69 | מתאים למעקב בלבד (watch only) |
| Quality below 55, or cannot be valued | לא מתאים כרגע להשקעת ערך (not suitable for value investing now) |
| A stock in the portfolio priced above fair value | מימוש חלקי / לא להוסיף (partial sale / do not add) |

Each label is shown next to the score itself, never instead of it. Graham's labels describe the stock for a cautious investor; Buffett's labels describe the business.

## 6. Further screens (K7)

These screens are built in K7 with this content. No special design requests.

| Screen | Content |
|---|---|
| **Search results** (from the top bar) | **Plain search:** name or ticker, typo-tolerant. **Smart search:** the filter the AI understood is shown, so the user can correct it, followed by the results as a table with the four scores. A stock not found offers the automatic add |
| **How we score** | The two models. The eight criteria and their weights. How fair value and buy price are set. The colours and labels. How the AI is used (quotes from the annual report). Not investment advice |
| **Account settings** | Name, email, password change, screen colour, export of the portfolio, account deletion |
| **Admin: approval queue** | One row per pending item: company, year, item, value, the report quote, the control and its result, and what it affects (score, value, buy price). Actions: approve, correct, reject. A correction triggers a recompute |
| **Import from file** | Upload, then a preview of what was recognised (ticker, quantity, price, date). Manual correction before saving. A list of stocks not found |
| **Processing state** | "מבצע עיבוד וניתוח של החברה" ("processing and analysing the company"), the partial score, AI progress "n of m", estimated time |

## 7. Open

1. Google sign-in.

## Appendix A — Metrics per profile (approved 2026-10-19, unchanged)

**Rule:** display only — no effect on any score. Computed in the view `v_display_metrics` from `financial_facts` (raw items and engine-derived items), one row per company and fiscal year. The company's profile selects the definition. Amounts in the reporting currency.

| Metric | STANDARD / TECH_ASSET_LIGHT | BANK | INSURANCE | INCOME_REAL_ESTATE |
|---|---|---|---|---|
| Revenue | Revenue (FIN-060) | Bank revenue = net interest income + noninterest income (FIN-063 + FIN-064) | Operating revenue = total revenue − investment gains in profit or loss (FIN-060 − FIN-030) | Total revenue (FIN-060) |
| Net income | Net income attributable to the parent (FIN-020) | Same | Same | Net income (FIN-020) **and** normalized FFO (FIN-070) |
| Earnings per share | Diluted EPS (FIN-062) | Same | Diluted EPS **and** operating EPS (DRV-006) | Normalized FFO per share (DRV-001) |
| Return on equity | ROE = net income / average equity (FIN-020 / avg FIN-010) | ROTCE = (net income − preferred dividends) / average tangible common equity; TCE = equity − preferred stock − goodwill − intangibles | Operating ROE = normalized operating profit after tax / average adjusted equity (DRV-004 / avg DRV-005) | Normalized FFO / average equity (labelled: ordinary ROE is distorted by depreciation) |
| Free cash flow | CFO − capex (FIN-080 − FIN-081; SBC not deducted, as the quality cards) | **Not shown** (cash flow is not representative for a bank) | **Not shown** | Owner earnings (DRV-002) |
| Debt / equity | Financial debt / equity (FIN-011 / FIN-010) | **CET1 ratio** instead (FIN-106; deposits are a bank's raw material) | Financial leverage = debt / (debt + adjusted equity) (FIN-011, DRV-005) | Net debt / EBITDAre (DRV-003) |

**Conventions:**

- **Average** equity = (start of year + end of year) / 2; first available year: end of year only, flagged.
- **Missing input** → the cell shows "—" with the reason (missing data, not applicable). No imputation.
- **Denominator ≤ 0** (e.g., negative equity, EBITDAre ≤ 0) → "not meaningful", not a number. For an **average** denominator, the test applies to **each end point**: if equity (or the profile's equity base) is ≤ 0 at the start or at the end of the year, the return on equity is "not meaningful", even when the average is positive (2026-10-19).
- **History:** every fiscal year in `financial_facts` (up to 10); the latest year is highlighted.
- **Labels** name the metric actually shown (e.g., "ROTCE" for a bank, "Net debt / EBITDAre" for real estate), never the generic name alone.

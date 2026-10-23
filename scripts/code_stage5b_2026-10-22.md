# דוח שלב ק5ב — תבנית 3.1 לשאלות הניקוד, וחילוץ נתונים ב-AI (B1–B14)

תאריך: 2026-10-22 · מודל מקובע: `gemini-3.5-flash-lite` (טמפרטורה 0, seed 20261021) · **הרצות המודל הושלמו ב-23.10 (ראו "תוצאות הרצה אמיתית"); הסעיפים שמתחתיו משקפים את המצב לפני האיפוס.**

## תוצאות הרצה אמיתית (23.10.2026, שעון ישראל 13:00–13:10) — מחליף את הערות "לא הורץ" שלמטה

**מכסה:** המונה המשותף (`usage.json`, יום פסיפיק 2026-10-23, תקרה 450) הסתיים ב-**168 קריאות** — ללא 429. תהליך אחד בכל פעם (ניקוד, ואז חילוץ). קובץ הניקוד הישן הועבר ל-`assessments_pre_fix.jsonl` (לא נמחק) וכל 108 התשובות נשאלו מחדש. שום כתיבה ל-Supabase, `.env` לא שונה, golden קיים לא שונה.

**תיקונים שנעשו תוך כדי (שני באגים שלי שנחשפו רק עם נתוני אמת):**
1. `src/ai/ext_checks.py` — הבקרות `loans_sum` ו-`bounds_0_100` קראו `row["item"]` שלא קיים בשורות האמיתיות (בבדיקות היחידה כן); ההרצה הראשונה התרסקה אחרי 3 קריאות של JPM (נשמרו ולא נשאלו שוב). הוספתי `_fld` שקורא את השדה השטוח או המקונן.
2. `scripts/ai_runner.py` — `attach_ext` מעולם לא נקרא מהמנוע, ולכן golden עם `VC_AI_EXT_STORE` הראה השפעה אפס. כעת `attach_ai` קורא גם ל-`attach_ext` (Bank/Insurance/REInputs; no-op בלי המשתנה). golden ההשפעה נבנו מחדש אחרי התיקון.

### א. ניקוד, תבנית 3.1 (סעיף 2) — 108/108 תשובות, 118 קריאות (7 ניסיונות חוזרים; שגיאות רשת ConnectError 6, ReadError 1)

| Run | Rows | Agreement (not low) | Agreement + close | Distribution 2/1/0 | Checks passed | Quotes found | Insufficient | Latency (sum) | Tokens in / out |
|---|---|---|---|---|---|---|---|---|---|
| K5a-3 (v3.1) | 108/108 | 91/106 = 86% | 96/106 = 91% | 97/4/3 | 104/108 = 96% | 200/205 = 98% | 4 | 229 s | 2,219,390 / 26,625 |
| K5b (3.1 default) | 108/108 | 92/106 = 87% | 98/106 = 92% | 94/4/6 | 104/108 = 96% | 196/198 = 99% | 4 | 1564 s | 2,216,440 / 27,384 |

התאמה לפי skill:

| Skill | K5a-3 (v3.1) | K5b (3.1 default) |
|---|---|---|
| A1 | 9/9 | 9/9 |
| A2 | 9/9 | 9/9 |
| A3 | 8/9 | 8/9 |
| A4 | 9/9 | 9/9 |
| A5 | 8/9 | 9/9 |
| A6 | 9/9 | 9/9 |
| A7 | 8/9 | 8/9 |
| A8 | 2/4 | 1/4 |
| A9 | 7/9 | 8/9 |
| A10 | 4/8 | 4/8 |
| A11 | 8/9 | 6/9 |
| A12 | 9/9 | 9/9 |
| A13 | 1/4 | 3/4 |

* **התאמה כוללת 87% (92/106) מול 86% בק5א-3; עם "קרוב" 92% מול 91%.** שיפור שולי, בתוך הרעש. התפלגות 2/1/0: 94/4/6 (ק5א-3: 97/4/3).
* **דחיות: 4 מתוך 108** (כמו בק5א-3), לעומת 8/36 בהרצה החלקית הקודמת — **נסיגת הציטוטים (`...`) נעלמה** עם הנוסח החדש וניסיון החוזר היחיד. ציטוטים נמצאו: 196/198 (99%).
* הזמן המצטבר (1564 שניות מול 229) נובע מ-`--rpm 20` ושגיאות רשת, לא מהמודל.

דחיות לפי סיבה:

| Company | Question | Reasons |
|---|---|---|
| KO | G3.1-Q3 (A11) | exposure_inconsistent |
| INTC | B3.7-Q3 (A8) | quote_from_facts |
| INTC | B3.8-Q6 (A10) | quote_from_facts |
| UBER | G3.1-Q3 (A11) | no_quote |

By reason: quote_from_facts 2, exposure_inconsistent 1, no_quote 1

**ארבע השורות המיוחדות:**

| Company | Skill | Expected (alt) | K5a-3 (v3.1): answer / result | K5b (3.1 default): answer / result | K5b reasoning (200) | K5b facts_check (200) |
|---|---|---|---|---|---|---|
| AMT | A8 | 0 (1) | 2 / differ | 1 / close | The company completed smaller asset acquisitions in 2025 and prior years, such as communications sites and data center facilities, while also engaging in significant divestitures like the sale of its … | The facts show no reported cash payments for acquisitions or continuing goodwill impairments in FY2021-FY2025, but report a goodwill impairment in discontinued operations in 2023 and a loss on the sal… |
| INTC | A11 | 1 | 0 / differ | 0 / differ | The company discloses that three customers account for 19%, 12%, and 12% of its net revenue, respectively. Because one or more customers exceed 25% of revenue? Wait, 19%, 12%, 12% do not exceed 25%. H… |  |
| UBER | A13 | 0 | 2 / differ | 0 / match | Reported earnings rely significantly on material one-time items, notably a $5.0 billion deferred tax valuation allowance release in 2025 and substantial unrealized gains and losses on equity securitie… | The facts show net income of -$0.50bn in FY2021, -$9.14bn in FY2022, $1.89bn in FY2023, $9.86bn in FY2024, and $10.05bn in FY2025, while the text details significant one-time items such as the $5.0 bi… |
| O | A10 | 1 (0) | 2 / differ | 2 / differ | Management details recurring and durable growth drivers including embedded contractual rent escalations, geographic expansion into international platforms, and portfolio diversification across propert… | The FACTS show consistent top-line revenue growth (5-year CAGR of 28.9%) and stable EPS growth with no reported acquisition cash outflows in the table, supporting clear and durable growth drivers desc… |

* **AMT A8:** 1 (קרוב; ציפייה 0, חלופה 1) — השתפר מ-2 (לא תואם). ✔
* **UBER A13:** 0 — תואם (בק5א-3: 2). ✔
* **INTC A11:** 0 — **לא תואם** (ציפייה 1). שלושה לקוחות 19/12/12%; הנימוק מכיל "Wait, ..." (חשיבה בקול בתוך השדה). **לא תוקן.**
* **O A10:** 2 — **לא תואם** (ציפייה 1, חלופה 0). לא השתנה.
* INTC A8 נדחה (`quote_from_facts` — המודל ציטט את שורת ה-FACTS); UBER A8 = 2 (ציפייה 1).

A11 (חשיפה):

| Company | Answer | largest_exposure | attempts |
|---|---|---|---|
| MSFT | 2 (answered) | {'name': 'None above 10%', 'share_pct': None, 'type': 'customer'} | 1 / 1 calls |
| KO | None (insufficient_evidence) | {'name': 'one bottler', 'share_pct': 10, 'type': 'customer'} | 6 / 2 calls |
| INTC | 0 (answered) | {'name': 'Customer A', 'share_pct': 19, 'type': 'customer'} | 1 / 2 calls |
| UBER | None (insufficient_evidence) | {'name': None, 'share_pct': None, 'type': 'none'} | 1 / 1 calls |
| JPM | 2 (answered) | {'name': 'None', 'share_pct': None, 'type': 'none'} | 1 / 1 calls |
| CB | 2 (answered) | {'name': 'None', 'share_pct': None, 'type': 'none'} | 1 / 1 calls |
| PGR | 2 (answered) | {'name': 'Personal Lines', 'share_pct': 87.0, 'type': 'product'} | 1 / 1 calls |
| O | 2 (answered) | {'name': '7-Eleven', 'share_pct': 3.3, 'type': 'customer'} | 1 / 1 calls |
| AMT | 1 (answered) | {'name': 'T-Mobile', 'share_pct': 18, 'type': 'customer'} | 1 / 1 calls |

KO: עדיין `exposure_inconsistent` (בקבוק אחד = 10% בדיוק; הכלל במסמך מול ציפיית הייחוס 2 — שאלה פתוחה #2 נשארת). UBER: `no_quote`.

אי-התאמות מול קבוצת הייחוס:

| Company | Question | Expected (alt) | Answer | First quote (150) | Reasoning (150) | facts_check (150) |
|---|---|---|---|---|---|---|
| MSFT | G3.8-Q3 (A13) | 2 (1) | 0 | Other income (expense), net included $6.5 billion of net gains, $4.8 billion of net losses, and $1.5 billion of net losses for fiscal years 2026, 2025… | Reported earnings rely on or include material one-time and recurring items such as net gains and losses from investments in OpenAI across multiple yea… | The facts show net income of $72.74bn in FY2022, $72.36bn in FY2023, $88.14bn in FY2024, $101.83bn in FY2025, and $133.75bn in FY2026. Reported earnin… |
| KO | G3.1-Q3 (A11) | 2 | insufficient | For the year ended December 31, 2025, one bottler accounted for 10% of our net operating revenues, which are reflected in our EMEA and Asia Pacific op… | For the year ended December 31, 2025, one bottler accounted for exactly 10 percent of net operating revenues, which does not exceed the 10 percent thr… |  |
| INTC | B3.7-Q3 (A8) | 0 | insufficient | Goodwill impairment (USD) per fiscal year, continuing operations: FY2021: 0.29bn; FY2022: 0.15bn; FY2023: 0.04bn; FY2024: 2.98bn; FY2025: 0.00bn. | The company recognized significant non-cash goodwill impairment charges in recent fiscal years, particularly in 2024 associated with Mobileye and Inte… | The FACTS show material goodwill impairments of $2.98bn in FY2024 and smaller impairments in other recent years, which indicates a mixed picture regar… |
| INTC | B3.8-Q6 (A10) | 0 (1) | insufficient | Revenue per fiscal year (USD): FY2021: 79.02bn; FY2022: 63.05bn; FY2023: 54.23bn; FY2024: 53.10bn; FY2025: 52.85bn; 5-year CAGR: -9.6%. | While the company describes ongoing expansion efforts and new technology drivers such as AI workloads and advanced process nodes, the actual growth re… | The facts show declining revenues over the 5-year period (CAGR of -9.6%), and fluctuating EPS and heavy reliance on acquisitions and external financin… |
| INTC | G3.1-Q3 (A11) | 1 | 0 | Customer A 19 % 19 % 19 % Customer B 12 % 14 % 11 % Customer C 12 % 12 % 10 % | The company discloses that three customers account for 19%, 12%, and 12% of its net revenue, respectively. Because one or more customers exceed 25% of… |  |
| UBER | B3.7-Q3 (A8) | 1 | 2 | On June 17, 2025, we completed the acquisition of an 85% controlling stake in Trendyol GO in an all-cash transaction, allowing us to expand our Delive… | The company completed acquisitions such as the Trendyol GO online meal and grocery delivery business in Türkiye during 2025 to expand its Delivery bus… | The facts given by code show acquisitions in FY2021 ($2.31bn), FY2022 ($0.06bn), and FY2025 ($0.81bn), with minimal goodwill impairments (only $0.07bn… |
| UBER | G3.1-Q3 (A11) | 2 | insufficient |  | The company operates across multiple reportable segments (Mobility, Delivery, and Freight) and a broad international geographic footprint without disc… |  |
| O | B3.8-Q6 (A10) | 1 (0) | 2 | This structure, together with our analytics-supported underwriting, is designed to generate a stable and predictable revenue stream, provide built-in … | Management details recurring and durable growth drivers including embedded contractual rent escalations, geographic expansion into international platf… | The FACTS show consistent top-line revenue growth (5-year CAGR of 28.9%) and stable EPS growth with no reported acquisition cash outflows in the table… |

### ב. חילוץ (סעיף 5) — 7 חברות, **43 קריאות** (3 מההרצה הראשונה + 40), 0 כשלי API; בהרצה השנייה 467,499 טוקני קלט / 66,398 פלט

| חברה | פרופיל | קריאות | בלוקים (שורות) |
|---|---|---|---|
| JPM | בנק | 3 | CAP 26, LOANS 8, GENERAL 3 |
| USB | בנק | 4 | CAP 19, LOANS 26, GENERAL 0 (`invalid_json` גם בניסיון השני — קריאה מבוזבזת) |
| CB | ביטוח | 3 | CAP 9, INV 24, GENERAL 7 |
| PGR | ביטוח | 3 | CAP 5, INV 20, GENERAL 22 |
| O | נדל"ן | 10 | OPS 7, MAINT 6, VALUE 4, LIQ 4, UNENC 2, NAV 22, OPU 10, FFO 25, PROFILE 11, GENERAL 20 |
| AMT | נדל"ן | 10 | 9, 9, 4, 3, 2, 24, 6, 21, 12, 22 |
| PLD | נדל"ן | 10 | 12, 6, 8, 4, 2, 18, 12, 24, 11, 14 |

סה"כ 503 שורות: **196 approved, 127 pending, 158 n/a (not_disclosed/NA), 22 rejected**.

**נדחו בבדיקות (22):** `quote_not_found` 12 (B1 7, B4 2, B8 2, B3 1), `number_not_in_quote` 6 (B11 3, B3 2, B4 1), `period_mismatch` 4 (B8), `value_state_inconsistent` 1 (B4).

**בקרות:** נכשלו — PGR INS-INV (קטגוריות 87.4 מיליארד מול סך 97.4, פער 10.3%); O FFO (פער E11 ‎-10.9%); O GENERAL (`sale_proceeds` 2023 מול שכנים). לא ניתנות לחישוב (`na`) — JPM CAP (CET1/RWA/יחס לא כולם בדוח), CB INV, VALUE ב-O/AMT/PLD (אין שווי הוגן), PLD MAINT (Q6). שאר הבקרות עברו.

**pending (127):** B10 54 (תמיד), B14 32, B12 21, B11 14 (תמיד), B4 6. **approved אוטומטי (196):** B2 34, B1 32, B13 30, B12 30, B5 19, B14 15, B6 14, B4 13, B8 6, B3 3. לא הורד 8-K (`supplemental_only` לא נבדק).

**השוואה ל-CSV (`ai_k5b_compare.py`):**

| בלוק | match | differ | class differs | חסר ב-AI | חסר ב-CSV |
|---|---|---|---|---|---|
| B1 | 13 | 0 | 0 | 4 | 19 |
| B2 | 1 | 1 | 0 | 0 | 6 |
| B3 | 0 | 0 | 0 | 0 | 3 |
| B4 | 4 | 4 | 0 | 4 | 11 |
| B5 | 5 | 5 | 0 | 10 | 8 |
| B6 | 4 | 4 | 0 | 10 | 2 |
| B8 | 2 | 1 | 0 | 4 | 2 |
| B9 | 0 | 0 | 0 | 1 | 0 |
| B10 | 16 | 0 | 5 | 34 | 33 |
| B11 | 2 | 2 | 0 | 2 | 10 |
| B12 | 23 | 11 | 0 | 27 | 17 |
| B13 | 4 | 0 | 0 | 0 | 26 |
| total | 74 | 28 | 5 | 96 | 137 |

מתוך 107 פריטים שקיימים בשני הצדדים: **74 תואמים (69%)**, 28 שונים, 5 הבדלי סיווג (B10). **96 פריטי CSV חסרים ב-AI**, ו-137 פריטי AI אינם ב-CSV.

#### Differing items (AI value, CSV value, AI quote)

| company | block | item | year | AI | CSV | AI quote |
|---|---|---|---|---|---|---|
| AMT | B12 | recon_nci_jv | 2024 | -3.527e+08 | 9.818e+08 |  / Adjustments and distributions for unconsolidated affiliates and noncontrolling interests (3) / / (450.7) / / / (352.7) / / / 28 / |
| AMT | B6 | maint_capex | 2024 | 1.574e+08 | 1.713e+08 | Capital improvement capital expenditures / / (185.2) / / / (157.4) |
| AMT | B6 | maint_capex | 2025 | 1.852e+08 | 1.956e+08 | Capital improvement capital expenditures / / (185.2) / / / (157.4) |
| CB | B4 | cat_loss_latest | 2025 | 5.84e+08 | 2.805e+09 |  / Net catastrophe losses / $ / 584 / / / $ / 1,103 / / / $ / 710 / |
| CB | B4 | inv_equity | 2025 | 5.282e+09 | 1.08e+10 | Equity securities (1)  / 5,163 / / / — / / / 119 / / / 5,282 |
| CB | B4 | inv_fixed_maturities | 2025 | 1.227e+11 | 1.308e+11 |  / / $ / 124,726 / / / $ / (52) / / / $ / 1,954 / / / $ / (3,948) / / / $ / 122,680 / / / / |
| CB | B4 | inv_other | 2025 | 1.075e+10 | 2.234e+10 | Total / $ / 10,749 / / / $ / 8,597 |
| JPM | B2 | loan_line | 2025 | 1.493e+12 | 1.409e+12 | Loans retained / $ / 1,408,905 / / / $ / 1,299,590 / / / $ / 8,273 / / $ / 7,175 |
| O | B11 | op_units_count | 2025 | 2.682e+06 | 2.76e+06 | (1) 2,681,808 units were outstanding as of both December 31, 2025 and 2024. 1,795,167 units were outstanding as of December 31, 2023. |
| O | B12 | recon_nci_jv | 2024 | 2.912e+07 | -3.902e+06 | Proportionate share of adjustments for unconsolidated entities 33,345 29,124 |
| O | B12 | recon_nci_jv | 2025 | 3.334e+07 | -1.005e+07 | Proportionate share of adjustments for unconsolidated entities 33,345 |
| O | B12 | recon_re_da | 2024 | 2.396e+09 | 2.422e+09 | Depreciation and amortization 2,524,200 2,395,644 |
| O | B12 | recon_re_da | 2025 | 2.524e+09 | 2.555e+09 | Depreciation and amortization 2,524,200 |
| O | B5 | acquisition_invested | 2025 | 4.152e+09 | 6.3e+09 |  / Total real estate acquisitions / 268 / / / / / $ / 4,152.1 / / / 10.1 / |
| O | B5 | acquisition_yield | 2025 | 7 | 7.3 | Initial weighted average cash yield (1)  / / / / / 7.0 / % / / / |
| O | B5 | occupancy | 2025 | 99 | 98.9 |  / Total/average / 15,511 / / 99 / % / / 355,035 / / 100.0 / % |
| O | B6 | straight_line_rent_affo | 2024 | -1.719e+08 | 1.719e+08 | Straight-line rent and expenses, net / / / / / (169,217) / / / (171,887) |
| O | B6 | straight_line_rent_affo | 2025 | -1.692e+08 | 1.692e+08 | Straight-line rent and expenses, net / / / / / (169,217) / / / (171,887) |
| PLD | B11 | op_units_count | 2025 | 1.49e+07 | 2.176e+07 | There were limited partnership units in the OP, excluding the Class A Units, that were exchangeable into cash or, at our option, 14.9 million and 9.0 million shares of the Parent’s common stock, at... |
| PLD | B12 | re29_re_sale_gains | 2024 | -4.14e+08 | 4.14e+08 | Gains on dispositions of development properties and land, net (258 ) (414 ) |
| PLD | B12 | re29_re_sale_gains | 2025 | -2.58e+08 | 2.58e+08 | Gains on dispositions of development properties and land, net (258 ) (414 ) |
| PLD | B12 | re29b_fx_net | 2024 | -6.8e+07 | 6.734e+07 | Unrealized foreign currency, derivative and other losses (gains), net 125 (68 ) |
| PLD | B12 | re29b_fx_net | 2025 | 1.25e+08 | -1.257e+08 | Unrealized foreign currency, derivative and other losses (gains), net 125 (68 ) |
| PLD | B12 | recon_re_da | 2024 | 2.504e+09 | 2.999e+09 | Real estate related depreciation and amortization 2,539 2,504 |
| PLD | B12 | recon_re_da | 2025 | 2.539e+09 | 3.09e+09 | Real estate related depreciation and amortization 2,539 2,504 |
| PLD | B5 | development_invested | 2024 | 1.235e+09 | 4.13e+09 | TEI $ 2,943 $ 1,235 |
| PLD | B5 | development_invested | 2025 | 2.943e+09 | 2.271e+09 | TEI $ 2,943 $ 1,235 |
| PLD | B8 | committed_undrawn_facilities | 2025 | 6.431e+09 | 6.5e+09 | Current availability $ 6,431 |
| O | B10 | bsa_inre [consolidated] (CSV class bsa_carry) | 2025 | 1.256e+09 | 1.256e+09 | Investment in unconsolidated entities / 1,256,456 / / / 1,229,699 |
| AMT | B10 | bsa_wc [CONSOLIDATED BALANCE SHEETS] (CSV class bsa_excl) | 2025 | 1.475e+09 | 1.475e+09 | Cash and cash equivalents / / $ / 1,474.8 |
| AMT | B10 | bsa_carryfin [CONSOLIDATED BALANCE SHEETS] (CSV class bsa_wc) | 2025 | 8.769e+08 | 8.769e+08 | NOTES RECEIVABLE AND OTHER NON-CURRENT ASSETS / / 876.9 |
| PLD | B10 | bsa_inre [consolidated] (CSV class bsa_carry) | 2025 | 1.109e+10 | 1.109e+10 | Investments in and advances to unconsolidated entities 11,093,936 |
| PLD | B10 | bsa_other [consolidated] (CSV class bsa_noi) | 2025 | 2.033e+08 | 2.033e+08 | Assets held for sale or contribution 203,344 |

תבניות בולטות בהבדלים: (1) **סימן** — O/PLD ב-B12 וב-B6 (`straight_line_rent_affo`, `re29_re_sale_gains`, `re29b_fx_net`): ה-AI שומר את הסימן כפי שבציטוט (סוגריים) והמנוע/ה-CSV מצפים לסימן הפוך; (2) **שנה** — PLD/O: בטבלה דו-שנתית המודל הצמיד עמודה לא נכונה (`recon_re_da`, `development_invested`); (3) **CB B4** — נלקחה שורת "Total" אחרת; (4) **JPM B2** — ברוטו מול "retained". ייתכן שחלק מהפערים הם טעויות CSV (למשל PLD `recon_re_da`); **לא נבדקו אחד-אחד**.

### ג. השפעה על ציון

**ניקוד AI בלבד (9 חברות; לפני = golden 2026-10-20 ללא AI):**

| Company | Model | Score before | Score after | Range before | Range after | Coverage before / after | Buy price before | Buy price after |
|---|---|---:|---:|---|---|---|---:|---:|
| MSFT | buffett | 96.18 | 96.12 | 78.12–97.12 | 96.12–96.12 | full 1.00 / full 1.00 | 306.03 | 305.96 |
| MSFT | graham | 94.04 | 92.38 | 88.38–94.38 | 92.38–92.38 | full 1.00 / full 1.00 | 85.74 | 85.14 |
| KO | buffett | 84.57 | 87.38 | 70.38–87.38 | 87.38–87.38 | full 1.00 / full 1.00 | 26.43 | 26.79 |
| KO | graham | 68.89 | 67.23 | 63.23–69.23 | 65.23–67.23 | full 1.00 / full 0.98 | 11.57 | 11.27 |
| INTC | buffett | 15.92 | 25.24 | 12.22–31.22 | 24.22–28.22 | full 1.00 / full 0.96 | - | - |
| INTC | graham | 48.39 | 45.64 | 43.64–49.64 | 45.64–45.64 | full 1.00 / full 1.00 | - | - |
| UBER | buffett | 61.82 | 69.84 | 49.84–69.84 | 69.84–69.84 | full 1.00 / full 1.00 | 5.51 | 5.97 |
| UBER | graham | 41.73 | 40.96 | 37.21–43.21 | 39.21–41.21 | full 1.00 / full 0.98 | - | - |
| JPM | buffett | 91.40 | 94.04 | 76.04–94.04 | 94.04–94.04 | full 1.00 / full 1.00 | 241.97 | 244.56 |
| JPM | graham | 87.03 | 87.03 | 83.03–87.03 | 87.03–87.03 | full 1.00 / full 1.00 | 122.36 | 122.36 |
| CB | buffett | 92.75 | 94.24 | 71.67–94.24 | 94.24–94.24 | full 0.90 / full 0.90 | 282.09 | 283.78 |
| CB | graham | 89.64 | 89.64 | 84.94–89.64 | 89.64–89.64 | full 0.85 / full 0.85 | 148.82 | 148.82 |
| PGR | buffett | 91.56 | 93.56 | 72.67–93.56 | 93.56–93.56 | full 0.90 / full 0.90 | 119.13 | 120.10 |
| PGR | graham | 90.40 | 90.40 | 85.06–90.40 | 90.40–90.40 | partial 0.75 / partial 0.75 | - | - |
| O | buffett | 79.38 | 84.93 | 59.27–85.10 | 82.74–85.10 | full 0.83 / full 0.83 | 46.95 | 49.23 |
| O | graham | 84.76 | 84.76 | 76.50–85.39 | 80.94–85.39 | full 0.86 / full 0.86 | 31.24 | 31.24 |
| AMT | buffett | 78.29 | 82.83 | 56.59–84.19 | 80.66–83.01 | full 0.83 / full 0.83 | 101.93 | 106.02 |
| AMT | graham | 92.14 | 90.81 | 86.81–92.14 | 90.81–90.81 | partial 0.75 / partial 0.75 | - | - |

השינויים ברמת הקריטריון מפורטים בפלט `scripts/ai_report_k5b.py scripts/output_k5b/golden_scoring`. הציונים הפכו מטווחים לערך בודד.

**חילוץ AI מול CSV (7 חברות; ניקוד ה-AI זהה בשלוש העמודות):**

| Company | Model | Score CSV | AI approved | AI incl. pending | Cov CSV / approved / all | Buy price CSV | approved | all |
|---|---|---:|---:|---:|---|---:|---:|---:|
| JPM | buffett | 94.04 | 94.04 | 94.04 | 1.00 / 1.00 / 1.00 | 244.56 | 244.56 | 244.56 |
| JPM | graham | 87.03 | 87.03 | 87.03 | 1.00 / 1.00 / 1.00 | 122.36 | 122.36 | 122.36 |
| USB | buffett | 74.97 | 74.97 | 74.97 | 1.00 / 1.00 / 1.00 | 40.55 | 40.55 | 40.55 |
| USB | graham | 70.75 | 70.75 | 70.75 | 1.00 / 1.00 / 1.00 | 30.72 | 30.72 | 30.72 |
| CB | buffett | 94.24 | 94.24 | 94.24 | 0.90 / 0.90 / 0.90 | 283.78 | 283.78 | 283.78 |
| CB | graham | 89.64 | 90.05 | 90.05 | 0.85 / 0.85 / 0.85 | 148.82 | 149.10 | 149.10 |
| PGR | buffett | 93.56 | 93.56 | 93.56 | 0.90 / 0.90 / 0.90 | 120.10 | 120.10 | 120.10 |
| PGR | graham | 90.40 | 90.40 | 90.40 | 0.75 / 0.75 / 0.75 | - | - | - |
| O | buffett | 84.93 | 88.72 | 80.09 | 0.83 / 0.83 / 0.83 | 49.23 | - | - |
| O | graham | 84.76 | 84.76 | 81.96 | 0.86 / 0.86 / 0.86 | 31.24 | 31.24 | 31.90 |
| AMT | buffett | 82.83 | 76.21 | 76.21 | 0.83 / 0.83 / 0.83 | 106.02 | 79.14 | 79.14 |
| AMT | graham | 90.81 | 85.92 | 85.92 | 0.75 / 0.75 / 0.75 | - | - | - |
| PLD | buffett | 77.93 | 71.03 | 71.03 | 0.98 / 0.98 / 0.98 | 47.14 | 43.90 | 43.90 |
| PLD | graham | 94.68 | 93.77 | 93.77 | 0.75 / 0.75 / 0.75 | - | - | - |

קריטריונים שהשתנו:

| Company | Model | Criterion | CSV | AI approved | AI incl. pending |
|---|---|---|---:|---:|---:|
| CB | graham | 3.7 Quality of equity and assets | 5.23 | 5.57 | 5.57 |
| O | buffett | 3.2 Moat | 9.18 | 9.18 | 5.82 |
| O | buffett | 3.5 Owner earnings | 11.65 | 13.92 | 11.93 |
| O | buffett | 3.8 Quality, sustainable growth | 9.58 | 10.52 | 8.53 |
| O | graham | 3.5 Dividend history | 9.30 | 9.30 | 9.15 |
| O | graham | 3.6 Moderate earnings growth | 12.57 | 12.57 | 10.21 |
| AMT | buffett | 3.2 Moat | 9.00 | 6.90 | 6.90 |
| AMT | buffett | 3.3 Consistent profitability | 13.97 | 12.97 | 12.97 |
| AMT | buffett | 3.5 Owner earnings | 10.83 | 10.13 | 10.13 |
| AMT | buffett | 3.7 Management and capital allocation | 8.09 | 8.54 | 8.54 |
| AMT | buffett | 3.8 Quality, sustainable growth | 9.28 | 7.00 | 7.00 |
| AMT | graham | 3.4 Earnings stability | 15.00 | 13.02 | 13.02 |
| AMT | graham | 3.5 Dividend history | 9.00 | 8.84 | 8.84 |
| AMT | graham | 3.6 Moderate earnings growth | 12.11 | 11.83 | 11.83 |
| AMT | graham | 3.8 Earnings quality and dilution | 10.00 | 8.75 | 8.75 |
| PLD | buffett | 3.2 Moat | 6.54 | 1.04 | 1.04 |
| PLD | buffett | 3.4 Return on capital | 11.28 | 11.32 | 11.32 |
| PLD | buffett | 3.5 Owner earnings | 11.93 | 9.96 | 9.96 |
| PLD | buffett | 3.6 Balance sheet and debt | 9.71 | 9.70 | 9.70 |
| PLD | buffett | 3.8 Quality, sustainable growth | 9.02 | 10.24 | 10.24 |
| PLD | graham | 3.2 Financial condition and liquidity | 14.82 | 14.79 | 14.79 |
| PLD | graham | 3.5 Dividend history | 9.59 | 9.66 | 9.66 |
| PLD | graham | 3.8 Earnings quality and dilution | 7.79 | 7.08 | 7.08 |

* **JPM, USB, PGR, CB buffett:** אפס שינוי. CB graham +0.41.
* **נדל"ן — שינוי ממשי:** AMT buffett ‎82.83→76.21 (מחיר קנייה 106.02→79.14), PLD buffett ‎77.93→71.03 (47.14→43.90), O buffett ‎84.93→88.72 (מאושרים בלבד) / 80.09 (כולל pending), ומחיר הקנייה של O buffett **נעלם** כשערכי ה-AI נכנסים. חלק מהכיוון נובע מהבדלי הסימן/שנה שלמעלה — **אין להפעיל חילוץ AI בנדל"ן לפני תיקון והשוואה פריט-פריט**.
* מאושרים מול pending: בבנקים/ביטוח אין הבדל; ב-O ההבדל גדול (88.72 מול 80.09).

### ד. קריאות בפועל וקיבולת (מדידה, מחליפה את ההערכה בסעיף 6)

* **ניקוד:** 118 קריאות ל-9 חברות = **13.1 לחברה** (בלי סיווג, שמוסיף 1).
* **חילוץ, דוח אחרון:** בנק 3.5 (JPM 3, USB 4), ביטוח 3, נדל"ן 10; חברה כללית — לא הורצה (B14 בלבד, 0–1).
* **לחברה (ניקוד + סיווג + חילוץ):** כללית ≈ 15; בנק ≈ 17.6; ביטוח ≈ 17; נדל"ן ≈ 24.
* **חברות ליום עם 450:** כללית ≈ 30; בנק ≈ 25; ביטוח ≈ 26; נדל"ן ≈ 18 (דוח אחרון בלבד; טעינת 5 שנים מוסיפה ~50–100% לחילוץ ← נדל"ן ≈ 13–15, בנק/ביטוח ≈ 20–22). היום נוצלו 168 מתוך 450.

**pytest מלא אחרי התיקונים: 545 עברו.**

### ה. מה נשאר פתוח
1. לפני שימוש בחילוץ AI: נירמול סימן לפי שם פריט (O/PLD B12/B6); בדיקת שיוך עמודת שנה בטבלאות דו-שנתיות; USB GENERAL `invalid_json`; INTC A11 "Wait,..." בנימוק. **לא בוצע** (מעבר לטווח הריצה האוטומטית).
2. שאלות #2 (KO A11) ו-#5 (רשימת B14) — ללא שינוי.

---

## עדכון לאחר ההחלטות (22.10, ‏~15:00) — הוחל בקוד, **עדיין לא נבדק מול המודל**

1. **commits:** שני ה-commits בוצעו (ההודעה השנייה: "model runs pending"). מסמך הסקילים הנוכחי: `docs/ai/ValueCompass_AI_Skills_Scoring_2026-10-22_14-49.*`; הגרסאות 21-19-28 ו-13-52 הוסרו; מפרט K6 — נשארה 14-39 (14-20 הוסר; 14-33 לא נגעתי בה).
2. **A11:** `share_pct` = אחוז מההכנסות כפי שדווח (לא נפח), נוסח בפלט של `scoring.yaml`. הסט של KO נשאר 2.
3. **ציטוטים:** כלל הציטוט נוסח בלי הסימן `...` ("Copy each quote as one continuous passage..."); ניסיון חוזר אחד כשהסיבה היחידה היא `quote_not_found`, עם ההערה "Quote not found verbatim: <120 תווים ראשונים>. Copy one continuous passage exactly as it appears in the TEXT." (גם ב-`extraction.yaml`). בדיקה חדשה ב-`tests/test_ai.py`.
4. **מכסה:** `src/ai/usage.py` — מונה יומי משותף בקובץ (`scripts/ai_store/usage.json`, יום לפי שעון פסיפיק, תקרה **450** לכל התהליכים יחד, כל ניסיון בקשה נספר) ונעילת תהליך יחיד (`run.lock`; תהליך חדש לא מתחיל כשיש פעיל ורענן). פעיל בלקוח אמיתי בלבד (לא בבדיקות). אותחל ל-500 להיום (מוצה).
5. **B14:** `src/ai/b14.py` — הרשימה נגזרת ממילון Part E לפי פרופיל: פריטי מנוע על דוח רווח והפסד / מאזן / תזרים (נוסף מקטע `X-CF`), נשלפים בקוד מתג (לא C5), שאינם מכוסים ב-B1–B13, וחסרי ערך מתג באותה שנה (מאזן: שתי שנים אחרונות). כולם בקריאה אחת לדוח. ספירה (פריט-שנה, 3 שנים אחרונות): JPM 66 נדרשו / 63 מכוסים בתגים / 3 נשאלים; USB 66/63/3; CB 87/80/7; PGR 87/65/22; O 93/73/20; AMT 93/71/22; PLD 93/79/14. פריט B14 שאינו ברשימת "מזין תת-פריט יחיד" → `pending`.

## 0. מצב השלב בקצרה (22.10, לפני האיפוס — הוחלף בסעיף "תוצאות הרצה אמיתית" למעלה)

| חלק | מצב |
|---|---|
| סעיף 1 — קוד: תבנית 3.1 כברירת מחדל, עובדות A8 כולל פעילות מופסקת, בדיקת עקביות A11 + בדיקות | **הושלם**, כל הבדיקות עוברות (525 + בדיקות החילוץ, ראו סעיף 7) |
| סעיף 2 — הרצת ניקוד, 9 חברות | **חלקי**: 36 תשובות ייחודיות מתוך ~108 (MSFT 13, KO 12, INTC 11). UBER, JPM, CB, PGR, O, AMT לא הורצו. אין חישוב השפעה על הציון |
| סעיף 3 — תשתית חילוץ (yaml, מקטעים לפי כותרת, בדיקות, בקרות, אישורים, אחסון, תור אישורים, חיבור למנוע) | **הושלם ונבדק בלי קריאות מודל** (בדיקות יחידה + ריצה יבשה על 7 החברות) |
| סעיף 4 — מיפוי עמודות ה-CSV לבלוקים | **הושלם** (בלי קריאות מודל) |
| סעיף 5 — הרצת חילוץ על 7 חברות והשוואה ל-CSV | **לא הורץ** — המכסה היומית נגמרה |
| סעיף 6 (תוצאות חילוץ, השפעה על ציון) | **תלוי בסעיפים 2 ו-5** — לא קיים |
| סעיף 7 — commits | **לא בוצע** (ממתין להחלטה, ראו סעיף 8) |

### מה קרה עם המכסה
* בדיקה ישירה מול ה-API (קריאה אחת, "OK") החזירה `429 RESOURCE_EXHAUSTED`: **`generate_content_free_tier_requests, limit: 500, model: gemini-3.5-flash-lite`**, "retry in 19h22m" — כלומר האיפוס הוא ב-23.10.2026 סביב 10:00 שעון ישראל (חצות שעון הפסיפיק).
* **המכסה האמיתית היא 500 קריאות ליום למודל, לא 200.** המגבלה בקוד (`DEFAULT_RPD = 200`, `--rpd`) נשארה כפי שהיא, אבל היא **מונה לכל תהליך בנפרד** ולא ליום: ק5א-3 הריץ היום 434 קריאות (216 + 218), ואלה נספרות בנפרד מהמונה של התהליך.
* **טעות שלי:** הפעלתי את הרצת הניקוד פעמיים במקביל (ההפעלה הראשונה לא מתה כשהמעטפת שלה הסתיימה, והפעלתי שוב). שני תהליכים שאלו אותן שאלות זה לצד זה כ-8 דקות, עד שזיהיתי ועצרתי את השני: 23 מתוך 59 השורות בקובץ הן כפילויות (36 ייחודיות), כלומר ~23 קריאות מבוזבזות. סה"כ היום: ~434 (ק5א-3) + ~59 + בדיקה אחת ≈ 500.
* ההרצה נתקעה בשאלה INTC G3.1-Q4 (המכסה כבר נגמרה; שכבת הלקוח ממשיכה לנסות מחדש), עצרתי את התהליכים. **שום דבר לא נכתב ל-Supabase, `.env` לא שונה, לא נמחק דבר.**
* המלצה: מונה יומי משותף בקובץ (`scripts/ai_store/usage_<תאריך פסיפיק>.json`) שכל תהליך קורא ומעדכן, כך ש-`--rpd` הוא תקרה לכל היום ולא לתהליך. לא יישמתי — זה משנה את משמעות המגבלה שביקשתם להשאיר.

## 1. תבנית 3.1 כברירת מחדל (סעיף 1) — הושלם

**קוד**
* `src/ai/prompt.py`: `build_prompt(..., variant="3.1")` — ברירת המחדל 3.1; שדה `facts_check` לפני `answer` רק כשיש FACTS; כלל הציטוט המעודכן (קטע רציף אחד, לעולם לא `...`, לא מתוך FACTS). `prompt_version` נשמר `<גרסת skill>.1` (`assess.prompt_version_of`).
* `src/ai/skills/scoring.yaml` נוצר מחדש מהמסמך `ValueCompass_AI_Skills_Scoring_2026-10-22_13-52` (A8: עובדות כולל פעילות מופסקת ו"לא דווח"; A11: `code_check`). בדיקת הסקאלה מילה במילה מול Rulebook 19-26 נשארה ועוברת.
* **A8 — עובדות:** `src/ai/facts.py` — שנה שאינה בסדרה מוצגת **"not reported"** ולא 0; סריקה דטרמיניסטית של הערת הרכישות/הפעילות המופסקת (`discontinued_facts`): ירידות ערך ורווחי/הפסדי מכירה שנרשמו בפעילות מופסקת. דוגמת AMT (הפלט שהמודל יקבל כ-FACTS):
  ```
  Goodwill impairment (USD) per fiscal year, continuing operations: FY2021..FY2025: not reported
  Recorded in DISCONTINUED operations (from the notes; not in the series above): year not stated: loss on the sale 1.20bn; 2023: goodwill impairment 0.32bn.
  ```
  שני הפריטים שנדרשו נמצאו (הפסד המכירה של ATC TIPL, 1.2 מיליארד; ירידת ערך הודו 322 מיליון ב-2023). **מגבלה:** בהערה, משפט הפסד המכירה אינו כולל שנה, ולכן מוצג "year not stated" (לא ניחשתי את 2024). ל-MSFT: "none found".
* **A11 — בדיקת עקביות בקוד:** `checks.exposure_consistent` — לקוח >25% מאפשר 0; 10–25% מאפשר 1 (או 0 רק עם תלות אחרת מוצהרת: מוצר/רישיון/שוק); <10% מאפשר 2 (או תלות אחרת). אי-עקביות → ניסיון חוזר אחד עם ההערה "Your share_pct does not match the level you chose"; עדיין לא עקבי → נדחה עם `exposure_inconsistent`.
* `scripts/run_ai_k5a3.py`: ברירת מחדל `--prompt-version 3.1`; מזין `discontinued` ל-FACTS של A8.

**בדיקות** (`tests/test_ai.py`, 45 בדיקות): 3.1 ברירת מחדל ו-`facts_check` רק עם FACTS; גרסה 3 במפורש; שמירה תחת `prompt_version` ‏`2.1`; עובדות A8 (פעילות מופסקת, "not reported", "none found"); A11 — כל הרמות, ניסיון חוזר אחד עם ההערה, דחייה כשנשאר לא עקבי, וקבלה כשהניסיון השני עקבי.

## 2. ניקוד עם תבנית 3.1 — חלקי (59 תשובות)

אחסון: `scripts/ai_store/k5b/scoring/gemini-3.5-flash-lite/v3.1/assessments.jsonl` (לא ב-git). 59 שורות בקובץ, **36 ייחודיות** (23 כפילויות מההרצה הכפולה; הטוען לוקח את האחרונה): MSFT 13, KO 12, INTC 11 (עד G3.1-Q3). חסרות: UBER, JPM, CB, PGR, O, AMT, וגם INTC G3.1-Q4 ו-G3.8-Q3.

התאמה לקבוצת הייחוס v2 — **רק החברות שהושלמו**, מול ק5א-3 (v3.1):

| חברה | ק5א-3 (v3.1) | ק5ב (3.1 ברירת מחדל) |
|---|---|---|
| MSFT | 10/12 | 8/12 |
| KO | 11/12 | 10/12 |
| INTC | 9/13 | 6/13 (2 שורות חסרות בגלל המכסה) |

**אין להסיק מכאן אחוז כולל** — 3 חברות בלבד ואחת חלקית. אבל יש ממצאים מהותיים:

1. **דחיות: 8 מתוך 36 תשובות ייחודיות (7 × `quote_not_found`, 1 × `exposure_inconsistent`); על אותן 36 שאלות ב-ק5א-3 (v3.1): 2 דחיות.** בולט במיוחד: MSFT A3, A4, A5; INTC A1, A7, A8 (גם A5/B3.2-Q5). בחלק מהן המודל עדיין מכניס `...` לתוך הציטוט (למשל `"Threat actors... continuously undertake attacks"`, `"...As a result of our impairment tests"`) למרות שהוראת הציטוט החדשה אוסרת זאת במפורש ("never '...'"); באחרות הציטוט מרכיב שני קטעים שאינם סמוכים. ההוראה החדשה לא מונעת את ההתנהגות; הבדיקה בקוד תופסת אותה, אבל אלה תשובות שנזרקות (`insufficient_evidence`). ההרצה אינה זהה מבחינת המדגם (36 שאלות, 3 חברות), אך הכיוון ברור: **נסיגה**. נדרש ניסוי נוסף (למשל ניסוח מחדש, או ניסיון חוזר אחד על `quote_not_found` מסוג `...`) — לא נעשה בלי מכסה.
2. **A11 — KO נדחה `exposure_inconsistent`:** המודל קבע שלקוח (בקבוק) אחד הוא 10% מההכנסות וענה 2; לפי בדיקת הקוד 10–25% מאפשר 1 בלבד, ולכן אחרי ניסיון חוזר אחד התשובה נדחתה. ציפיית קבוצת הייחוס ל-KO היא 2. הכלל במסמך הניקוד סותר את שורת הייחוס; צריך להחליט איזה מהם נכון (ראו שאלות פתוחות).
3. **A11 — INTC:** ק5א-3 ענה 0 (לא תואם); ק5ב ענה **1 (תואם לציפייה 1)** — שלושה לקוחות מעל 10% (19%, 12%, 12%). זו התוצאה שהבדיקה אמורה לתקן.
4. **שורות הבדיקה הנוספות:** AMT A8, UBER A13, O A10 — **לא הורצו**. INTC A8 נדחה (`quote_not_found`, אותה בעיית `...`); ב-ק5א-3 ענה 0 (תואם).
5. MSFT A13: ק5ב ענה 0 (ציפייה 2; חלופה 1) לעומת 2 בק5א-3 — שינוי תשובה אחד, ללא דחייה.

השפעה על ציון (9 חברות): **לא חושבה** — נדרשת ההרצה המלאה. הפקודה מוכנה (ראו סעיף 9).

## 3. תשתית החילוץ (סעיף 3) — הושלם, נבדק בלי קריאות מודל

| רכיב | קובץ |
|---|---|
| skill-ים B1–B14 כנתונים: תבנית 2.1 + כללי ציטוט 3.1, פריטים (`item_key`), בקרה, כלל אישור, מפרט מקטעים | `src/ai/skills/extraction.yaml` |
| מקטעים חדשים **לפי כותרת** (הערה ממוספרת לפי כותרתה) ובחזרה ל**עוגנים** (חלונות טקסט סביב ביטויים) — הון/נזילות בנק, הון סטטוטורי ורול-פורוורד עתודות, השקעות ואיכות אשראי, חוב ופדיונות, שווי הוגן נדל"ן, הון/NCI/EPS, FFO/AFFO ב-MD&A, מאזן ודוח רווח והפסד | `src/ai/sections.py` (`ext_section`, `ext_sections`) |
| בדיקות פריט: JSON תקין (כולל הצלה של תשובה שנחתכה), ציטוט מילה במילה, המספר מופיע בציטוט אחרי המרת סקאלה (מיליון/אלף/מיליארד, סוגריים = שלילי, אחוזים), יחידה מותרת, התקופה שייכת לדוח, `value_state` עקבי (null רק עם NA/not_disclosed) | `src/ai/ext_checks.py` |
| בקרות בלוק: B1 (CET1 מול RWA ±0.2pp), B2 (סכום שורות = סך הלוואות ±1%), B4 (קטגוריות = סך השקעות ±2%), B5/B9 (גבולות 0–100%), B10 (שורות = סך נכסים ±0.5%; לא מזוהה >10% → ללא ציון מחיר גרהם), B14 (פי 3 משכנים); בקרות מנוע (נדל"ן) — Q6 (B6), רצועת כיסוי 0.8–1.25 (B8), E11 + RE29b (B12), טווח שווי/עלות 0.5–3× ובסיס (B7), רצועת הראוטר 5pp (B13) | `src/ai/ext_checks.py`, `src/scoring/ext_items.py` (`re_controls`) |
| קריאה לכל skill לדוח, אחסון קריאות (התשובה הגולמית נשמרת → בדיקות/בקרות/אישורים ניתנים להרצה מחדש בלי קריאה), אישורים, תור אישורים | `src/ai/extract.py` |
| חיבור למנוע: המרת פריטים ל-`reg` בצורת טוענות ה-CSV; `attach_ext` — **no-op בלי `VC_AI_EXT_STORE`**; פריטי `pending` נכנסים רק עם `VC_AI_EXT_UNAPPROVED=1` ומסמנים `extraction_unapproved` | `src/scoring/ext_items.py` |
| ריצה / השוואה / מיפוי | `scripts/run_ai_k5b_extract.py`, `scripts/ai_k5b_compare.py`, `scripts/ai_k5b_csv_map.py`, `scripts/ai_report_k5b.py` |

**סטטוסי אישור (ספק §7), כפי שמומשו:** `approved` (אוטומטי לפי כלל הבלוק) או `pending`; **תמיד `pending`:** B10, B11; **לפי בקרה:** B6 (Q6), B7 (בסיס + טווח), B8 (כיסוי מחוץ ל-0.8–1.25 = אוטומטי), B12 (E11 ו-RE29b), B13 (רחוק >5pp מהסף); **B14:** פריט שמזין שווי/מחיר קנייה/פרופיל, או שהבקרה סימנה אותו → `pending`. בלוק "אוטומטי" שבקרתו נכשלה → `pending` (החמרה שלי — המסמך לא מגדיר מה קורה אז). בקרה שאי אפשר לחשב (`na`) בבלוק "לפי בקרה" → `pending`. פריט שנדחה בבדיקות → `rejected` (נשמר עם הסיבה). `not_disclosed` של פריט שמופיע בדרך כלל רק ב-supplemental (תפוסה, תשואות, unencumbered, מכסת CapEx ועוד) מסומן `supplemental_only` — לא הורדתי 8-K.

**B14 (חילוץ כללי):** שאלה אחת לחברה לדוח, עם הפריטים החסרים בלבד. ספירה: לכל חברה נספרים פריטי-שנה (3 שנים אחרונות) מרשימת פריטי מנוע שיש להם תג XBRL במקרים רגילים; רק חוסר בתג נשאל. הרשימה (`B14_CANDIDATES` ב-`run_ai_k5b_extract.py`) היא רשימת הפריטים שזיהיתי כחסרים ב-golden; **לא גזרתי אותה ממילון Part E** (יש שם 190+ שורות; זו החלטה שצריך לאשר).

**בדיקות:** `tests/test_ai_extract.py` — 11 בדיקות (14 הבלוקים קיימים; הנחיה; בדיקות פריט עם כל סיבת דחייה; המרות מספר/סקאלה/סוגריים/אחוזים; כל הבקרות; כללי אישור; הצלת תשובה חתוכה; `ask_block` שומר קריאה פעם אחת ושורות נושאות בדיקה/בקרה/אישור; מקטעים לפי כותרת ולפי עוגן; מיפוי CSV; `to_reg`/`attach_ext`). **ריצה יבשה** (`run_ai_k5b_extract.py --no-calls`) על 7 החברות רצה עד הסוף, כולל חישוב בקרות מנוע הנדל"ן על קלט ריק.

**מקטעים (אורך בתווים) — בדיקה על 7 החברות:** כל המקטעים נמצאו (לאחר תיקון חיפוש המאזן/דוח רווח והפסד לטבלאות בלי `|`); הפרומפט הגדול ביותר ~64K תווים (~16K טוקנים). רוב המקטעים נחתכו ל-cap (`trimmed`) — סיכון: נתון שאינו בחלון לא יימצא; נדרש כיול לאחר הרצה אמיתית.

## 4. מיפוי עמודות ה-CSV לבלוקים (סעיף 4) — בלי קריאות מודל

הפלט המלא בנספח א׳ (ובקובץ `scripts/ai_store/k5b/csv_map.md`). סיכום:

| קובץ | שורות (פריט-שנה) | שמות פריטים | מכוסות בבלוק | לא מכוסות |
|---|---|---|---|---|
| `bank_regulatory.csv` | 268 (12 בנקים; שנה אחת, 2025) | 114 | 209 — B1: 102, B2: 107 | 59 שורות: funding:* (33), nonaccrual_loans, past_due_90_accruing:*, nco, avg_loans, acl_loans, preferred_stock |
| `insurance_regulatory.csv` | 127 (12 מבטחות; 2023–2025 רק ב-`adverse_prior_year_dev`) | 20 | 117 — B3: 18, B4: 99 | 10 שורות: total_fixed_income (6), debt_total (2), structural_event:* (2) |
| `realestate_extracted.csv` | 871 (11 חברות; 2020–2025 + רבעונים) | 210 | 791 — B5: 98, B6: 137, B7: 10, B8: 30, B9: 14, B10: 150, B11: 33, B12: 305, B13: 14 | 80 שורות: affo_br__*/affo_addback_* (גשר AFFO, ~55), rental_revenue_extracted, property_opex_extracted, bs_check__*, debt_total_bs, secured_debt, same_store_revenue_growth |

מועמדי B14 / מחוץ לבלוקים: כל מה שבעמודת "לא מכוסות" (לא ידוע אם המנוע זקוק להם בהכרח; `funding:*` ו-`nonaccrual`/`past_due` נכנסו לרשימת B14 של הבנקים). הערות: (א) שורות רבעוניות (`*_q`) ב-RE מסוכמות בטוען ל-שנה; ה-AI מחלץ שנתי — ההשוואה מדלגת על `_q`. (ב) `alm_disclosed` ב-CSV הוא טקסט, ב-AI 1/0. (ג) ב-B12, `recon_jv_other_adjust` ו-`recon_nci_adjust` ממופים ל-`recon_nci_jv` (שני עמודות CSV → פריט אחד ב-AI) ולכן השוואה לפי סכום.

## 5. הרצת חילוץ (סעיף 5) — תכנון (הורץ ב-23.10; ראו תוצאות למעלה)

תכנון ההרצה (חברות: JPM, USB; CB, PGR; O, AMT, PLD; דוח אחרון בלבד כולל תקופות ההשוואה): בנק 2 בלוקים + B14 = 3 קריאות; מבטחת 2 + B14 = 3; נדל"ן 9 בלוקים (B5–B13) + B14 = 10. סה"כ **42 קריאות** (+ ניסיונות חוזרים), מתחת ל-70. הפקודה (אחרי איפוס המכסה):

```bash
.venv/Scripts/python.exe scripts/run_ai_k5b_extract.py --rpm 20 --rpd 70
.venv/Scripts/python.exe scripts/ai_k5b_compare.py
```

## 6. ספירת קריאות והערכת קיבולת (הערכה, לא מדידה)

קריאות לחברה, דוח אחרון: בנק ומבטחת — 3 (2 בלוקי פרופיל + B14); נדל"ן — 10; חברה כללית — 1 (B14, ואם אין פריט חסר — 0). טעינה ראשונית של 5 שנים: הדוח האחרון מכסה 3 שנים (דוח רווח והפסד) / 2 (מאזן), ולכן דרוש דוח אחד נוסף לשנים 4–5 בבלוקים רב-שנתיים (B5, B6, B12, B13, B14) — בערך פי 1.5–2 קריאות: בנק/מבטחת ~5–6, נדל"ן ~15–18. ועוד ~12 קריאות ניקוד + 1 סיווג לחברה. לכן חברה: כללית ~13; בנק/מבטחת ~19; נדל"ן ~30. **חברות ליום:** עם 200 קריאות (תקרת הקוד) ≈ 6–15; עם 500 (המכסה האמיתית שנמדדה) ≈ 16–38. **ללא אימות** — נדרשת הרצת סעיף 5 כדי לקבל ממוצע אמיתי.

## 7. בדיקות

`pytest` מלא: **525 עברו** (אחרי כל השינויים, כולל `tests/test_ai.py` 45 ו-`tests/test_ai_extract.py` 11).

## 8. החלטות ושאלות פתוחות

1. **להמתין לאיפוס (מומלץ) ולהשלים את סעיפים 2 ו-5 לפני ה-commits, או לבצע commit לקוד עכשיו (בלי תוצאות מודל)?** פירוט: commit א׳ (תבנית 3.1, עובדות A8, בדיקת A11) מוכן; commit ב׳ (תשתית החילוץ) מוכן אך לא נבדק מול תשובות מודל אמיתיות — ייתכנו תיקונים (כיול מקטעים, ניסוח).
2. **שורת הייחוס של KO ב-A11 (ציפייה 2) מול כלל העקביות (10% → רמה 1):** אחד מהם צריך להשתנות.
3. **`...` בציטוטים:** הוראה כתובה לא מספיקה (8 דחיות מתוך 36 לעומת 2 בק5א-3). רוצים ניסיון חוזר אחד על דחיית `quote_not_found` מסוג `...`?
4. **מונה מכסה יומי משותף** (סעיף 0) — מאשרים?
5. **רשימת B14:** לאשר את הרשימה הצרה, או לגזור ממילון Part E.

## 9. קבצים ופקודות

**חדשים:** `src/ai/ext_checks.py`, `src/ai/extract.py`, `src/ai/skills/extraction.yaml`, `src/scoring/ext_items.py`, `tests/test_ai_extract.py`, `scripts/run_ai_k5b_extract.py`, `scripts/ai_k5b_compare.py`, `scripts/ai_k5b_csv_map.py`, `scripts/ai_report_k5b.py`, `docs/ai/ValueCompass_AI_Skills_Scoring_2026-10-22_13-52.{md,docx}` (לא מעוקב עד כה), דוח זה.
**שונו:** `src/ai/prompt.py`, `src/ai/assess.py`, `src/ai/checks.py`, `src/ai/facts.py`, `src/ai/sections.py`, `src/ai/skills/scoring.yaml`, `scripts/run_ai_k5a3.py`, `tests/test_ai.py`. **לא נגע:** golden, `.env`, Supabase. `scripts/ai_store/**` ב-gitignore.

**commits מוצעים:** (א) "code K5b: scoring template 3.1, A8 facts incl. discontinued ops, A11 consistency check" — `prompt.py`, `assess.py`, `checks.py`, `facts.py`, `scoring.yaml`, `run_ai_k5a3.py`, `tests/test_ai.py`, מסמך ה-Skills Scoring. (ב) "code K5b: AI extraction B1–B14, checks, approvals, CSV comparison" — `ext_checks.py`, `extract.py`, `extraction.yaml`, `ext_items.py`, `sections.py`, `tests/test_ai_extract.py`, סקריפטי k5b, דוח זה.

**להשלמה אחרי האיפוס (23.10 ~10:00):**
```bash
GEMINI_RPM=20 .venv/Scripts/python.exe -u scripts/run_ai_k5a3.py --model gemini-3.5-flash-lite --prompt-version 3.1 --rpm 20 --rpd 200 --no-repeat --no-cls --out-root scripts/ai_store/k5b/scoring
```
(ממשיך מהמקום שנעצר: ~72 קריאות). בנוסף — ב**תהליך אחד בלבד**.

---

## נספח א׳ — מיפוי CSV → בלוק (פלט `ai_k5b_csv_map.py`)


## bank_regulatory.csv - 268 item-year rows, 114 distinct item names, 12 companies

Covered by a block: 209 rows (91 item names); not covered by any block: 59 rows (14 item groups).

| block | rows | AI item_keys | CSV years |
|---|---|---|---|
| B1 | 102 | cet1_capital, cet1_ratio_advanced, cet1_ratio_standardized, cet1_required_advanced, cet1_required_standardized, lcr_q4_average, rwa_advanced, rwa_standardized, scb, total_capital_advanced, total_capital_standardized, uninsured_deposits | 2025 |
| B2 | 107 | loan_line, total_loans | 2025 |

Not covered (B14 candidates / outside the blocks):

- `funding:deposits:*`: 11 rows
- `funding:long_term:*`: 10 rows
- `nonaccrual_loans`: 8 rows
- `funding:short_term:*`: 8 rows
- `past_due_90_accruing:total`: 7 rows
- `funding:repo:*`: 4 rows
- `nco_YYYY`: 3 rows
- `avg_loans_YYYY`: 2 rows
- `past_due_90_accruing:credit card`: 1 rows
- `past_due_90_accruing:wholesale`: 1 rows
- `past_due_90_accruing:government-insured mortgage`: 1 rows
- `past_due_90_accruing:consumer`: 1 rows
- `acl_loans_YYYY`: 1 rows
- `preferred_stock_YYYY`: 1 rows

## insurance_regulatory.csv - 127 item-year rows, 20 distinct item names, 12 companies

Covered by a block: 117 rows (16 item names); not covered by any block: 10 rows (4 item groups).

| block | rows | AI item_keys | CSV years |
|---|---|---|---|
| B3 | 18 | prior_year_dev, reg_capital_ratio | 2023, 2024, 2025 |
| B4 | 99 | alm_disclosed, cat_loss_latest, inv_cash, inv_equity, inv_fixed_maturities, inv_ig_fixed, inv_ig_share, inv_illiquid_loans, inv_other, inv_real_estate, inv_short_term, inv_total | 2025 |

Not covered (B14 candidates / outside the blocks):

- `total_fixed_income`: 6 rows
- `debt_total`: 2 rows
- `structural_event:FY2024`: 1 rows
- `structural_event:FY2023`: 1 rows

## realestate_extracted.csv - 871 item-year rows, 210 distinct item names, 11 companies

Covered by a block: 791 rows (183 item names); not covered by any block: 80 rows (27 item groups).

| block | rows | AI item_keys | CSV years |
|---|---|---|---|
| B5 | 98 | acquisition_invested, acquisition_yield, development_invested, development_yield, largest_tenant_share, occupancy, same_property_noi_growth | 2021, 2021-2025, 2022, 2022-2024, 2023, 2024, 2025 |
| B6 | 137 | maint_capex, straight_line_rent_affo, ti_lc | 2021, 2021-2025, 2021Q1, 2021Q2, 2021Q3, 2021Q4, 2022, 2022Q1, 2022Q2, 2022Q3, 2022Q4, 2023, 2023Q1, 2023Q2, 2023Q3, 2023Q4, 2024, 2024Q1, 2024Q2, 2024Q3, 2024Q4, 2025, 2025Q1, 2025Q2, 2025Q3, 2025Q4 |
| B7 | 10 | fair_value_real_estate | 2025 |
| B8 | 30 | committed_undrawn_facilities, debt_maturity_year1, debt_maturity_year2 | 2025 |
| B9 | 14 | unencumbered_assets_share, unencumbered_noi_share | 2021, 2023, 2024, 2025 |
| B10 | 150 | bsa_carry, bsa_carryfin, bsa_excl, bsa_inre, bsa_noi, bsa_other, bsa_wc | 2025 |
| B11 | 33 | diluted_includes_op, inc_share_of_bplp, op_units_book_value, op_units_count, partnership_units_weighted, shares_basis_override | 2021, 2022, 2023, 2024, 2025 |
| B12 | 305 | core_ffo_ps_reported, re29_nonre_impairments, re29_re_sale_gains, re29a_nonre_inv, re29b_fx_net, recon_gi_net, recon_nci_jv, recon_net_income, recon_re_da, reported_affo, reported_core_ffo, reported_ebitdare, reported_ffo | 2020, 2021, 2021Q1, 2021Q2, 2021Q3, 2021Q4, 2022, 2022Q1, 2022Q2, 2022Q3, 2022Q4, 2023, 2023Q1, 2023Q2, 2023Q3, 2023Q4, 2024, 2024Q1, 2024Q2, 2024Q3, 2024Q4, 2025, 2025Q1, 2025Q2, 2025Q3, 2025Q4 |
| B13 | 14 | profile_property_value, profile_rental_revenue, profile_total_assets, profile_total_revenue | 2025 |

Not covered (B14 candidates / outside the blocks):

- `rental_revenue_extracted`: 6 rows
- `property_opex_extracted`: 6 rows
- `affo_addback_non_re_depr`: 5 rows
- `affo_addback_amortization`: 5 rows
- `affo_br__straight_line_revenue`: 4 rows
- `affo_br__straight_line_expense`: 4 rows
- `affo_br__deferred_tax`: 4 rows
- `affo_br__non_re_da`: 4 rows
- `affo_br__amort_financing`: 4 rows
- `affo_br__other_expense`: 4 rows
- `affo_br__other_operating`: 4 rows
- `affo_br__capital_improvement`: 4 rows
- `affo_br__corporate_capex`: 4 rows
- `affo_br__unconsolidated_nci`: 4 rows
- `debt_total_bs`: 2 rows
- `affo_br__discontinued`: 2 rows
- `affo_br__nci_dividends`: 2 rows
- `affo_br__retirement_loss`: 2 rows
- `affo_br__consolidated_to_attributable`: 2 rows
- `same_store_revenue_growth`: 1 rows
- `secured_debt`: 1 rows
- `bs_check__finance_lease_current`: 1 rows
- `bs_check__finance_lease_noncurrent`: 1 rows
- `bs_check__mortgage_current`: 1 rows
- `bs_check__senior_notes_current`: 1 rows
- `bs_check__mortgage_noncurrent`: 1 rows
- `bs_check__senior_notes_noncurrent`: 1 rows

# שלב קוד ק4א — תכנון נתב הפרופילים (ח-09) — 2026-10-20

**היקף:** תכנון והרצה "על יבש" בלבד. בלי שינוי קוד, בלי DB, בלי commit. מקור: `docs/scoring/ValueCompass_Rulebook_2026-10-20_12-31_EN.md`, חלק B (S3, S3a), E10, P1, ח-09 / C-27.

## 0. בדיקות מקדימות

| בדיקה | תוצאה |
|---|---|
| א. ה-push | `git fetch`; `git status -sb`: `## main...origin/main` (ללא פיגור/הקדמה); `git log origin/main -1`: **a872d46** "code K3: rulebook part H fixes ..." — הגיע |
| ב. golden מחדש מהקוד הנוכחי | `make_golden.py --as-of=2026-10-20 --stub-yfinance` לתיקייה זמנית (0 בקשות SEC), `compare_golden.py` מול `tests/golden/2026-10-20`: **55 קבצים, 0 הבדלים** |

## 1. מצב קיים — איפה הקוד משייך פרופיל היום, ומה שונה מחלק B

| # | מיקום | מה בודק | פער מחלק B |
|---|---|---|---|
| 1 | `src/scoring/bank.py:72` `bank_path` + `BANK_SIC = (6021, 6022, 6029, 6035, 6036)` | נתיב 1: SIC בנקאי **וגם** פיקדונות/התחייבויות ≥50% **וגם** הלוואות/נכסים ≥30% (עם S3a). נתיב 1b: `regulated_bhc and reports_cet1 and reports_lcr` | (א) `regulated_bhc=True` הוא **ערך ברירת מחדל קבוע** — המבחן "חברת אחזקה בנקאית מפוקחת" לא קיים בפועל; CET1/LCR נקבעים לפי נוכחות בקובץ החילוץ של FY2025 בלבד. (ב) מכנה הפיקדונות ב-`run_bank_test.py:~42` הוא `assets − equity`, לא תג `Liabilities` (כולל NCI ומניות בכורה). (ג) כישלון שני הנתיבים = `sector_not_supported_v1` לכולם; חלק B מבחין: בנקי השקעה/ברוקרים → **STANDARD**, אשראי → **UNSUPPORTED**. (ד) שנה אחרונה בלבד. (ה) `loans` חסר ב-XBRL נלקח מ-`loans_2025` (חילוץ) — תקין לפי RE11-מקביל, אך רק לשנה אחת (WFC) |
| 2 | `scripts/run_insurance_test.py:46` `profile_check` + `INSURANCE_SIC = (6311, 6321, 6324, 6331, 6351, 6361, 6399, 6411)`; סף `insurance.py:29 INSURANCE_TEST = 0.50` | SIC ברשימה **וגם** (תביעות + FPB + PAB + פרמיות שטרם הורווחו + חשבונות נפרדים + MRB) / התחייבויות ≥50% | נמצא בסקריפט, לא במנוע. אין תוצאת כישלון → STANDARD (רק `is_insurance` בוליאני). רכיב חסר מקטין את היחס בשקט (`missing_components` נרשם בלבד). שנה אחרונה. אין S3a |
| 3 | `scripts/run_managed_care.py:94` `profile_check` | אותו מבחן ביטוח על 6 ארגוני טיפול מנוהל | `"profile": "STANDARD"` מקודד קבוע (`:137`); התוצאה (`passes_insurance_test`) מידעית בלבד |
| 4 | `src/scoring/realestate.py:462` `_profile_check` (נקרא מ-`derive_re`, שורה 358) | נכסי השקעה/נכסים ≥50% **וגם** הכנסות שכירות/הכנסות ≥50%; RE11 (חילוץ כשהתג חסר), RE15 (אינטנגיבלס שכירות), S3a | תואם את שורה 3 בטבלה. אך: שנה אחרונה בלבד; אין שער ענף (SIC) — ה"ענף" בא מ-`ASSET_TYPE` לפי טיקר ב-`realestate_facts.py:123`; `assignment: STANDARD` הוא שדה מידע — **המנוע מנקד גם כשהמבחן נכשל**; `RENTAL_PROXY` (PSA) לפי טיקר |
| 5 | `src/scoring/profiles.py:9-12` | `SUPPORTED_PROFILES = (STANDARD, TECH_ASSET_LIGHT)`, `UNSUPPORTED_PROFILES = (BANK, INSURANCE, INCOME_REAL_ESTATE)` | השם מטעה: "לא נתמך" כאן = "לא מנוקד במודל הכללי". ב-Part B **UNSUPPORTED** הוא פרופיל נפרד (ללא מודל). הקוד אינו מכיר אותו |
| 6 | runners: `run_scoring_test.py:30 COMPANIES` (טיקר, פרופיל, הערה), `run_managed_care.py:27`, `run_bank_test.py:31 BANKS`, `run_insurance_test.py:27`, רשימת הנדל"ן ב-`run_realestate_pricing_v7.py` | **הפרופיל נקבע ברשימה** (MSFT/ORCL/AVGO/CRM/UBER/ADBE/INTU = TECH; KO/MCD/HD/NUE/DOW/INTC/KHC = STANDARD) | אין כלל 5a/5b (מו"פ ושולי רווח), אין SIC, אין חריגי UNSUPPORTED (REIT משכנתאות, BDC) |
| 7 | `src/scoring/profile_flags.py` | S3a: מרחק ≤5 נק' אחוז מהסף → `borderline_assignment` | כללי ושמיש — הנתב ישתמש בו כמו שהוא |
| 8 | **חסר כליל** | יציבות של שנתיים; חישוב מחדש לכל דוח שנתי (E10); תיקון ידני (P1); רשימת סקירה למנהל; שמירת היסטוריית ענף | — |

## 2. טקסונומיה והמיפוי SIC → ענף

### 2.1 ענפי ValueCompass (שמות משלנו)

| קוד ענף | שם תצוגה | שורה בחלק B | תוצאה |
|---|---|---|---|
| `BANKS` | Banks | 1a → 1b | BANK |
| `BROKER_DEALERS` | Investment banks and brokers | 1b | BANK אם מדווח CET1 + LCR, אחרת STANDARD |
| `CREDIT_LENDERS` | Consumer and commercial credit | 1b | BANK אם 1b, אחרת **UNSUPPORTED** |
| `INSURANCE_CARRIERS` | Insurance carriers | 2 | INSURANCE אם יחס ≥50%, אחרת STANDARD |
| `MANAGED_HEALTH` | Managed health insurance | 2 | כנ"ל (ארגוני טיפול מנוהל בארה"ב נכשלים → STANDARD) |
| `INSURANCE_SERVICES` | Insurance brokers and services | 6 (מפורש "insurance brokers") | STANDARD; **עם שומר**: יחס התחייבויות ≥50% → INSURANCE (שומר מפני סיווג SIC שגוי; מתיישב עם `INSURANCE_SIC` הנוכחי הכולל 6411) |
| `PROPERTY_REIT` | Income real estate / property REIT | 3 | INCOME_REAL_ESTATE אם שני המבחנים עוברים, אחרת STANDARD |
| `MORTGAGE_REIT` | Mortgage REITs | 4 | **UNSUPPORTED** (בלי מבחן) |
| `FUNDS_BDC` | BDCs and credit funds | 4 | **UNSUPPORTED** |
| `SOFTWARE` | Software | 5a | TECH_ASSET_LIGHT |
| `IT_SERVICES` | IT services | 5a | TECH_ASSET_LIGHT |
| `INTERNET_ADVERTISING` | Internet and advertising | 5a | TECH_ASSET_LIGHT |
| `HARDWARE`, `SEMICONDUCTORS`, `SEMI_EQUIPMENT`, `COMM_EQUIPMENT`, `ELECTRONIC_COMPONENTS` | חמשת הענפים של 5b | 5b | TECH אם מו"פ/הכנסות ≥10% וגם שולי גולמי ≥50% (חציוני 5 שנים), אחרת STANDARD |
| `ASSET_MANAGERS`, `EXCHANGES_DATA`, `PAYMENTS`, `HOMEBUILDERS_DEVELOPERS` | 6 (מפורשים בטבלה) | 6 | STANDARD |
| `OTHER` | אחר | 6 | STANDARD |

שכבת ה-classification (תצוגה והשוואת עמיתים) תרחיב את `OTHER` לענפים נוספים; הנתב צריך רק את הענפים שלמעלה.

### 2.2 טבלת SIC → ענף (טווחים; "?" = קוד רב-ענפי, ראו 2.3)

| טווח SIC | ענף | הערה |
|---|---|---|
| 6021, 6022, 6029, 6035, 6036 | `BANKS` | זהה ל-`BANK_SIC` |
| 6011, 6019, 6081, 6082 | `BANKS` | מועמדים; המבחן מכריע (נדירים כמגישי 10-K) |
| 6211 | `BROKER_DEALERS` | GS, MS, SCHW; (בדוגמה: GS = 6211) |
| 6221 | `BROKER_DEALERS` ? | חוזים סחורות; ברוקרים |
| 6111, 6141, 6153, 6159, 6162, 6163, 6172, 6199 ? | `CREDIT_LENDERS` | 6199 ? ראו 2.3 |
| 6311, 6321, 6331, 6351, 6361, 6399 | `INSURANCE_CARRIERS` | 6361 (ביטוח כותרת): ייתכן שהמבחן ייכשל — אין התחייבויות ארוכות |
| 6324 ? | `MANAGED_HEALTH` | UNH, ELV, CI, HUM, CNC, MOH |
| 6411 ? | `INSURANCE_SERVICES` | MMC, AON, AJG, BRO, WTW |
| 6798 ? | **מפוצל מספרית** | `PROPERTY_REIT` או `MORTGAGE_REIT` (סעיף 3.1) |
| 6500, 6510, 6512, 6513, 6519 | `PROPERTY_REIT` (מועמד) | מפעילי נדל"ן ומשכירים; המבחן מכריע |
| 6531 | `OTHER` | תיווך וניהול נדל"ן (CBRE) |
| 6552, 1520–1531 | `HOMEBUILDERS_DEVELOPERS` | 1531 = בונים (DHI, LEN) |
| 6282 | `ASSET_MANAGERS` | BLK, TROW |
| 6200 ? | `EXCHANGES_DATA` | CME, ICE, NDAQ; אך גם ברוקרים מסוימים |
| 6726 ?, 6770 ?, 6799 ? | `FUNDS_BDC` | 6726: BDC וקרנות סגורות; 6770: חברות "שיק ריק" (SPAC) — הספר לא מזכיר; הצעה: UNSUPPORTED |
| 7371, 7372 | `SOFTWARE` | MSFT, ORCL, CRM, ADBE, INTU |
| 7373, 7374 ?, 7379 | `IT_SERVICES` | 7374 גם עיבוד תשלומים/שכר |
| 7370 ?, 7310, 7311 ? | `INTERNET_ADVERTISING` | 7370: GOOGL, META; 7311: סוכנויות פרסום (OMC) — לא נכס-קל; מועמד לבדיקה |
| 3570–3579 | `HARDWARE` | 3576 ? (גם ציוד תקשורת, CSCO) |
| 3674 | `SEMICONDUCTORS` | AVGO, INTC |
| 3559 ?, 3827 ? | `SEMI_EQUIPMENT` | 3559 הוא גם מכונות תעשייה כלליות |
| 3661, 3663 ?, 3669 | `COMM_EQUIPMENT` | |
| 3670–3679 (בלי 3674) | `ELECTRONIC_COMPONENTS` | |
| 7389 ? | `PAYMENTS` או `OTHER` | V, MA, PYPL — אך גם UBER, DASH וכל "שירותים עסקיים" |
| כל השאר | `OTHER` | |

### 2.3 קודים שמתאימים ליותר מענף אחד

| SIC | ענפים אפשריים | פתרון מוצע |
|---|---|---|
| **6798** | נכס / משכנתאות / (גם יער, חוות, מלונות, מרכזי נתונים, מגדלים — כולם REIT) | פיצול מספרי מהדוח (3.1) |
| **6411** | ברוקרים (STANDARD) / סוכנויות/TPA / מבטחים שסווגו שגוי | שומר מספרי: התחייבויות ביטוח ≥50% → INSURANCE |
| **6324** | טיפול מנוהל / תוכניות רפואה-שיניים-ראייה / תוכניות Blue Cross | המבחן מכריע (כבר כך בספר) |
| **6199** | אשראי צרכני (AXP) / קריפטו (COIN) / שירותים פיננסיים אחרים | ענף מ-SIC הוא `CREDIT_LENDERS` רק אם המבחן מספרי (הלוואות+אשראי/נכסים); אחרת סיווג AI מרשימה סגורה |
| **6211** | בנק השקעות (GS, MS) / ברוקר (SCHW, IBKR) / בורסות | `BROKER_DEALERS`; 1b מכריע בין BANK ל-STANDARD |
| **6200** | בורסות (CME) / ברוקרים | `EXCHANGES_DATA` כברירת מחדל; חריגים ב-P1 |
| **7389** | תשלומים / UBER, DASH / שירותים עסקיים | דורש סיווג AI מרשימה סגורה (R16/R18) |
| **7374** | שירותי IT / עיבוד תשלומים / שכר | `IT_SERVICES` (מחייב 5a); הפרדה רק בסיווג תצוגה |
| **7370** | אינטרנט/פרסום (GOOGL, META) / שירותי מחשוב | `INTERNET_ADVERTISING` (שניהם 5a — אותה תוצאה) |
| **3576** | חומרה / ציוד תקשורת | שניהם 5b — אותה תוצאה |
| **3559** | ציוד למוליכים למחצה / מכונות כלליות | 5b רק עבור שיוך לציוד מוליכים (AMAT, LRCX); מכונות כלליות = `OTHER`. דורש רשימה סגורה או סיווג AI |
| **6726 / 6770 / 6799** | BDC / קרנות סגורות / SPAC / משקיעים | UNSUPPORTED בכולם; הבחנה לתצוגה בלבד |

**הערה מרכזית:** חברות אינטרנט רבות אינן ב-SIC של תוכנה (AMZN 5961, NFLX 7841, UBER 7389, ABNB 7011, BKNG 4700) — SIC לבדו אינו מספיק לשורה 5a. ה-fallback של הספר (שאלת AI מרשימה סגורה כשאין סיווג) הוא כלי הכרחי, לא רק גיבוי.

## 3. פערים — כללים דטרמיניסטיים מוצעים (לא מומשו)

### 3.1 REIT משכנתאות מול REIT נכסים בתוך SIC 6798

הסיווג נקבע **לפני** שורות הטבלה (שלב סיווג-ענף מספרי), לכן שורה 3 אינה מועמדת עבור REIT משכנתאות ושורה 4 תופסת:

`MORTGAGE_REIT` אם **שניהם**: (א) נכסי השקעה במקרקעין / סך הנכסים <50% (הכישלון של מבחן שורה 3), ו-(ב) אחד מ: הכנסות ריבית / סך הכנסות ≥50% (תגיות `InterestAndDividendIncomeOperating` / `InterestIncomeOperating` מול `Revenues` או סכום ריבית + שאר ההכנסות), **או** (הלוואות משכנתא + ניירות MBS/סוכנות) / סך נכסים ≥50% (`MortgageLoansOnRealEstate`, `AvailableForSaleSecuritiesDebtSecurities` / `MortgageBackedSecurities…`).
אחרת, בתוך 6798 שנכשל במבחן הנכסים (מלונות, יער, WELL וכד'): `PROPERTY_REIT` שנכשל → STANDARD. היברידי קרוב לסף → S3a + רשימת סקירה.
**מגבלת אימות:** אין REIT משכנתאות בקובץ 54 החברות, ולכן הכלל והתגיות **לא נבדקו על נתונים**. מומלץ להוסיף 3–4 חברות בדיקה (למשל NLY, AGNC, STWD, BXMT) בק4ב — דורש הורדת נתוני SEC חדשים (אישור מצדך).

### 3.2 איך REIT משכנתאות מגיע ל-UNSUPPORTED ולא ל-STANDARD

הגורם: **סדר הפעולות** (סיווג-ענף → שורה) ולא כישלון מבחן. בטבלת חלק B "Fails → STANDARD" שייך לשורה 3 (נכסים). REIT משכנתאות אינו נכנס לשורה 3; הוא ענף `MORTGAGE_REIT` שבשורה 4 (ללא מבחן, תוצאה UNSUPPORTED). אותו עיקרון ל-BDC (`FUNDS_BDC`) ול-`CREDIT_LENDERS` שנכשל ב-1b. זיהוי BDC: SIC 6726/6799, או תגיות `NetAssetValuePerShare` + `InvestmentOwnedAtFairValue` ≥50% מהנכסים.

### 3.3 נתונים חסרים לנתב

| נתון | מצב היום | מקור מוצע |
|---|---|---|
| קוד SIC | נקרא מ-`submissions` רק בספקי בנק/ביטוח (`raw["sic"]`); לא נשמר באף מקום; **אין עמודה** במיגרציות שלב 1 (ל-`companies` יש רק `profile`, `profile_reason`, `profile_since`; נבדקו קבצי ה-SQL, לא המסד החי) | `https://data.sec.gov/submissions/CIK….json` שדות `sic`, `sicDescription` (קיים במטמון לכל 54). הערה: הקובץ מחזיק את ה-SIC **הנוכחי** בלבד — אין היסטוריה |
| הוצאות מו"פ | **לא נקראות בשום ספק** (חיפוש ב-`src/`: 0 מופעים) | `ResearchAndDevelopmentExpense`; חלופה `ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost`; נבדק: כל הנתונים ל-INTC ו-AVGO נמצאו (5 שנים). חסר מפתח במילון (אין `FIN-` ל-R&D) — תוספת למילון בק5 |
| שולי גולמי | `GrossProfit` קיים בספק הכללי; גזירה (הכנסות−עלות) **אסורה** במוט (R9) | להחליט אם 5b מתיר גזירה מסומנת (סיווג ≠ ניקוד); מומלץ כן, עם דגל |
| סך התחייבויות | תג `Liabilities`; בבנקים הקוד מחשב `assets − equity` | `Liabilities`; חלופה `assets − equity` מסומנת |
| מעמד חברת אחזקה בנקאית מפוקחת, CET1, LCR **לכל שנה** | קובץ חילוץ FY2025 בלבד; `regulated_bhc=True` קבוע | פריטי חילוץ `cet1_ratio_*` ו-`lcr_q4_average` לכל שנה בחלון (המבנה `extraction_items` תומך); מעמד BHC: טקסט 10-K ("bank holding company", Regulation) כפריט חילוץ בוליאני |
| הכנסות ריבית / סך הכנסות, MBS, משכנתאות | לא נקראים | תגיות בסעיף 3.1 |
| רכיבי ביטוח חלופיים | ALL: תג התביעות חסר ב-FY2021–22 → יחס 30% (ראו 4) | שרשרת תגים חלופית + חילוץ; **כלל**: רכיב חסר אינו נכשל אלא "לא נקבע" |
| נכסי השקעה / הכנסות שכירות **לכל שנה** | XBRL חסר לפני FY2025 ב-AMT, EQIX, PSA; החילוץ (RE11) קיים ל-FY2025 בלבד | פריטי `profile_*` לכל שנה בחלון |
| BDC / מזהה קרן | אין | SIC + תגיות NAV |
| ענף לא-SIC (אינטרנט) | אין | שאלת AI מרשימה סגורה (R16/R18), נשמרת כתשובה מאושרת |
| ישראל / אחרים | לא בהיקף ק4א | סיווג TASE / ספק נתונים — כפי שבספר |

## 4. הרצה על יבש — 54 החברות

**שיטה:** בזיכרון, מהקלט שבקובצי ה-golden (`financials`, `inputs`, `reg`) ומה-cache של SEC (**0 בקשות**); SIC מ-`sub_<cik>.json`. מיפוי ענף לפי 2.2. הבדיקות הרלוונטיות לענף בלבד, **לכל אחת מ-5 השנים האחרונות** (R&D/שולי גולמי: חציון 5 שנים שמסתיים באותה שנה). מבחני נדל"ן דרך `_profile_check` של המנוע על קלט קטום לשנה. יציבות: מתחילים בתוצאת השנה הראשונה בחלון ועוברים רק אחרי **שתי שנים רצופות** שונות. הנחות: סטטוס 1b (CET1+LCR) של FY2025 נשמר לכל שנה (אין נתון היסטורי); ה-SIC הנוכחי לכל השנים. (קוד ההרצה: סקריפט בתיקיית העבודה, לא נכנס ל-repo — ניתן להוסיף לפי בקשה.)

**סימון ערכי שנים:** B=BANK I=INSURANCE R=INCOME_REAL_ESTATE S=STANDARD T=TECH_ASSET_LIGHT ?=לא נקבע (נתון חסר).

### 4.1 מקבצים

| קבוצה | חברות | ענף (SIC) | פרופיל לפי חלק B | פרופיל נוכחי | התאמה |
|---|---|---|---|---|---|
| תוכנה | MSFT, ORCL, CRM, ADBE, INTU | SOFTWARE (7372) | T בכל 5 השנים (5a, בלי מבחן) | TECH | ✓ |
| טיפול מנוהל | UNH, ELV, CI, HUM, CNC, MOH | MANAGED_HEALTH (6324) | S בכל השנים; יחס התחייבויות ביטוח: CI 7.8%, UNH 18.9%, ELV 24.2%, HUM 32.0%, CNC 36.2%, MOH 42.5% (FY2025) | STANDARD | ✓ |
| בנקים | BAC, C, FITB, FLG, JPM, KEY, MTB, PNC, TFC, USB, WFC | BANKS (6021/6022/6036) | B בכל השנים | BANK | ✓ |
| ביטוח | AFL, AIG, ALL, CB, CINF, HIG, MET, PGR, PRU, RNR, TRV, WRB | INSURANCE_CARRIERS (6311/6321/6331) | I (יחס FY2025: 70.5%–89.3%) | INSURANCE | ✓ (ALL: ראו 4.3) |
| נדל"ן | ARE, BXP, EQR, FRT, O, PLD, SPG (RRRRR); AMT, EQIX, PSA (????R) | REIT 6798 → PROPERTY_REIT | R | INCOME_REAL_ESTATE | ✓ (ראו 4.3) |
| מזון/תעשייה/קמעונאות | KO, MCD, HD, NUE, DOW, KHC | OTHER | S | STANDARD | ✓ |
| מוליכים למחצה | AVGO | SEMICONDUCTORS (3674) | T: מו"פ 17.2%, גולמי 66.6% | TECH | ✓ |
| מוליכים למחצה | INTC | SEMICONDUCTORS (3674) | T,T,T,S,S → **STANDARD** (מו"פ 27.8%, גולמי 40.0%) | STANDARD | ✓ (ראו 4.3) |
| בנק השקעות | GS | BROKER_DEALERS (6211) | B (רק דרך 1b: פיקדונות 29.8%, הלוואות 13.3%) | BANK | ✓ |
| תחבורה/פלטפורמה | **UBER** | OTHER (7389) | **S** | **TECH** | **✗ אי-התאמה** |

### 4.2 ערכי המבחנים והסימון S3a (שנת הדוח האחרונה, FY2025)

| חברה | מבחן | ערך | סף | מרחק | S3a |
|---|---|---|---|---|---|
| BAC | הלוואות/נכסים | 34.75% | 30% | +4.75 נק' | **בגבול** |
| JPM | הלוואות/נכסים | 31.84% | 30% | +1.84 נק' | **בגבול** |
| C | הלוואות/נכסים | 28.31% | 30% | −1.69 נק' | **בגבול**; נכשל בנתיב 1, עובר דרך 1b |
| WFC | פיקדונות/התחייבויות | 72.5% | 50% | +22.5 | הלוואות/נכסים נלקחות מחילוץ (XBRL חסר מ-FY2022) |
| AMT | נכסי השקעה/נכסים | 55.2% | 50% | +5.2 נק' | **ממש מחוץ** לטווח (5.0); תלוי בחילוץ ובאינטנגיבלס RE15 |
| EQIX | נכסי השקעה/נכסים | 58.8% (FY2025) | 50% | +8.8 | בגבול ב-FY2022 (54.9%) |
| MOH | יחס התחייבויות ביטוח | 42.5% | 50% | −7.5 | לא בגבול |
| INTC | גולמי (חציון 5ש') | 40.0% | 50% | −10 | לא בגבול (FY2023: 55.5%) |
| AVGO | גולמי (חציון 5ש') | 66.6% | 50% | +16.6 | לא בגבול (FY2021: 55.2%) |
| שאר הבנקים, המבטחים, ה-REITs | — | — | — | >5 נק' | לא בגבול |

### 4.3 אי-התאמות והסבר

| חברה | מה נראה | הסבר | מסקנה |
|---|---|---|---|
| **UBER** | נתב: STANDARD, נוכחי: TECH | SIC 7389 ("שירותים עסקיים") → `OTHER`; חלק B דורש ענף תוכנה/IT/אינטרנט־פרסום ב-5a. הרשימה ב-`run_scoring_test.py` שייכה אותה ל-TECH ידנית | **החלטה שלך**: סיווג ענף (שאלת AI מרשימה סגורה / תיקון ידני P1 עם נימוק) קובע; בלי זה — STANDARD |
| **AMT, EQIX, PSA** | שנים קודמות "?" | מבחן נכסי ההשקעה (AMT: PP&E בחילוץ בלבד) או ההכנסות מהשכירות (EQIX, PSA) חסר ב-XBRL לפני FY2025; החילוץ (RE11) קיים לשנה אחת | לא אי-התאמה בפועל. כלל מוצע: "לא נקבע" לא נחשב שנה שונה ולא מאפס את הרצף; נדרש חילוץ לכל שנה בחלון |
| **ALL** | S,S,I,I,I | יחס התחייבויות ביטוח 29.6%/30.4% ב-FY2021–22: תג `LiabilityForClaimsAndClaimsAdjustmentExpense` חסר באותן שנים (הרכיב הגדול נעלם מהסכום; בנוסף מנוע הביטוח מראה `claims_gross=None`) | נתון חסר ולא פרופיל שונה. ביציבות של שנתיים התוצאה נשארת INSURANCE, אך בלי כלל "רכיב חסר → לא נקבע" שנתיים שגויות ברצף היו מעבירות פרופיל |
| **INTC** | T,T,T,S,S | חציון שולי הגולמי ירד מ-58.6% (FY2021) ל-40.0% (FY2025) | התוצאה STANDARD תואמת להיום, **אך** לפי כלל השנתיים המעבר מתרחש רק בדוח FY2025; בדוח FY2024 היה עדיין TECH. זו הדגמה לחשיבות היציבות |
| **C** | נתיב 1b בלבד | הלוואות/נכסים 27–29.5% בכל השנים | תקין, תלוי בדיווח CET1+LCR **לכל** שנה (לא קיים היסטורית) |
| **GS** | נתיב 1b בלבד | SIC 6211, פיקדונות 29.8% | תקין לפי שורה 1b |

**סיכום:** 53 מתוך 54 החברות מקבלות את הפרופיל הנוכחי שלהן; 1 (UBER) דורשת החלטה; ל-3 (AMT, EQIX, PSA) חסר חילוץ היסטורי, ללא השפעה על התוצאה הנוכחית.

## 5. מבנה מוצע — `src/scoring/router.py`

**עיקרון:** פונקציה טהורה, ללא I/O, ללא רשימות חברות. כל התלות החיצונית — כנתון.

```
route(facts_by_year: Mapping[int, FactSet],     # k2: FactSet לכל שנה בחלון (כולל שורות חילוץ מאושרות)
      classification: Classification,            # sic, sic_description, industry (או None), source ('sic'|'ai'|'override'), approved
      previous: Sequence[YearResult],            # היסטוריה (company_profile_history)
      override: Override | None) -> RouterResult
```

| רכיב | תוכן |
|---|---|
| `classify(sic, numeric_facts) -> industry` | טבלת SIC→ענף (נתון, מקובץ/טבלת reference — לא `if` בקוד), פיצול מספרי ל-6798, שומר ל-6411; ללא SIC → `None` (דורש תשובת AI מאושרת) |
| `ROWS` | טבלה דקלרטיבית של שורות 1a…6: ענפי מועמד, שם המבחן, סף, מה קורה בכישלון — מבנה זהה לחלק B. הספים (0.5, 0.3, 0.10, 0.5) קבועים אחד במקום; S3a דרך `profile_flags.borderline_flag` |
| מבחנים | `bank_deposits_loans`, `bank_regulated_cet1_lcr`, `insurance_liabilities`, `property_real_estate` (כולל RE11/RE15), `mortgage_reit`, `tech_5b` — העברת הלוגיקה הקיימת (`bank_path`, `_profile_check`, `profile_check` של הביטוח) לכאן; המנועים יקראו לנתב ולא יחזיקו לוגיקה כפולה |
| `YearResult` | `fiscal_year`, `profile_raw` או `undetermined`, `tests{name: (value, threshold, basis)}`, `borderline`, `missing_inputs` |
| `RouterResult` | `profile` (אפקטיבי), `industry`, `reason` (רשימת נימוקים קריאים), `borderline` + בדיקות, `per_year`, `since`, `pending_change` (השנה האחרונה שונה, ממתינה לשנה שנייה), `override_applied`, `computed_profile` (תמיד מוצג גם בעקיפה), `missing_inputs` |
| יציבות | פונקציה נפרדת: מקבלת היסטוריה + תוצאה חדשה, מחזירה פרופיל אפקטיבי; "לא נקבע" אינו שנה שונה; שינוי ענף נרשם |
| תיקון ידני (P1) | `Override(profile|industry, reason, set_by, set_at, valid_from_fy)` — **נתון** שמוזן לנתב, לא רשימה בקוד; בלי נימוק — נדחה; התוצאה מציגה גם את החישוב וגם את העקיפה. אחסון: `company_profile_history` מכיל כבר `reason` ו-`override_by`; חסרים ענף ו-`valid_from` — החלטה בק5 |
| פלט למסד | שורה ל-`company_profile_history` לכל שנה; `companies.profile/profile_reason/profile_since` מהאפקטיבי |

**נקודות סכמה (לשאול לפני ק5, לא בוצע דבר):** (1) `companies.profile` ו-`company_profile_history.profile` מוגבלים ל-5 ערכים ו**אינם כוללים UNSUPPORTED**; (2) אין עמודות SIC/ענף; (3) עקיפה ידנית מצריכה עמודת ענף/תוקף.

## 6. קבועים לפי חברה מק1 (סעיף 1.4) — האם הנתב תלוי בהם

| קבוע | מיקום | הנתב תלוי? | תחליף |
|---|---|---|---|
| `LOAN_MAP` (שורות הלוואה לפי בנק) | `bank.py:26` | לא (קלט לניקוד האיכות) | לא קשור לנתב |
| `LINE_OF_BUSINESS` | `insurance.py:26` | לא (תת-סיווג ביטוח לניקוד) | אפשרי כסיווג ענף משני; לא חוסם את הנתב |
| `EXTRA_DOC_SUFFIX` (PGR) | `insurance_facts.py:101` | לא | — |
| `CIK_OVERRIDE` (EQR, AVB) | `realestate_facts.py:21` | **כן, עקיף**: הנתב צריך CIK כדי לקרוא SIC | עמודת `cik` ב-`companies` (נתון reference) |
| `RENTAL_PROXY` (PSA) | `realestate_facts.py:132` | **כן**: מבחן הכנסות שכירות של PSA | פריט החילוץ `profile_rental_revenue` לכל שנה (כבר בשימוש ל-FY2025) |
| `ASSET_TYPE` (טיקר → סוג נכס) | `realestate_facts.py:123` | חלקית: מזהה "REIT נכסים" (גם WELL) | הענף מ-SIC; סוג הנכס לניקוד = סיווג משני (AI מרשימה סגורה), לא תנאי בנתב |
| `NOI_METHOD`, `UTILIZATION` | `realestate_facts.py` | לא | — |
| `BANKS` (CET1 נדרש) | `run_bank_test.py:31` | לא (קלט רגולטורי לניקוד) | פריט חילוץ `cet1_required_*` (קיים) |
| `COMPANIES` (פרופיל לפי רשימה) | `run_scoring_test.py:30`, `run_managed_care.py:27,137`, `run_insurance_test.py:27`, רשימת הנדל"ן ב-v7 | **כן — זה בדיוק מה שהנתב מחליף** | הפרופיל מהנתב; הרשימות הופכות לרשימת הרצה (טיקרים בלבד) |
| `FLOAT_CURRENCY` | ראנרים | לא | — |
| `price_entity_issue` של EQR | `run_realestate_pricing_v7.py:66` | לא (C16) | — |
| `regulated_bhc=True` (ברירת מחדל) | `bank.py:72` | **כן** | פריט חילוץ בוליאני לכל שנה |
| `BANK_SIC`, `INSURANCE_SIC` | `bank.py`, `run_insurance_test.py:29` | **כן** (שתי רשימות SIC כפולות) | טבלת SIC→ענף אחת |

## 7. שאלות פתוחות להחלטתך (לפני ק4ב)

1. **UBER** (ואחרות כמוה): סיווג ענף — שאלת AI מרשימה סגורה כברירת מחדל לכל חברה שה-SIC אינו מכריע, או תיקון ידני? (המלצה: AI מרשימה סגורה + אישור מנהל, נשמר כנתון.)
2. **5b ושולי גולמי:** להתיר גזירת רווח גולמי (הכנסות − עלות) כשחסר `GrossProfit`, עם דגל? (המלצה: כן, בסיווג בלבד.)
3. **רכיב ביטוח חסר:** "לא נקבע" ולא כישלון? (המלצה: כן.)
4. **SPAC / 6770** ו-**ABS (6189)**: UNSUPPORTED?
5. **הוספת חברות בדיקה** ל-REIT משכנתאות ו-BDC (נתוני SEC חדשים): לאשר הורדה של ~4–6 חברות.
6. **סכמה (ק5):** ערך UNSUPPORTED, עמודות SIC/ענף ועקיפה.
7. **דגל S3a** ל-5b: ברירת המחדל 5 נק' אחוז על שני המבחנים — לאשר.
8. **היקף ק4ב:** לממש `router.py` + העברת `bank_path`/`_profile_check`/בדיקת הביטוח אליו + בדיקות יחידה לכל שורה + הרצה על 54 החברות מול הטבלה בסעיף 4 (צפוי: 53 התאמות + UBER לפי ההחלטה).

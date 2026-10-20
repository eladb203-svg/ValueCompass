# שלב קוד ק4ב — מימוש נתב הפרופילים (ח-09) — 2026-10-20

**היקף:** `src/scoring/router.py` ומה שמסביבו. בלי DB, בלי commit. מקור: `docs/scoring/ValueCompass_Rulebook_2026-10-20_13-27_EN.md` (חלק B, B.1, CL15) ו-`scripts/code_stage4a_2026-10-20.md` סעיף 5. הורדות נתונים שבוצעו (באישורך): `yfinance.industry` ל-58 טיקרים, ונתוני SEC (companyfacts + submissions) ל-NLY, AGNC, STWD, BXMT, ARCC, MAIN (18 בקשות). אין AI.

## 0. תקציר

| בדיקה | תוצאה |
|---|---|
| pytest מלא | **469 עברו** (408 קודם + 60 ב-`tests/test_router.py` + 1 ב-`test_etl_field_map.py`) |
| golden (`--as-of=2026-10-20 --stub-yfinance`, ענף ספק מקובץ קבוע, 0 בקשות SEC) מול `tests/golden/2026-10-20` | **0 הבדלים** בכל ציון, שווי, מחיר קנייה, דגל ופרופיל. ההבדל היחיד: מפתח חדש `profile_router` בכל 54 הקבצים (פלט הנתב). בלי המפתח: 0 הבדלים ב-54 קבצים |
| UBER | TECH_ASSET_LIGHT דרך מדרגה 2 (SIC 7389 רב-משמעי, yfinance "Software - Application" → Software) |
| נתב מול הפרופיל הנוכחי | 54 מתוך 54 תואמים |
| 6 חברות הבדיקה | NLY, AGNC, STWD, BXMT (REIT משכנתאות) ו-ARCC, MAIN (BDC): **כולן UNSUPPORTED** (STWD דרך מדרגה 2 — ראו 4) |
| repo | golden לא הוחלף (החדש בתיקיית העבודה). לא בוצע commit |

## 1. מה נבנה

| קובץ | תפקיד |
|---|---|
| `src/scoring/router.py` | הנתב: פונקציה טהורה (בלי I/O ובלי רשימות חברות). שורות 1a–6 כנתון (`ROWS`), ספים בקבוע אחד, מבחנים (`bank_path`, `insurance_liability_test`, `property_test`, `mortgage_reit_test`, `bdc_test`, `tech_5b_test`), סיווג בשלוש מדרגות (`classify`), יציבות (`stability`), תיקון ידני (`Override`), ממשק מדרגה 3 (`AIAnswer`), מתאם מ-FactSet (`router_data_from_factset`) |
| `src/scoring/router_data/sic_industry.csv`, `provider_industry.csv` | טבלאות B.1 כנתון: טווחי SIC → ענף (auto / multi / split_6798 / credit_6199, עם ברירת מחדל ורשימת ענפים מותרים) ומיפוי ענף-ספק → ענף (`map` / `tier3`) |
| `src/etl/router_inputs.py` + `field_map.FIELDS["router"]` | FactSet מסוג `router`: עובדות מספריות (הסדרות שהמנוע כבר בנה גוברות, השאר משרשראות תגים מה-cache) ושורות טקסט: `sic_code`/`sic_description` (FIN-188), `provider_industry` (FIN-189). חדשים במילון (ק6): `rd_expense` (FIN-187), `interest_income_operating` (FIN-190), `mortgage_loans_mbs` (FIN-191), `nav_per_share` + `investments_fair_value` (FIN-192) |
| `src/providers/industry_provider.py` | ענף ספק: קובץ קבוע (בדיקות/golden) → cache → yfinance |
| `scripts/router_runner.py`, `scripts/provider_industry_2026-10-20.csv` | `route_company` ל-runners; הקובץ הקבוע (58 טיקרים, yfinance 2026-10-20) |
| מנועים/ראנרים | `bank.bank_path` ו-`BANK_SIC` מגיעים מהנתב; `realestate._profile_check` קורא ל-`router.property_test`; בדיקת הביטוח ב-`run_insurance_test` ובדיקת ה-managed care משתמשות ב-`insurance_liabilities_ratio` של הנתב (`INSURANCE_SIC`/`INSURANCE_TEST` נגזרים ממנו); `run_scoring_test.COMPANIES` הוא עכשיו `(טיקר, הערה)` והפרופיל מהנתב; managed care – הפרופיל מהנתב; כל ה-runners כותבים `profile_router` |

פלט הנתב (`RouterResult`): פרופיל אפקטיבי, פרופיל מחושב (לפני עקיפה), ענף + מדרגה + סטטוס (`decided` / `classification_pending`), נימוקים, borderline + בדיקות, תוצאה לכל שנה בחלון (שורה, פרופיל או `None`, ערכי המבחנים, הערות), `since`, `pending_change`, עקיפה שהופעלה, דגלים.

## 2. סיווג — מדרגות 1–2, ממשק ל-3

- **מדרגה 1 (SIC):** SIC שממופה לענף אחד מכריע. נבדק גם ה-cross-check מול הספק (הבדל נרשם בנימוק, SIC מכריע).
- **מדרגה 2 (ענף ספק):** ל-SIC רב-משמעי (`multi`) — מכריע ענף הספק אם הוא ברשימת המותרים של אותו SIC, אחרת ברירת המחדל של הקוד (6200 → בורסות; השאר → Other). ל-SIC ש-ממופה ל-Other — מכריע ענף הספק רק אם הוא ענף מועמד.
- **מדרגה 3 (AI):** רק ממשק: `AIAnswer(industry, quote, approved)`. מדרגה 3 פועלת כשמדרגות 1–2 לא מכריעות: תשובה המתאימה לענף הספק, או מאושרת ע"י מנהל, מכריעה; אי-התאמה בלי אישור → `classification_pending`. בלי תשובה: `classification_pending` ← STANDARD + דגל. המימוש (שאלת AI) בק5.
- **מספרי:** SIC 6798 (REIT משכנתאות או נכסים) ו-6199 (אשראי אם הלוואות/נכסים ≥50%), וזיהוי BDC (SIC 6726/6799 או NAV למניה + השקעות בשווי הוגן ≥50% מהנכסים) — לפני כל מדרגה.
- **שני כללים שהוספתי (לבדיקתך):** (א) מבחן REIT משכנתאות נכשל רק כששני המדדים (שיעור ריבית ושיעור נכסי משכנתא) ניתנים לחישוב ושניהם מתחת ל-50%; אם אחד חסר והשני מתחת — "לא נקבע" ואז ענף הספק מכריע (אחרת STWD, ללא תג ריבית, היה מסווג STANDARD). (ב) שורת נכסי ההשקעה החסרה במאזן = 0 במבחן זה (C5).

### yfinance `industry` ל-AMZN, ABNB, BKNG (ו-UBER)

| חברה | SIC (מהידע שלי, לא ממטמון SEC) | yfinance industry | ענף | מדרגה / סטטוס |
|---|---|---|---|---|
| UBER | 7389 (מהמטמון) | Software - Application | Software | מדרגה 2, מוכרע ⇒ TECH |
| AMZN | 5961 | Internet Retail | Other | מוכרע (קמעונאות מקוונת עם מלאי — מחוץ להגדרת הפלטפורמה) ⇒ STANDARD |
| ABNB | 7011 | Travel Services | Other | `classification_pending` ⇒ STANDARD עד שאלת AI (שוק מקוון?) |
| BKNG | 4700 | Travel Services | Other | `classification_pending` ⇒ STANDARD עד שאלת AI |

(ה-SIC של AMZN/ABNB/BKNG הוזנו ידנית לבדיקת המיפוי; לא הורדו נתוני SEC עבורן.)

מיפוי ענף הספק: ב-"Travel Services" ו-"Entertainment" הוגדר `tier3` (ספק רב-משמעי). "Credit Services" ממופה ל-Payments (V, MA; AXP נקבע דרך ה-SIC 6199 המספרי).

## 3. טבלת החברות (54 + 6)

עמודת "שנים" = תוצאת הנתב לכל אחת מ-5 שנות החלון (B=BANK, I=INSURANCE, R=INCOME_REAL_ESTATE, S=STANDARD, T=TECH_ASSET_LIGHT, U=UNSUPPORTED, ?=לא נקבע). "נוכחי" = הפרופיל שלפיו החברה מנוקדת היום (golden).

| חברה | ענף | מדרגה | פרופיל (נתב) | נוכחי | borderline (S3a) | שנים | דגל |
|---|---|---|---|---|---|---|---|
| ADBE | Software | sic | TECH_ASSET_LIGHT | TECH_ASSET_LIGHT | — | `TTTTT` |  |
| AVGO | Semiconductors | sic | TECH_ASSET_LIGHT | TECH_ASSET_LIGHT | — | `TTTTT` |  |
| CRM | Software | sic | TECH_ASSET_LIGHT | TECH_ASSET_LIGHT | — | `TTTTT` |  |
| DOW | Other | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| HD | Other | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| INTC | Semiconductors | sic | STANDARD | STANDARD | — | `TTTSS` |  |
| INTU | Software | sic | TECH_ASSET_LIGHT | TECH_ASSET_LIGHT | — | `TTTTT` |  |
| KHC | Other | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| KO | Other | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| MCD | Other | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| MSFT | Software | sic | TECH_ASSET_LIGHT | TECH_ASSET_LIGHT | — | `TTTTT` |  |
| NUE | Other | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| ORCL | Software | sic | TECH_ASSET_LIGHT | TECH_ASSET_LIGHT | — | `TTTTT` |  |
| UBER | Software | provider | TECH_ASSET_LIGHT | TECH_ASSET_LIGHT | — | `TTTTT` |  |
| CI | Managed health insurance | sic | STANDARD | STANDARD | — | `?????` | profile_undetermined_standard_default |
| CNC | Managed health insurance | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| ELV | Managed health insurance | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| HUM | Managed health insurance | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| MOH | Managed health insurance | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| UNH | Managed health insurance | sic | STANDARD | STANDARD | — | `SSSSS` |  |
| BAC | Banks | sic | BANK | BANK | כן (loans_to_assets) | `BBBBB` |  |
| C | Banks | sic | BANK | BANK | כן (loans_to_assets) | `BBBBB` |  |
| FITB | Banks | sic | BANK | BANK | — | `BBBBB` |  |
| FLG | Banks | sic | BANK | BANK | — | `BBBBB` |  |
| GS | Investment banks and brokers | sic | BANK | BANK | — | `BBBBB` |  |
| JPM | Banks | sic | BANK | BANK | כן (loans_to_assets) | `BBBBB` |  |
| KEY | Banks | sic | BANK | BANK | — | `BBBBB` |  |
| MTB | Banks | sic | BANK | BANK | — | `BBBBB` |  |
| PNC | Banks | sic | BANK | BANK | — | `BBBBB` |  |
| TFC | Banks | sic | BANK | BANK | — | `BBBBB` |  |
| USB | Banks | sic | BANK | BANK | — | `BBBBB` |  |
| WFC | Banks | sic | BANK | BANK | — | `B???B` |  |
| AFL | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| AIG | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| ALL | Insurance carriers | sic | INSURANCE | INSURANCE | — | `??III` |  |
| CB | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| CINF | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| HIG | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| MET | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| PGR | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| PRU | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| RNR | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| TRV | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| WRB | Insurance carriers | sic | INSURANCE | INSURANCE | — | `IIIII` |  |
| AMT | Property REITs and income real estate | provider | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `????R` |  |
| ARE | Property REITs and income real estate | numeric | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `RRRRR` |  |
| BXP | Property REITs and income real estate | numeric | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `RRRRR` |  |
| EQIX | Property REITs and income real estate | numeric | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `????R` |  |
| EQR | Property REITs and income real estate | numeric | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `RRRRR` |  |
| FRT | Property REITs and income real estate | numeric | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `RRRRR` |  |
| O | Property REITs and income real estate | numeric | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `RRRRR` |  |
| PLD | Property REITs and income real estate | numeric | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `RRRRR` |  |
| PSA | Property REITs and income real estate | numeric | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `????R` |  |
| SPG | Property REITs and income real estate | numeric | INCOME_REAL_ESTATE | INCOME_REAL_ESTATE | — | `RRRRR` |  |
| NLY | Mortgage REITs | numeric | UNSUPPORTED | UNSUPPORTED | — | `UUUUU` |  |
| AGNC | Mortgage REITs | numeric | UNSUPPORTED | UNSUPPORTED | — | `UUUUU` |  |
| STWD | Mortgage REITs | provider | UNSUPPORTED | UNSUPPORTED | — | `UUUUU` |  |
| BXMT | Mortgage REITs | numeric | UNSUPPORTED | UNSUPPORTED | — | `UUUUU` |  |
| ARCC | BDCs and credit funds | numeric | UNSUPPORTED | UNSUPPORTED | — | `UUUUU` |  |
| MAIN | BDCs and credit funds | numeric | UNSUPPORTED | UNSUPPORTED | — | `UUUUU` |  |

## 4. הערות על התוצאות

1. **בנקים:** BAC, JPM, C בגבול S3a על הלוואות/נכסים (34.8%, 31.8%, 28.3%). C עובר רק דרך 1b. GS (ברוקר/בנק השקעות) – 1b בלבד. WFC: `loans` חסר ב-XBRL בשנים 2022–24 ⇒ "?" (נלקחות מהחילוץ רק בשנה האחרונה); פרופיל אפקטיבי BANK.
2. **INTC:** T,T,T,S,S — עובר ל-STANDARD רק לאחר שתי שנים רצופות (FY2024–25). זהה לפרופיל הנוכחי; בדוח FY2024 היה עדיין TECH.
3. **ALL:** שתי שנים ראשונות "לא נקבע" (תג התביעות חסר) — מסומן כ"לא נקבע" ולא ככישלון (CL15); בניגוד לחישוב ק4א (S,S).
4. **CI:** כל השנים "לא נקבע": התחייבות התביעות של CI מדווחת בתג-הרחבה (לא us-gaap), ולכן ללא חילוץ מבחן הביטוח לא ניתן לחישוב. התוצאה STANDARD ברירת מחדל עם דגל `profile_undetermined_standard_default` (המנוע הישן חישב 7.8% בשקט עם רכיב חסר). דורש פריט חילוץ בק5.
5. **AMT, EQIX, PSA:** "?" לפני FY2025 — נכסי השקעה/הכנסות שכירות מחושבים רק מחילוץ (RE11) לשנה אחת; פרופיל אפקטיבי R. AMT: מבחן הנכסים 55.2% (5.2 נק' מהסף, מחוץ ל-S3a בקושי). ב-AMT הסיווג (6798) נקבע דרך ענף הספק כי מבחן המשכנתאות "לא נקבע".
6. **STWD:** תג הריבית (FIN-190) לא נמצא בטקסונומיית us-gaap שלו; נכסי משכנתא לפי תגים = 33.5% (<50%) ⇒ המבחן "לא נקבע" ⇒ ענף הספק "REIT - Mortgage" מכריע ⇒ UNSUPPORTED. בלי כלל (א) לעיל – STANDARD.
7. **NLY, AGNC:** אין תג `Revenues` בכלל; הכרעה לפי נכסי MBS (66%, 70% מהנכסים) דרך תגים (`MortgageBackedSecuritiesAvailableForSaleFairValueDisclosure`, `FinancialInstrumentsOwnedMortgagesMortgageBackedAndAssetBackedSecuritiesAtFairValue`). BXMT – הלוואות משכנתא 90% מהנכסים.
8. **ARCC, MAIN:** אין SIC ב-submissions; זוהו כ-BDC לפי NAV למניה + השקעות בשווי הוגן ≥50% מהנכסים.

## 5. תיקון ידני ויציבות

- `Override(reason, set_by, set_at, profile|industry, valid_from_fy)` — נתון שמוזן לנתב; בלי נימוק נדחה (`ValueError`). עקיפת פרופיל: `profile` = העקיפה, `computed_profile` נשאר גלוי; עקיפת ענף מחליפה את הסיווג (מדרגה `override`).
- `stability(results, previous_profile)`: שינוי רק אחרי שתי שנים רצופות עם אותה תוצאה שונה; שנה "לא נקבע" אינה שונה ואינה שוברת רצף; `previous_profile` (היסטוריה מאוחסנת) מזין את הרצף; `pending_change` מראה תוצאה שממתינה לשנה שנייה.
- אחסון בבסיס (ק5/ק6): `company_profile_history` מכיל `reason`, `override_by`, `borderline`, אך **הערך UNSUPPORTED חסר** ב-CHECK של `companies.profile` ושל הטבלה, ואין עמודות SIC/ענף/תוקף עקיפה. לא נגעתי בסכמה.

## 6. מגבלות והחלטות פתוחות

1. הנתב מניח ענף אחד לכל החלון (מחושב על השנה האחרונה); שינויי ענף מתועדים בנימוקים בלבד.
2. מעמד CET1/LCR נלקח מהגילוי האחרון ומועבר לכל שנות החלון (אין נתון היסטורי); מעמד "חברת אחזקה בנקאית מפוקחת" מוסק מכך (לא קיים פריט נפרד).
3. ה-SIC הוא הנוכחי (אין היסטוריית SIC ב-submissions).
4. גזירת רווח גולמי ב-5b מותרת ומסומנת (C4, לפי הספר) — לא נוצלה באף אחת מ-54 החברות.
5. מיפוי ענף-ספק: ~50 שורות; ענפי yfinance שלא במיפוי = Other (מוכרע). הרחבה לחברות חדשות = הוספת שורות בקובץ הנתונים.
6. **golden:** להחליף את `tests/golden/2026-10-20` בחדש (מוסיף `profile_router` בלבד)? אם כן — אבצע בק4ג/commit לפי הוראתך.
7. מילון DB (FIN-187…192) וסכמה: ק6.

## 7. כיצד חוזרים על הבדיקות

```
.venv/Scripts/python -m pytest -q -p no:cacheprovider
.venv/Scripts/python tests/golden/2026-10-20/make_golden.py --as-of=2026-10-20 --stub-yfinance <raw_dir> <golden_dir>
```
(`--stub-yfinance` קובע גם את ענף הספק מ-`scripts/provider_industry_2026-10-20.csv`). ההשוואה: כל הפרשים מחוץ למפתח `profile_router` = 0.

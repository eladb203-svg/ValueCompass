# דוח שלב ק6ב — RESOLVE, AUDIT, SRC, DQ, WRITE, יומן עבודות, פקודות load / audit / status (2026-10-25)

כל הכתיבה על **valuecompass-test** בלבד (`VC_DB_TARGET=test`; הפקודות ובדיקות הקבלה מסרבות ל-prod). 0 קריאות ל-Gemini. golden לא שונה. מפתחות לא הודפסו.

## 0. תיקון מק6א — עדיפות K5b
התאמת ק5ב קודמת ל-YES הישן: שורה עם התאמת ק5ב מקבלת `k5b_confirmed`, `legacy_verified` נשאר לשורות בלי התאמה.
- `src/etl/k5b_match.py` מחשב את 89 השורות מ-`compare.json` של ק5ב (JPM 8, USB 11, PGR 3, CB 1, O 20, PLD 18, AMT 28); `approval_for` מעדיף `k5b_match`; בדיקות יחידה.
- על test עודכנה רק העמודה `approval_source` ב-89 שורות (`scripts/k6b_apply_k5b_precedence.py`).
- **ספירה לפי מקור (extraction_items בבדיקה):** `k5b_confirmed` 89 · `legacy_verified` 1,158 · `human_review` 1 (שורת בדיקה ישנה) · `pending` 7 (6 שלא אומתו + שורת בדיקה ישנה). ‏0 שינוי ב-golden.

## 1. RESOLVE (`src/pipeline/resolve.py`)
טיקר → CIK מ-`company_tickers.json` → submissions: שם, שמות קודמים, SIC, סוף שנה, בורסות, כל רשימת ההגשות (כולל הקבצים הישנים). חברה אחת = CIK אחד; `company_listings` נכתב לפי טיקר+בורסה (שינוי טיקר מעדכן רישום, לא חברה); מצב `resolved` לא חוזר אחורה. **לא נתמכות** (נרשמות `unsupported` + סיבה, כלום לא רץ): מגישות 20-F/40-F (כשההגשה האחרונה כזו), SPAC (SIC 6770), ABS (SIC 6189), בלי דוח שנתי. **E2:** טיקר שאינו ברשימת הטיקרים של הישות המגישה → אזהרה, הרישום לא פעיל, "אי אפשר לתמחר".

## 2. AUDIT (`audit.py`)
דוחות 10-K/10-K/A/10-KT מול `filing_periods`, חלון 10 שנים (t−9…t): `present`, `missing`, `superseded`, `not_available`. תיקון (10-K/A) מחליף רק כשהנתונים שלו ב-companyfacts (רוב ה-10-K/A הם חלק III בלבד). accession-placeholder מק6א נחשב `superseded` עד שנטען accession אמיתי. `audit <ticker>` מדפיס ולא כותב.

## 3. SRC + COLLECT (`collect.py`, `sec_source.py`)
- **לקוח SEC:** User-Agent מ-`.env`; **מגבלה בקוד:** חלון הזזה של שנייה (לא יותר מ-10 בקשות) + מרווח מינימלי 0.12ש'; כל קובץ שהורד נשמר ב-`scripts/cache/sec_live` (נפרד מ-`scripts/cache/sec` של ה-golden; קבצי הגשות ישנים נקראים מהמטמון הישן בקריאה בלבד). מסמכים משתנים (רשימת טיקרים, submissions, companyfacts) מורדים מחדש אחרי 20 שעות. מסמכי הגשות עוברים באותו לקוח (הוק קטן ב-`_get_raw`).
- **היררכיה:** (1) companyfacts ו-(2) תגיות inline-XBRL — בתוך ה-providers הקיימים; (3) סכום 4 רבעונים → `quarterly_sum` (מקודד ונבדק); (5) חילוץ מאושר → `extraction` (רק approved, רק כשחסר, רק מפתח שקיים במילון; ה-engines לא קוראים אותם כקלט — הם קוראים את שורות החילוץ); (6) חסר — אין שורה, אף פעם לא 0. **(4) FR Y-9C (E8) — לא נבנה:** אין בריפוזיטורי מקור נתונים כזה; נרשם ב-log כ"דולג".
- `source_kind` ו-`tag_id` בכל שורה. ‏`accession` **אמיתי** ב-`filing_periods` (במקום ה-placeholder).
- **ניתוב:** הנתב רץ פעמיים. מעבר ראשון בלי סדרות קובע מנוע; אחר כך נבדקים גם מנועים שה-SIC או תגיות ה-XBRL רומזים עליהם, והנתב רץ עם הסדרות והחילוץ של המנוע — מנוע מתמחה שהנתב מאשר גובר על general. (נמצא תוך כדי עבודה: AMT יצא קודם STANDARD/general כי SIC 6798 לא מספיק והנתב צריך את סדרות הנדל"ן; תוקן, ו-AMT נטען מחדש.) **מגבלה:** לחברה חדשה בלי שורות חילוץ מאושרות הנתב לא יזהה נדל"ן/בנק שדורשים חילוץ — יתוקן כשתור החילוץ יפעל (ק6ג).
- **מחיר:** `market_snapshot` שורה אחת למניה, מתעדכנת במקום, בדיקת טריות (E1, מעל 5 ימים = stale).

## 4. DQ (`dq.py`)
סקאלת מניות (C14/E3: חזקה של 10 → תיקון+דגל `share_scale_rescaled`; חריגה אחרת פי 100+ → ערך מעוכב=חסר) · מטבע (לא USD → ערכים כספיים מעוכבים) · זהות מאזנית בטווח 1% (דגל `balance_identity` על שנה) · סימנים (הכנסות/נכסים שליליים → `negative_value`) · הצגה מחדש (ערך שונה מהשמור → `restated`, הדגל נשמר כשהערך לא משתנה כדי שטעינה שנייה לא תכתוב) · כיסוי שנים (לפי המנוע) · טריות מחיר. כל תוצאה ב-flags של השורה וב-`data_update_log`. **E11** — `reconciliation_inputs` מכין את הנתונים בלבד, לא רץ.

## 5. WRITE + נתב + log + סוגי עבודות (`runner.py`)
`financial_facts` (upsert אידמפוטנטי; `extraction_id` נתמך), `filing_periods` (accession, form, filed_at, סוף שנה, מטבע, גרסת חישוב `k6b-sec-1`), `data_update_log` (שורה לכל עבודה: ספירות, שנים, חסרים, אזהרות; `source_details` מערך עם מקורות, DQ, בקשות, שניות, AI נדרש, restated), הפרופיל ל-`companies.profile` ול-`company_profile_history` (E10), `processing_state` `resolved`→`data_loaded` (טעינה חוזרת בלי שינוי לא נוגעת במצב). עבודות: `initial_import`, `backfill` (רק חסרות), `new_report` (שנה חדשה+נתב+"AI נדרש" ב-log), `amendment` (שנים שהוחלפו → כתיבה+`restated`), `repair` (בלי הורדה). בלי תזמון.

## 6. פקודות
`.venv/Scripts/python scripts/vc.py load|audit|status <ticker> [--job ...] [--dry-run]`. ‏`--dry-run` לא כותב כלום (גם לא תגית חדשה). דוגמת `status`: מצב, שנים, מקורות, דגלים, accession לכל שנה, העבודה האחרונה, מחיר.

## 7. טעינת סט הפיתוח על test — טבלה
| חברה | פרופיל / מנוע | שנים | עובדות | מקורות | דגלים | זמן טעינה | בקשות SEC (טעינה ראשונה / חוזרת) |
|---|---|---|---|---|---|---|---|
| KO | STANDARD / general | 10 | 339 | xbrl 313, derived 26 | — | 33–37ש' | 0* / 0 |
| MSFT | TECH_ASSET_LIGHT / general | 10 | 369 | xbrl 322, derived 47 | — | 38–43ש' | 4 / 0 |
| JPM | BANK / bank | 10 | 305 | xbrl 271, derived 21, extraction 13 | from_extraction 13 | 39–121ש' | 73 / 0 |
| CB | INSURANCE / insurance | 10 | 431 | xbrl 378, ixbrl 24, derived 21, extraction 8 | balance_identity 9 (שנים 2023–2025: 1.8–2.2%), from_extraction 8 | 43–49ש' | 3 / 0 |
| O | INCOME_REAL_ESTATE / realestate | 10 | 422 | xbrl 314, derived 50, extraction 58 | from_extraction 58 | 40–46ש' | 3 / 0 |
| AMT | INCOME_REAL_ESTATE / realestate | 10 | 412 | xbrl 314, derived 51, extraction 47 | from_extraction 47 | 43–51ש' | 3 / 0 |
| INTC | STANDARD / general | 10 | 358 | xbrl 324, derived 34 | — | 43–49ש' | 4 / 0 |
\* ‏KO: ההורדה נעשתה בפקודת `audit` שרצה קודם. רוב הזמן (כ-35 שניות) הוא עיבוד מקומי של קבצי companyfacts גדולים ו-yfinance, לא SEC. כל הפרופילים זהים לפרופיל ב-golden.

## 8. השוואה למטמון
`scripts/k6b_compare_cache.py`: אותם providers על המטמון הקפוא (`scripts/cache/sec`) ועל SEC עכשיו, ועל מה שנשמר ב-DB.
- **SEC מול מטמון: 0 הבדלים בכל 7 החברות** (339 / 369 / 292 / 423 / 364 / 365 / 358 עובדות). **ההסבר:** המטמון נוצר ב-2026-10-20, חמישה ימים לפני הטעינה, ולא הוגש דוח שנתי חדש או 10-K/A בין התאריכים — לכן אין הבדלים אמיתיים. ההשוואה הזו לא בודקת הצגה מחדש אמיתית; זה נבדק בסימולציה (סעיף 9).
- **SEC מול DB:** 0 הבדלים, חוץ מ-CB: 9 הבדלים — דגל `balance_identity` שנוסף ב-DQ לשורות (הערך לא השתנה). עובדות שנגזרו מחילוץ מאושר (`extraction`) לא נכללות בהשוואה (לא קלט למנועים).
- golden לא עודכן.

## 9. בדיקות קבלה (על test, חברה בדיקה PEP, `scripts/k6b_acceptance.py`) — 15/15 עברו
| בדיקה | תוצאה |
|---|---|
| dry-run על טיקר לא מוכר | לא נכתב כלום (332 עובדות היו נכתבות) |
| חברה חדשה (PEP) | נוצרה, 332 עובדות, 10 תקופות עם accession אמיתי, רישום, פרופיל, מחיר; `data_loaded` |
| אידמפוטנטיות | טעינה שנייה: 0 שורות השתנו (עובדות+תקופות), 0 בקשות SEC |
| הצגה מחדש מדומה | 10-K/A מדומה (שכבת-על על מסמכי SEC האמיתיים) משנה הכנסות FY2025 ב-1%: audit מזהה `superseded` לשנה אחת; ערך אחד נכתב מחדש עם `restated`; accession ו-form (`10-K/A`) עודכנו; log: `amendment` + הפריט |
| דוח חדש מדומה | 10-K מדומה ל-FY2026: נוספה רק השנה החדשה (33 עובדות), הנתב רץ (היסטוריית פרופיל 2025+2026), "AI נדרש" נרשם ב-log |
| לא נתמך | TSM → `unsupported`, "files 20-F (foreign private issuer, IFRS)", 0 עובדות |
| ניקוי | אחרי כל סימולציה נמחקו נתוני PEP וחזרו מהנתונים האמיתיים (332 עובדות, בלי דגל `restated`); שורות ה-log נשארו כראיה |
בדיקות יחידה: ‏`tests/test_pipeline_core.py` (לקוח SEC, מגבלת קצב, מטמון, RESOLVE, AUDIT, היררכיה, DQ, מחיר), `tests/test_pipeline_runner.py` (קצה-לקצה על DB מדומה: טעינה, אידמפוטנטיות, dry-run, תיקון, דוח חדש, backfill, לא נתמך, טיקר לא קיים, status, בחירת מנוע), `tests/test_k5b_match.py`. אף אחת לא פונה לרשת. **סה"כ 624 בדיקות עוברות.**

## 10. מגבלות ופתוחים
1. FR Y-9C (E8) לא נבנה (אין מקור נתונים).
2. נתב לחברה חדשה שדורשת חילוץ (בנק/נדל"ן) — ראו סעיף 3.
3. ‏K6a `--via-db` כותב עובדות מהמטמון בלי דגלי DQ; הרצה שלו על test אחרי ק6ב תמחק את הדגלים עד הטעינה הבאה (לא הורץ).
4. מצב `unsupported` של TSM נוצר עם exchange/country/currency ברירת מחדל (US/USD) כי הם NOT NULL; לא משפיע על הלוגיקה.
5. תוכנית AUDIT לא מפרידה 10-K405 מוקדם (לפני 2009 ממילא `not_available`).

## 11. רשימה מוכנה לטעינת סט הפיתוח לייצור (לאישור נפרד — לא בוצע)
1. לוודא ש-fingerprint של הייצור = test (מיגרציות 1–11 + `extraction_items_approval_source_legacy_verified`, אחרי ק6א).
2. `.env`: מפתח ייצור + `VC_DB_TARGET=prod`; קוד הנתב/הפקודות לא דורש שינוי. **הדגל `--db-approve-all` נדחה ב-prod.**
3. טעינת שורות החילוץ (CSV) לייצור לפי כלל האישור (k5b_confirmed / legacy_verified / pending) — לפני טעינת הנדל"ן/בנקים/ביטוח, כי הנתב והעובדות הנגזרות צריכות אותן: `make_golden --via-db` אינו הכלי לכך; נדרש סקריפט טעינת חילוץ קצר (ק6ג או שלב נפרד).
4. לפי הסדר: KO, MSFT, INTC (general) → JPM → CB → O, AMT: `scripts/vc.py load <T>` (קודם `--dry-run`).
5. אימות אחרי כל חברה: `status <T>` (state=data_loaded, 10 שנים, accession אמיתי), טעינה שנייה = 0 שורות, `select count(*)` ב-`financial_facts`/`filing_periods` מול test (339/369/305/431/422/412/358 עובדות), 0 שורות ב-`extraction_items` שאינן approved בגלל הטעינה, שורת `data_update_log` לכל עבודה.
6. אם משהו לא תואם: עצירה; לא נמחק דבר בייצור בלי אישור.

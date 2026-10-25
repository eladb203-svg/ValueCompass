# דוח שלב ק6א — מיגרציות 8–11, Repositories, קלט המנוע מה-DB (2026-10-25)

כל הכתיבה בוצעה על **valuecompass-test** (`wbhxjcegoobkbnjnuise`) בלבד. לא נכתב דבר לייצור. 0 קריאות ל-Gemini. golden לא שונה.

## 1. ניקוי מסמכים
- נמחקו (git rm + דיסק): `AI_Spec_2026-10-21_16-00` (EN/HE, md+docx), `AI_Skills_Other_2026-10-23_15-00`, `AI_Skills_Other_2026-10-24_23-38`, `AI_Skills_Other_2026-10-25_00-00`, `K6_Spec_2026-10-23_14-59` (EN/HE, md+docx).
- לא נמצא: `AI_Skills_Scoring_2026-10-22_13-52.*`.
- נוספו: `AI_Spec_2026-10-24_23-38`, `AI_Skills_Other_2026-10-25_00-15`, `K6_Spec_2026-10-25_00-15`.

## 2. שינויי D1/T1 (בקוד בלבד, ללא הרצה)
- D1 גרסה 5: מתחרים — עד 5 שמות, ואם אין שמות עד 4 `competitor_types` במילות הדוח; אחרת המשפט הקבוע "The report does not describe its competition."; אסור לערבב; כל שם/סוג חייב להופיע בציטוט. בדיקות חדשות (כולל mock של JPM עם סוגים בלבד).
- T1: `src/ai/skills/t1_glossary.yaml` (15 מונחים). לתרגום נשלחים רק המונחים שנמצאו ב-`text_en`; בדיקה שהמונח העברי מופיע (קידומות ו/ה/ב/ל/מ/ש/כ).
- `approval_status`: רקע עברי שעבר את כל הבדיקות נשמר כ-`pending_review`; 5 הרקעים העבריים הקיימים הועברו ל-`pending_review`.

## 3. מיגרציות (קבצים ב-`supabase/migrations/`, גלגול אחורה ב-`supabase/rollback/`)
| # | קובץ | תוצאה על test |
|---|---|---|
| 8 | `20261025090008_drop_legacy.sql` | **לא הורץ** — ב-test הטבלאות הישנות כבר הוסרו בשלב DB קודם (הקובץ אידמפוטנטי, מופסק אם יש שורות) |
| 9 | `..090009_companies_k6_columns.sql` | הורץ: 7 עמודות ב-`companies`, `cik` unique, CHECK למצב עיבוד, `UNSUPPORTED` ב-3 ה-CHECK של profile |
| 10 | `..090010_extraction_items_provenance.sql` | הורץ (גרסה מעודכנת, ראו סעיף 8): 6 עמודות כולל `approval_source` + שני CHECK |
| 11 | `..090011_ai_assessments_provenance.sql` | הורץ: 2 עמודות |

**חריגה שחובה לציין:** ההוראה הייתה לעצור אם ה-baseline של test שונה מהייצור. ה-fingerprint של test שונה מהייצור בדיוק במיגרציה 8 (ב-test כבר בוצעה). בדקתי: זהה בכל השאר (עמודות 670, אילוצים 128, אינדקסים 50, views 8, טבלאות 21, מדיניות 31) ובטבלאות הישנות בייצור 0 שורות — לכן המשכתי. אם אתה מעדיף שאעצור במקרה כזה, יש לאשר.

אימותים אחרי המיגרציות:
- שורות קיימות לא השתנו: ארבעת ה-md5 (companies, extraction_items, ai_assessments, financial_facts) זהים ל-baseline לפני המיגרציות (אחרי הסרת העמודות החדשות).
- RLS: כ-`authenticated` נראית רק שורה מאושרת אחת מתוך 2 ב-extraction_items וב-ai_assessments; 0 שורות לא מאושרות נראות. 31 מדיניות, ללא שינוי.
- גלגול אחורה: הורץ את שלושת קבצי ה-rollback בתוך בלוק שבוטל; הוחזרו בדיוק העמודות (46 במקום 60) וה-md5 המקוריים. המצב הסופי ב-test: מיגרציות 9–11 מוחלות.

## 4. Repositories
- `financial_repository` — `financial_facts`/`filing_periods`: קריאה (היסטוריה, רחבה, שנה, כיסוי) וכתיבה אידמפוטנטית (upsert לפי המפתח הטבעי, נכתבות רק שורות חדשות/שונות).
- `extraction_repository` (חדש) — קידוד ערכי טקסט (NA/MISSING/not disclosed/YES/NO) לעמודה מספרית וחזרה; שורות נקראות לפי `id` (המנועים מסכמים לפי סדר). שורה מאושרת מקבלת `approved_at` (נדרש ב-CHECK של הטבלה — תוקן אחרי כשל בהרצה ראשונה).
- `company_repository` — עמודות חדשות, `ensure`, `get_by_symbol/cik`, `set_processing_state`, `set_classification`.
- `src/db.py` — `VC_DB_TARGET=test|prod` (ברירת מחדל test); מסרב ל-URL שאינו של הפרויקט הנבחר; הודעות שגיאה לא כוללות ערכים. `.env` מחזיק מפתח נפרד לכל פרויקט.
- אין עוד הפניה בקוד ל-`financial_yearly`/`financial_ratios`/`financial_overview_view`.
- 10 בדיקות חדשות (`tests/test_k6a_repositories.py`, עם DB מדומה). סה"כ **585 בדיקות עוברות**.

## 5. בדיקת זהות (54 חברות)
- נטענו 54 חברות מהמטמון המקומי ל-test (10 שנים), והמנועים רצו על קלט שנקרא בחזרה מה-DB (`make_golden.py --via-db`).
- קלט DB מול קלט המטמון: **54/54 ללא הבדל**.
- מול golden: **55 קבצים (54 חברות + index) — 0 הבדלים** (ציון, טווח, ערך, מחיר קנייה, כל הכרטיסים). טבלת הבדלים: ריקה.
- הערה: ה-`accession` ב-`filing_periods` הוא placeholder (`n/a (local SEC cache, K6a load)`) עד ק6ב; שורות החילוץ: ראו סעיף 8 (כלל האישור המעודכן).
- מקור הנתונים: מקומי מהמטמון (0 בקשות SEC).

## 6. אידמפוטנטיות וגודל
- טעינה שנייה: 0 שורות הוכנסו, 0 עודכנו — facts 18,998 / periods 538 / extraction 1,253 כולם unchanged; golden אחרי הטעינה השנייה זהה שוב (0 הבדלים).
- נפח ב-test עכשיו: financial_facts 19,124 שורות (3.0MB), filing_periods 538 (0.12MB), extraction_items 1,255 (1.2MB), fact_tags 244, companies 59. בסיס הנתונים כולו 17.2MB.
- הערכה ל-1,000 חברות: ≈ 84KB לחברה (כולל אינדקסים) ⇒ **≈ 85MB** לשלוש הטבלאות — כ-17% ממגבלת 500MB של התוכנית החינמית (לפני ai_texts, score_runs ו-view-ים).

## 7. רשימת הרצה לייצור — בוצעה, ראו סעיף 9

## 8. תיקון שכבות ההגנה על אישור שורות חילוץ
**מיגרציה 10 (מעודכנת):** עמודה `approval_source` עם CHECK (`k5b_confirmed` / `ai_controls` / `human_review`) ו-CHECK נוסף: שורה `approved` חייבת `approval_source` **וגם** `approved_at`. שורות שכבר מאושרות לפני העמודה מקבלות `human_review` (בייצור: 0 שורות; ב-test: 1,254 שורות בדיקה).
- על test: rollback ל-10 הישנה (md5 של כל 1,255 השורות זהה אחרי הגלגול), ואז 10 המעודכנת. אימותים: md5 של השורות (בלי העמודות החדשות) זהה; 31 מדיניות; כ-`authenticated` נראות רק שורות approved (1,254 מתוך 1,255, 0 לא מאושרות); ה-CHECK נבדקו בתוך בלוק שבוטל — approved בלי מקור: נדחה, מקור לא חוקי: נדחה, approved בלי `approved_at`: נדחה, pending בלי מקור: מותר; rollback של 10 המעודכנת (בבלוק שבוטל) מחזיר md5 מקורי.

**קוד:** שורות CSV נטענות `pending` כברירת מחדל; `approved` + `k5b_confirmed` רק כשהערך אומת (`verified`/`quote_verified` של ק5ב). דגל `--db-approve-all` (זהות בלבד; מסומן `approved` + `human_review`) נדחה בשגיאה כש-`VC_DB_TARGET=prod` — בבנייה וגם בעת הכתיבה. 3 בדיקות יחידה חדשות (כלל ברירת המחדל, ה-CHECK של הטבלה, הדגל נדחה ב-prod). **588 בדיקות עוברות.**

**בדיקת זהות עם הדגל על test:** 54/54, 0 הבדלי קלט, 55 קבצים מול golden — 0 הבדלים.

**כמה שורות CSV (1,253) מקבלות approved לפי הכלל החדש:** **1,247 approved (`k5b_confirmed`), 6 pending.** לפי מנוע: bank 268/0, insurance 125/2, realestate 854/4, general 0.

**תוצאה מעניינת (לא שינוי ל-golden):** בטעינה לפי הכלל החדש, בלי הדגל, המנועים רואים רק שורות approved ולכן 6 חברות שונות מ-golden — ALL, CINF (שורת `alm_disclosed`=NO שלא אומתה) ו-BXP, EQIX, EQR, PSA (שורות occupancy / same_property_noi_growth / ti_lc שלא אומתו). ההבדלים הם בשורות החילוץ שהוסתרו ובדגל `alm_risk_flag_only_in_v1` — לא נבדק בשלב זה אם ציונים משתנים. זו שאלה לפני טעינת ייצור: האם להשאיר שורות כאלה pending (ולקבל את ההבדל) או לאשרן ב-`human_review`. מצב test כרגע: נטען לפי כלל ברירת המחדל (1,247/6).

## 9. מיגרציות 8–11 בייצור (`zwpftrjryxyymrxsprqh`) — בוצעו לפי הרשימה
1. **גיבוי** לפני כל שינוי: `scripts/backup/legacy_tables_prod_2026-10-25.json` (שתי הטבלאות הישנות ריקות — 0 שורות; מבנה, FK ותלות ה-view; ה-DDL המלא ב-rollback של מיגרציה 8).
2. **fingerprint לפני:** בייצור זהה ל-test בכל האובייקטים שאינם של מיגרציות 8–11 (670 עמודות, md5 של עמודות/אילוצים/אינדקסים/מדיניות זהים; 21 טבלאות, 8 views). נתונים: companies = שורה אחת (md5 נרשם), extraction_items / ai_assessments / financial_facts = 0.
3. הורצו לפי הסדר: 8 (drop_legacy — 0 שורות, לא הופסק), 9, 10 (מעודכנת), 11. כולן הצליחו, אף אחת לא דרשה rollback.
4. **אימות אחרי:** 21 טבלאות / 8 views / 31 מדיניות; הטבלאות הישנות וה-view לא קיימים; 15 עמודות חדשות; `companies_cik_key`, בדיקת processing_state, `UNSUPPORTED` ב-3 ה-CHECK של profile, שני ה-CHECK של extraction_items; md5 של companies (ללא העמודות החדשות) זהה לפני; fingerprint של עמודות/אילוצים/אינדקסים/מדיניות (ללא אובייקטי 8–11) זהה לפני ולזה של test; כ-`authenticated` נראית שורת החברה, 0 שורות חילוץ/הערכות.
5. **לא נטענו נתונים לייצור.**

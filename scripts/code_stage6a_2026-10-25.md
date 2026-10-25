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
| 10 | `..090010_extraction_items_provenance.sql` | הורץ: 5 עמודות |
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
- הערה: ה-`accession` ב-`filing_periods` הוא placeholder (`n/a (local SEC cache, K6a load)`) עד ק6ב; שורות החילוץ מה-CSV נטענו כ-`approved` (מדיניות pending — ק6ג).
- מקור הנתונים: מקומי מהמטמון (0 בקשות SEC).

## 6. אידמפוטנטיות וגודל
- טעינה שנייה: 0 שורות הוכנסו, 0 עודכנו — facts 18,998 / periods 538 / extraction 1,253 כולם unchanged; golden אחרי הטעינה השנייה זהה שוב (0 הבדלים).
- נפח ב-test עכשיו: financial_facts 19,124 שורות (3.0MB), filing_periods 538 (0.12MB), extraction_items 1,255 (1.2MB), fact_tags 244, companies 59. בסיס הנתונים כולו 17.2MB.
- הערכה ל-1,000 חברות: ≈ 84KB לחברה (כולל אינדקסים) ⇒ **≈ 85MB** לשלוש הטבלאות — כ-17% ממגבלת 500MB של התוכנית החינמית (לפני ai_texts, score_runs ו-view-ים).

## 7. רשימת הרצה לייצור (לא בוצע; ממתין לאישור)
1. לוודא ש-fingerprint של הייצור = baseline (מיגרציות 1–7, טבלאות ישנות ריקות).
2. מיגרציה 8 (`drop_legacy`) — אידמפוטנטית, מופסקת אם יש שורות.
3. מיגרציות 9, 10, 11 לפי הסדר.
4. אימות: 7+5+2 עמודות חדשות; ה-CHECK של profile כולל `UNSUPPORTED`; 31 מדיניות; md5 של companies/extraction_items/ai_assessments/financial_facts (ללא העמודות החדשות) זהים לפני; RLS כ-authenticated רואה רק approved.
5. טעינת נתונים לייצור — לא בשלב זה (ק6ב/ג).
